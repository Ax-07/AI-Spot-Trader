# 01 — Project Master

## 1. Rôle

Ce document est la spécification fonctionnelle et architecturale principale d'**AI Spot Trader**. Depuis le Batch 16, le projet couvre **SPOT + Kraken Derivatives**, sans changer le principe d'un agent stratégique unique ni l'autorité finale du Risk Engine.

Référence GitHub intégrée actuelle : `main` au commit `74c168180716e484ea2ec76f461620f595cb1b91` (`fix: finalize Batch 16.1 perpetual paper smoke`).

## 2. Vision et invariants

### Invariants globaux

- un seul agent IA stratégique ;
- Kraken comme exchange initial ;
- premières versions exclusivement en PAPER ;
- actions stratégiques : `BUY`, `SELL`, `HOLD` ;
- GPT-5.6 Luna pour les premiers essais, Sol sélectionnable par configuration ;
- Risk Engine déterministe avec autorité finale ;
- seul Risk peut produire un `ExecutionIntent` ;
- aucune sortie LLM ne déclenche directement un Broker ou un ordre Kraken ;
- frais, spread, slippage et, pour les perpetuals, funding pris en compte ;
- toutes les décisions, y compris HOLD/REJECT, sont auditables ;
- aucun secret dans prompts, logs ou fichiers versionnés ;
- aucun look-ahead ;
- backend = application de trading ; frontend = cockpit uniquement ;
- un seul cycle à la fois ;
- cible expérimentale +4 %/jour = métrique de recherche, jamais une garantie.

### Invariants SPOT

- aucun short ;
- aucun levier/margin ;
- impossible de vendre un actif non détenu ;
- `AssetPosition` reste le modèle de détention SPOT.

### Invariants Derivatives

- `LONG` et `SHORT` sont autorisés uniquement pour les instruments dérivés ;
- `BUY` peut ouvrir/augmenter LONG ou réduire SHORT ;
- `SELL` peut ouvrir/augmenter SHORT ou réduire LONG ;
- le levier est déterministe/configuré, jamais choisi par le LLM ;
- Risk impose le plafond de levier, les caps de notionnel/exposition et la marge ;
- `reduce_only` appartient au domaine d'exécution/Risk ;
- aucun retournement accidentel de position par dépassement ;
- funding, marge, maintenance margin et risque de liquidation font partie du modèle PAPER ;
- Batch 16 exécute uniquement des **perpetuals linéaires en marge ISOLATED** ;
- contrats inverses, futures datés et CROSS sont fail-closed à l'exécution PAPER.

## 3. Architecture

Le flux de confiance canonique reste unique :

```text
Kraken public data
      |
      v
 MarketState -----------------+
                              |
 PortfolioState --------------+--> AgentInput --> Agent
                                                   |
                                            BUY/SELL/HOLD
                                                   |
                                                   v
                                              Risk Engine
                                       ALLOW/MODIFY/REJECT
                                                   |
                                                   v
                                           ExecutionIntent
                                                   |
                                                   v
                                             Paper Broker
                                                   |
                                             Fill + ledger
                                                   |
                                                   v
                                          TradingCycleResult
                                                   |
                                      audit PostgreSQL / analytics
                                                   |
                                             FastAPI / cockpit
```

L'ajout Derivatives ne crée ni second agent, ni second runner, ni voie parallèle d'exécution.

## 4. Contrats de domaine

### Marché

`MarketState` porte explicitement `market_type = SPOT | PERPETUAL | FUTURE`, les champs historiques `symbol`, `last_price`, `context`, et un `DerivativeMarketContext` optionnel pour les dérivés.

`DerivativeMarketContext` contient l'instrument normalisé, mark, index optionnel, funding rate optionnel et timestamp d'observation.

`DerivativeInstrument` expose notamment : symbole canonique/venue, type de marché, famille `LINEAR|INVERSE`, underlying/quote, contract size, tick size, taille minimale, limite de position éventuelle, taux de marge initiale/maintenance, levier public dérivé et funding interval.

### Portefeuille

`PortfolioState` conserve `balances`, positions SPOT et `derivative_positions` séparées.

Une `DerivativePosition` est one-way par symbole et porte : `LONG|SHORT`, quantité, prix moyen, mark, contract size, notionnel, P&L réalisé/non réalisé, levier, marge utilisée, maintenance margin, funding cumulé, prix de liquidation estimé et mode de marge.

### Agent

Le schéma de sortie LLM reste simple : `action = BUY | SELL | HOLD`, `symbol`, `proposed_quantity?`, `rationale?`.

Le provider applicatif copie `market_type` depuis le `MarketState` dans `DecisionCandidate`. Le LLM ne choisit jamais le type de marché ni le levier. Le prompt stratégique est versionné `agent-strategy-v3`.

### Risk / execution

`DecisionCandidate` et `ExecutionIntent` portent `market_type` avec défaut SPOT pour compatibilité historique. En dérivés, l'intent ajoute `leverage` et `reduce_only`, produits par Risk.

`Fill` conserve les champs historiques et ajoute de manière rétrocompatible les métadonnées dérivés : contract size, reduce-only, realized P&L, margin delta et funding payment.

## 5. Kraken

La séparation provider reste claire :

- Spot : API publique historique `api.kraken.com` + WebSocket Spot ;
- Derivatives : REST public `https://futures.kraken.com/derivatives/api/v3`.

Le client Derivatives n'expose aucun endpoint privé. Les instruments sont découverts via l'API publique et normalisés en `BASE/QUOTE`, avec alias `XBT -> BTC`.

### `contractValueTradePrecision`

Le parser traite `contractValueTradePrecision` comme un exposant décimal entier signé pour dériver la quantité minimale :

```text
min_order_quantity = 10 ^ (-contractValueTradePrecision)
```

Une valeur `4` donne `0.0001`. Une valeur `-3`, observée sur certains contrats Kraken comme `PF_PEPEUSD`, `PF_SHIBUSD` et `PF_BONKUSD`, donne `1000`.

Le Batch 16.1 corrige le rejet incorrect des valeurs négatives sans modifier le reste du chemin Derivatives.

## 6. PAPER Derivatives

Les ouvertures/augmentations passent par Risk, calculent notionnel et marge initiale, bloquent marge + frais puis recalculent prix moyen, mark, unrealized P&L, maintenance margin et liquidation price.

Une action opposée devient `reduce_only`. La quantité autorisée ne peut pas dépasser la position existante. La marge est libérée au prorata, le P&L est réalisé et le funding correspondant est transféré au cash.

Le market source dérivés marque le ledger avant le snapshot portefeuille du cycle. Le funding perpetual est accumulé en fonction du notional marqué et du temps écoulé. Un funding positif débite un LONG et crédite un SHORT dans le modèle PAPER.

Batch 16 modèle un prix de liquidation estimé et impose un buffer déterministe dans Risk sans prétendre reproduire l'intégralité du moteur privé Kraken.

## 7. Risk Engine

Les règles SPOT existantes restent inchangées. Pour les dérivés, Risk ajoute : cohérence `market_type`, contrat exécutable `PERPETUAL + LINEAR`, quantité minimale/max instrument, `ISOLATED` uniquement, levier configuré <= plafond Risk <= limite instrument, max order notional, max derivative position notional, max total derivative exposure, marge disponible, buffer maintenance/liquidation, réduction/fermeture et interdiction du retournement accidentel.

## 8. Analytics / API

Les réponses API portfolio et market restent rétrocompatibles en ajoutant des champs dérivés. Le journal durable existant stocke les payloads JSON sans migration spécifique Batch 16.

Les analytics PAPER valorisent exposition SPOT, exposition dérivés notionnelle, marge isolée, unrealized/realized P&L, funding, equity et drawdown combinés.

### Limite connue — isolation des runs PAPER

Les analytics calculent actuellement leurs métriques sur les cycles présents dans la base interrogée. Plusieurs expériences PAPER indépendantes écrites dans une même base peuvent donc être agrégées ensemble.

Il n'existe pas encore de `paper_run_id` durable propagé de la création d'un run jusqu'aux cycles, décisions, fills et requêtes analytics. Le smoke Batch 16.1 a utilisé une base PostgreSQL isolée pour garantir un jeu de données propre.

Cette dette est volontairement hors périmètre du Batch 16.1 et doit faire l'objet d'un batch séparé avant de considérer les analytics multi-runs comme correctement isolés.

## 9. Configuration

SPOT reste le défaut (`PAPER_MARKET_TYPE=SPOT`). Pour PERPETUAL : `PAPER_MARKET_TYPE=PERPETUAL`, `PAPER_DERIVATIVE_LEVERAGE` (défaut sécurité 1), `PAPER_DERIVATIVE_MARGIN_MODE=ISOLATED`, `RISK_MAX_DERIVATIVE_LEVERAGE` (défaut 1), caps explicites de position/exposition et buffer liquidation configurable. `FUTURE` est rejeté par la composition du Batch 16.

## 10. Validation et intégration

### Batch 16 intégré

Batch 16 est intégré sur `main` depuis le commit fonctionnel `06e3185c8a8c638263427842ab6591a2397810e0`.

### Batch 16.1 intégré et validé

Batch 16.1 est intégré sur `main` au commit `74c168180716e484ea2ec76f461620f595cb1b91` (`fix: finalize Batch 16.1 perpetual paper smoke`).

Validation locale confirmée le 21 septembre 2026 :

```text
pytest            : 339 passés
ruff check .       : OK
mypy .             : OK
git diff --check   : aucune erreur, warnings LF -> CRLF uniquement
```

Smoke réel Kraken PERPETUAL PAPER : `BTC/USD` / `PF_XBTUSD`, cycle `COMPLETED`, Agent `HOLD`, Risk `ALLOW` / `HOLD_NO_EXECUTION`.

Analytics `paper-analytics-v2` sur base PostgreSQL isolée : `initial_equity=1000`, `ending_equity=1000`, `trade_count=0`, `hold_count=1`.

Le smoke réel ne valide pas encore LONG/SHORT, fills dérivés, funding accumulé sur position, P&L de position ni `reduce_only`, puisque aucune exécution n'a eu lieu.

## 11. LIVE

LIVE reste hors périmètre. Il nécessitera un batch séparé : auth/permissions, adaptateur privé Kraken, réconciliation, idempotence, recovery, garde-fous opérateur, clés sans retrait et activation explicite.
