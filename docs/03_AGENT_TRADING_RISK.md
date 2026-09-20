# 03 — Agent, Trading et Risk

## 1. Principe central

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Ce principe reste inchangé par les Batches 13/14. L'agressivité et le choix Luna/Sol appartiennent à la couche stratégique Agent ; ils ne sont ni des limites Risk, ni des permissions d'exécution, ni des formules de sizing déterministes.

---

## 2. Agent IA

L'agent reçoit un `AgentInput` structuré contenant le `MarketState`, le `PortfolioState`, le `cycle_id`, le timestamp, l'agressivité, son `AggressivenessContext` canonique et éventuellement un `ExperimentManifest`.

Il produit uniquement :

```text
DecisionCandidate
  action = BUY | SELL | HOLD
  symbol
  proposed_quantity
  rationale
```

BUY/SELL nécessitent une quantité stratégique positive ; HOLD n'en porte aucune. `decision_id`, `cycle_id` et `created_at` restent contrôlés par l'application.

Le provider LLM ne dispose d'aucun outil Broker/Kraken et ne connaît pas l'API de lifecycle. Luna et Sol utilisent le **même `OpenAIDecisionProvider`** et le même schéma de sortie.

### Prompt versionné

Le prompt courant est `agent-strategy-v2`.

Il précise notamment que :

- `AgentInput.aggressiveness_context` est l'interprétation canonique du niveau `1..10` ;
- l'agressivité peut influencer la volonté d'agir et la quantité **proposée** ;
- elle ne relâche jamais les limites Risk, balances, positions, solvabilité, chronologie, whitelist ou contraintes PAPER ;
- un niveau élevé ne garantit ni ALLOW, ni fill, ni rendement ;
- HOLD reste valide lorsqu'aucune thèse défendable n'est supportée par les faits fournis.

Le provider normalise les anciens `AgentInput` sans contexte en ajoutant le mapping canonique avant l'appel LLM. Si un manifeste expérimental est présent, il vérifie avant l'appel son digest, son modèle LLM, sa version de prompt et son mapping d'agressivité.

---

## 3. Mapping agressivité 1–10 — Batch 13

Version : `aggressiveness-map-v1`.

Le mapping est **discret**, pas dérivé d'une formule de Risk ou d'un multiplicateur de taille. Les dix postures restent celles intégrées au Batch 13, de `capital_preservation` à `maximum_experimental`.

Ce mapping ne contient aucun seuil de prix, indicateur, exposition, drawdown, balance ou notional. Il ne constitue donc pas une stratégie déterministe parallèle.

---

## 4. Risk Engine

Risk reste synchrone et déterministe. Il reçoit la décision et les mêmes snapshots que l'agent.

Résultats :

- `ALLOW` : la quantité est conservée ;
- `MODIFY` : la quantité est strictement réduite ;
- `REJECT` : aucune quantité n'est autorisée ;
- HOLD : assessment complet sans `ExecutionIntent`.

Seul Risk peut construire un `ExecutionIntent`. Il ne peut pas changer BUY en SELL, SELL en BUY ou le symbole stratégique.

Ni l'agressivité ni le modèle LLM ne sont passés au `RiskEngine.evaluate(...)`. Les contrôles de symbole, chronologie, whitelist, fraîcheur, max notional, solvabilité BUY et position SELL sont identiques quel que soit le modèle.

---

## 5. TradingCycleRunner

`TradingCycleRunner.run_cycle()` reste la primitive canonique.

Ordre :

1. acquisition d'un unique `MarketState` ;
2. snapshot du portefeuille PAPER ;
3. résolution déterministe de `AggressivenessContext` ;
4. construction de `AgentInput` avec manifeste expérimental éventuel ;
5. décision Agent ;
6. évaluation Risk ;
7. Broker uniquement si Risk a produit un intent ;
8. snapshot portefeuille post-exécution si applicable ;
9. `TradingCycleResult`.

Le verrou du runner empêche le chevauchement des cycles. Les pannes techniques sont des résultats `FAILED` avec stage/type/timeout sanitizés ; elles ne deviennent jamais un HOLD.

Si un `ExperimentManifest` est injecté, son digest est vérifié et son niveau/univers doivent correspondre à la configuration du runner avant tout cycle.

---

## 6. Manifestes expérimentaux durables

### `paper-experiment-v1`

Le v1 reste le protocole Batch 13 pour comparer l'agressivité. Il enregistre niveau/mapping, modèle, prompt, univers, `RiskPolicy`, coûts PAPER, version analytics, source/dataset et fenêtre éventuelle. Son `comparison_identity` exclut l'agressivité mais conserve le modèle comme champ contrôlé.

### `paper-experiment-v2`

Le Batch 14 intégré ajoute un protocole où le modèle est l'unique variable expérimentale :

```text
protocol_version = paper-experiment-v2
comparison_variable = LLM_MODEL
experiment_group_digest
experiment_digest
replicate_index
replicate_count
aggressiveness { mapping_version, level, posture, strategic_instruction }
llm_model
prompt_version
universe[]
risk_policy { max_order_notional, allowed_pairs, stale_after_seconds, allow_quantity_reduction }
paper_costs { fee_rate, spread_bps, slippage_bps }
analytics_version
source_id
source_digest
window_start?
window_end?
```

`source_digest` est obligatoire. Le digest de groupe varie si un champ contrôlé change et exclut uniquement le modèle et l'index de répétition. Le digest complet identifie chaque run.

Le manifeste est inclus dans `AgentInput`. Le journal Batch 09 persistant déjà l'`AgentInput` complet, aucune migration n'est nécessaire.

Aucun digest ne rend le LLM déterministe : il identifie le **protocole** et les relations entre runs ; les décisions réalisées restent des faits durables séparés.

---

## 7. Comparaison Luna / Sol

`compare_model_runs(...)` compare des `PaperAnalyticsReport` Batch 12 déjà calculés.

Deux runs appartiennent au même groupe uniquement si restent identiques :

- agressivité + version de mapping ;
- version de prompt ;
- univers ;
- `RiskPolicy` ;
- coûts PAPER ;
- `source_id` et `source_digest` ;
- fenêtre ;
- version analytics ;
- nombre de répétitions déclaré.

La seule variable autorisée est `llm_model`, avec l'index de répétition comme identité de réalisation.

La comparaison expose factuellement :

- P&L brut/net ;
- frais, spread, slippage ;
- drawdown ;
- exposition ;
- nombre de trades BUY/SELL ;
- HOLD / REJECT / MODIFY / FAILED ;
- points cumulés déjà calculés par Batch 12 ;
- séries quotidiennes Batch 12.

Elle ne recalcule aucune métrique métier, ne réordonne pas les décisions et ne produit aucun « gagnant » automatique.

---

## 8. Répétitions et non-déterminisme

Le LLM peut rester non parfaitement déterministe même avec modèle, prompt et faits identiques. Le patch ne prétend pas disposer d'un seed fournisseur inexistant.

`replicate_count = N` annonce explicitement le nombre de réalisations prévues par modèle. `compare_model_runs(...)` exige alors les répétitions `1..N` pour Luna **et** Sol. Une comparaison incomplète est refusée.

Ce mécanisme permet de conserver une dispersion observable sans créer de score ou de modèle statistique caché. Les statistiques de dispersion éventuelles pourront être ajoutées séparément si elles sont définies explicitement.

---

## 9. Persistance

`AuditedTradingCycleRunner` continue d'envelopper le runner canonique :

```text
result = delegate.run_cycle()
audit_writer.record(result)
return result
```

La persistance conserve les faits produits, notamment HOLD et REJECT, mais ne crée aucun artefact métier.

Le manifeste v2, l'identité de groupe et l'index de répétition sont persistés à l'intérieur du payload `AgentInput` existant. Le schéma SQL reste inchangé.

La limite exactly-once entre mutation du ledger mémoire et commit PostgreSQL reste documentée et non résolue.

---

## 10. API et frontend

Aucune nouvelle route ni surface cockpit n'est ajoutée au Batch 14.

Motif : le protocole expérimental est une configuration backend/domaine et les analytics comparés existent déjà. Une future UI de lancement d'expériences nécessitera un contrat de composition produit explicite plutôt qu'un configurateur stratégique improvisé dans le frontend.

Le frontend reste strictement cockpit et ne peut pas muter modèle, mapping, `RiskPolicy`, coûts ou manifeste d'un moteur en cours.

---

## 11. No-look-ahead et anti cherry-picking

Pour comparer Luna et Sol honnêtement :

- utiliser le même prompt et la même agressivité ;
- utiliser la même `RiskPolicy` et les mêmes coûts PAPER ;
- utiliser le même univers ;
- lier les runs au même `source_id` et au même `source_digest` figé ;
- conserver la même fenêtre et la même version analytics ;
- annoncer `replicate_count` avant la comparaison et conserver toutes les répétitions des deux modèles ;
- ne jamais réécrire une décision déjà prise ;
- ne jamais supprimer a posteriori des HOLD, REJECT, FAILED ou mauvais trades ;
- valoriser les résultats uniquement via les faits durables et `paper-analytics-v1`.

Deux passages successifs sur un flux live non figé ne constituent pas une expérience appariée stricte. Un dataset/snapshot replay figé avec digest identique est nécessaire pour attribuer proprement les écarts au modèle seul.

---

## 12. Invariants conservés

- un seul agent IA ;
- même provider canonique pour Luna/Sol ;
- SPOT/PAPER uniquement ;
- aucun short/levier/margin/future/perpetual ;
- SELL uniquement sur position détenue ;
- IA stratégique ;
- Risk autorité finale ;
- aucun LLM -> Broker direct ;
- seul Risk crée l'intent ;
- agressivité et modèle hors contrôle des limites Risk ;
- HOLD/ALLOW/MODIFY/REJECT conservent leur sémantique ;
- erreurs techniques distinctes de HOLD ;
- aucun secret exposé ;
- aucun look-ahead ;
- aucun cherry-picking post-hoc ;
- aucun LIVE.
