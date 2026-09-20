# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD fonctionnel Batch 09 audité le 20 septembre 2026 : `c53d04f14bcda82359d11c2e14fc1eb601ed14e0`
- Commit : `feat: add durable audit persistence`
- Batch 09 — Persistance et journal d'audit : **intégré fonctionnellement sur `main`**.
- Le push `4af32bb..c53d04f` a été confirmé et `git status --short` était vide après intégration fonctionnelle.

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

## Limite de reprise

Le journal durable ne garantit pas encore un exactly-once global entre la mutation du ledger PAPER mémoire et le commit PostgreSQL. Reconstruction du ledger, réconciliation après crash et stratégie de recovery restent à traiter explicitement.

## Prochaine étape

**Batch 10 — API FastAPI de contrôle** : exposition de l'état moteur, portefeuille, décisions, Risk, historique et contrôles autorisés, sans donner au frontend l'autorité sur la logique de trading.

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
