# 11 — Améliorations planifiées

> Référence de reprise des chantiers 19.x. Ce document distingue ce qui est **intégré**, ce qui est **implémenté dans le patch 19.2**, ce qui reste **planifié** et ce qui reste **à décider**.

## 1. Référence

```text
Repository              : Ax-07/AI-Spot-Trader
Branche                 : main
HEAD GitHub main audité : 01ca1e857947d969556481e5593c5712d137f5ad
Date Batch 19.2         : 2026-09-24
```

Le Batch 19.1 est intégré. Le patch 19.2 n'est pas déclaré intégré à GitHub avant validation/commit explicites de l'opérateur.

## 2. Invariants transverses

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement ;
- SPOT + PERPETUAL linéaire ;
- aucune sortie LLM ne déclenche directement Broker/Kraken ;
- Risk Engine déterministe = autorité finale ;
- IA = choix stratégique ;
- calculs, comptabilité, monitoring et statistiques = déterministes ;
- frontend jamais source de vérité trading ;
- aucun secret dans prompts/logs/docs/Git ;
- frais, spread, slippage et funding pris en compte sans double comptage ;
- HOLD auditable ;
- aucun look-ahead ni sélection rétrospective.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## 3. Cadences cibles

| Cadence | But | LLM |
| --- | --- | --- |
| Monitoring / mark-to-market | prix, marks, P&L, exposition, marge, liquidation, funding | non |
| Cycle stratégique | BUY / SELL / HOLD | oui, Agent unique |
| Discovery / watchlist | réévaluer les marchés intéressants | oui, même Agent |

Le monitoring 19.2 utilise par défaut une cadence de 5 s en SPOT et 15 s en PERPETUAL, avec 5 s de timeout et 30 s de staleness. Les cadences restent configurables séparément.

# 4. Comptabilité SPOT par position — INTÉGRÉE 19.1

Confirmé : coût économique moyen pondéré, coût restant frais BUY inclus, ventes partielles au prorata, P&L réalisé net, pas de double comptage spread/slippage/frais, recovery JSON et compatibilité `accounting_complete=false`.

# 5. Monitoring / mark-to-market — PATCH 19.2 IMPLÉMENTÉ

## Confirmé dans le patch

- source de mark SPOT : dernier ticker Kraken causal (`LAST_PRICE`) ;
- `mark_price`, `mark_observed_at`, `mark_source`, `market_value`, `unrealized_pnl`, `valuation_complete` ;
- P&L latent calculé uniquement côté backend avec `market_value - remaining_cost_basis` ;
- mark absent ou périmé => valeurs indisponibles ;
- position legacy avec coût inconnu => valeur de marché possible, P&L latent interdit ;
- agrégats portfolio : cash, coût restant, valeur SPOT, P&L réalisé/latent, equity, exposition ;
- monitor backend indépendant de l'Agent et du frontend ;
- source d'exécution SPOT poussant également le `MarketState` dans le ledger ;
- snapshot/recovery compatible sans migration SQL ;
- Agent et Risk reçoivent le `PortfolioState` enrichi sans calcul financier parallèle ;
- cockpit Positions branché sur les champs backend, `—` pour indisponible.

## Définition equity retenue

```text
equity = cash settlement
       + valeur SPOT
       + Σ(margin_used + unrealized_pnl + cumulative_funding) dérivés
```

Le réalisé n'est pas additionné une seconde fois à l'equity.

## Compatibilité historique

- les snapshots 19.1/legacy sans total réalisé global conservent `spot_realized_pnl_total=None` ;
- les marques restaurées sont soumises au seuil de fraîcheur courant ;
- aucun replay des fills n'est utilisé pour reconstituer un passé inconnu.

## À décider plus tard

- besoin éventuel d'un modèle durable séparé d'historique de positions fermées au-delà des fills/audits ;
- politique d'arrondi/quantification spécifique exchange si un besoin réel apparaît au-delà de `Decimal` ;
- extension éventuelle du monitor à une watchlist dynamique lorsque 19.4 existera.

# 6. Mode gestion lorsque l'exposition est saturée — PLANIFIÉ 19.3

Objectif : lorsque le backend sait qu'aucune nouvelle exposition ne peut être autorisée, éviter la recherche IA inutile d'ouverture et concentrer le même Agent sur l'existant.

Cible :

```text
Portfolio mark-to-market + limites Risk
-> CapacityEvaluator déterministe
   -> NORMAL
   -> MANAGEMENT
```

En MANAGEMENT : univers stratégique = positions ouvertes ; HOLD/réduction/clôture restent possibles ; aucune augmentation d'exposition ne doit contourner Risk.

À décider : nom des états, granularité de la capacité et métriques exactes de tokens économisés.

# 7. Explicabilité des décisions IA — PLANIFIÉ 19.5

Le `rationale` existe déjà. Le chantier porte sur son exposition produit :

- Accueil : dernière décision + « Pourquoi l'IA ? » ;
- Positions : décisions/trades corrélés ;
- Historique : lecture synthétique avant JSON ;
- chart : rationale associé aux markers ;
- Risk toujours affiché séparément.

# 8. Discovery automatique et watchlist — PLANIFIÉ 19.4

Deux étapes distinctes :

1. backend déterministe → univers techniquement admissible ;
2. même Agent stratégique → watchlist.

Invariant :

```text
univers surveillé = watchlist IA actuelle + toutes les positions ouvertes
```

Le mode manuel reste nécessaire pour les tests reproductibles.

À décider : taille de watchlist, persistence/versionnement, lien avec Campaign/paper_run et recovery.

# 9. Nouvel espace Marchés — PLANIFIÉ 19.6B

Navigation cible :

```text
Accueil | Marchés | Positions | Historique | Réglages
```

La vue Marchés affichera en onglets les marchés surveillés. Le frontend n'a aucune autorité sur la watchlist ou le moteur.

# 10. Charts chandeliers — PLANIFIÉ 19.6B

Renderer privilégié : **TradingView Lightweight Charts** avec données Kraken normalisées par le backend.

À afficher lorsque disponible : OHLC, prix courant, volume, prix moyen, mark/liquidation PERPETUAL et événements BUY/SELL/réduction/clôture.

# 11. Historique candles + WebSocket — PLANIFIÉ 19.6A

Pipeline cible :

```text
Kraken REST -> historique initial
Kraken WebSocket -> updates temps réel
backend -> normalisation/cache/persistence éventuelle
WebSocket cockpit -> frontend
```

Le backend doit gérer déduplication, candle courante mutable, reconnect/backfill et limitations de profondeur sans inventer de données.

# 12. Ordre global

| Ordre | Batch | Résultat principal | Statut |
| ---: | --- | --- | --- |
| 1 | 19.1 — Comptabilité SPOT | coût moyen, coût restant, P&L réalisé, recovery | intégré |
| 2 | 19.2 — Monitoring | P&L latent et état vivant sans LLM | patch implémenté |
| 3 | 19.3 — Mode gestion | évite recherche IA inutile à exposition saturée | planifié |
| 4 | 19.4 — Discovery/watchlist | univers dynamique versionné | planifié |
| 5 | 19.5 — Explicabilité | rationale visible vs Risk | planifié |
| 6 | 19.6A — Candles/streaming | données chart canoniques | planifié |
| 7 | 19.6B — Marchés/charts | rendu, onglets, markers | planifié |

## 13. Validation attendue des prochains batches

### 19.3

- aucune recherche d'ouverture lorsque capacité saturée ;
- réduction/clôture/HOLD ;
- retour au mode normal ;
- métriques IA.

### 19.4

- eligibility sans ranking ;
- watchlist Agent bornée ;
- versionnement/recovery ;
- invariant watchlist + positions ouvertes ;
- mode manuel reproductible.

### 19.5

- API/audit ;
- lint/typecheck/build frontend ;
- rationale et Risk clairement séparés.

### 19.6A

- parsing OHLC, déduplication, reconnect/backfill ;
- persistence/cache ;
- WebSocket cockpit ;
- staleness/lifecycle.

### 19.6B

- lint/typecheck/build ;
- light/dark ;
- changement onglet/timeframe ;
- cleanup subscriptions ;
- markers cohérents avec les fills.
