# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **SPOT + Kraken Derivatives** pilotée par **un agent IA unique**. L'agent conserve la décision stratégique (`BUY`, `SELL`, `HOLD`) tandis qu'un **Risk Engine déterministe** garde l'autorité finale avant toute exécution.

> **État Batch 16.2 : intégré sur GitHub `main` au commit fonctionnel `003bbadd7ae2f8288ccde049433832046f066957` (`feat: add durable paper run isolation`). Validation locale complète confirmée le 21 septembre 2026 : migration PostgreSQL `0002_paper_runs` appliquée, **344 tests passés**, Ruff OK, mypy OK sur 106 fichiers et `git diff --check` sans erreur (warnings LF→CRLF Windows uniquement).

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

Validation locale confirmée le 21 septembre 2026 :

```text
alembic upgrade head : 0001_audit_journal -> 0002_paper_runs
alembic current      : 0002_paper_runs (head)
pytest               : 344 passed, 2 warnings externes
ruff check .          : All checks passed
mypy .                : Success: no issues found in 106 source files
git diff --check      : aucune erreur, warnings LF -> CRLF uniquement
```

Pendant la préparation de la livraison, ChatGPT a également exécuté `compileall`, des contrôles de métadonnées SQLAlchemy et des vérifications de structure du ZIP. La validation PostgreSQL et la suite complète ci-dessus ont été exécutées localement par l'opérateur avant intégration.

Le smoke Batch 16.1 `BTC/USD / PF_XBTUSD` a validé un cycle `HOLD`, mais pas encore une exécution réelle PAPER LONG/SHORT, un fill dérivé, funding sur position, P&L de position ou `reduce_only`.

## Sécurité / LIVE

- PAPER uniquement.
- Aucun endpoint Kraken Derivatives privé d'ordre n'est implémenté.
- Aucun secret Kraken requis.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- Le passage au LIVE restera une décision séparée et explicite.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et développement. Il ne constitue pas un conseil financier et ne garantit aucun rendement. La cible expérimentale de +4 %/jour reste une métrique de recherche, jamais une promesse.
