# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité : `f29c51545cd63763ea9fefbfd37d441e52850609` (`docs: record Batch 10 integration`).
- Commit fonctionnel Batch 10 : `e6bcfd4dd345c934769b2f90fa7822232a80dd80` (`feat: add paper control and observation api`).
- Batch 10 — API FastAPI de contrôle/observation : **intégré sur `main`**.
- Batch 11 — Frontend cockpit : **patch préparé pour validation locale, non intégré**.

## État intégré confirmé

- Kraken public SPOT et `MarketState` déterministe, sans look-ahead.
- `PaperPortfolioLedger` et `PaperBroker` avec frais, spread et slippage injectables.
- Agent Luna/Sol derrière `LLMProvider`, sortie limitée à BUY/SELL/HOLD + quantité stratégique.
- Risk Engine déterministe avec ALLOW/MODIFY/REJECT ; seul Risk crée l'`ExecutionIntent`.
- `TradingCycleRunner.run_cycle()` orchestre un cycle PAPER cohérent ; `TradingEngine` le répète séquentiellement.
- HOLD et REJECT restent des issues métier complètes ; erreurs techniques distinctes.
- Persistance durable PostgreSQL via SQLAlchemy async + `asyncpg` + Alembic.
- API REST `/api/v1` pour état moteur, start/stop, portefeuille, cycles, décisions, Risk, exécutions/fills, dernière erreur et dernier marché durable.
- Aucun auto-start du moteur, aucun WebSocket, aucune API Kraken privée et aucun LIVE.

## Batch 11 proposé

- Next.js consomme uniquement FastAPI via un rewrite same-origin `/backend/*` vers `AI_SPOT_TRADER_BACKEND_URL`.
- Polling d'affichage borné à 10 s et suspendu lorsque l'onglet n'est pas visible.
- Cockpit : disponibilité backend/audit, lifecycle moteur, portefeuille PAPER, marché durable, cycles, décisions, Risk, exécutions/fills et dernière erreur.
- États `loading`, vide, non configuré/503, 404 et erreur réseau explicites.
- Aucun calcul de stratégie, aucun appel OpenAI/Kraken, aucun `ExecutionIntent` et aucun moteur local dans le frontend.

## Dernière validation intégrée

Batch 10, Windows, 20 septembre 2026 :

- `pytest backend` : **222 tests passés**, 2 warnings de dépréciation non bloquants ;
- `ruff check backend` : **All checks passed** ;
- mypy : **70 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement.

## À valider avant intégration du Batch 11

- `pnpm --dir frontend lint`
- `pnpm --dir frontend typecheck`
- `pnpm --dir frontend build`
- `git diff --check`
- comportement réel avec backend configuré, non configuré et audit store vide/indisponible.

## Limite de reprise

Le journal durable ne garantit pas encore un exactly-once global entre mutation du ledger PAPER mémoire et commit PostgreSQL. Reconstruction du ledger, réconciliation après crash et stratégie de recovery restent différées.

## Prochaine étape

Valider localement le Batch 11, puis commit/push. Le Batch 12 — analytics et expérimentation reproductible — reste futur tant que cette intégration n'est pas confirmée.

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
