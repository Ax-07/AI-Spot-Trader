# Batch 19.12 — Gestion robuste des erreurs OpenAI 429 / Rate Limit

## Référence

Audit initial réalisé sur GitHub `main` au HEAD `5c92958414ce4fb52865dedfb17b808232fdc91c`.

Batch intégré sur GitHub `main` au commit `f8397d207be67309db083e49e113253fe88b3624` (`fix: handle OpenAI rate limits and quota errors robustly`). Ce commit est un descendant direct du HEAD audité et constitue le HEAD `main` vérifié lors de la synchronisation documentaire post-batch.

## Audit

### Confirmé

- `OpenAIResponsesClient` convertissait tout HTTP 429 en `LLMRateLimitError` sans lire le payload d'erreur ni `Retry-After`.
- `LLM_PRE_DECISION_RETRY_POLICY` utilisait 2 tentatives, backoff 0,5 s plafonné à 1 s.
- le retry ne s'applique qu'aux `LLMTransientError`.
- `TradingCycleRunner` borne l'appel Agent par `TradingCycleTimeouts.agent_seconds` et transforme l'échec en `TradingCycleFailure` ; Market Selection échoue avant Risk/Broker.
- le cockpit affichait directement `error_type`, d'où `MARKET_SELECTION · LLMRateLimitError`.

### Obsolète après intégration

- considérer tous les 429 comme un simple débit temporaire ;
- limiter le retry pré-décision à 2 tentatives avec un backoff maximal de 1 s ;
- présenter le Batch 19.12 comme un patch proposé ou non validé ;
- utiliser `5c92958414ce4fb52865dedfb17b808232fdc91c` comme HEAD intégré courant dans `00_ETAT_ACTUEL.md`.

### Manquant avant le batch

- classification quota/crédit/usage/spend ;
- exploitation de `Retry-After` ;
- métadonnées provider sûres `error.type` / `error.code` ;
- libellés opérateur explicites.

### Décidé et intégré dans ce batch

- Les codes OpenAI documentés au 26/09/2026 comme non retryables sont : `credit_balance_exhausted`, `organization_usage_limit_exceeded`, `organization_spend_limit_exceeded`, `project_spend_limit_exceeded`. Le type `insufficient_quota` est également traité comme non transitoire lorsque le code n'est pas plus précis.
- Un 429 qui n'est pas identifié comme quota/spend reste un rate limit transitoire et peut être réessayé.
- Le message brut OpenAI n'est jamais recopié dans l'exception ni dans le journal de retry.
- `Retry-After` numérique valide prime sur le backoff. En son absence ou s'il est invalide, le backoff est 1 s puis 2 s, avec 3 tentatives maximum.
- Aucun jitter n'est ajouté afin de garder la politique entièrement déterministe et testable.
- Le budget externe `agent_seconds` reste l'autorité temporelle supérieure : un `Retry-After` trop long est interrompu par le timeout du cycle avant qu'un retry supplémentaire ne puisse déclencher Risk/Broker.

## Contrat d'erreur

- `LLMRateLimitError` : limitation temporaire retryable ;
- `LLMQuotaError` : quota, crédit, usage ou spend limit non retryable ;
- `LLMProviderLimitError` : catégorie provider-agnostic disponible pour une limite non classifiable ;
- `LLMTimeoutError`, `LLMNetworkError`, `LLMServerError` : transitoires comme auparavant ;
- `LLMHTTPError` : HTTP permanent non retryable.

Les exceptions transport peuvent conserver uniquement des métadonnées bornées et non sensibles : HTTP status, `provider_error_type`, `provider_error_code`, `retry_after_seconds`.

## UX

`formatFailure` traduit les erreurs IA connues :

- `LLMRateLimitError` → `Limite temporaire du fournisseur IA` ;
- `LLMQuotaError` → `Quota / limite de dépenses du fournisseur IA` ;
- timeout → `Timeout du fournisseur IA` ;
- autres erreurs provider connues → `Autre erreur fournisseur IA`.

Le préfixe existant « Échec technique distinct de Risk » est conservé. Aucun payload brut provider n'est exposé.

## Invariants

Aucun fallback algorithmique, aucun HOLD artificiel, aucun changement Risk/Broker, aucun ordre direct depuis le LLM et aucun changement LIVE. Un échec Market Selection reste un échec technique avant décision finale, Risk et Broker.

## Validation post-intégration

Validation locale opérateur communiquée après intégration :

- backend complet : `665 passed, 2 warnings` ;
- frontend : `37 passed` ;
- ESLint : OK ;
- TypeScript : OK ;
- build Next.js : OK ;
- `git diff --check` : aucune erreur ;
- working tree propre après commit/push.

Cette validation est une validation opérateur ; la synchronisation documentaire post-batch ne réexécute pas les suites applicatives.
