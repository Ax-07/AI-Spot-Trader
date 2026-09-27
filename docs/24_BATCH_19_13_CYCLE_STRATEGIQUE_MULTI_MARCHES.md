# 24 — Batch 19.13 — Cycle stratégique multi-marchés / multi-décisions

## 1. Statut

État au 27 septembre 2026 : **implémentation terminée et validée dans le présent état du repository**.

Base GitHub vérifiée avant le Batch 19.13 :

```text
Ax-07/AI-Spot-Trader
main
18596ac9d4f6554aa4817a9bdb374ab597c2399f
fix: harden paper perpetual execution precision
```

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
- les contraintes PERPETUAL ;
- le no-look-ahead ;
- l'absence de ranking stratégique déterministe ;
- l'absence de LIVE implicite.

## 11. Validation locale exécutée

Backend :

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

Ces validations sont des résultats locaux fournis pour le Batch 19.13. Elles ne constituent pas encore une intégration GitHub tant que le commit/push n'a pas été effectué par l'opérateur.

## 12. Invariants à conserver après intégration

- l'IA propose ; Risk autorise, modifie ou refuse ;
- chaque décision suivante voit le portefeuille réellement courant ;
- aucune sortie Agent ne devient directement un ordre ;
- `HOLD` et `REJECT` restent auditables et non bloquants ;
- un échec technique Risk/Broker reste atomique en PAPER ;
- aucun look-ahead ;
- aucun secret ;
- aucune promesse de rendement ;
- aucune transformation silencieuse en bot algorithmique traditionnel.
