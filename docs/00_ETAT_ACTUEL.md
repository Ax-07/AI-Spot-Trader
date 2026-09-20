# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub / commit fonctionnel Batch 10 : `e6bcfd4dd345c934769b2f90fa7822232a80dd80`
- Commit : `feat: add paper control and observation api`
- Batch 10 — API FastAPI de contrôle/observation : **intégré sur `main`**.
- Working tree local confirmé propre après push.

## État backend intégré

- Kraken public SPOT et `MarketState` déterministe, sans look-ahead.
- `PaperPortfolioLedger` et `PaperBroker` avec frais, spread et slippage injectables.
- Agent Luna/Sol derrière `LLMProvider`, sortie limitée à BUY/SELL/HOLD + quantité stratégique.
- Risk Engine déterministe avec ALLOW/MODIFY/REJECT ; seul Risk crée l'`ExecutionIntent`.
- `TradingCycleRunner.run_cycle()` orchestre un cycle PAPER cohérent ; `TradingEngine` le répète séquentiellement.
- HOLD et REJECT restent des issues métier complètes ; erreurs techniques distinctes.
- Persistance durable PostgreSQL via SQLAlchemy async + `asyncpg` + Alembic.
- Journal corrélé par `cycle_id` avec décision, Risk, intent éventuel, fills, snapshots et erreurs sanitizées.
- API REST `/api/v1` pour état moteur, start/stop, portefeuille, cycles, décisions, Risk, exécutions/fills, dernière erreur et dernier marché durable.
- `CycleAuditReader` / `SqlAlchemyCycleAuditQueryService` séparent les routes FastAPI des modèles ORM.
- Aucun auto-start du moteur, aucune migration Batch 10, aucun WebSocket, aucune API Kraken privée et aucun LIVE.

## Validation finale Batch 10

Validation locale Windows confirmée le 20 septembre 2026 :

- `pytest backend` : **222 tests passés**, 2 warnings de dépréciation FastAPI/Starlette non bloquants ;
- `ruff check backend` : **All checks passed** ;
- mypy : **Success: no issues found in 70 source files** ;
- `git diff --check` : aucune erreur, uniquement warnings LF -> CRLF ;
- commit/push confirmé sur `main` : `e6bcfd4`.

## Limite de reprise

Le journal durable ne garantit pas encore un exactly-once global entre mutation du ledger PAPER mémoire et commit PostgreSQL. Reconstruction du ledger, réconciliation après crash et stratégie de recovery restent différées.

## Prochaine étape

**Batch 11 — Frontend cockpit** : construire le cockpit Next.js/shadcn comme client du backend existant, sans rendre le frontend propriétaire du moteur.

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
- Source d'événements et protocole exact d'un futur WebSocket.
