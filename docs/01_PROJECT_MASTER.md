# 01 — Project Master

## 1. Rôle

Ce document est la spécification fonctionnelle et architecturale principale d'**AI Spot Trader**. Depuis le Batch 16, le projet couvre **SPOT + Kraken Derivatives**, sans changer le principe d'un agent stratégique unique ni l'autorité finale du Risk Engine.

Référence fonctionnelle intégrée Batch 16.3 : GitHub `main` au commit `520b016eb501f1a208bcb6d0e90eb1df947e1d0b` (`test: add controlled perpetual paper smoke harness`), poussé le 21 septembre 2026 après validation locale et smokes PERPETUAL PAPER contrôlés.

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

L'ajout Derivatives, l'isolation des runs et le harness 16.3 ne créent ni second agent, ni second runner, ni voie parallèle d'exécution.

Le harness 16.3 est un outil de validation explicite. Il injecte des décisions déterministes au niveau de la frontière stratégique afin de tester les composants aval. Il n'est pas appelé par la composition normale et ne constitue pas une stratégie de production.

## 4. Contrats de domaine

### Marché

`MarketState` porte explicitement `market_type = SPOT | PERPETUAL | FUTURE`, les champs historiques `symbol`, `last_price`, `context`, et un `DerivativeMarketContext` optionnel pour les dérivés.

`DerivativeMarketContext` contient l'instrument normalisé, mark, index optionnel, funding rate optionnel et timestamp d'observation.

`DerivativeInstrument` expose notamment : symbole canonique/venue, type de marché, famille `LINEAR|INVERSE`, underlying/quote, contract size, tick size, taille minimale, limite de position éventuelle, taux de marge initiale/maintenance, levier public dérivé et funding interval.

### Portefeuille

`PortfolioState` conserve `balances`, positions SPOT et `derivative_positions` séparées.

Une `DerivativePosition` est one-way par symbole et porte : `LONG|SHORT`, quantité, prix moyen, mark, contract size, notionnel, P&L réalisé/non réalisé, levier, marge utilisée, maintenance margin, funding cumulé, prix de liquidation estimé et mode de marge.

Le ledger PAPER reste actuellement **process-local**. Un redémarrage backend recrée le portefeuille au capital initial et ne peut donc pas reprendre honnêtement un run précédent.

### Agent

Le schéma de sortie LLM reste simple : `action = BUY | SELL | HOLD`, `symbol`, `proposed_quantity?`, `rationale?`.

Le provider applicatif copie `market_type` depuis le `MarketState` dans `DecisionCandidate`. Le LLM ne choisit jamais le type de marché ni le levier. Le prompt stratégique est versionné `agent-strategy-v3`.

Le `paper_run_id` est une identité d'audit/exécution et n'est pas ajouté au contrat stratégique LLM : il n'influence pas la décision de marché.

### Risk / execution

`DecisionCandidate` et `ExecutionIntent` portent `market_type` avec défaut SPOT pour compatibilité historique. En dérivés, l'intent ajoute `leverage` et `reduce_only`, produits par Risk.

`Fill` conserve les champs historiques et ajoute de manière rétrocompatible les métadonnées dérivés : contract size, reduce-only, realized P&L, margin delta et funding payment.

## 5. Kraken

La séparation provider reste claire :

- Spot : API publique historique `api.kraken.com` + WebSocket Spot ;
- Derivatives : REST public `https://futures.kraken.com/derivatives/api/v3`.

Le client Derivatives n'expose aucun endpoint privé. Les instruments sont découverts via l'API publique et normalisés en `BASE/QUOTE`, avec alias `XBT -> BTC`.

### `contractValueTradePrecision`

Le parser traite `contractValueTradePrecision` comme un exposant décimal entier signé :

```text
min_order_quantity = 10 ^ (-contractValueTradePrecision)
```

Une valeur `4` donne `0.0001`. Une valeur `-3` donne `1000`.

## 6. PAPER Derivatives

Les ouvertures/augmentations passent par Risk, calculent notionnel et marge initiale, bloquent marge + frais puis recalculent prix moyen, mark, unrealized P&L, maintenance margin et liquidation price.

Une action opposée devient `reduce_only`. La quantité autorisée ne peut pas dépasser la position existante. La marge est libérée au prorata, le P&L est réalisé et le funding correspondant est transféré au cash.

Le market source dérivés marque le ledger avant le snapshot portefeuille du cycle. Le funding perpetual est accumulé en fonction du notional marqué et du temps écoulé. Un funding positif débite un LONG et crédite un SHORT dans le modèle PAPER.

## 7. Risk Engine

Les règles SPOT existantes restent inchangées. Pour les dérivés, Risk ajoute : cohérence `market_type`, contrat exécutable `PERPETUAL + LINEAR`, quantité minimale/max instrument, `ISOLATED` uniquement, levier configuré <= plafond Risk <= limite instrument, max order notional, max derivative position notional, max total derivative exposure, marge disponible, buffer maintenance/liquidation, réduction/fermeture et interdiction du retournement accidentel.

Le Batch 16.3 a confirmé en smoke réel que la fermeture opposée surdimensionnée est réduite à la quantité détenue avec `MODIFY / DERIVATIVE_REDUCE_ONLY_LIMIT`, sans retournement de position.

## 8. Persistance des runs PAPER

### Définition

Un run PAPER est une expérience durable associée à une initialisation cohérente du ledger PAPER. Il possède :

- `paper_run_id` UUID ;
- `started_at` ;
- `ended_at` optionnel ;
- `market_type` ;
- `symbol`.

La table canonique est `paper_runs`.

### Rattachement des données

`audit_cycles.paper_run_id` est la FK de rattachement. Les sous-objets du journal restent normalisés :

```text
paper_runs
    |
    +--> audit_cycles
            |
            +--> audit_decisions
            +--> audit_risk_assessments
            +--> audit_execution_intents
                    |
                    +--> audit_fills
```

### Cycle de vie

- le run est créé au démarrage de la composition backend PAPER ;
- le lifecycle est persisté avant d'accepter les cycles ;
- `engine stop/start` dans le même processus conserve le run ;
- arrêt backend propre : le moteur s'arrête puis `ended_at` est persisté ;
- un run fermé refuse de nouveaux cycles ;
- crash : `ended_at` peut rester `NULL` ;
- redémarrage backend : nouveau `paper_run_id`, car le ledger mémoire est réinitialisé.

Aucune rotation à chaud n'est autorisée tant que le ledger ne sait pas être reset/repris durablement.

### Migration / legacy

La migration `0002_paper_runs` crée `paper_runs` et ajoute `audit_cycles.paper_run_id` nullable.

Les anciennes lignes restent **NULL**. Aucun backfill en pseudo-run historique n'est autorisé.

## 9. Analytics / API

Les analytics PAPER valorisent exposition SPOT, exposition dérivés notionnelle, marge isolée, unrealized/realized P&L, funding, equity et drawdown combinés.

Depuis le Batch 16.2, le replay est run-scoped : equity initiale/finale, drawdown, trade/hold counts, coûts, exposition et P&L sont calculés uniquement sur les cycles portant exactement le même `paper_run_id`.

API de run :

```text
GET /api/v1/paper-runs
GET /api/v1/paper-runs/current
GET /api/v1/paper-runs/{paper_run_id}
GET /api/v1/analytics?paper_run_id={paper_run_id}
```

Les endpoints audit `cycles`, `decisions`, `risk-assessments`, `executions`, `errors/latest` et `market/latest` supportent une sélection explicite par run.

Le Batch 16.3 a confirmé sur deux smokes distincts que les analytics et cycles peuvent être relus séparément sans mélange.

## 10. Configuration

SPOT reste le défaut (`PAPER_MARKET_TYPE=SPOT`). Pour PERPETUAL : `PAPER_MARKET_TYPE=PERPETUAL`, `PAPER_DERIVATIVE_LEVERAGE` (défaut sécurité 1), `PAPER_DERIVATIVE_MARGIN_MODE=ISOLATED`, `RISK_MAX_DERIVATIVE_LEVERAGE` (défaut 1), caps explicites de position/exposition et buffer liquidation configurable. `FUTURE` reste rejeté par la composition exécutable actuelle.

Le `paper_run_id` n'est pas un paramètre opérateur : il est généré par le backend afin d'éviter les collisions/reprises manuelles ambiguës.

## 11. Validation et intégration

### Batch 16.1 intégré

Le smoke réel Batch 16.1 sur `BTC/USD / PF_XBTUSD` a terminé `COMPLETED`, Agent `HOLD`, Risk `ALLOW / HOLD_NO_EXECUTION`.

### Batch 16.2 intégré

L'isolation durable multi-runs est intégrée au commit `003bbadd7ae2f8288ccde049433832046f066957`. La migration PostgreSQL `0002_paper_runs` a été appliquée et Alembic confirme `0002_paper_runs (head)`.

### Batch 16.3 intégré

Commit fonctionnel : `520b016eb501f1a208bcb6d0e90eb1df947e1d0b`.

Validation locale :

```text
pytest          : suite complète OK, 2 warnings externes FastAPI/Starlette
ruff check .    : All checks passed
mypy .          : Success: no issues found in 109 source files
git diff --check: aucune erreur
```

Smokes réels contrôlés :

```text
LONG  : 9523ec8c-7dd1-4706-bf07-47ef9669d56b
SHORT : b75f6e86-4724-41de-8d63-e8132d212530
```

Les deux runs ont validé ouverture, mark/HOLD, funding observé, réduction `reduce_only`, fermeture complète sans reversal, P&L/marge/coûts PAPER et audit durable. `verify-isolation` a retourné `isolation_verified=true`.

Ces décisions étaient déterministes et réservées au harness : elles ne valident pas encore la qualité stratégique de Luna. Elles valident le chemin d'exécution aval.

## 12. Prochaine expérimentation

Le prochain jalon est un premier run avec **GPT-5.6 Luna réel en PERPETUAL PAPER**, sans décision forcée. Le Risk Engine conserve l'autorité finale et un `HOLD` naturel reste un résultat valide.

## 13. LIVE

LIVE reste hors périmètre. Il nécessitera un batch séparé : auth/permissions, adaptateur privé Kraken, réconciliation, idempotence, recovery, garde-fous opérateur, clés sans retrait et activation explicite.
