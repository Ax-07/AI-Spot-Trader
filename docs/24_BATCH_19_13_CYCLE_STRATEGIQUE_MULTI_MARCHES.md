# 24 — Batch 19.13 — Cycle stratégique multi-marchés / multi-décisions

## 1. Statut

Le Batch 19.13 a été intégré initialement à GitHub `main` au commit :

```text
29316d7521accfe46316cb2bc6dfcf7652ba04bf
feat: add multi-market multi-decision trading cycles
```

Les durcissements suivants sont également intégrés :

```text
aa404e46c1f05269ac2279507aa746b3af7a965d  fix: harden multi-market LLM plan contract
b4f1e50f22164c7d019d11d930485733c01c6711  fix: restore paper perpetual session support
282267b1f491bb07b2644f6b9c5dca01c539697f  refactor: recalibrate strategic LLM prompts
463850d8281faebe86a6ee733d58781c349015d0  refactor: make strategic agent cost aware
```

Le recalibrage cost-aware est intégré à GitHub `main` dans `463850d` après validation locale.

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

Le plan peut contenir plusieurs `BUY`, `SELL` et `HOLD` sur des marchés distincts de l'univers causal.

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

Le détail de cycle expose une trajectoire ordonnée permettant au cockpit de restituer : ordre, marché, action, rationale Agent, résultat Risk, intention/fills éventuels et échec technique éventuel.

Le frontend reste une projection de lecture et ne reconstruit pas Risk, P&L ou causalité.

## 9. Analytics

Les analytics continuent de mesurer l'activité économique réelle : fills, trades, notional, coûts, P&L et exposition.

Le nombre de décisions du plan n'est pas utilisé comme nombre de trades. `HOLD` et `REJECT` restent visibles dans l'audit sans gonfler les métriques d'exécution.

## 10. Compatibilité avec les invariants existants

Le cycle multi-décisions ne change pas :

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

## 11. Validation

Résultats locaux fournis lors de l'intégration initiale du Batch 19.13 :

```text
pytest ciblé : 51 passed
pytest complet : 698 passed, 2 warnings
alembic upgrade head : succès PostgreSQL réel
```

Frontend historique :

```text
pnpm test      : 39 passed
pnpm lint      : succès
pnpm typecheck : succès
pnpm build     : succès
```

Validation locale du recalibrage net/cost-aware intégré dans `463850d`, réalisée le 28 septembre 2026 :

```text
pytest ciblé : 47/47 passed
pytest complet : 100 % passed, 0 failure
warnings : 2 dépréciations Starlette/AnyIO hors périmètre
```

Les nombres ci-dessus correspondent à leurs validations respectives et ne doivent pas être fusionnés en un total unique.

## 12. Durcissement du contrat LLM

Le schéma `STRATEGIC_PLAN_SCHEMA` encode le contrat :

```text
BUY  -> number > 0
SELL -> number > 0
HOLD -> null
```

Pydantic reste la seconde barrière. Aucun résultat invalide n'est normalisé ou transformé en ordre valide.

`StrategyInstructionsClient` reconnaît `strategic_plan_contract` et utilise `strategic-multi-market-plan-v1` :

- un seul Agent ;
- un seul appel stratégique ;
- `market_states` comme univers causal ;
- décisions ordonnées et distinctes ;
- Risk séquentiel avec autorité finale ;
- maintien des sections stratégie opérateur, agressivité, style et coûts.

Le prompt historique singleton reste conservé pour les chemins legacy/replay et n'est pas réécrit rétroactivement.

## 13. SPOT / PERPETUAL

Le contrat protégé courant autorise :

- `SPOT` avec règles anti-short/anti-oversell ;
- `PERPETUAL` linéaire lorsqu'il appartient à l'univers causal ;
- `FUTURE` daté interdit.

La sémantique PERPETUAL reste symétrique :

```text
BUY  -> ouvre/augmente LONG, ou réduit SHORT
SELL -> ouvre/augmente SHORT, ou réduit LONG
```

Levier, marge, `reduce_only`, exposition et liquidation restent du ressort exclusif du Risk Engine déterministe.

## 14. Recalibrage cost-aware intégré après observation PAPER

Une session PAPER réelle d'environ 9 h a montré :

```text
capital initial      ~ 100
equity finale        ~ 97,713
P&L brut             ~ +0,727
P&L net              ~ -2,287
frais                ~ 2,123
spread               ~ 0,425
slippage             ~ 0,425
funding              ~ -0,042
fills                 1 246
cycles                395
```

Ce run montre un turnover élevé et un avantage brut insuffisant pour absorber les coûts. Il **motive** le recalibrage mais ne constitue pas une preuve générale de performance ou de biais directionnel.

Le contrat Campaign courant est donc précisé sans modifier Risk :

- objectif économique = progression de l'equity nette après coûts ;
- frais, spread, slippage et funding disponible appartiennent au résultat économique ;
- tradable != économiquement intéressant ;
- `HOLD`, cash et maintien d'une position sont des allocations valides ;
- une rotation doit être comparée à la conservation car elle cumule plusieurs coûts ;
- faible conviction != petite position « pour essayer » ;
- agressivité élevée = plus d'initiative sur opportunités convaincantes, pas obligation de turnover/micro-trades ;
- multi-marchés = raisonnement en allocation et coût d'opportunité.

Aucun seuil de profit, cooldown, durée minimale, quota de trades ou score algorithmique n'est ajouté.

## 15. Mapping d'agressivité et historique

Le mapping expérimental historique `aggressiveness-map-v1` reste inchangé pour les manifests/replays.

Le mapping LLM courant est passé de `aggressiveness-map-v2` à `aggressiveness-map-v3` dans `463850d` afin de versionner explicitement le nouveau comportement cost-aware. Le niveau 10 reste `maximum_experimental`, mais n'implique ni quantité maximale, ni fréquence maximale, ni rotation obligatoire.

`AGENT_SYSTEM_PROMPT` `agent-strategy-v4` reste inchangé.

## 16. Audit du biais SELL / SHORT PERPETUAL

Classification du présent audit :

- **confirmé** : pas de biais directionnel explicite dans le planner, le mapping BUY/SELL PERPETUAL, la sélection multi-marchés ou Risk ;
- **confirmé** : `aggressiveness-map-v2` pouvait pousser le turnover global via davantage de rotation/fréquence potentielle ;
- **confirmé** : le texte générique de gestion « signal automatique de vente » était directionnellement asymétrique ; il a été remplacé par « réduction/clôture » et une formulation BUY/SELL symétrique ;
- **corrigé** : objectif net-equity et coût d'opportunité explicites ;
- **à décider** : existence d'un biais SHORT persistant sur plusieurs runs comparables.

Aucun quota LONG/SHORT ou contre-biais artificiel n'est introduit.

## 17. Invariants à conserver

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
