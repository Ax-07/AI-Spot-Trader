# 03 — Agent, Trading et Risk

## 1. Principe central

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Ce principe reste inchangé par le Batch 13. L'agressivité est un contexte stratégique versionné pour l'Agent ; elle n'est ni une limite Risk, ni une permission d'exécution, ni une formule de sizing déterministe.

---

## 2. Agent IA

L'agent reçoit un `AgentInput` structuré contenant le `MarketState`, le `PortfolioState`, le `cycle_id`, le timestamp, l'agressivité et, pour les nouveaux cycles Batch 13, son `AggressivenessContext` canonique.

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

### Prompt versionné Batch 13

Le prompt devient `agent-strategy-v2`.

Il précise que :

- `AgentInput.aggressiveness_context` est la seule interprétation canonique du niveau `1..10` ;
- l'agressivité peut influencer la volonté d'agir et la quantité **proposée** ;
- elle ne relâche jamais les limites Risk, balances, positions, solvabilité, chronologie, whitelist ou contraintes PAPER ;
- un niveau élevé ne garantit ni ALLOW, ni fill, ni rendement ;
- HOLD reste toujours valide lorsqu'aucune thèse défendable n'est supportée par les faits fournis.

Le provider normalise les anciens `AgentInput` sans contexte en ajoutant le mapping canonique avant l'appel LLM. Si un manifeste expérimental est présent, il vérifie avant l'appel que son digest, son modèle LLM, sa version de prompt et son mapping d'agressivité correspondent à la configuration réellement active.

---

## 3. Mapping agressivité 1–10 — Batch 13

Version : `aggressiveness-map-v1`.

Le mapping est **discret**, pas dérivé d'une formule de Risk ou d'un multiplicateur de taille. Les niveaux décrivent une posture stratégique :

1. `capital_preservation` — HOLD par défaut sauf signal exceptionnel ; plus petite quantité stratégiquement utile ;
2. `very_conservative` — preuve forte requise, quantités très petites ;
3. `conservative` — trades sélectifs, petites quantités ;
4. `measured` — sélection mesurée, pas d'activité forcée ;
5. `balanced` — équilibre opportunité/retenue, quantité modérée ;
6. `active` — davantage d'initiative sur thèse supportée, quantité un peu plus grande ;
7. `assertive` — action plus affirmée sur thèse cohérente, sans activité artificielle ;
8. `aggressive` — éventail plus large d'opportunités bien raisonnées, grandes quantités proposées possibles ;
9. `very_aggressive` — forte propension à agir sur opportunité plausible/cohérente, très grandes quantités proposées possibles ;
10. `maximum_experimental` — initiative stratégique maximale, sans aucune relaxation des contraintes Risk.

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

L'agressivité n'est pas passée au `RiskEngine.evaluate(...)`. Les contrôles de symbole, chronologie, whitelist, fraîcheur, max notional, solvabilité BUY et position SELL restent identiques pour les niveaux 1 et 10.

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

Le verrou du runner empêche le chevauchement des cycles.

Les pannes techniques sont des résultats `FAILED` avec stage/type/timeout sanitizés. Elles ne deviennent jamais un HOLD.

Si un `ExperimentManifest` est injecté au runner, son digest est vérifié et son niveau/univers doivent correspondre à la configuration du runner avant tout cycle.

---

## 6. Manifeste expérimental durable

Version : `paper-experiment-v1`.

Le manifeste enregistre :

```text
protocol_version
experiment_digest
aggressiveness { mapping_version, level, posture, strategic_instruction }
llm_model
prompt_version
universe[]
risk_policy { max_order_notional, allowed_pairs, stale_after_seconds, allow_quantity_reduction }
paper_costs { fee_rate, spread_bps, slippage_bps }
analytics_version
source_id
source_digest?
window_start?
window_end?
```

Le digest SHA-256 est calculé sur la représentation canonique de ces champs. À configuration identique, le digest est identique ; changer le niveau, le modèle, le prompt, Risk, les coûts, l'univers ou les faits sources change l'identité expérimentale.

Le manifeste est inclus dans `AgentInput`. Comme le journal Batch 09 persiste déjà l'`AgentInput` complet, aucune migration n'est nécessaire. Le `result_digest` du cycle inclut naturellement le manifeste via le payload canonique.

Le digest ne rend pas le LLM déterministe. Il identifie le **protocole** ; les décisions effectivement réalisées restent des faits durables séparés.

---

## 7. Comparaison des niveaux

`compare_aggressiveness_runs(...)` compare des `PaperAnalyticsReport` Batch 12 déjà calculés.

Les runs ne sont comparables que si tous les champs contrôlés hors agressivité sont identiques : modèle, prompt, univers, `RiskPolicy`, coûts PAPER, source/dataset, fenêtre et version analytics.

La comparaison expose factuellement :

- P&L brut/net ;
- frais, spread, slippage ;
- drawdown ;
- exposition ;
- nombre de trades ;
- HOLD / REJECT / MODIFY / FAILED ;
- séries quotidiennes déjà calculées par Batch 12.

Elle ne recalcule aucune métrique, ne réordonne pas les décisions, ne sélectionne pas rétrospectivement les meilleurs cycles et ne produit aucun « gagnant » automatique.

---

## 8. TradingEngine

`TradingEngine` répète le runner séquentiellement :

```text
cycle -> attente cadence -> cycle -> ...
```

Il n'ajoute aucune stratégie. `start()` crée une seule boucle autonome, `stop()` est coopératif et attend le cycle borné éventuellement en cours.

Les propriétés `is_running`, `last_result` et `last_unexpected_error_type` fournissent l'observation minimale utilisée par l'API.

---

## 9. Persistance

`AuditedTradingCycleRunner` enveloppe le runner canonique :

```text
result = delegate.run_cycle()
audit_writer.record(result)
return result
```

La persistance conserve les faits produits, notamment HOLD et REJECT, mais ne crée aucun artefact métier.

Le mapping et le manifeste Batch 13 sont persistés à l'intérieur du payload `AgentInput` existant. Le schéma SQL reste inchangé.

La limite exactly-once entre mutation du ledger mémoire et commit PostgreSQL reste documentée et non résolue.

---

## 10. API et frontend

Aucune nouvelle route ni surface cockpit n'est ajoutée au Batch 13.

Motif : le protocole expérimental est une configuration backend/domaine et les analytics comparés existent déjà. Une future UI de lancement d'expériences nécessitera un contrat de composition produit explicite plutôt qu'un configurateur stratégique improvisé dans le frontend.

Le frontend reste strictement cockpit et ne peut pas muter le mapping, `RiskPolicy`, les coûts ou le manifeste d'un moteur en cours.

---

## 11. No-look-ahead et anti cherry-picking

Pour comparer deux niveaux honnêtement :

- utiliser le même modèle et la même version de prompt ;
- utiliser la même `RiskPolicy` et les mêmes coûts PAPER ;
- utiliser le même univers ;
- lier les runs au même `source_id` et, pour un dataset figé, au même `source_digest` ;
- conserver les mêmes fenêtres temporelles ;
- ne jamais réécrire une décision déjà prise ;
- ne jamais supprimer a posteriori des HOLD, REJECT, FAILED ou mauvais trades ;
- valoriser les résultats uniquement via les faits durables et `paper-analytics-v1`.

Sur un flux live, deux runs séquentiels ne voient pas mécaniquement les mêmes faits. Pour isoler strictement l'effet de l'agressivité, un dataset/snapshot replay figé avec digest identique est requis.

---

## 12. Limite de reproductibilité LLM

Même manifeste + mêmes faits ne signifie pas nécessairement même sortie Luna/Sol : le fournisseur LLM peut rester non parfaitement déterministe et le projet ne prétend pas disposer d'un seed/replay exact fournisseur.

La reproductibilité Batch 13 porte donc sur :

- l'identité du protocole ;
- la conservation des entrées et décisions réalisées ;
- la comparaison des métriques Batch 12 à faits réalisés identiques.

Le Batch 14 pourra réutiliser exactement ce mécanisme pour comparer Luna/Sol en changeant explicitement le modèle tout en maintenant le reste du protocole contrôlé.

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
- agressivité hors contrôle des limites Risk ;
- erreurs techniques distinctes de HOLD ;
- aucun secret exposé ;
- aucun look-ahead ;
- aucun cherry-picking post-hoc ;
- aucun LIVE.
