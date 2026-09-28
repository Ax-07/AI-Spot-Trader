# Batch 25 — Historique économique par Session

## 1. Base auditée

Référence vérifiée le 28 septembre 2026 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 59f92938bf5159004783ae004fe99c808cb2c8c2
Fonctionnel: 463850d8281faebe86a6ee733d58781c349015d0
```

Le batch part du constat que l'application possède déjà les faits canoniques nécessaires : cycles, décisions ordonnées, RiskAssessment, ExecutionIntent, fills, snapshots de portefeuille, lineage de PAPER runs et `PaperAnalyticsReport`.

## 2. Audit

### Confirmé

- `CycleRecord` est rattaché à `paper_run_id` ;
- les décisions multi-marchés sont ordonnées par `decision_index` ;
- Risk, intents et fills sont corrélés à la décision ;
- `Fill` contient déjà quantité, prix de référence, prix exécuté, notional, frais, spread, slippage, `realized_pnl`, `funding_payment`, type de marché et `reduce_only` ;
- `PortfolioState` contient les positions SPOT/PERPETUAL et leurs informations comptables/valorisées ;
- `SqlAlchemyPaperAnalyticsQueryService` rejoue les faits durables et suit le lineage `resumed_from_paper_run_id` ;
- les fills d'un cycle `FAILED` sont conservés comme preuve d'audit mais exclus de l'économie canonique ;
- `/api/v1/analytics?paper_run_id=...` fournit déjà equity, P&L brut/net, coûts, funding, drawdown et exposition ;
- le cockpit `Historique` expose déjà Agent → Risk → PAPER, mais par cycle et sans table économique consolidée.

### Obsolète

- considérer `trade_count` comme un nombre de fills : la métrique canonique actuelle compte les `execution_id` uniques ;
- supposer qu'un `SELL` PERPETUAL est une clôture : l'effet dépend de la position signée avant/après.

### Manquant avant ce batch

- vue simple des opérations économiques réellement exécutées ;
- fill count explicite distinct du nombre de trades/exécutions ;
- notional total, turnover, coûts/notional, coûts/equity et fills/heure ;
- classification descriptive ouverture/augmentation/réduction/clôture/flip ;
- sélection Session → historique de Campaign/run dans l'écran Historique ;
- export JSON dédié à l'analyse économique.

### À décider ultérieurement

- interface dédiée de comparaison côte à côte entre deux runs ;
- durée de position complète si une reconstruction causale robuste est souhaitée ;
- éventuels graphiques spécifiques au turnover après accumulation de plusieurs runs comparables.

## 3. Architecture retenue

Aucune seconde comptabilité n'est créée.

`PaperAnalyticsReport` reste la source des métriques financières canoniques :

- equity initiale/finale ;
- P&L brut/net ;
- frais, spread, slippage, funding ;
- drawdown ;
- exposition ;
- nombre canonique de trades/exécutions.

`economic_history.py` ajoute uniquement une **projection descriptive en lecture seule** :

1. charge le lineage du PAPER run demandé ;
2. relit les cycles persistés du lineage ;
3. exclut économiquement les cycles `FAILED`, comme l'analytics canonique ;
4. agrège les fills appartenant à une même trajectoire de décision en une opération économique ;
5. utilise `Fill.realized_pnl` au lieu de recalculer le P&L réalisé ;
6. compare les positions canoniques avant/après pour qualifier l'effet économique ;
7. calcule uniquement les métriques descriptives de turnover à partir du notional et des coûts persistés.

Définition retenue pour `turnover_fraction` :

```text
total_notional / initial_equity
```

Définition retenue pour `total_costs` :

```text
fees + spread_cost + slippage_cost - funding_pnl
```

Le signe du funding suit `PaperAnalyticsReport` : un funding négatif augmente donc les coûts totaux, un funding positif les réduit.

## 4. Sémantique PERPETUAL

La position PERPETUAL est projetée en quantité signée :

```text
LONG  => quantité positive
SHORT => quantité négative
FLAT  => 0
```

L'effet économique vient de la transition avant/après, pas du verbe BUY/SELL seul.

Exemples :

```text
SHORT -2 -> SHORT -1 avec BUY  = REDUCE_SHORT
LONG  +2 -> LONG  +1 avec SELL = REDUCE_LONG
FLAT   0 -> SHORT -1 avec SELL = OPEN_SHORT
LONG  +1 -> SHORT -1           = FLIP_LONG_TO_SHORT
```

## 5. API

Nouveaux endpoints sur le routeur analytics existant :

```text
GET /api/v1/economic-history?paper_run_id=<uuid>
GET /api/v1/economic-history/export?paper_run_id=<uuid>
```

La réponse contient :

- résumé économique ;
- lineage de runs ;
- opérations économiques ;
- résumés des cycles pour conserver HOLD/REJECT/FAILED consultables ;
- version de calcul et digest de la source analytics.

L'export JSON contient la même projection et aucun secret.

## 6. Cockpit

La page `Historique` :

- charge Sessions, Campaigns et PAPER runs existants ;
- associe les runs aux Sessions via `Session.strategy_id == Campaign.strategy_id` ;
- ne présente que les têtes de lineage comme runs économiques sélectionnables ;
- affiche résumé, coûts, turnover et opérations ;
- filtre les opérations par BUY/SELL, SPOT/PERPETUAL et marché ;
- conserve un audit récent Agent → Risk → PAPER pour HOLD/REJECT ;
- ne recalcule aucun P&L ou état de position.

## 7. Invariants préservés

- PAPER uniquement ;
- SPOT + PERPETUAL linéaire ;
- aucun changement du prompt stratégique ;
- aucun changement `aggressiveness-map-v3` ;
- aucun changement Risk Engine ;
- aucun changement Broker/coûts/cadence ;
- aucune sortie LLM vers Kraken ;
- aucune migration SQL ;
- aucune donnée de `trades_9h_analysis.json` ajoutée au repository.

## 8. Validation

Test ajouté : `backend/tests/test_economic_history.py` couvre :

- projection SPOT d'ouverture ;
- BUY PERPETUAL réduisant un SHORT, sans hypothèse BUY=LONG ;
- P&L réalisé lu depuis les fills ;
- coûts d'exécution + funding ;
- notional, turnover et fills/heure ;
- décisions HOLD/REJECT distinctes des opérations ;
- rotation entre marchés.

Validations réellement exécutées dans l'environnement de préparation du patch :

- `python -m py_compile` sur les quatre fichiers Python créés/modifiés : OK ;
- parsing TypeScript/TSX via TypeScript `transpileModule` : OK ;
- harness d'exécution isolé de la projection économique, incluant `BUY` réduisant un SHORT : OK ;
- contrôle whitespace équivalent `git diff --check` sur le contenu du ZIP : OK ;
- recherche de motifs de secrets évidents dans les fichiers livrés : aucun résultat.

Validation locale finale exécutée sur le checkout complet après application du correctif :

- `pytest tests/test_economic_history.py tests/test_analytics.py tests/test_derivatives_analytics.py tests/test_multi_market_persistence.py -q` : `11/11` passés ;
- `pytest -q` : suite backend complète passée à `100 %`, sans échec ;
- `pnpm test` : `39/39` passés ;
- `pnpm lint` : passé ;
- `pnpm typecheck` : passé ;
- warnings Starlette/AnyIO de dépréciation et warnings Node `MODULE_TYPELESS_PACKAGE_JSON` : non bloquants, hors périmètre.


## 9. Correctif après validation locale

La première validation locale du patch a révélé :

- un échec backend dans `test_economic_history_projects_costs_turnover_and_perpetual_effects` : les payloads JSON persistés étaient relus avec `model_validate(...)` alors que les modèles de domaine sont stricts ;
- quatre erreurs ESLint `react-hooks/set-state-in-effect` introduites dans `history-panel.tsx` ;
- une cinquième erreur identique préexistante dans `llm-audit-panel.tsx`, hors fonctionnalité Historique mais bloquant `pnpm lint` global ;
- `pnpm test` : `39/39` passés ;
- `pnpm typecheck` : passé.

Correctif préparé :

- `economic_history.py` relit désormais `Fill` et `PortfolioState` via `model_validate_json(json.dumps(payload))`, comme l'analytics canonique ;
- le chargement du détail d'un cycle est déclenché depuis l'action utilisateur, sans `setState` synchrone dans un effet ;
- la sélection du run devient dérivée (`effectiveRunId`) au lieu d'être synchronisée par un effet ;
- les états de chargement/filtres sont modifiés depuis les handlers utilisateur ou les callbacks asynchrones ;
- `llm-audit-panel.tsx` reçoit un correctif lint-only : chargement initial direct dans l'effet, tandis que le refresh manuel conserve son handler dédié.

Ce correctif ne change aucune règle de trading, aucun calcul financier canonique ni aucun contrat Agent/Risk/Broker. Les suites complètes ont été relancées localement après extraction du ZIP correctif et sont toutes passées. Le correctif est donc validé sur le checkout complet.
