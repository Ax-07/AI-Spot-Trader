# 03 — Agent, Trading et Risk

## 1. Principe central

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Ce principe reste inchangé par le Batch 10. L'API est une façade d'observation et de lifecycle ; elle n'est ni un agent, ni un Risk Engine, ni un Broker.

---

## 2. Agent IA

L'agent reçoit un `AgentInput` structuré contenant le `MarketState`, le `PortfolioState`, le `cycle_id`, le timestamp et l'agressivité.

Il produit uniquement :

```text
DecisionCandidate
  action = BUY | SELL | HOLD
  symbol
  proposed_quantity
  rationale
```

BUY/SELL nécessitent une quantité stratégique positive ; HOLD n'en porte aucune. `decision_id`, `cycle_id` et `created_at` restent contrôlés par l'application.

Le provider LLM ne dispose d'aucun outil Broker/Kraken et ne connaît pas l'API de lifecycle.

---

## 3. Risk Engine

Risk reste synchrone et déterministe. Il reçoit la décision et les mêmes snapshots que l'agent.

Résultats :

- `ALLOW` : la quantité est conservée ;
- `MODIFY` : la quantité est strictement réduite ;
- `REJECT` : aucune quantité n'est autorisée ;
- HOLD : assessment complet sans `ExecutionIntent`.

Seul Risk peut construire un `ExecutionIntent`. Il ne peut pas changer BUY en SELL, SELL en BUY ou le symbole stratégique.

---

## 4. TradingCycleRunner

`TradingCycleRunner.run_cycle()` reste la primitive canonique.

Ordre :

1. acquisition d'un unique `MarketState` ;
2. snapshot du portefeuille PAPER ;
3. construction de `AgentInput` ;
4. décision Agent ;
5. évaluation Risk ;
6. Broker uniquement si Risk a produit un intent ;
7. snapshot portefeuille post-exécution si applicable ;
8. `TradingCycleResult`.

Le verrou du runner empêche le chevauchement des cycles.

Les pannes techniques sont des résultats `FAILED` avec stage/type/timeout sanitizés. Elles ne deviennent jamais un HOLD.

---

## 5. TradingEngine

`TradingEngine` répète le runner séquentiellement :

```text
cycle -> attente cadence -> cycle -> ...
```

Il n'ajoute aucune stratégie. `start()` crée une seule boucle autonome, `stop()` est coopératif et attend le cycle borné éventuellement en cours.

Les propriétés `is_running`, `last_result` et `last_unexpected_error_type` fournissent l'observation minimale utilisée par l'API.

---

## 6. Persistance

`AuditedTradingCycleRunner` enveloppe le runner canonique :

```text
result = delegate.run_cycle()
audit_writer.record(result)
return result
```

La persistance conserve les faits produits, notamment HOLD et REJECT, mais ne crée aucun artefact métier.

La limite exactly-once entre mutation du ledger mémoire et commit PostgreSQL reste documentée et non résolue au Batch 10.

---

## 7. API Batch 10 : frontières

### Autorisé

L'API peut :

- lire l'état lifecycle du `TradingEngine` injecté ;
- demander `start()` ou `stop()` au même moteur canonique ;
- lire un snapshot du ledger PAPER injecté ;
- lire les faits durables via `CycleAuditReader` ;
- exposer des réponses Pydantic dédiées et sanitizées.

### Interdit

L'API ne doit jamais :

- créer un `DecisionCandidate` ;
- appeler le LLM pour forcer une décision ;
- créer un `RiskAssessment` ;
- construire un `ExecutionIntent` ;
- appeler directement le Broker ;
- fabriquer un faux cycle dans le journal ;
- muter une RiskPolicy ou une stratégie sans contrat explicitement décidé ;
- activer le LIVE.

---

## 8. Start/stop via HTTP

Le Batch 10 retient start/stop uniquement parce que `TradingEngine` possède déjà un lifecycle canonique clair.

`POST /api/v1/engine/start` délègue à `TradingEngine.start()` ; il n'existe aucune implémentation parallèle dans la route. Un start alors que le moteur tourne retourne un conflit.

`POST /api/v1/engine/stop` délègue à `TradingEngine.stop()` et peut être répété sans créer d'effet de trading supplémentaire.

Le moteur n'est jamais démarré automatiquement par FastAPI.

---

## 9. Portefeuille et dernier marché

Le portefeuille courant exposé par l'API vient du ledger mémoire réel injecté. L'API ne tente pas de reconstruire un portefeuille « supposé » depuis les fills PostgreSQL.

Le dernier marché de l'API d'audit vient du dernier `MarketState` déjà enregistré dans un `AgentInput`. Il ne déclenche aucun appel Kraken.

---

## 10. HOLD / REJECT / MODIFY / ALLOW dans l'API

Le journal et l'API préservent la sémantique existante :

- HOLD : décision + assessment, aucun intent/fill ;
- REJECT : décision + assessment, aucun intent/fill ;
- MODIFY : décision + assessment + intent Risk + fill(s) ;
- ALLOW tradable : décision + assessment + intent Risk + fill(s).

Aucune route ne transforme ces résultats en score ou recommandation secondaire.

---

## 11. Erreurs techniques

Les réponses API n'exposent que :

```text
stage
error_type
timed_out
```

Les messages d'exception bruts ne sont pas renvoyés. Cette règle vaut pour les erreurs de cycle comme pour les erreurs DB.

---

## 12. WebSocket

Un WebSocket n'est pas justifié dans ce batch. Le projet ne dispose pas encore d'un flux d'événements métier canonique réutilisable sans dupliquer l'état.

REST constitue donc le contrat initial du cockpit. La fréquence de rafraîchissement et un futur mécanisme push seront décidés séparément.

---

## 13. Invariants conservés

- un seul agent IA ;
- SPOT/PAPER uniquement ;
- aucun short/levier/margin/future/perpetual ;
- SELL uniquement sur position détenue ;
- IA stratégique ;
- Risk autorité finale ;
- aucun LLM -> Broker direct ;
- seul Risk crée l'intent ;
- erreurs techniques distinctes de HOLD ;
- aucun secret exposé ;
- aucun look-ahead ;
- aucun LIVE.
