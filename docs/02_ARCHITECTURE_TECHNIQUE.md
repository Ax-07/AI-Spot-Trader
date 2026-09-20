# 02 — Architecture technique

## 1. Objet

Ce document décrit l'architecture technique courante d'AI Spot Trader. Le Batch 15 — Chat opérateur avec l'Agent est intégré au commit fonctionnel `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6`, sur la base du Batch 14 fonctionnel `dc60033f60bf5d98a68e6131a9320e575d46cc8d`.

---

## 2. Vue d'ensemble

```text
+--------------------------+
| Frontend cockpit         |
| Next.js / TS / shadcn    |
+------------+-------------+
             |
      /backend/* rewrite
             |
            REST
             |
+------------v-------------+
| FastAPI API              |
| observation + lifecycle  |
| + chat conversationnel   |
+------+-------------------+
       |               |
       |               +------------------------------+
       v                                              v
TradingEngine / ledger                    CycleAuditReader
canonique PAPER                           query service SQLAlchemy
       |                                              |
       v                                              v
Agent -> Risk -> Paper Broker                     PostgreSQL
       |                                              |
       v                                              v
TradingCycleResult -> AuditedTradingCycleRunner -> journal durable
                                                     |
                                  +------------------+------------------+
                                  |                                     |
                                  v                                     v
                         audit query service                   analytics reducer
                                  |                                     |
                                  +------------------+------------------+
                                                     |
                                                     v
                                             FastAPI / cockpit
```

Le frontend n'est jamais l'ordonnanceur du moteur. PostgreSQL conserve des faits ; il ne produit aucune stratégie.

Le Batch 15 ajoute un chemin parallèle de **lecture + conversation** :

```text
ChatPanel
   |
   v
/api/v1/chat/messages
   |
   v
OperatorChatService ----> RuntimeChatContextSource
   |                         |-> engine snapshot
   |                         |-> portfolio snapshot
   |                         |-> CycleAuditReader
   |                         `-> PaperAnalyticsReader
   v
OpenAIChatProvider -----> OpenAIResponsesClient
   |
   `-> settings.llm_model (Luna ou Sol)
```

Aucune flèche ne part du chat vers `risk`, `broker`, `integrations.kraken` ou `trading`.

---

## 3. Découpage backend

```text
backend/src/ai_spot_trader/
  agent/
  analytics/
  api/
    routes/
      chat.py              # Batch 15 intégré
  broker/
  chat/                    # Batch 15 intégré
    errors.py
    models.py
    prompt.py
    provider.py
    service.py
  core/
  domain/
  experiments/
  integrations/kraken/
  market/
  persistence/
  portfolio/
  risk/
  trading/
  main.py
```

Responsabilités :

- `domain` : contrats canoniques fournisseur-agnostiques ;
- `market` : construction déterministe du `MarketState` ;
- `portfolio` : ledger PAPER mémoire ;
- `agent` : décision stratégique structurée ;
- `risk` : autorité déterministe avant exécution ;
- `broker` : exécution PAPER uniquement après intent Risk ;
- `trading` : orchestration et boucle séquentielle ;
- `persistence` : écriture/lecture durable ;
- `analytics` : calculs PAPER purs dérivés des faits durables ;
- `experiments` : protocoles et comparaisons factuelles ;
- `api` : transport HTTP sans métier de trading ;
- `core.runtime` : dépendances process-locales et lifecycle explicite ;
- `chat` : conversation informative, lecture seule du contexte canonique, sans contrat d'exécution.

Le package `chat` n'importe pas `risk`, `broker`, `integrations.kraken` ou `trading`. Il n'importe pas non plus `AgentInput`, `DecisionCandidate`, `RiskAssessment`, `ExecutionIntent`, `RiskPolicy` ou `PaperBroker`.

---

## 4. Flux de confiance canonique

```text
MarketDataSource.snapshot(symbol) ----+
                                      |
PaperPortfolioLedger.snapshot() ------+--> AgentInput
                                             |
                                             v
                                      DecisionCandidate
                                             |
                                             v
                                        RiskEngine
                                      /      |      \
                                  REJECT  MODIFY  ALLOW
                                      \      |      /
                                             v
                                      RiskAssessment
                                             |
                                      ExecutionIntent
                                       si tradable
                                             |
                                             v
                                       PaperBroker
                                             |
                                             v
                                      Fill(s) + ledger
                                             |
                                             v
                                    TradingCycleResult
                                             |
                                             v
                                  audit persistence
```

Ce flux reste inchangé au Batch 15. Le chat ne construit aucun artefact de cette chaîne.

---

## 5. Contrats expérimentaux Batches 13/14

`aggressiveness-map-v1` reste discret et déterministe. `ExperimentManifest` conserve le niveau/mapping, modèle, prompt, univers, snapshot Risk, coûts PAPER, version analytics, source/dataset et fenêtre.

`paper-experiment-v1` compare l'agressivité. `paper-experiment-v2` compare Luna/Sol avec :

```text
comparison_variable = LLM_MODEL
experiment_group_digest
replicate_index
replicate_count
```

`source_digest` reste obligatoire en v2. Le chat ne modifie aucun de ces contrats et ne participe à aucun digest expérimental.

---

## 6. Agent et transport OpenAI

Le prompt stratégique reste `agent-strategy-v2` et `OpenAIDecisionProvider` reste le seul provider produisant un `DecisionCandidate`.

`OpenAIResponsesClient` garde son appel Structured Outputs existant pour la stratégie et ajoute au Batch 15 une méthode `generate_text_response(...)` :

- même endpoint Responses API ;
- même `LLMModel` typé ;
- `store = false` ;
- aucun `tools` ;
- aucun schéma `DecisionCandidate` ;
- même sanitization des erreurs transport/enveloppe.

`OpenAIChatProvider` utilise uniquement cette méthode texte et le prompt `operator-chat-v1`.

---

## 7. ChatContextSnapshot et no-look-ahead

`RuntimeChatContextSource` agrège uniquement des surfaces déjà canoniques :

- `AppRuntime.engine_snapshot()` ;
- `PortfolioSnapshotSource.snapshot()` ;
- `CycleAuditReader.latest_market_state()` ;
- `CycleAuditReader.latest_cycle()` / `get_cycle()` / `list_cycles()` ;
- `PaperAnalyticsReader.paper_analytics()`.

Aucune donnée métier n'est reconstruite avec une formule parallèle.

Le snapshot distingue :

```text
historical_cycle          # faits persistés d'un cycle identifié
historical_cycle_id
current_market            # état durable le plus récent au moment de la question
current_portfolio         # snapshot PAPER courant
recent_cycles             # résumés récents, absent si cycle historique explicite
analytics_summary         # analytics courants
```

Pour un `context_cycle_id` explicite, `historical_cycle.agent_input` est le contexte réellement persisté lors de la décision. La liste de cycles récents est volontairement omise pour réduire le risque de look-ahead. L'état courant peut rester visible comme section séparée, mais le prompt interdit de l'utiliser comme justification causale de la décision passée.

---

## 8. Sessions chat V1

`OperatorChatService` conserve les sessions en mémoire process uniquement :

- `OrderedDict` borné par défaut à 32 sessions ;
- `deque` bornée par défaut à 20 messages/session ;
- éviction LRU des sessions les plus anciennes ;
- UUID de session explicite ;
- aucune table SQL ni migration ;
- aucun message chat dans `AgentInput`, le journal ou les analytics.

Une erreur fournisseur ne persiste pas le message opérateur dans l'historique de session. Les formes de secrets courantes sont redigées avant stockage/envoi au provider.

---

## 9. Risk Engine inchangé

`RiskEngine` reste synchrone et déterministe. Il ne lit ni `AggressivenessContext`, ni `ExperimentManifest`, ni `LLMModel`, ni message chat.

Les contrôles restent : symbole/correspondance marché, whitelist, chronologie, fraîcheur, max notional, rôles d'actifs, balance quote, solvabilité BUY avec coûts et position SELL disponible.

`MODIFY` ne change jamais BUY↔SELL ou le symbole et n'augmente jamais la taille stratégique. Seul Risk peut produire un `ExecutionIntent`.

---

## 10. TradingCycleRunner inchangé

Le runner canonique reste unique. Le pipeline reste : Market -> Portfolio -> Agent -> Risk -> Broker -> post-portfolio. Le chat n'est pas injecté comme dépendance du runner et ne partage aucun verrou de cycle.

Le moteur peut donc continuer ses cycles pendant qu'un appel chat attend la réponse du fournisseur LLM.

---

## 11. Persistance durable

Le journal Batch 09 persiste `agent_input_payload` en JSON/JSONB et le `result_digest` sur le résultat de cycle complet. Les manifestes expérimentaux y sont durables sans migration.

Batch 15 choisit explicitement **mémoire seulement** pour l'historique conversationnel. Motifs :

1. pas de besoin de reprise durable pour la première V1 ;
2. séparation maximale entre conversation et faits de trading ;
3. aucune contamination des digests/analytics/expériences ;
4. aucune migration avant d'avoir un besoin produit réel de rétention.

Si une persistance chat devient nécessaire, elle devra utiliser une table/agrégat séparé du journal de trading.

---

## 12. API FastAPI

Routes Batch 15 intégrées :

```text
POST /api/v1/chat/messages
GET  /api/v1/chat/sessions/{session_id}
```

Le POST accepte `message`, `session_id?` et `context_cycle_id?`. Un UUID de cycle peut également être détecté dans une formulation `cycle <UUID>`.

Codes d'erreur :

- `404` : session ou cycle historique absent ;
- `502` : transport/provider chat indisponible, message générique sanitizé ;
- `503` : chat non configuré.

Une erreur chat ne modifie ni `last_cycle_status`, ni la journalisation du moteur.

REST est suffisant pour la V1 ; aucun WebSocket/SSE n'est introduit.

---

## 13. Frontend Batch 15

Fichiers concernés :

```text
frontend/src/app/page.tsx
frontend/src/components/cockpit/chat-panel.tsx
frontend/src/hooks/use-chat.ts
frontend/src/lib/api/client.ts
frontend/src/lib/api/types.ts
```

`useChat` :

- garde uniquement l'UUID de session dans `localStorage` ;
- relit l'historique auprès du backend si la session process existe encore ;
- recrée proprement une session si le backend a redémarré et renvoie 404 ;
- ne possède aucune référence à `startEngine`/`stopEngine`.

`ChatPanel` indique explicitement le caractère informatif du canal et permet d'ancrer une explication sur un cycle UUID.

---

## 14. Reproductibilité et expérimentation

Les identités existantes restent distinctes :

1. `experiment_group_digest` ;
2. `experiment_digest` ;
3. `result_digest` ;
4. `PaperAnalyticsReport.source_digest`.

Les messages/réponses chat ne participent à aucune de ces identités. Le contenu conversationnel n'est jamais réinjecté dans `AgentInput`, même si l'opérateur y écrit une nouvelle agressivité ou un ordre BUY/SELL.

---

## 15. Testabilité Batch 15

Le patch ajoute des tests pour :

- envoyer un message moteur RUNNING sans start/stop ;
- vérifier Luna/Sol sur la même architecture provider ;
- vérifier `store=false`, absence de `tools` et absence de Structured Output stratégique pour le chat ;
- vérifier qu'une demande BUY/Risk n'altère pas le moteur ni une `RiskPolicy` ;
- vérifier l'identité de `AgentInput` avant/après conversation ;
- vérifier l'ancrage historique et la séparation du marché courant ;
- vérifier la redaction de secrets ;
- vérifier l'erreur chat HTTP 502 séparée du dernier cycle ;
- analyser l'AST du package chat pour interdire les imports/symboles d'exécution ;
- vérifier l'historique borné ;
- vérifier l'absence de lifecycle moteur dans le frontend Chat.

La compatibilité complète Batches 01–14 doit être confirmée par `pytest backend`, Ruff et mypy dans le checkout local complet.

---

## 16. Hors périmètre Batch 15

- mutation de stratégie depuis le chat ;
- configuration d'agressivité/Risk/modèle active par conversation ;
- persistance PostgreSQL du chat ;
- streaming SSE/WebSocket ;
- outils/fonctions LLM ;
- private Kraken ;
- LIVE ;
- recovery/reconciliation exactly-once ;
- moteur alternatif côté frontend.
