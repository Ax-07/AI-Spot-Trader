# 24 — Batch 19.13 — Cycle stratégique multi-marchés / multi-décisions

## 1. Statut

État au 27 septembre 2026 : le Batch 19.13 a été intégré initialement à GitHub `main` au commit :

```text
Ax-07/AI-Spot-Trader
main
29316d7521accfe46316cb2bc6dfcf7652ba04bf
feat: add multi-market multi-decision trading cycles
```

Le durcissement post-Batch 19.13 du contrat LLM est désormais intégré à `main` au commit `aa404e46c1f05269ac2279507aa746b3af7a965d` (`fix: harden multi-market LLM plan contract`). Ce commit a aussi ajouté par erreur un garde-fou SPOT-only au runtime. Le présent correctif PERPETUAL retire uniquement cette restriction erronée et reste un patch proposé tant qu'il n'a pas été intégré par l'opérateur.

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

Les Sessions PAPER canoniques peuvent utiliser `SPOT` et `PERPETUAL` linéaire. Les contrôles dérivés existants restent déterministes et conservent l'autorité finale : marge isolée, levier configuré et plafonné, plafonds de notionnel/exposition, buffer de liquidation et `reduce_only`. `FUTURE` daté reste interdit.

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

Ces nombres décrivent le Batch 19.13 intégré. Ils ne valent pas validation du durcissement `aa404e4` ni du correctif PERPETUAL courant.

Après `aa404e4`, l'opérateur a fourni les résultats suivants avant le présent correctif :

```text
pytest multi-market ciblé : 36 passed
pytest backend complet    : 718 passed, 2 warnings
```

Ces résultats constituent le baseline du commit `aa404e4`, pas une validation du patch PERPETUAL livré ici.

## 12. Invariants à conserver

- l'IA propose ; Risk autorise, modifie ou refuse ;
- chaque décision suivante voit le portefeuille réellement courant ;
- aucune sortie Agent ne devient directement un ordre ;
- `HOLD` et `REJECT` restent auditables et non bloquants ;
- un échec technique Risk/Broker reste atomique en PAPER ;
- SPOT reste sans short, levier ni marge ;
- PERPETUAL reste soumis aux contrôles dérivés déterministes ;
- `FUTURE` daté reste interdit ;
- aucun look-ahead ;
- aucun secret ;
- aucune promesse de rendement ;
- aucune transformation silencieuse en bot algorithmique traditionnel.

## 13. Durcissement post-intégration du contrat LLM et correctif PERPETUAL

### 13.1 Régression LLM corrigée dans `aa404e4`

Le premier schéma `STRATEGIC_PLAN_SCHEMA` du Batch 19.13 acceptait `proposed_quantity` comme `number | null` indépendamment de l'action, alors que `_StrategicPlanEntryPayload` imposait :

```text
BUY / SELL -> quantité strictement positive
HOLD       -> null
```

Une sortie pouvait donc être acceptée par le Structured Output strict du fournisseur puis échouer immédiatement dans Pydantic avec `LLMOutputValidationError`.

### 13.2 Correction du schéma conservée

`aa404e4` encode trois variantes strictes de décision dans un `anyOf` imbriqué :

```text
BUY  -> number > 0
SELL -> number > 0
HOLD -> null
```

Pydantic reste la seconde barrière de validation. Aucun résultat invalide n'est normalisé ou transformé en ordre valide.

### 13.3 Contrat protégé multi-marchés conservé

`StrategyInstructionsClient` reconnaît `strategic_plan_contract` et utilise un contrat explicite `strategic-multi-market-plan-v1` :

- un seul Agent ;
- un seul appel stratégique ;
- `market_states` comme univers causal ;
- décisions ordonnées et distinctes ;
- Risk séquentiel avec autorité finale ;
- maintien des sections stratégie opérateur, agressivité, style et coûts.

Le prompt historique singleton est conservé pour les chemins legacy/replay et n'est pas réécrit rétroactivement.

Le présent correctif réaligne uniquement les règles de types de marchés du contrat protégé :

- `SPOT` autorisé avec règles anti-short/anti-oversell ;
- `PERPETUAL` linéaire autorisé lorsqu'il appartient à l'univers causal ;
- `FUTURE` daté interdit ;
- levier, marge, `reduce_only`, exposition et liquidation restent du ressort du Risk Engine déterministe.

### 13.4 Diagnostic fail-closed conservé

Le durcissement distingue sans inclure la sortie brute :

- sortie vide ;
- JSON invalide ;
- action invalide ;
- incohérence action/quantité ;
- liste de décisions invalide ;
- dépassement de `max_decisions_per_cycle` ;
- doublon ;
- marché hors univers.

Aucun retry sémantique LLM n'est ajouté. Un plan invalide échoue avant Risk.

### 13.5 Correction du garde-fou SPOT-only

`aa404e4` a ajouté `_ensure_spot_only_session()` dans `campaign_composition.py` et l'a appelé au début de `build_campaign_runtime()`. Ce garde-fou rejetait tout bootstrap ou toute discovery non-SPOT avant même la composition des composants dérivés déjà canoniques.

C'est la cause directe du chemin :

```text
build_campaign_runtime
-> configuration error
-> CampaignActivationError
-> API Sessions
-> HTTP 503 · Session operation is unavailable
```

Le correctif retire uniquement ce garde-fou et son appel. Il ne supprime ni ne contourne les validations canoniques existantes :

- `SPOT` reste autorisé ;
- `PERPETUAL` linéaire redevient autorisé dans les Sessions PAPER et la discovery ;
- `FUTURE` daté reste refusé par la configuration, la discovery et l'exécution ;
- les contrôles d'exposition, de levier, de marge, de liquidation et `reduce_only` restent inchangés ;
- le multi-market, le contrat LLM strict et le fail-closed de `aa404e4` restent inchangés.
