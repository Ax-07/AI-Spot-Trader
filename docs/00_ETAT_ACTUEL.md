# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` vérifié au lancement du Batch 19.12 : `5c92958414ce4fb52865dedfb17b808232fdc91c` (`fix: restore session risk profile from persisted configuration`).
- La référence précédente de ce document (`47e12798f54c3686b59faf339315ff39d9191b44`) était obsolète au lancement du batch.

## État intégré avant Batch 19.12

- un seul Agent IA stratégique ; pipeline Risk déterministe ;
- versions actuelles en PAPER ; aucune sortie LLM directe vers Broker/Kraken ;
- Session comme façade UX principale ;
- Trading Style `SCALP` / `SWING`, contexte multi-timeframes et gestion stratégique des positions intégrés ;
- erreurs LLM techniques fail-closed : aucun `ExecutionIntent` après un échec Agent/Market Selection ;
- avant 19.12, tous les HTTP 429 OpenAI étaient toutefois ramenés à `LLMRateLimitError` et le retry pré-décision était limité à 2 tentatives (0,5 s puis arrêt).

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Patch proposé — Batch 19.12

- parsing sûr de `error.type` / `error.code` OpenAI sans conserver le message provider ;
- distinction rate limit transitoire / quota-crédit-usage-spend non retryable ;
- prise en compte de `Retry-After` numérique valide ; sinon backoff exponentiel borné ;
- 3 tentatives maximum pour les erreurs transitoires ;
- compatibilité avec `TradingCycleTimeouts.agent_seconds` préservée : le retry reste à l'intérieur de l'appel Agent déjà borné par le cycle ;
- cockpit : libellés explicites pour rate limit temporaire, quota/spend, timeout et autre erreur fournisseur ;
- aucun fallback HOLD, aucune règle de trading ajoutée, aucun changement LIVE.

Détails : `docs/23_BATCH_19_12_OPENAI_RATE_LIMIT_HANDLING.md`.

## Validation

Tests exécutés par ChatGPT sur le patch isolé : voir note Batch 19.12 et livraison. Le backend/frontend complets restent à valider sur le clone opérateur après extraction.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer l'état intégré GitHub, les éventuelles modifications locales fournies par l'opérateur et tout patch proposé non encore intégré.
