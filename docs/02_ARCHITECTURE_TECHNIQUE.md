# 02 — Architecture technique

## 1. Objet

Ce document décrit l'architecture technique courante d'AI Spot Trader. Depuis le Batch 16, l'architecture canonique couvre SPOT et Kraken Derivatives PAPER sans créer de moteur parallèle.

Référence fonctionnelle Batch 16.5 : `595bd2c8b4311ac255db927515207f10875b1505` (`feat: enrich perpetual paper market context`). Validation comportementale Batch 16.6 intégrée sur `main` : `251d530ad12951605068c1c8eb8cbeb313c36b49` (`docs: validate Batch 16.6 Luna perpetual behavior`).

Le Batch 16.4 est un résultat d'exécution local confirmé : premier run réel GPT-5.6 Luna en PERPETUAL PAPER, 4 cycles `COMPLETED`, 4 HOLD naturels, aucune erreur et aucun trade.

Le Batch 16.5 enrichit le `MarketState.context` PERPETUAL en réutilisant le pipeline descriptif déjà utilisé en SPOT. Il ne modifie ni la responsabilité stratégique de l'Agent, ni l'autorité finale du Risk Engine.

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
- `market` : construction déterministe du `MarketState` et du `MarketContext` ;
- `integrations.kraken` : acquisition/normalisation des données publiques Kraken ;
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

SPOT et PERPETUAL utilisent ce même flux. Le `market_type` et le contexte dérivés modifient les données et contraintes de domaine/Risk, pas l'architecture générale.

Le harness 16.3 utilise les mêmes composants aval mais remplace temporairement la source de décision stratégique par une séquence déterministe explicitement réservée au smoke. Aucun mécanisme de force BUY/SELL n'est exposé dans l'API ou dans la composition normale.

---

## 5. Construction canonique du contexte marché

`MarketStateBuilder` est le composant canonique, fournisseur-agnostique, qui transforme une série de `MarketObservation` en contexte descriptif multi-horizon.

Il calcule actuellement, par fenêtre :

- nombre d'observations et complétude ;
- premier/dernier prix ;
- minimum, maximum et range ;
- rendement de fenêtre ;
- volatilité réalisée descriptive ;
- métadonnées de fraîcheur du snapshot.

Le builder n'émet ni signal, ni score directionnel, ni `BUY/SELL/HOLD`.

### SPOT

Le pipeline existant reste :

```text
Kraken Spot OHLC 1m clôturé ----+
                                |
Kraken ticker courant ----------+--> MarketStateBuilder
                                       |
                                       v
                               MarketState.context
```

Le ticker courant pilote `last_price` et la fraîcheur, mais ne modifie pas les statistiques de fenêtres tant qu'une nouvelle bougie statistique clôturée n'est pas disponible.

### PERPETUAL — Batch 16.5

Le pipeline intégré réutilise exactement le même builder :

```text
Kraken Futures Charts
mark candles 1m clôturées ------+
                                 |
Kraken Derivatives ticker ------+--> MarketStateBuilder
 mark / index / funding                 |
                                       v
                               MarketState.context
                                       |
                                       +--> DerivativeMarketContext
                                       |     mark / index / funding
                                       v
                                   AgentInput
                                       |
                                       v
                                  GPT-5.6 Luna
```

Les bougies mark publiques servent uniquement à la série statistique. Le ticker courant reste l'autorité pour le mark instantané, l'index et le funding courant.

Une bougie Charts porte un timestamp de début ; l'intégration normalise son observation statistique au moment de clôture (`start + 1 minute`). Seules les bougies dont la clôture est **strictement antérieure** au timestamp du ticker courant sont admissibles dans les fenêtres. Une bougie ouverte, égale au ticker ou future est ignorée pour éviter le look-ahead.

`statistics_as_of` reste ancré sur la dernière observation statistique retenue. Des cycles plus fréquents qu'une minute peuvent donc recevoir un mark courant différent tout en conservant les mêmes statistiques tant qu'aucune nouvelle bougie clôturée n'est arrivée.

---

## 6. Contrats expérimentaux

`aggressiveness-map-v1` reste discret et déterministe. `ExperimentManifest` conserve niveau/mapping, modèle, prompt, univers, snapshot Risk, coûts PAPER, version analytics, source/dataset et fenêtre.

`paper-experiment-v1` compare l'agressivité. `paper-experiment-v2` compare Luna/Sol avec `comparison_variable = LLM_MODEL`, `experiment_group_digest`, `replicate_index`, `replicate_count` et `source_digest`.

Le `paper_run_id` reste une frontière d'audit/exécution et ne devient pas une instruction stratégique.

---

## 7. Agent et transport OpenAI

Le prompt stratégique courant est **`agent-strategy-v4`**. `OpenAIDecisionProvider` reste le provider normal produisant un `DecisionCandidate`.

La v4 localise les instructions humaines en français sans modifier le schéma structuré ni le vocabulaire contractuel : `BUY`, `SELL`, `HOLD`, `SPOT`, `PERPETUAL`, `FUTURE`, `LONG` et `SHORT` restent les valeurs techniques attendues. Le champ `rationale` doit être rédigé en français.

Le provider sérialise toujours l'`AgentInput` complet. Le prompt v4 conserve les contraintes de la v3 : décision uniquement à partir de l'`AgentInput`, aucune invention de données absentes, aucun contrôle LLM du levier, du `reduce_only` ou de la validation finale Risk.

`OpenAIResponsesClient` reste le transport partagé. Le chat utilise `OpenAIChatProvider` et `operator-chat-v1` sans tools d'exécution.

Le harness 16.3 n'appelle pas OpenAI : il sert uniquement à vérifier le chemin aval avec des décisions techniques reproductibles.

---

## 8. Kraken Spot / Derivatives

Kraken Spot et Kraken Derivatives ont des intégrations publiques séparées.

Pour Derivatives :

- métadonnées/ticker : REST public `https://futures.kraken.com/derivatives/api/v3` ;
- historique descriptif Batch 16.5 : Futures Charts public `/api/charts/v1/mark/{symbol}/1m` ;
- aucune clé privée Kraken ;
- aucune authentification d'ordre ;
- normalisation `XBT -> BTC` ;
- `contractValueTradePrecision` interprété comme exposant décimal signé ;
- première exécution PAPER : perpetual linéaire uniquement, marge `ISOLATED`.

Le client Derivatives conserve une frontière publique uniquement. L'URL Charts est dérivée de l'origine Kraken Futures, distincte du préfixe `/derivatives/api/v3`, afin de ne pas produire un chemin REST invalide.

Le market source dérivés met à jour le mark/funding du ledger avec le `MarketState` enrichi avant la construction de l'`AgentInput`.

Les données malformed, non chronologiques ou incohérentes échouent explicitement. Une absence de bougies historiques exploitables ne fabrique pas de métriques : le contexte reste présent avec des fenêtres incomplètes/vides construites par le builder canonique.

---

## 9. Risk Engine

`RiskEngine` reste synchrone et déterministe.

SPOT conserve ses contrôles historiques. Pour PERPETUAL, Risk contrôle en plus contrat supporté, taille minimale, levier, marge, caps de notionnel/exposition, buffer liquidation et sémantique de réduction.

Les rendements, ranges ou volatilités présents dans `MarketState.context` ne sont pas des règles Risk et ne déclenchent aucune action. Risk évalue uniquement le `DecisionCandidate` proposé par l'Agent contre ses contraintes déterministes.

`MODIFY` ne change jamais BUY↔SELL ou le symbole. Sur une action opposée dépassant la position ouverte, Risk peut réduire la quantité autorisée à la position restante et produire `DERIVATIVE_REDUCE_ONLY_LIMIT`, ce que les smokes 16.3 LONG et SHORT ont confirmé.

Seul Risk peut produire un `ExecutionIntent`.

---

## 10. TradingCycleRunner

Le runner canonique reste unique :

```text
Market -> Portfolio -> Agent -> Risk -> Broker -> post-portfolio
```

Les pannes techniques restent `FAILED` et ne deviennent jamais HOLD. Le verrou du runner empêche le chevauchement des cycles.

Le contexte PERPETUAL enrichi est produit en amont par `MarketDataSource.snapshot()`. Le runner n'a aucune logique spécifique d'indicateur et propage le `MarketState` inchangé dans `AgentInput`.

---

## 11. Persistance durable et paper_run_id

La table `paper_runs` et `audit_cycles.paper_run_id` définissent la frontière durable d'une expérience PAPER.

- démarrage backend/composition PAPER : nouveau run ;
- `engine stop/start` dans le même process : même run ;
- arrêt propre : `ended_at` persisté ;
- redémarrage backend : nouveau run, car le ledger reste process-local ;
- cycles legacy pré-migration : `paper_run_id = NULL`.

Les analytics et readers audit peuvent être explicitement scopés par run. Le Batch 16.4 a confirmé qu'un run Agent réel peut être fermé durablement sans fill ni trade lorsque Luna choisit naturellement HOLD.

---

## 12. Batch 16.4 — preuve Agent réelle

Run confirmé : `36fe73e0-f52f-4e27-995b-c5c848f46da2`.

Sur `BTC/USD / PF_XBTUSD`, GPT-5.6 Luna, agressivité 2, levier déterministe `1x`, marge `ISOLATED` :

- 4 cycles `COMPLETED` ;
- 4 décisions réelles `HOLD` ;
- 0 cycle `FAILED` ;
- 4 Risk `ALLOW / HOLD_NO_EXECUTION` ;
- aucun `ExecutionIntent`, fill ou trade ;
- exposition et P&L finaux nuls ;
- capital final `1000 USD` ;
- run clôturé durablement avec `ended_at`.

L'`AgentInput` réel observé avait `market_state.context = null`. Ce constat motive le Batch 16.5 sans invalider les HOLD naturels du Batch 16.4.

---

## 13. ChatContextSnapshot et no-look-ahead

`RuntimeChatContextSource` agrège uniquement les surfaces canoniques : état moteur, portefeuille, audit et analytics.

Pour un cycle historique, `historical_cycle.agent_input` reste la source causale. Les états plus récents ne doivent jamais être présentés comme ayant causé une décision passée.

Le Batch 16.5 applique la même règle aux bougies PERPETUAL : aucune bougie dont la clôture n'était pas antérieure au ticker du cycle ne peut entrer dans les statistiques envoyées à l'Agent.

Le chat ne construit aucun artefact d'exécution et ne modifie pas un futur `AgentInput`.

---

## 14. Sessions chat

`OperatorChatService` conserve les sessions en mémoire process uniquement, avec historique borné. Aucun message chat n'est ajouté au journal de trading, au manifeste expérimental ou aux analytics.

---

## 15. API FastAPI

Les routes de chat restent :

```text
POST /api/v1/chat/messages
GET  /api/v1/chat/sessions/{session_id}
```

Les surfaces run-scoped incluent :

```text
GET /api/v1/paper-runs
GET /api/v1/paper-runs/current
GET /api/v1/paper-runs/{paper_run_id}
GET /api/v1/analytics?paper_run_id={paper_run_id}
```

Les lectures audit peuvent aussi être filtrées par `paper_run_id`.

Le Batch 16.5 n'ajoute aucune route API : le contexte enrichi est déjà sérialisé dans l'artefact `AgentInput` audité.

---

## 16. Frontend

Le frontend reste un cockpit de visualisation/contrôle. Il ne possède pas le moteur detrading et sa fermeture n'arrête pas le backend.

Aucun changement frontend n'est requis pour le Batch 16.5.

---

## 17. Validation Batch 16.5

La validation ciblée et la suite complète ont été confirmées localement avant intégration sur `main` au commit `595bd2c8b4311ac255db927515207f10875b1505` :

- `pytest backend` : 357 tests passés, 2 warnings externes FastAPI/Starlette ;
- Ruff : `All checks passed!` ;
- mypy avec `backend/pyproject.toml` : aucun problème sur 107 fichiers source ;
- `git diff --check` : aucune erreur de contenu ;
- tests ciblés : réutilisation de `MarketStateBuilder`, causalité/no-look-ahead, déterminisme, fraîcheur/fail-closed, sérialisation `AgentInput`, conservation mark/index/funding et absence d'auth Kraken privée.

Smoke réel via la composition normale après redémarrage backend :

- `paper_run_id = 8bbfe6a5-a5d5-4c32-96dc-eb9c5e4113d2` ;
- `cycle_id = c097f3fc-4954-4985-a364-f6ffe99b24e6`, statut `COMPLETED` ;
- `MarketState.context` sérialisé dans le vrai `AgentInput` ;
- 5 min : 6 observations, fenêtre complète ;
- 30 min : 31 observations, fenêtre complète ;
- fraîcheur `0.773542 s` ;
- `DerivativeMarketContext` conserve mark `86628.99777100343`, index `86622.3` et funding `0.00001373689662899510173815517115`.

Le critère stratégique n'est pas l'obtention d'un BUY ou SELL. L'Agent conserve la décision et un HOLD reste légitime.

---

## 18. Hors périmètre actuel

- exécution Kraken Derivatives privée/LIVE ;
- CROSS ;
- contrats inverses exécutables ;
- futures datés exécutables ;
- recovery durable du ledger ;
- rotation à chaud d'un `paper_run_id` ;
- stratégie algorithmique parallèle ;
- force BUY/SELL dans le runtime normal ;
- score de tendance déterministe transformé en décision ;
- historique de funding, order book, volume ou métriques de liquidité supplémentaires tant qu'un besoin mesuré ne justifie pas leur intégration.
