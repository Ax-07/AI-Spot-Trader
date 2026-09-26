# Batch 19.12 — Gestion robuste des erreurs OpenAI 429 / Rate Limit

## Référence

Audit réalisé sur GitHub `main` au HEAD `5c92958414ce4fb52865dedfb17b808232fdc91c`.

## Audit

### Confirmé

- `OpenAIResponsesClient` convertissait tout HTTP 429 en `LLMRateLimitError` sans lire le payload d'erreur ni `Retry-After`.
- `LLM_PRE_DECISION_RETRY_POLICY` utilisait 2 tentatives, backoff 0,5 s plafonné à 1 s.
- le retry ne s'applique qu'aux `LLMTransientError`.
- `TradingCycleRunner` borne l'appel Agent par `TradingCycleTimeouts.agent_seconds` et transforme l'échec en `TradingCycleFailure` ; Market Selection échoue avant Risk/Broker.
- le cockpit affichait directement `error_type`, d'où `MARKET_SELECTION · LLMRateLimitError`.

### Obsolète

- considérer tous les 429 comme un simple débit temporaire.
- la référence HEAD `47e12798f54c3686b59faf339315ff39d9191b44` dans `00_ETAT_ACTUEL.md`.

### Manquant avant le batch

- classification quota/crédit/usage/spend ;
- exploitation de `Retry-After` ;
- métadonnées provider sûres `error.type` / `error.code` ;
- libellés opérateur explicites.

### Décidé dans ce batch

- Les codes OpenAI documentés au 26/09/2026 comme non retryables sont : `credit_balance_exhausted`, `organization_usage_limit_exceeded`, `organization_spend_limit_exceeded`, `project_spend_limit_exceeded`. Le type `insufficient_quota` est également traité comme non transitoire lorsque le code n'est pas plus précis.
- Un 429 qui n'est pas identifié comme quota/spend reste un rate limit transitoire et peut être réessayé.
- Le message brut OpenAI n'est jamais recopié dans l'exception ni dans le journal de retry.
- `Retry-After` numérique valide prime sur le backoff. En son absence ou s'il est invalide, le backoff est 1 s puis 2 s, avec 3 tentatives maximum.
- Aucun jitter n'est ajouté dans ce batch afin de garder la politique entièrement déterministe et testable.
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

## Validation attendue opérateur

```powershell
cd backend
pytest tests/test_openai_client.py tests/test_openai_rate_limits.py tests/test_market_selection_runner.py -q
pytest
cd ..\frontend
pnpm test
pnpm lint
pnpm typecheck
pnpm build
```
