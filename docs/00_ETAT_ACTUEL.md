# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD fonctionnel Batch 14 confirmé : `dc60033f60bf5d98a68e6131a9320e575d46cc8d` (`feat: add controlled Luna Sol experiments`).
- Batch 13 : **intégré** au commit fonctionnel `1747beb5efd1fe9763bc9b2d23f3a115575daaec`.
- Batch 14 : **intégré** après validation locale complète, commit, push et working tree propre confirmés.

## État intégré confirmé

- Backend PAPER autonome : Kraken public, Agent Luna/Sol via le même provider canonique, Risk Engine déterministe, Paper Broker et boucle séquentielle.
- Seul Risk produit `ExecutionIntent` ; HOLD/REJECT restent des issues métier auditées ; les erreurs techniques restent distinctes.
- Analytics PAPER `paper-analytics-v1` : P&L brut/net, coûts, drawdown, exposition, trades, HOLD/REJECT/MODIFY/FAILED, séries par cycle et daily UTC.
- Agressivité `1..10` figée par `aggressiveness-map-v1` ; prompt Agent courant `agent-strategy-v2`.
- `paper-experiment-v1` reste le protocole de comparaison d'agressivité.
- `paper-experiment-v2` compare Luna/Sol avec `LLM_MODEL` comme unique variable contrôlée, `experiment_group_digest`, `experiment_digest` et répétitions appariées.
- `source_digest` est obligatoire en v2 ; prompt, agressivité, univers, `RiskPolicy`, coûts PAPER, fenêtre, version analytics et nombre de répétitions restent contrôlés.
- `compare_model_runs(...)` réutilise les `PaperAnalyticsReport` Batch 12 sans score composite, ranking ni « meilleur modèle » automatique.
- Persistance inchangée via `AgentInput` JSON/JSONB ; aucune migration, aucun changement API/frontend, aucun LIVE.

## Validation Batch 14

Validation locale confirmée le 21 septembre 2026 :

- `pytest backend` : **266 tests passés**, 2 warnings de dépréciation externes ;
- Ruff : **All checks passed** ;
- mypy : **81 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push confirmé : `dc60033f60bf5d98a68e6131a9320e575d46cc8d` ;
- working tree propre après push.

Préparation ChatGPT également exécutée : 34 tests ciblés Batch 14 et `py_compile` des fichiers Python modifiés.

## Limites conservées

- Pas d'exactly-once global entre ledger PAPER mémoire et commit PostgreSQL ; recovery/réconciliation différés.
- Le digest du manifeste identifie le protocole/configuration, **pas** une décision LLM bit-à-bit déterministe.
- `paper-experiment-v2` exige l'identité d'un dataset figé mais n'ajoute pas de moteur de replay historique.
- Les répétitions sont conservées factuellement ; aucune agrégation statistique ou conclusion automatique « meilleur modèle » n'est inventée.
- Capital PAPER, devise de référence produit, cadence, univers initial et valeurs de coûts/Risk restent injectés ; aucun défaut produit n'est inventé.

## Prochaine étape

Définir le prochain batch avant implémentation. Le LIVE reste séparé et hors périmètre tant qu'aucune décision explicite ne l'ouvre.
