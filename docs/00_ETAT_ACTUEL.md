# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD fonctionnel Batch 15 : `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6` (`feat: add operator agent chat`).
- Référence précédente : Batch 14 fonctionnel `dc60033f60bf5d98a68e6131a9320e575d46cc8d`, documentation Batch 14 `b2c74672744639f86c38e873f25d56c77f899c76`.
- Le commit fonctionnel Batch 15 a été poussé sur `origin/main` le 21 septembre 2026.

## État intégré confirmé

- Backend PAPER autonome : Kraken public -> Agent Luna/Sol -> Risk déterministe -> Paper Broker.
- Seul Risk produit `ExecutionIntent`; HOLD/REJECT restent audités; erreurs techniques distinctes.
- Journal PostgreSQL, API REST, cockpit Next.js et analytics `paper-analytics-v1` intégrés.
- `aggressiveness-map-v1`, prompt `agent-strategy-v2`, `paper-experiment-v1/v2` et comparaison Luna/Sol appariée intégrés.
- Chat opérateur V1 intégré : même `LLMModel` Luna/Sol, provider conversationnel séparé, REST, historique mémoire borné, contexte canonique en lecture seule.
- Le chat ne rejoint jamais `AgentInput`, Risk, Broker, Kraken privé ou `ExecutionIntent`; aucune instruction conversationnelle ne modifie la stratégie future.
- Pour un cycle historique, le chat s'ancre sur l'`AgentInput` persisté exact et sépare explicitement l'état courant afin d'éviter le look-ahead.
- Le panneau Chat reste indépendant du lifecycle moteur ; fermer ou recharger le frontend ne stoppe pas le moteur backend.

## Validation Batch 15

Validation locale confirmée le 21 septembre 2026 :

- `pytest backend` : **277 tests passés**, 2 warnings de dépréciation externes ;
- Ruff : **All checks passed** ;
- mypy : **89 fichiers sans erreur** ;
- `pnpm lint` : **réussi** ;
- `pnpm typecheck` : **réussi** ;
- `pnpm build` : **réussi** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push fonctionnel confirmé : `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6`.

Le premier passage de `pnpm lint` a détecté une unique erreur `react-hooks/set-state-in-effect` dans `use-chat.ts`; le correctif a été appliqué puis lint, typecheck et build ont tous réussi avant le commit fonctionnel.

## Limites conservées

- Historique chat non durable : un redémarrage backend perd les sessions V1.
- Redaction de secrets best-effort : le chat ne doit jamais servir à transmettre des secrets.
- Pas de mutation de stratégie via conversation ; un futur mécanisme opérateur devra être explicite, audité, versionné et appliqué à partir d'un cycle identifié.
- Pas d'exactly-once global entre ledger PAPER mémoire et commit PostgreSQL ; recovery/réconciliation restent différés.
- Aucun LIVE, aucune API Kraken privée, aucune modification du protocole expérimental.

## Prochaine étape

Finaliser le commit documentaire Batch 15, puis lancer les premiers essais PAPER réels. La préparation LIVE reste séparée et correspond au Batch 16 éventuel.
