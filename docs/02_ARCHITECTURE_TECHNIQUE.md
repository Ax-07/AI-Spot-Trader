# 02 — Architecture technique

## 1. Objet

Ce document décrit l'architecture technique courante d'AI Spot Trader. Les Batches 10 à 13 sont intégrés ; le Batch 14 est un **patch préparé localement, non intégré**. Le HEAD GitHub resynchronisé avant Batch 14 est `655b66b639c4e9c1803cef3920c9a96e7dd16055`, après le commit fonctionnel Batch 13 `1747beb5efd1fe9763bc9b2d23f3a115575daaec`.

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
+------+-------------------+
       |               |
       |               +------------------------------+
       v                                              v
TradingEngine / ledger                    CycleAuditReader
canonique PAPER                           query service SQLAlchemy
       |                                              |
       v                                              v
Agent -> Risk -> Paper Broker                     PostgreSQL
       |
       v
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

Les Batches 13/14 ajoutent des contrats expérimentaux backend/domaine sans modifier ce flux de confiance.

---

## 3. Découpage backend

```text
backend/src/ai_spot_trader/
  agent/
  analytics/
    paper.py
  api/
  broker/
  core/
  domain/
    enums.py
    experiments.py
    models.py
    ports.py
    symbols.py
  experiments/
    __init__.py
    comparison.py
    protocol.py
  integrations/kraken/
  market/
  persistence/
  portfolio/
  risk/
  trading/
    engine.py
  main.py
```

Responsabilités :

- `domain.experiments` : mapping d'agressivité et identités/digests des protocoles sans dépendance Risk/Broker ;
- `experiments.protocol` : construction des manifestes à partir des configurations injectées Risk/coûts ;
- `experiments.comparison` : comparaison factuelle de rapports Batch 12 sans recalcul analytics ;
- `analytics` : calculs PAPER purs et déterministes dérivés des faits durables ;
- `domain` : contrats canoniques fournisseur-agnostiques ;
- `market` : construction déterministe du `MarketState` ;
- `portfolio` : ledger PAPER mémoire ;
- `agent` : décision stratégique structurée ;
- `risk` : autorité déterministe avant exécution ;
- `broker` : exécution PAPER uniquement après intent Risk ;
- `trading` : orchestration et boucle séquentielle ;
- `persistence` : écriture/lecture durable ;
- `api` : transport HTTP sans métier de trading ;
- `core.runtime` : dépendances process-locales et lifecycle explicite.

Le package Agent n'importe pas directement `risk` ou `broker`. Le changement Luna/Sol reste un paramètre du même provider canonique.

---

## 4. Flux de confiance canonique

```text
MarketDataSource.snapshot(symbol) ----+
                                      |
PaperPortfolioLedger.snapshot() ------+--> AgentInput
                                             |
                                             |  aggressiveness_context
                                             |  experiment_manifest?
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

L'API ne peut ni créer `DecisionCandidate`, ni appeler le LLM, ni construire `RiskAssessment`/`ExecutionIntent`, ni appeler le Broker pour contourner le runner. Le frontend ne peut pas non plus effectuer ces opérations.

Ni l'agressivité ni l'identité Luna/Sol ne sont transmises comme paramètres au Risk Engine.

---

## 5. Contrats expérimentaux

### 5.1 `AggressivenessContext`

Le mapping `aggressiveness-map-v1` est discret et déterministe. Chaque niveau `1..10` produit `mapping_version`, `level`, `posture` et `strategic_instruction`. Il ne contient aucun seuil Risk, indicateur, balance minimale, notional ou multiplicateur d'exécution.

### 5.2 `ExperimentManifest` commun

Les champs communs persistables sont :

```text
protocol_version
experiment_digest
aggressiveness
llm_model
prompt_version
universe[]
risk_policy
paper_costs
analytics_version
source_id
source_digest?
window_start?
window_end?
```

Le digest SHA-256 utilise une sérialisation canonique : clés triées, `Decimal` sérialisés sans flottants, timestamps explicites et collections triées lorsque l'ordre n'est pas sémantique.

### 5.3 `paper-experiment-v1` — agressivité

Le v1 reste le protocole Batch 13. `comparison_identity(...)` exclut volontairement l'agressivité et conserve le modèle comme champ contrôlé. Les nouveaux champs v2 sont optionnels dans le modèle Pydantic mais exclus du digest v1 afin de préserver l'identité des anciens payloads.

### 5.4 `paper-experiment-v2` — Luna/Sol

Le v2 ajoute :

```text
comparison_variable = LLM_MODEL
experiment_group_digest
replicate_index
replicate_count
```

`source_digest` est obligatoire en v2.

Le `experiment_group_digest` est calculé sur le manifeste en excluant :

```text
experiment_digest
experiment_group_digest
llm_model
replicate_index
```

Il conserve donc l'agressivité, le prompt, l'univers, le snapshot `RiskPolicy`, les coûts PAPER, `analytics_version`, `source_id`, `source_digest`, la fenêtre et `replicate_count`. Deux runs Luna/Sol n'appartiennent au même groupe que si ces champs sont identiques.

Le `experiment_digest` complet inclut ensuite le groupe, le modèle et l'index de répétition et devient l'identité durable du run.

### 5.5 Snapshots de configuration

`RiskPolicy` est projetée vers :

```text
max_order_notional
allowed_pairs
stale_after_seconds
allow_quantity_reduction
```

`PaperExecutionCostModel` est projeté vers :

```text
fee_rate
spread_bps
slippage_bps
```

Ces snapshots servent uniquement à l'identité expérimentale ; aucune logique Risk/Broker n'est déplacée dans `experiments`.

---

## 6. Agent et prompt

Le prompt courant reste `agent-strategy-v2`.

`OpenAIDecisionProvider` :

1. valide le symbole et la chronologie existante ;
2. résout `aggressiveness-map-v1` ;
3. normalise un ancien `AgentInput` sans contexte pour l'appel LLM ;
4. si un manifeste existe, vérifie son digest, son modèle, son prompt et son mapping ;
5. appelle le client structured-output canonique avec `LLMModel.LUNA` ou `LLMModel.SOL` ;
6. revalide la décision comme avant et retourne uniquement `DecisionCandidate`.

Aucun tool-calling, accès Risk/Broker/Kraken ou retry automatique n'est ajouté. Aucun modèle ne produit directement un `ExecutionIntent`.

---

## 7. TradingCycleRunner

Le runner canonique reste unique. Son constructeur accepte un `experiment_manifest` optionnel.

À la construction :

- le symbole reste validé en forme canonique ;
- l'agressivité est validée via `aggressiveness_context(...)` ;
- si un manifeste est présent, son digest doit être valide ;
- le niveau du manifeste doit correspondre au niveau du runner ;
- le symbole du runner doit appartenir à l'univers du manifeste.

Lors de chaque cycle, l'`AgentInput` contient le même contexte et le même manifeste. Aucun composant expérimental n'exécute un ordre.

Le pipeline reste : Market -> Portfolio -> Agent -> Risk -> Broker -> post-portfolio.

---

## 8. Risk Engine inchangé

`RiskEngine` reste synchrone et déterministe. Il ne lit ni `AggressivenessContext`, ni `ExperimentManifest`, ni `LLMModel`.

Les contrôles restent : symbole/correspondance marché, whitelist, chronologie, fraîcheur, max notional, rôles d'actifs, balance quote, solvabilité BUY avec coûts et position SELL disponible.

La quantité stratégique peut être réduite ou rejetée exactement comme avant. À `DecisionCandidate`, marché et portefeuille identiques, le résultat Risk ne dépend pas du modèle LLM qui a produit la décision.

---

## 9. Persistance durable sans migration

Le journal Batch 09 persiste déjà `agent_input_payload` en JSON/JSONB et le `result_digest` est calculé à partir du résultat complet.

Conséquences Batches 13/14 :

- mapping, manifeste, `experiment_group_digest` et répétitions sont durables sans nouvelle colonne ;
- changer le manifeste change naturellement le `result_digest` ;
- les anciens payloads restent valides grâce aux champs optionnels et au digest v1 préservé ;
- aucune migration Alembic n'est requise.

Le writer durable ne connaît pas la sémantique du manifeste : il persiste le modèle canonique comme n'importe quel autre fait `AgentInput`.

---

## 10. Compatibilité analytics Batch 12

`AgentInput.model_validate_json(...)` continue de lire les payloads sans manifeste, v1 et v2. Le reducer `analytics.paper` reste inchangé.

Aucune formule P&L/drawdown/coût/exposition n'est modifiée.

`compare_aggressiveness_runs(...)` continue de consommer les `PaperAnalyticsReport` existants pour le v1.

`compare_model_runs(...)` consomme les mêmes rapports pour v2 et expose :

- gross/net P&L ;
- frais/spread/slippage ;
- drawdown ;
- exposition ;
- trades BUY/SELL ;
- HOLD/REJECT/MODIFY/FAILED ;
- `points` cumulés Batch 12 ;
- `daily` Batch 12.

Le comparateur ne recharge pas le journal, ne revalorise pas les positions et ne modifie pas le `PaperAnalyticsReport.source_digest`.

---

## 11. Comparaison appariée et anti cherry-picking

`compare_model_runs(...)` vérifie :

- protocole v2 ;
- même `experiment_group_digest` ;
- même version analytics que le manifeste ;
- absence de doublon `(llm_model, replicate_index)` ;
- même `replicate_count` ;
- présence exacte des répétitions `1..N` pour Luna **et** Sol.

Une comparaison qui change agressivité, prompt, RiskPolicy, coûts PAPER, source/dataset, univers, fenêtre ou version analytics est donc refusée par identité de groupe.

La sortie reste factuelle et ne contient aucun champ de ranking, score ou gagnant.

---

## 12. No-look-ahead et dataset figé

Le `MarketState` réellement fourni au cycle reste la seule donnée de marché décisionnelle.

Pour une comparaison Luna/Sol strictement appariée :

- même `source_id` ;
- même `source_digest` obligatoire ;
- même fenêtre ;
- même univers ;
- même agressivité/mapping ;
- même prompt ;
- même `RiskPolicy` ;
- mêmes coûts PAPER ;
- même version analytics ;
- même nombre de répétitions annoncé avant comparaison.

Le v2 formalise cette identité mais n'introduit pas de replay historique parallèle. Le dataset/replay concret reste une dépendance d'exécution à fournir séparément.

---

## 13. Reproductibilité et limite LLM

Quatre identités sont distinguées :

1. `experiment_group_digest` : champs contrôlés communs d'une expérience Luna/Sol ;
2. `experiment_digest` : configuration complète d'un run/modèle/répétition ;
3. `result_digest` : faits réalisés d'un cycle ;
4. `PaperAnalyticsReport.source_digest` : séquence de cycles utilisée par les analytics.

Cette séparation évite de prétendre qu'un digest de protocole reproduit une sortie LLM.

Même modèle + prompt + faits + manifeste peuvent produire des décisions différentes si le fournisseur n'offre pas un déterminisme bit-à-bit. Les répétitions v2 capturent ces réalisations sans inventer de seed fournisseur.

---

## 14. Runtime FastAPI et frontend

`create_app()` reste sans I/O externe et sans démarrage du trading à l'import. Batch 14 n'ajoute aucune route de création/mutation d'expérience.

Le cockpit Batch 11 n'est pas modifié. Il ne contient ni constructeur de manifeste, ni logique de comparaison métier, ni configurateur stratégique.

---

## 15. PostgreSQL et schéma

Le schéma reste :

```text
audit_cycles
  +-- audit_decisions
  +-- audit_risk_assessments
  +-- audit_execution_intents
         +-- audit_fills
```

Aucune migration Batch 14 n'est ajoutée.

---

## 16. Testabilité Batch 14

Le patch ajoute/adapte les tests de protocole pour vérifier notamment :

- Luna/Sol représentables dans un même groupe ;
- comparabilité lorsque seul le modèle change ;
- rejet si agressivité, prompt, RiskPolicy, coûts, dataset/source, univers, fenêtre ou version analytics changent ;
- `source_digest` obligatoire en v2 ;
- répétitions complètes et appariées ;
- digests déterministes ;
- round-trip durable du manifeste v2 ;
- lecture des anciens payloads v1 ;
- compatibilité analytics Batch 12 ;
- invariance de Risk vis-à-vis de l'identité du modèle.

Validation exécutée dans l'environnement de préparation : **34 tests ciblés passés** et `py_compile` réussi. Ruff/mypy ne sont pas installés dans cet environnement ; la suite complète et `git diff --check` restent à exécuter sur le checkout local utilisateur.

---

## 17. Hors périmètre du Batch 14

- configuration de stratégie/Risk/modèle par cockpit ;
- lancement d'expériences via FastAPI ;
- moteur de replay historique complet ;
- seed/déterminisme exact du fournisseur LLM ;
- score composite ou sélection automatique d'un modèle ;
- scanner multi-paires ;
- private Kraken ;
- LIVE ;
- recovery/reconciliation exactly-once ;
- bus temps réel/WebSocket ;
- moteur alternatif côté frontend.
