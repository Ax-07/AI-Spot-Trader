# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` vérifié après intégration du Batch 19.12 : `f8397d207be67309db083e49e113253fe88b3624` (`fix: handle OpenAI rate limits and quota errors robustly`).
- Parent du Batch 19.12 : `5c92958414ce4fb52865dedfb17b808232fdc91c` (`fix: restore session risk profile from persisted configuration`).

## État intégré

- un seul Agent IA stratégique ; Risk Engine déterministe avec autorité finale ;
- versions actuelles en PAPER ; aucune sortie LLM directe vers Broker/Kraken ;
- Session comme façade UX principale ;
- Trading Style `SCALP` / `SWING`, contexte multi-timeframes et gestion stratégique des positions intégrés ;
- erreurs LLM techniques fail-closed : aucun `ExecutionIntent` après un échec Agent/Market Selection ;
- Batch 19.12 intégré : les HTTP 429 OpenAI distinguent limitation temporaire et quota/crédit/usage/spend non retryable ; `Retry-After` numérique valide est pris en compte, sinon le retry utilise un backoff borné avec 3 tentatives maximum ;
- le cockpit distingue explicitement rate limit temporaire, quota/spend, timeout et autre erreur fournisseur ; aucun échec LLM n'est converti artificiellement en HOLD.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Détails 19.12 : `docs/23_BATCH_19_12_OPENAI_RATE_LIMIT_HANDLING.md`.

## Validation post-intégration 19.12

Validation locale opérateur communiquée : backend complet `665 passed, 2 warnings`, frontend `37 passed`, ESLint OK, TypeScript OK, build Next.js OK et `git diff --check` sans erreur. Working tree annoncé propre après commit/push.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer l'état intégré GitHub, les éventuelles modifications locales fournies par l'opérateur et tout patch proposé non encore intégré.
