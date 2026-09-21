# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **SPOT + Kraken Derivatives** pilotée par **un agent IA unique**. L'agent conserve la décision stratégique (`BUY`, `SELL`, `HOLD`) tandis qu'un **Risk Engine déterministe** garde l'autorité finale avant toute exécution.

> **État Batch 16 :** le support Kraken Derivatives est ajouté en **PAPER uniquement** sous forme de patch local proposé. Le HEAD GitHub vérifié avant le batch est `c2e21f9b5b47086ea8dad336cc80ff15afa27ba0`. Aucun ordre LIVE/private Kraken Derivatives n'est implémenté.

## Principes

- Exchange initial : **Kraken**.
- Marchés : **SPOT** et **Kraken Derivatives**.
- SPOT : aucun short, aucun levier ; `SELL` reste impossible sans actif détenu.
- Derivatives : `LONG`/`SHORT` autorisés uniquement dans le domaine dérivés.
- Batch 16 exécute en PAPER uniquement les **perpetuals linéaires** ; futures datés et contrats inverses sont représentés/découverts mais refusés à l'exécution.
- Marge PAPER dérivés : **ISOLATED** ; `CROSS` reste représenté mais non exécuté.
- Levier PAPER dérivés : **1x par défaut**, borné par une limite Risk interne et les métadonnées instrument disponibles.
- L'agent ne choisit pas et ne modifie pas le levier.
- Aucune sortie LLM ne déclenche directement un ordre Kraken.
- Frais, spread, slippage et funding sont pris en compte.
- Toutes les décisions, y compris `HOLD`, restent auditables.
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

## Sémantique SPOT / Derivatives

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

Le Batch 16 ajoute un client public séparé de Kraken Spot, basé sur :

```text
https://futures.kraken.com/derivatives/api/v3
```

Il découvre les instruments et lit les tickers publics. Les symboles Kraken sont normalisés vers le format canonique `BASE/QUOTE` (`XBT -> BTC`). Aucune clé privée Kraken n'est utilisée.

## Risk Engine dérivés

En plus des garde-fous historiques SPOT, Risk contrôle :

- type de marché et type de contrat ;
- quantité minimale et limite instrument ;
- levier demandé/configuré et plafond interne ;
- marge disponible ;
- notionnel maximal par ordre ;
- notionnel maximal par position ;
- exposition dérivés totale ;
- buffer de liquidation ;
- `reduce_only` et interdiction de retournement accidentel.

Les contrats inverses, `CROSS` et futures datés sont fail-closed dans ce premier batch PAPER.

## Funding et marge PAPER

Le market source dérivés marque les positions avant la création du `PortfolioState` du cycle. Le funding perpetual est accumulé dans le ledger à partir du taux public normalisé, du mark et du temps écoulé. Les ouvertures bloquent une marge isolée et les réductions/fermetures libèrent la marge au prorata en réalisant P&L et funding.

Le modèle reste volontairement conservateur : il ne prétend pas reproduire l'intégralité du moteur de liquidation privé de Kraken.

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

Les paramètres SPOT historiques (`PAPER_SYMBOL`, capital, cadence, coûts, max order notional, whitelist, etc.) restent utilisés.

## API / analytics

Les contrats API ajoutent `market_type`, le contexte dérivés et `derivative_positions` sans retirer les champs SPOT historiques. Les analytics PAPER valorisent désormais l'exposition dérivés, la marge, le P&L non réalisé et le funding tout en conservant le replay historique SPOT.

## Validation Batch 16

Exécuté par ChatGPT sur la reconstruction locale du patch :

```text
pytest ciblé Batch 16 : 23 passed
python -m compileall   : OK
```

`ruff` et `mypy` ne sont pas installés dans l'environnement de reconstruction ChatGPT et doivent être exécutés dans le dépôt local utilisateur. La suite complète du repo doit également être rejouée localement avant intégration.

## Sécurité / LIVE

- PAPER uniquement.
- Aucun endpoint Kraken Derivatives privé d'ordre n'est implémenté.
- Aucun secret Kraken requis.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- Le passage au LIVE restera une décision séparée et explicite.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et développement. Il ne constitue pas un conseil financier et ne garantit aucun rendement. La cible expérimentale de +4 %/jour reste une métrique de recherche, jamais une promesse.
