# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié au démarrage du Batch 10 : `328cdcea155905e2859e73ab3c46a195dc52047e` (`docs: record Batch 09 integration`).
- HEAD fonctionnel Batch 09 : `c53d04f14bcda82359d11c2e14fc1eb601ed14e0` (`feat: add durable audit persistence`).
- Batch 09 — Persistance et journal d'audit : **intégré fonctionnellement sur `main`**.
- Batch 10 — API FastAPI de contrôle/observation : **patch proposé, non intégré**.

## État backend intégré

- Données publiques Kraken SPOT et `MarketState` déterministe, sans look-ahead.
- `PaperPortfolioLedger` et `PaperBroker` avec frais, spread et slippage injectables.
- Agent Luna/Sol derrière `LLMProvider`, sortie limitée à BUY/SELL/HOLD + quantité stratégique.
- Risk Engine déterministe avec ALLOW/MODIFY/REJECT ; seul Risk crée l'`ExecutionIntent`.
- `TradingCycleRunner.run_cycle()` orchestre un cycle PAPER cohérent avec un unique `MarketState` partagé Agent/Risk/Broker.
- `TradingEngine` répète les cycles séquentiellement, sans chevauchement ni rattrapage concurrent.
- HOLD traverse Risk ; REJECT reste une issue métier normale ; erreurs techniques distinctes.
- Persistance durable via SQLAlchemy async + PostgreSQL + `asyncpg`, migrations Alembic.
- `AuditedTradingCycleRunner` persiste le `TradingCycleResult` sans dupliquer l'orchestration.
- Journal corrélé par `cycle_id` : décision, Risk, intent éventuel, fills, snapshots disponibles et erreurs techniques.
- Idempotence stricte par `cycle_id` + empreinte du résultat ; rollback transactionnel complet.
- PostgreSQL local reproductible via Docker Compose.
- Aucune API Kraken privée et aucun LIVE.

## Patch Batch 10 proposé

Le patch Batch 10 ajoute une façade FastAPI versionnée `/api/v1` sans créer de seconde logique de trading :

- état moteur et commandes lifecycle `start`/`stop` uniquement contre un `TradingEngine` canonique injecté ;
- aucune exécution automatique au démarrage FastAPI ;
- portefeuille PAPER courant via un lecteur injecté ;
- lecture durable des cycles, décisions, résultats Risk, intents/fills, dernière erreur et dernier état marché ;
- pagination `limit`/`offset`, ordre déterministe `asc`/`desc` et filtres utiles ;
- couche `SqlAlchemyCycleAuditQueryService` entre FastAPI et SQLAlchemy ;
- erreurs techniques exposées seulement sous forme sanitizée (`stage`, `error_type`, `timed_out`) ;
- DB non configurée ou indisponible représentée explicitement sans fuite de secret ;
- lifecycle DB possédé par FastAPI uniquement lorsqu'il est créé depuis `AI_SPOT_TRADER_DATABASE_URL` ;
- aucune migration supplémentaire ;
- aucun WebSocket dans ce batch : REST suffit tant qu'aucun bus d'événements canonique n'existe.

Le bootstrap produit (capital, paire, cadence) n'est pas inventé : sans moteur/portfolio injecté, les endpoints correspondants signalent qu'ils ne sont pas configurés.

## Validation finale connue du Batch 09

Validation locale Windows confirmée :

- `pytest backend` : **209 tests passés**, 2 warnings de dépréciation FastAPI/Starlette sans échec ;
- `ruff check backend` : **All checks passed** ;
- mypy : **Success: no issues found in 63 source files** ;
- `git diff --check` : aucune erreur ;
- commit/push fonctionnel confirmé sur `main` : `c53d04f`.

Validation PostgreSQL réelle confirmée :

- Docker Desktop actif ;
- `ai-spot-trader-postgres` : **healthy** ;
- image : `postgres:18.6-bookworm` ;
- `python -m alembic -c backend\alembic.ini upgrade head` : **OK** ;
- révision : `0001_audit_journal` ;
- tables : `audit_cycles`, `audit_decisions`, `audit_risk_assessments`, `audit_execution_intents`, `audit_fills`, `alembic_version`.

## Validation du patch Batch 10 dans l'environnement ChatGPT

Exécuté sur le patch reconstruit depuis `main` :

- tests FastAPI ciblés : **15 passés** ;
- `python -m compileall` sur les sources/tests concernés : **OK** ;
- génération/import des routes FastAPI : **OK**.

Non exécuté ici faute de dépendances/outils réseau dans l'environnement :

- test SQL `aiosqlite` du query service ;
- suite complète `pytest backend` ;
- Ruff ;
- mypy ;
- `git diff --check` sur un clone Git réel ;
- validation PostgreSQL réelle.

## Limite de reprise

Le journal durable ne garantit pas encore un exactly-once global entre la mutation du ledger PAPER mémoire et le commit PostgreSQL. Reconstruction du ledger, réconciliation après crash et stratégie de recovery restent à traiter explicitement. Le Batch 10 ne prétend pas résoudre cette limite.

## Prochaine étape

**Valider localement le patch Batch 10, puis seulement après validation/commit/push mettre cette mémoire à jour comme intégrée.**

## Points encore à décider

- Capital PAPER initial et devise de référence produit.
- Univers initial de paires Kraken.
- Valeur produit de cadence.
- Valeurs produit des limites Risk.
- Mapping exact de l'agressivité 1–10.
- Valeurs de référence fee/spread/slippage PAPER.
- Politique de rétention.
- Frontière de journée et données P&L.
- Reconstruction/reprise du ledger et réconciliation après panne.
- Besoin et protocole exact d'un WebSocket lorsque le cockpit temps réel le justifiera.
