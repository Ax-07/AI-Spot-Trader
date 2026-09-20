# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- Commit fonctionnel Batch 11 : `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7` (`feat: add frontend paper cockpit`).
- Batch 11 — Frontend cockpit : **intégré sur `main`**.
- Working tree local confirmé propre après push.

## État intégré confirmé

- Backend PAPER autonome : Kraken public, Agent Luna/Sol, Risk Engine déterministe, Paper Broker et boucle séquentielle.
- Seul Risk peut produire un `ExecutionIntent` ; HOLD/REJECT restent des issues métier auditées et les erreurs techniques restent distinctes.
- Persistance durable PostgreSQL via SQLAlchemy async + `asyncpg` + Alembic.
- API REST `/api/v1` pour lifecycle moteur, portefeuille, cycles, décisions, Risk, exécutions/fills, dernière erreur et dernier marché durable.
- Cockpit Next.js/shadcn consommant uniquement FastAPI via rewrite same-origin `/backend/*`.
- Polling d'affichage borné à 10 s, suspendu lorsque l'onglet est masqué ; aucun WebSocket ni moteur alternatif frontend.
- Aucun appel OpenAI/Kraken direct, aucune logique Risk, aucun LIVE dans le frontend.

## Validation Batch 11

Validation locale Windows confirmée le 20 septembre 2026 :

- `pnpm --dir frontend lint` : **réussi** ;
- `pnpm --dir frontend typecheck` : **réussi** ;
- `pnpm --dir frontend build` : **réussi**, Next.js 16.3.3, route `/` statique compilée ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- smoke test runtime : backend accessible, moteur non configuré, ressources vides/503 et backend hors ligne gérés proprement ;
- commit/push confirmé : `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7` ;
- working tree propre après push.

## Limite de reprise

Le journal durable ne garantit pas encore un exactly-once global entre mutation du ledger PAPER mémoire et commit PostgreSQL. Reconstruction du ledger, réconciliation après crash et stratégie de recovery restent différées.

## Prochaine étape

**Batch 12 — Analytics et expérimentation reproductible** : P&L brut/net, drawdown, frais, spread/slippage, exposition, trades et métriques quotidiennes/cumulées, sans modifier rétroactivement les décisions.

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
