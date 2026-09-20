# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD fonctionnel Batch 13 confirmé : `1747beb5efd1fe9763bc9b2d23f3a115575daaec` (`feat: add versioned aggressiveness experiments`).
- Batch 12 : **intégré** au commit fonctionnel `3f39999736b6fc3800ecfd36ddee0253c734d25d`.
- Batch 13 : **intégré** après validation locale complète, commit, push et working tree propre confirmés.

## État intégré confirmé

- Backend PAPER autonome : Kraken public, Agent Luna/Sol, Risk Engine déterministe, Paper Broker et boucle séquentielle.
- Seul Risk produit `ExecutionIntent` ; HOLD/REJECT restent des issues métier auditées ; les erreurs techniques restent distinctes.
- Journal durable PostgreSQL SQLAlchemy/Alembic, API REST `/api/v1` et cockpit Next.js/shadcn intégrés.
- Analytics PAPER déterministes : P&L brut/net, coûts, drawdown, exposition, trades, séries par cycle et daily UTC, sous `paper-analytics-v1`.
- Agressivité `1..10` figée par le mapping discret `aggressiveness-map-v1`, limitée à la stratégie Agent et sans effet sur l'autorité Risk.
- Prompt Agent courant pour ce protocole : `agent-strategy-v2`.
- Manifeste expérimental `paper-experiment-v1` persistant niveau/mapping, modèle, prompt, univers, snapshot `RiskPolicy`, coûts PAPER, source/dataset, fenêtre éventuelle, version analytics et digest SHA-256.
- Comparaison d'agressivité réutilisant les `PaperAnalyticsReport` Batch 12 et refusant les runs dont les champs contrôlés hors agressivité diffèrent.
- Aucun changement API/frontend au Batch 13 ; aucun LIVE, Kraken privé ou WebSocket.

## Validation Batch 13

Validation locale confirmée le 21 septembre 2026 :

- Python : **3.13.14** ;
- `pytest backend` : **249 tests passés**, 2 warnings de dépréciation externes ;
- Ruff : **All checks passed** ;
- mypy : **81 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push confirmé : `1747beb5efd1fe9763bc9b2d23f3a115575daaec` ;
- working tree propre après push.

Validation de préparation également exécutée : 47 tests ciblés Batch 13, `py_compile` et smoke `TradingCycleRunner` niveau 10 confirmant REJECT Risk avec Broker non appelé.

## Limites conservées

- Pas d'exactly-once global entre ledger PAPER mémoire et commit PostgreSQL ; recovery/réconciliation différés.
- Le digest du manifeste reproduit l'identité du protocole/configuration, **pas** une décision LLM bit-à-bit déterministe.
- Pour isoler strictement l'agressivité, les runs doivent partager les mêmes faits sources ; un dataset figé avec `source_digest` identique reste préférable à des passages live successifs.
- Capital PAPER, devise de référence produit, cadence, univers initial et valeurs de coûts/Risk restent injectés ; aucun défaut produit n'est inventé.

## Prochaine étape

**Batch 14 — Comparaison Luna / Sol** : comparer les modèles sous protocole expérimental contrôlé, en conservant mêmes faits sources, prompt, RiskPolicy, coûts et paramètres hors modèle.
