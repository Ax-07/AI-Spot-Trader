# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub resynchronisé avant Batch 12 : `cab3920d4d924d785b0a54c06b51066ccc949eb0` (`docs: record Batch 11 integration`).
- Commit fonctionnel Batch 11 : `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7` (`feat: add frontend paper cockpit`).
- Batch 11 : **intégré**.
- Batch 12 : **patch préparé, non intégré** tant que validation locale + commit/push ne sont pas confirmés.

## État intégré confirmé

- Backend PAPER autonome : Kraken public, Agent Luna/Sol, Risk Engine déterministe, Paper Broker et boucle séquentielle.
- Seul Risk produit `ExecutionIntent` ; HOLD/REJECT restent des issues métier auditées ; les erreurs techniques restent distinctes.
- Journal durable PostgreSQL SQLAlchemy/Alembic, API REST `/api/v1` et cockpit Next.js/shadcn intégrés.
- Aucun LIVE, Kraken privé, stratégie frontend ou WebSocket.

## Patch Batch 12 préparé

- reducer analytics pur et déterministe, sans nouvelle migration ;
- source : faits durables existants, jamais l'état mémoire courant ;
- P&L net = equity marquée - equity initiale ; P&L brut = net + frais + spread + slippage ;
- drawdown sur equity nette ; exposition mark-to-market ; trades = exécutions fillées ;
- HOLD/REJECT/MODIFY/FAILED comptés explicitement ;
- jours en UTC et prix historique limité au `MarketState` du cycle, sans look-ahead ;
- reproductibilité par version de calcul + digest des `result_digest` durables ;
- `GET /api/v1/analytics` et panneau analytics cockpit ;
- incohérences de continuité/valorisation refusées explicitement.

Test réellement exécuté pendant la préparation : `backend/tests/test_analytics.py` : **6 réussis**. Les validations complètes backend/frontend restent à exécuter localement.

## Limites conservées

- Pas d'exactly-once global entre ledger PAPER mémoire et commit PostgreSQL ; recovery/réconciliation différés.
- Pas encore de manifeste expérimental complet permettant de rejouer une décision LLM avec modèle/prompt/RiskPolicy/config identiques ; Batches 13/14.
- Capital PAPER, devise de référence produit et valeurs de coûts/Risk restent injectés, sans défaut produit inventé.

## Prochaine étape

Valider localement le patch Batch 12 (backend + frontend + smoke runtime), puis commit/push. Ne marquer Batch 12 intégré qu'après confirmation.
