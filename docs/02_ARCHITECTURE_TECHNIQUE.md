# 02 — Architecture technique

## 1. Objet

Ce document décrit l'architecture technique courante d'AI Spot Trader. Depuis le Batch 16, l'architecture canonique couvre SPOT et Kraken Derivatives PAPER. Le Batch 16.3 ajoute uniquement un harness CLI de validation contrôlée ; il ne remplace ni le runner, ni le Risk Engine, ni le Paper Broker.

Référence fonctionnelle actuelle : `520b016eb501f1a208bcb6d0e90eb1df947e1d0b` (`test: add controlled perpetual paper smoke harness`).

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

Le chat opérateur reste un chemin parallèle de **lecture + conversation** et ne pointe jamais vers `risk`, `broker`, `integrations.kraken` ou `trading`.

---

## 3. Découpage backend

```text
backend/src/ai_spot_trader/
  agent/
  analytics/
  api/
  broker/
  chat/
  core/
  domain/
  experiments/
  integrations/kraken/
  market/
  persistence/
  portfolio/
  risk/
  tools/                    # outils explicites de validation, hors runtime normal
    derivatives_smoke.py    # Batch 16.3
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
- `persistence` : écriture/lecture durable et lifecycle `paper_run_id` ;
- `analytics` : calculs PAPER purs dérivés des faits durables ;
- `experiments` : protocoles et comparaisons factuelles ;
- `api` : transport HTTP sans métier de trading ;
- `core.runtime` : dépendances process-locales et lifecycle explicite ;
- `chat` : conversation informative, lecture seule du contexte canonique ;
- `tools` : outils manuels de validation non invoqués par la composition normale.

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

SPOT et PERPETUAL utilisent ce même flux. Le `market_type` et le contexte dérivés modifient les contraintes de domaine/Risk, pas l'architecture générale.

Le harness 16.3 utilise les mêmes composants aval mais remplace temporairement la source de décision stratégique par une séquence déterministe explicitement réservée au smoke. Aucun mécanisme de force BUY/SELL n'est exposé dans l'API ou dans la composition normale.

---

## 5. Contrats expérimentaux

`aggressiveness-map-v1` reste discret et déterministe. `ExperimentManifest` conserve niveau/mapping, modèle, prompt, univers, snapshot Risk, coûts PAPER, version analytics, source/dataset et fenêtre.

`paper-experiment-v1` compare l'agressivité. `paper-experiment-v2` compare Luna/Sol avec `comparison_variable = LLM_MODEL`, `experiment_group_digest`, `replicate_index`, `replicate_count` et `source_digest`.

Le `paper_run_id` reste une frontière d'audit/exécution et ne devient pas une instruction stratégique.

---

## 6. Agent et transport OpenAI

Le prompt stratégique courant est **`agent-strategy-v3`**. `OpenAIDecisionProvider` reste le provider normal produisant un `DecisionCandidate`.

Le v3 explicite les sémantiques SPOT/PERPETUAL sans donner au LLM le contrôle du levier, du `reduce_only` ou de la validation finale.

`OpenAIResponsesClient` reste le transport partagé. Le chat utilise `OpenAIChatProvider` et `operator-chat-v1` sans tools d'exécution.

Le harness 16.3 n'appelle pas OpenAI : il sert uniquement à vérifier le chemin aval avec des décisions techniques reproductibles.

---

## 7. Kraken Spot / Derivatives

Kraken Spot et Kraken Derivatives ont des intégrations publiques séparées.

Pour Derivatives :

- source REST publique : `https://futures.kraken.com/derivatives/api/v3` ;
- aucune clé privée Kraken ;
- normalisation `XBT -> BTC` ;
- `contractValueTradePrecision` interprété comme exposant décimal signé ;
- première exécution PAPER : perpetual linéaire uniquement, marge `ISOLATED`.

Le market source dérivés met à jour le mark/funding du ledger avant la construction de l'`AgentInput`.

---

## 8. Risk Engine

`RiskEngine` reste synchrone et déterministe.

SPOT conserve ses contrôles historiques. Pour PERPETUAL, Risk contrôle en plus contrat supporté, taille minimale, levier, marge, caps de notionnel/exposition, buffer liquidation et sémantique de réduction.

`MODIFY` ne change jamais BUY↔SELL ou le symbole. Sur une action opposée dépassant la position ouverte, Risk peut réduire la quantité autorisée à la position restante et produire `DERIVATIVE_REDUCE_ONLY_LIMIT`, ce que les smokes 16.3 LONG et SHORT ont confirmé.

Seul Risk peut produire un `ExecutionIntent`.

---

## 9. TradingCycleRunner

Le runner canonique reste unique :

```text
Market -> Portfolio -> Agent -> Risk -> Broker -> post-portfolio
```

Les pannes techniques restent `FAILED` et ne deviennent jamais HOLD. Le verrou du runner empêche le chevauchement des cycles.

Le harness 16.3 réutilise `TradingCycleRunner`, le même Risk Engine, le même Paper Broker et le même ledger ; il ne crée pas de moteur dérivés parallèle.

---

## 10. Persistance durable et paper_run_id

La table `paper_runs` et `audit_cycles.paper_run_id` définissent la frontière durable d'une expérience PAPER.

- démarrage backend/composition PAPER : nouveau run ;
- `engine stop/start` dans le même process : même run ;
- arrêt propre : `ended_at` persisté ;
- redémarrage backend : nouveau run, car le ledger reste process-local ;
- cycles legacy pré-migration : `paper_run_id = NULL`.

Les analytics et readers audit peuvent être explicitement scopés par run. Les smokes 16.3 ont confirmé que deux runs PERPETUAL distincts restent séparés dans les cycles et analytics.

---

## 11. ChatContextSnapshot et no-look-ahead

`RuntimeChatContextSource` agrège uniquement les surfaces canoniques : état moteur, portefeuille, audit et analytics.

Pour un cycle historique, `historical_cycle.agent_input` reste la source causale. Les états plus récents ne doivent jamais être présentés comme ayant causé une décision passée.

Le chat ne construit aucun artefact d'exécution et ne modifie pas un futur `AgentInput`.

---

## 12. Sessions chat

`OperatorChatService` conserve les sessions en mémoire process uniquement, avec historique borné. Aucun message chat n'est ajouté au journal de trading, au manifeste expérimental ou aux analytics.

---

## 13. API FastAPI

Les routes de chat restent :

```text
POST /api/v1/chat/messages
GET  /api/v1/chat/sessions/{session_id}
```

Les surfaces run-scoped ajoutées au Batch 16.2 incluent :

```text
GET /api/v1/paper-runs
GET /api/v1/paper-runs/current
GET /api/v1/paper-runs/{paper_run_id}
GET /api/v1/analytics?paper_run_id={paper_run_id}
```

Les lectures audit peuvent aussi être filtrées par `paper_run_id`.

Le harness `python -m ai_spot_trader.tools.derivatives_smoke ...` est un outil CLI local, pas une route FastAPI.

---

## 14. Frontend

Le frontend reste un cockpit de visualisation/contrôle. Il ne possède pas le moteur de trading et sa fermeture n'arrête pas le backend.

Aucun changement frontend n'était requis pour les Batches 16.2 ou 16.3.

---

## 15. Reproductibilité et validation Batch 16.3

Les décisions du harness sont marquées `CONTROLLED_SMOKE_BATCH_16_3` afin de ne pas être confondues avec des décisions stratégiques Luna/Sol.

Smokes réels validés sur `BTC/USD / PF_XBTUSD` :

- LONG puis réduction/fermeture ;
- SHORT puis réduction/fermeture ;
- funding observé ;
- `reduce_only` confirmé ;
- fermeture oversize bornée par Risk sans reversal ;
- audit durable et analytics isolées par run.

Validation locale du commit `520b016eb501f1a208bcb6d0e90eb1df947e1d0b` : suite `pytest` complète OK, Ruff OK, mypy OK sur 109 fichiers, `git diff --check` OK.

---

## 16. Hors périmètre actuel

- exécution Kraken Derivatives privée/LIVE ;
- CROSS ;
- contrats inverses exécutables ;
- futures datés exécutables ;
- recovery durable du ledger ;
- rotation à chaud d'un `paper_run_id` ;
- stratégie algorithmique parallèle ;
- force BUY/SELL dans le runtime normal.
