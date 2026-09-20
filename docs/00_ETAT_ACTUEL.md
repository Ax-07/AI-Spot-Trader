# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` resynchronisé avant Batch 13 : `bc1b06ad25a2aa0ba7781d50c9e642dc113850ad` (`docs: record Batch 12 integration`).
- HEAD fonctionnel Batch 12 : `3f39999736b6fc3800ecfd36ddee0253c734d25d` (`feat: add reproducible paper analytics`).
- Écart confirmé : `bc1b06ad...` est un commit documentaire uniquement, 1 commit au-dessus du HEAD fonctionnel Batch 12.
- Batch 12 : **intégré**.
- Batch 13 : **patch préparé, non intégré** tant que validation locale complète + commit/push ne sont pas confirmés.

## État intégré confirmé

- Backend PAPER autonome : Kraken public, Agent Luna/Sol, Risk Engine déterministe, Paper Broker et boucle séquentielle.
- Seul Risk produit `ExecutionIntent` ; HOLD/REJECT restent des issues métier auditées ; les erreurs techniques restent distinctes.
- Journal durable PostgreSQL SQLAlchemy/Alembic, API REST `/api/v1` et cockpit Next.js/shadcn intégrés.
- Analytics PAPER déterministes dérivés des faits durables : P&L brut/net, coûts, drawdown, exposition, trades, séries par cycle et daily UTC.
- Reproductibilité des métriques par `paper-analytics-v1` + digest des `result_digest`, sans look-ahead.
- Aucun LIVE, Kraken privé, stratégie frontend ou WebSocket.

## Patch Batch 13 préparé

- mapping discret canonique `1..10` sous `aggressiveness-map-v1` ;
- chaque niveau porte une posture et une instruction stratégique explicite ;
- `AgentInput` accepte un `AggressivenessContext` versionné et un `ExperimentManifest` optionnel ;
- prompt Agent proposé : `agent-strategy-v2` ;
- manifeste `paper-experiment-v1` : niveau/mapping, modèle, prompt, univers, snapshot `RiskPolicy`, coûts PAPER, source/dataset, fenêtre éventuelle, version analytics et digest SHA-256 ;
- `TradingCycleRunner` persiste automatiquement ce contexte via l'`AgentInput` déjà journalisé ;
- aucune migration : le payload `AgentInput` existant suffit ;
- comparaison factuelle réutilisant directement les `PaperAnalyticsReport` Batch 12, sans formule divergente ni ranking ;
- aucune modification API/frontend ;
- aucune agressivité n'entre dans le Risk Engine ni ne peut produire directement un intent.

## Validation réellement exécutée pendant préparation

- tests ciblés `backend/tests/test_experiments.py` + `backend/tests/test_agent_provider.py` sur sous-ensemble reconstruit depuis `main` : **47 réussis** ;
- `python -m py_compile` sur tous les fichiers Python du patch : **réussi** ;
- smoke `TradingCycleRunner` niveau 10 + manifeste : **REJECT Risk confirmé, Broker non appelé** ;
- Ruff : **non exécuté**, binaire absent de l'environnement ;
- suite backend complète / mypy / `git diff --check` : **à exécuter localement** dans le repository complet ;
- frontend : non modifié, donc aucune validation frontend spécifique ajoutée au patch.

## Limites conservées

- Pas d'exactly-once global entre ledger PAPER mémoire et commit PostgreSQL ; recovery/réconciliation différés.
- Le digest du manifeste reproduit l'identité du protocole/configuration, **pas** la décision LLM : Luna/Sol peuvent rester non parfaitement déterministes à entrées identiques.
- Un `source_digest` est recommandé pour un dataset figé ; avec un flux live non figé, l'identité du protocole reste reproductible mais les faits réalisés diffèrent naturellement.
- Capital PAPER, devise de référence produit, cadence, univers initial et valeurs de coûts/Risk restent injectés ; Batch 13 ne leur invente aucun défaut produit.

## Prochaine étape

Valider le patch Batch 13 dans le repository local complet, corriger si nécessaire, puis commit/push. Ne marquer Batch 13 intégré qu'après confirmation du push et working tree propre.
