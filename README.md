# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **SPOT + Kraken Derivatives** pilotée par **un agent IA unique**. L'agent conserve la décision stratégique (`BUY`, `SELL`, `HOLD`) tandis qu'un **Risk Engine déterministe** garde l'autorité finale avant toute exécution.

> **État Batch 16.3 : commit fonctionnel intégré sur GitHub `main` : `520b016eb501f1a208bcb6d0e90eb1df947e1d0b` (`test: add controlled perpetual paper smoke harness`). Validation locale et smokes réels contrôlés confirmés le 21 septembre 2026 : suite `pytest` complète OK, Ruff OK, mypy OK sur 109 fichiers, `git diff --check` OK, smoke LONG OK, smoke SHORT OK et isolation durable des deux `paper_run_id` vérifiée.**

## Principes

- Exchange initial : **Kraken**.
- Marchés : **SPOT** et **Kraken Derivatives**.
- SPOT : aucun short, aucun levier ; `SELL` reste impossible sans actif détenu.
- Derivatives : `LONG`/`SHORT` autorisés uniquement dans le domaine dérivés.
- Exécution PAPER dérivés : perpetuals linéaires en marge ISOLATED ; futures datés, contrats inverses et CROSS restent fail-closed.
- Levier dérivés : déterministe, borné par Risk, jamais choisi par le LLM.
- Aucune sortie LLM ne déclenche directement un ordre Kraken.
- Frais, spread, slippage et funding sont pris en compte.
- Toutes les décisions, y compris `HOLD` et `REJECT`, restent auditables.
- Aucun secret dans prompts, logs ou fichiers versionnés.
- Le frontend reste un cockpit ; fermer le frontend n'arrête jamais le moteur backend.

Principe central : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Architecture canonique

```text
Kraken public Spot / Derivatives
        |
        v
   MarketState
        |
        +----------------+
        |                |
        v                v
 PortfolioState      AgentInput
        |                |
        +-------> Agent IA
                    BUY/SELL/HOLD
                         |
                         v
                    Risk Engine
             ALLOW / MODIFY / REJECT
                         |
             HOLD/REJECT|tradable
                         v
                  ExecutionIntent
                         |
                         v
                   Paper Broker
                         |
                  Fill(s) + ledger
                         |
                         v
                TradingCycleResult
                         |
                         v
              PostgreSQL audit/analytics
                         |
                         v
                 FastAPI / cockpit
```

Le chemin reste unique : `Market -> Agent -> DecisionCandidate -> Risk -> ExecutionIntent -> Paper Broker`.

## Sémantique SPOT / PERPETUAL

### SPOT

`BUY` augmente un actif détenu. `SELL` ne peut vendre qu'une quantité réellement disponible. Aucun short, levier ou marge n'est appliqué au SPOT.

### PERPETUAL

Le même vocabulaire stratégique `BUY / SELL / HOLD` est conservé :

- `BUY` sans position ouvre/augmente un `LONG` ;
- `SELL` sans position ouvre/augmente un `SHORT` ;
- une action opposée réduit/ferme la position existante ;
- le Risk Engine produit `reduce_only` lorsque nécessaire ;
- un dépassement ne peut pas retourner silencieusement une position `LONG` en `SHORT` ou inversement.

Le portefeuille dérivés conserve notamment : side, quantité, prix moyen, mark, notionnel, P&L réalisé/non réalisé, levier, marge utilisée, maintenance margin, funding cumulé et prix de liquidation estimé.

## Kraken Derivatives public

Le client public Derivatives est séparé de Kraken Spot et utilise :

```text
https://futures.kraken.com/derivatives/api/v3
```

Les symboles Kraken sont normalisés vers `BASE/QUOTE` (`XBT -> BTC`). Aucune clé privée Kraken n'est utilisée.

`contractValueTradePrecision` est traité comme un exposant décimal entier signé : `min_order_quantity = 10^-precision`. Exemples validés : `PF_XBTUSD = 4 -> 0.0001` et plusieurs contrats à `-3 -> 1000`.

## Risk Engine dérivés

Risk contrôle notamment : type de marché/contrat, quantité minimale/limite instrument, levier, marge disponible, notionnel maximal par ordre/position, exposition dérivés totale, buffer de liquidation, `reduce_only` et interdiction de retournement accidentel.

## Funding et marge PAPER

Le market source dérivés marque les positions avant l'`AgentInput`. Le funding perpetual est accumulé dans le ledger à partir du taux public normalisé, du mark et du temps écoulé. Les ouvertures bloquent une marge isolée ; les réductions/fermetures libèrent la marge au prorata en réalisant P&L et funding.

## Isolation durable des runs PAPER — Batch 16.2

Le Batch 16.2 ajoute une identité durable d'expérience PAPER afin que plusieurs essais puissent partager la même base PostgreSQL sans mélanger leurs analytics.

```text
paper_runs
    |
    +--> audit_cycles.paper_run_id
            |
            +--> decisions / risk / intents / fills
```

Principes :

- un run est créé au démarrage du backend PAPER ;
- `engine stop/start` dans le même processus conserve le même run ;
- un arrêt backend propre clôt le run avec `ended_at` ;
- un redémarrage backend crée un nouveau run, car le ledger PAPER reste en mémoire et repart du capital initial ;
- les anciens cycles antérieurs à la migration restent `paper_run_id = NULL` et ne sont jamais regroupés artificiellement ;
- les analytics d'un run filtrent strictement sur son identifiant ;
- SPOT et PERPETUAL utilisent le même mécanisme.

API associée :

```text
GET /api/v1/paper-runs
GET /api/v1/paper-runs/current
GET /api/v1/paper-runs/{paper_run_id}
GET /api/v1/analytics?paper_run_id={paper_run_id}
```

Les endpoints audit acceptent aussi une sélection explicite `paper_run_id`. Dans la composition normale, le run courant reste le défaut ; aucune modification frontend n'est nécessaire pour continuer à afficher le run actif.

Aucun endpoint de rotation à chaud n'est ajouté : tant que le ledger ne dispose pas d'un reset/recovery durable, démarrer une nouvelle expérience signifie arrêter proprement puis redémarrer le backend.

## Batch 16.3 — Smokes PERPETUAL PAPER contrôlés

Le Batch 16.3 ajoute un outil CLI explicitement réservé à la validation technique. Il réutilise les composants canoniques (`TradingCycleRunner`, Risk Engine, Paper Broker, ledger, audit PostgreSQL et lifecycle de run) mais injecte des décisions déterministes de smoke. **Ces décisions ne sont pas des décisions Luna/Sol et ne modifient pas la stratégie normale de l'application.**

Smokes réels contrôlés sur `BTC/USD / PF_XBTUSD`, levier `1x`, marge `ISOLATED` :

- LONG : ouverture `BUY 0.0002`, mark/HOLD, réduction `SELL 0.0001`, fermeture oversize demandée `SELL 0.0002` ramenée par Risk à `0.0001` avec `MODIFY / DERIVATIVE_REDUCE_ONLY_LIMIT` ;
- SHORT : ouverture `SELL 0.0002`, mark/HOLD, réduction `BUY 0.0001`, fermeture oversize demandée `BUY 0.0002` ramenée par Risk à `0.0001` avec le même garde-fou ;
- `reduce_only=true` confirmé sur les réductions/fermetures ;
- funding réellement observé sur position ouverte dans les deux sens ;
- P&L réalisé/non réalisé, marge et coûts PAPER effectivement valorisés ;
- exposition finale nulle et aucune inversion accidentelle de position ;
- chaque smoke produit 4 cycles `COMPLETED`, 3 exécutions et 0 cycle `FAILED` ;
- deux runs distincts, fermés proprement avec `ended_at`, ont été relus séparément avec `isolation_verified=true`.

Runs de preuve locaux :

```text
LONG  : 9523ec8c-7dd1-4706-bf07-47ef9669d56b
SHORT : b75f6e86-4724-41de-8d63-e8132d212530
```

Les fichiers JSON complets de preuve restent hors Git.

## Configuration

SPOT reste le défaut. Pour activer le chemin PERPETUAL PAPER :

```text
AI_SPOT_TRADER_PAPER_MARKET_TYPE=PERPETUAL
AI_SPOT_TRADER_PAPER_DERIVATIVE_LEVERAGE=1
AI_SPOT_TRADER_PAPER_DERIVATIVE_MARGIN_MODE=ISOLATED
AI_SPOT_TRADER_RISK_MAX_DERIVATIVE_LEVERAGE=1
AI_SPOT_TRADER_RISK_MAX_DERIVATIVE_POSITION_NOTIONAL=<positive-decimal>
AI_SPOT_TRADER_RISK_MAX_TOTAL_DERIVATIVE_EXPOSURE=<positive-decimal>
AI_SPOT_TRADER_RISK_DERIVATIVE_LIQUIDATION_BUFFER_RATIO=1.10
```

Le `paper_run_id` est généré par le backend ; il n'est pas configuré manuellement.

## Migration Batch 16.2

Avec `AI_SPOT_TRADER_DATABASE_URL` défini dans l'environnement ou dans `backend/.env` :

```text
alembic upgrade head
```

La migration `0002_paper_runs` crée `paper_runs` puis ajoute une FK nullable sur `audit_cycles`. Aucun backfill historique n'est effectué.

## Validation

Validation locale du commit fonctionnel Batch 16.3 confirmée le 21 septembre 2026 :

```text
pytest               : suite complète OK, 2 warnings externes FastAPI/Starlette
ruff check .          : All checks passed
mypy .                : Success: no issues found in 109 source files
git diff --check      : aucune erreur
git status --short    : propre après commit/push fonctionnel
```

Smokes réels contrôlés : LONG OK, SHORT OK, funding observé, `reduce_only` OK, fermeture sans reversal, analytics run-scoped cohérentes et isolation entre les deux `paper_run_id` vérifiée.

## Prochaine étape

Le chemin d'exécution PERPETUAL PAPER est maintenant validé techniquement au-delà de `HOLD`. La prochaine étape est un **premier run expérimental avec l'Agent réel GPT-5.6 Luna en PERPETUAL PAPER**, sans décision forcée. Un `HOLD` naturel restera un résultat valide.

## Sécurité / LIVE

- PAPER uniquement.
- Aucun endpoint Kraken Derivatives privé d'ordre n'est implémenté.
- Aucun secret Kraken requis.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- Le passage au LIVE restera une décision séparée et explicite.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et développement. Il ne constitue pas un conseil financier et ne garantit aucun rendement. La cible expérimentale de +4 %/jour reste une métrique de recherche, jamais une promesse.
