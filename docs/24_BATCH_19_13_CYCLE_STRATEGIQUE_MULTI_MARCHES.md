# 24 — Batch 19.13 — Cycle stratégique multi-marchés / multi-décisions

## 1. Statut

État au 27 septembre 2026 : le Batch 19.13 est **intégré** à GitHub `main` au commit :

```text
Ax-07/AI-Spot-Trader
main
29316d7521accfe46316cb2bc6dfcf7652ba04bf
feat: add multi-market multi-decision trading cycles
```

Un correctif post-intégration de la frontière LLM et du garde-fou SPOT-only est décrit en section 13. Il reste un patch proposé tant qu'il n'a pas été intégré par l'opérateur.

## 2. Objectif

Permettre à un cycle stratégique unique de contenir plusieurs décisions ordonnées sur plusieurs marchés, tout en conservant :

- un seul Agent IA ;
- l'Agent comme autorité stratégique ;
- Risk déterministe comme autorité finale ;
- aucune sortie LLM directement exécutable ;
- PAPER comme phase courante ;
- causalité stricte et audit complet.

## 3. Contrat stratégique

Au stade décisionnel du cycle, **un seul appel stratégique** produit un plan ordonné.

Le plan peut contenir plusieurs :

- `BUY` ;
- `SELL` ;
- `HOLD`.

Les décisions portent sur des marchés distincts de l'univers exécutable du cycle.

`max_decisions_per_cycle` :

```text
default    = 6
hard limit = 20
```

Cette borne limite la taille du plan ; elle ne force jamais l'Agent à utiliser toute la capacité.

## 4. Exécution séquentielle

La trajectoire est appliquée strictement dans l'ordre :

```text
P0
-> Risk(D1, P0)
-> Broker éventuel
-> P1
-> Risk(D2, P1)
-> Broker éventuel
-> P2
-> ...
```

Chaque décision suivante voit donc le portefeuille après les éventuelles exécutions précédentes.

Cette causalité permet notamment une rotation de capital dans le même cycle sans règle automatique : un SELL peut libérer du cash qu'un BUY ultérieur du plan pourra utiliser, uniquement si l'Agent l'a proposé et si Risk l'autorise.

## 5. HOLD et REJECT

`HOLD` et `REJECT` :

- sont persistés/auditables ;
- ne produisent pas de fill ;
- n'interrompent pas les décisions suivantes ;
- ne sont pas assimilés à une erreur technique.

Le plan reste donc une trajectoire complète, pas une boucle « stop au premier non-trade ».

## 6. Échecs techniques et atomicité PAPER

Une erreur technique Risk ou Broker :

1. fait passer le cycle à `FAILED` ;
2. arrête la trajectoire ;
3. restaure le checkpoint PAPER du début du cycle ;
4. conserve l'audit nécessaire au diagnostic.

Aucune mutation économique partielle du cycle ne doit subsister dans le portefeuille PAPER après ce rollback.

## 7. Persistence

Migration :

```text
0006_paper_control_plane
-> 0007_multi_decision_cycles
```

Le modèle d'audit devient explicitement 1:N :

```text
cycle
-> decisions ordonnées
-> risk assessments
-> execution intents
-> fills éventuels
```

La compatibilité historique avec les anciens cycles/configurations reste préservée.

## 8. API et cockpit

Le détail de cycle expose une trajectoire ordonnée permettant au cockpit de restituer :

- ordre de la décision ;
- marché ;
- action ;
- rationale Agent ;
- résultat Risk ;
- intention éventuelle ;
- fills éventuels ;
- échec technique éventuel.

Le frontend reste une projection de lecture et ne reconstruit pas Risk, P&L ou causalité.

## 9. Analytics

Les analytics continuent de mesurer l'activité économique réelle :

- fills ;
- trades ;
- notional ;
- coûts ;
- P&L ;
- exposition.

Le nombre de décisions du plan n'est pas utilisé comme nombre de trades. `HOLD` et `REJECT` restent visibles dans l'audit sans gonfler les métriques d'exécution.

## 10. Compatibilité avec les invariants existants

Le Batch 19.13 ne change pas :

- l'unicité de l'Agent ;
- la séparation discovery / stratégie / Risk / Broker ;
- `trading-style-map-v1` ;
- `strategic-mtf-v1` ;
- `position-management-v1` ;
- les règles SPOT anti-short/anti-oversell ;
- le no-look-ahead ;
- l'absence de ranking stratégique déterministe ;
- l'absence de LIVE implicite.

Les capacités PERPETUAL intégrées historiquement restent dans le code pour compatibilité, mais l'invariant projet courant impose désormais une Session canonique SPOT-only.

## 11. Validation historique du Batch 19.13

Résultats locaux fournis lors de l'intégration du Batch 19.13 :

```text
pytest ciblé : 51 passed
pytest complet : 698 passed, 2 warnings
alembic upgrade head : succès PostgreSQL réel
```

Frontend :

```text
pnpm test      : 39 passed
pnpm lint      : succès
pnpm typecheck : succès
pnpm build     : succès
```

Ces nombres décrivent le Batch 19.13 intégré. Ils ne valent pas validation du correctif post-intégration décrit ci-dessous.

## 12. Invariants à conserver

- l'IA propose ; Risk autorise, modifie ou refuse ;
- chaque décision suivante voit le portefeuille réellement courant ;
- aucune sortie Agent ne devient directement un ordre ;
- `HOLD` et `REJECT` restent auditables et non bloquants ;
- un échec technique Risk/Broker reste atomique en PAPER ;
- aucun look-ahead ;
- aucun secret ;
- aucune promesse de rendement ;
- aucune transformation silencieuse en bot algorithmique traditionnel.

## 13. Correctif post-intégration du contrat LLM

### 13.1 Régression confirmée

Le premier schéma `STRATEGIC_PLAN_SCHEMA` du Batch 19.13 acceptait `proposed_quantity` comme `number | null` indépendamment de l'action, alors que `_StrategicPlanEntryPayload` imposait :

```text
BUY / SELL -> quantité strictement positive
HOLD       -> null
```

Une sortie pouvait donc être acceptée par le Structured Output strict du fournisseur puis échouer immédiatement dans Pydantic avec `LLMOutputValidationError`.

### 13.2 Correction du schéma

Le correctif encode trois variantes strictes de décision dans un `anyOf` imbriqué :

```text
BUY  -> number > 0
SELL -> number > 0
HOLD -> null
```

Pydantic reste la seconde barrière de validation. Aucun résultat invalide n'est normalisé ou transformé en ordre valide.

### 13.3 Contrat protégé multi-marchés

`StrategyInstructionsClient` reconnaît `strategic_plan_contract` et utilise un contrat explicite `strategic-multi-market-plan-v1` :

- un seul Agent ;
- un seul appel stratégique ;
- `market_states` comme univers causal ;
- décisions ordonnées et distinctes ;
- Risk séquentiel avec autorité finale ;
- maintien des sections stratégie opérateur, agressivité, style et coûts.

Le prompt historique singleton est conservé pour les chemins legacy/replay et n'est pas réécrit rétroactivement.

### 13.4 Diagnostic fail-closed

Le correctif distingue sans inclure la sortie brute :

- sortie vide ;
- JSON invalide ;
- action invalide ;
- incohérence action/quantité ;
- liste de décisions invalide ;
- dépassement de `max_decisions_per_cycle` ;
- doublon ;
- marché hors univers.

Aucun retry sémantique LLM n'est ajouté.

### 13.5 SPOT-only

La composition du runtime PAPER canonique refuse désormais toute Session dont le bootstrap ou la discovery contient un marché non-SPOT.

Les composants PERPETUAL historiques restent présents uniquement pour compatibilité de code et d'historique. Leur suppression complète ou leur éventuelle réactivation future est hors périmètre de ce correctif.
