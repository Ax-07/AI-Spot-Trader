# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub resynchronisé avant Batch 14 : `655b66b639c4e9c1803cef3920c9a96e7dd16055` (`docs: record Batch 13 integration`).
- HEAD fonctionnel Batch 13 : `1747beb5efd1fe9763bc9b2d23f3a115575daaec` (`feat: add versioned aggressiveness experiments`).
- Batch 13 : **intégré** après validation locale complète, commit, push et working tree propre confirmés.
- Batch 14 : **patch préparé localement, non intégré** ; aucune modification GitHub n'a été effectuée.

## État intégré confirmé

- Backend PAPER autonome : Kraken public, Agent Luna/Sol via le même provider, Risk Engine déterministe, Paper Broker et boucle séquentielle.
- Seul Risk produit `ExecutionIntent` ; HOLD/REJECT restent des issues métier auditées ; les erreurs techniques restent distinctes.
- Journal durable PostgreSQL SQLAlchemy/Alembic, API REST `/api/v1` et cockpit Next.js/shadcn intégrés.
- Analytics PAPER déterministes : P&L brut/net, coûts, drawdown, exposition, trades, séries par cycle et daily UTC, sous `paper-analytics-v1`.
- Agressivité `1..10` figée par `aggressiveness-map-v1`, limitée à la stratégie Agent ; prompt courant `agent-strategy-v2`.
- `paper-experiment-v1` reste le protocole intégré de comparaison d'agressivité.

## Patch Batch 14 préparé

- `paper-experiment-v2` réserve explicitement l'axe `LLM_MODEL` sans casser `paper-experiment-v1`.
- Identité durable : `experiment_digest` par run + `experiment_group_digest` commun aux runs contrôlés.
- Répétitions appariées : `replicate_index` / `replicate_count` ; toutes les répétitions déclarées doivent être présentes pour Luna et Sol.
- Dataset strict : `source_digest` obligatoire en v2 ; prompt, agressivité, univers, RiskPolicy, coûts PAPER, fenêtre et version analytics doivent rester identiques.
- `compare_model_runs(...)` réutilise les `PaperAnalyticsReport` Batch 12, sans formule parallèle, score magique ni sélection automatique d'un gagnant.
- Persistance inchangée : l'`ExperimentManifest` enrichi reste dans `AgentInput` JSON/JSONB ; aucune migration.
- Aucun changement API/frontend, aucun LIVE.

## Validation de préparation Batch 14

- tests ciblés `backend/tests/test_experiments.py` dans un arbre local reconstruit : **34 passés** ;
- `py_compile` des fichiers Python modifiés : **réussi** ;
- contrôle manuel lignes >100 sur les fichiers modifiés : aucun écart après correction ;
- Ruff : **non exécuté**, outil absent de l'environnement de préparation ;
- mypy : **non exécuté**, outil absent de l'environnement de préparation ;
- `pytest backend` complet et `git diff --check` sur un checkout réel : **restent à exécuter localement**.

## Limites conservées

- Pas d'exactly-once global entre ledger PAPER mémoire et commit PostgreSQL ; recovery/réconciliation différés.
- Le digest du manifeste reproduit l'identité du protocole/configuration, **pas** une décision LLM bit-à-bit déterministe.
- Le patch rend obligatoire l'identité d'un dataset figé pour la comparaison modèle stricte, mais n'ajoute pas de moteur de replay historique.
- Les répétitions sont conservées et comparées factuellement ; aucune agrégation statistique ou conclusion automatique « meilleur modèle » n'est inventée.
- Capital PAPER, devise de référence produit, cadence, univers initial et valeurs de coûts/Risk restent injectés ; aucun défaut produit n'est inventé.

## Prochaine étape

Valider le Batch 14 sur le checkout local complet (`pytest backend`, Ruff, mypy, `git diff --check`), puis seulement commit/push et confirmer un working tree propre avant de marquer le batch intégré.
