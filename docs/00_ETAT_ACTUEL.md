# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD fonctionnel Batch 12 confirmé : `3f39999736b6fc3800ecfd36ddee0253c734d25d` (`feat: add reproducible paper analytics`).
- Batch 11 : **intégré** au commit `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7`.
- Batch 12 : **intégré** après validation locale et push confirmé.
- Working tree local confirmé propre après push du commit Batch 12.

## État intégré confirmé

- Backend PAPER autonome : Kraken public, Agent Luna/Sol, Risk Engine déterministe, Paper Broker et boucle séquentielle.
- Seul Risk produit `ExecutionIntent` ; HOLD/REJECT restent des issues métier auditées ; les erreurs techniques restent distinctes.
- Journal durable PostgreSQL SQLAlchemy/Alembic, API REST `/api/v1` et cockpit Next.js/shadcn intégrés.
- Analytics PAPER déterministes dérivés des faits durables : P&L brut/net, coûts, drawdown, exposition, trades, séries par cycle et daily UTC.
- `GET /api/v1/analytics` et panneau analytics cockpit intégrés.
- Reproductibilité des métriques par `paper-analytics-v1` + digest des `result_digest`, sans look-ahead.
- Aucun LIVE, Kraken privé, stratégie frontend ou WebSocket.

## Validation Batch 12

Validation locale confirmée le 20 septembre 2026 :

- `pytest backend` : **231 tests passés**, 2 warnings de dépréciation externes ;
- Ruff : **All checks passed** ;
- mypy : **76 fichiers sans erreur** ;
- `pnpm --dir frontend lint` : **réussi** ;
- `pnpm --dir frontend typecheck` : **réussi** ;
- `pnpm --dir frontend build` : **réussi**, Next.js 16.3.3 ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push confirmé : `3f39999736b6fc3800ecfd36ddee0253c734d25d` ;
- working tree propre après push.

Aucun smoke test PostgreSQL/runtime Batch 12 distinct n'a été fourni ; il n'est pas revendiqué.

## Limites conservées

- Pas d'exactly-once global entre ledger PAPER mémoire et commit PostgreSQL ; recovery/réconciliation différés.
- Pas encore de manifeste expérimental complet permettant de rejouer une décision LLM avec modèle/prompt/RiskPolicy/config identiques ; Batches 13/14.
- Capital PAPER, devise de référence produit et valeurs de coûts/Risk restent injectés, sans défaut produit inventé.

## Prochaine étape

**Batch 13 — Expérimentation agressivité 1–10** : figer un mapping versionné et comparer les niveaux sous protocole identique, sans jamais contourner Risk.
