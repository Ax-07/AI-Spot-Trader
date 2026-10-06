# Batch 51.1 / 51.1.1 — Provider LLM local Ollama et durcissement du contrat

## État intégré

```text
51.1   : aeaf04f — feat: add local Ollama LLM provider
51.1.1 : 7e2ce28 — fix: harden causal Ollama decision contract
HEAD audité au lancement de 51.2 : 7e2ce2821660c9be7f5ffdfe053244d56fae7986
```

Les deux batches sont intégrés à `main`. La suite backend complète, le frontend typecheck/tests et le smoke réel `qwen3.5:9b` ont été validés localement avant 51.2.

## Architecture canonique

Le Batch 51.1 a ajouté Ollama derrière la même frontière et le même Agent :

```text
même Agent stratégique
        ↓
OpenAIMultiMarketDecisionProvider  (nom legacy conservé)
        ↓
StrategyInstructionsClient
        ↓
StructuredDecisionClient
        ├── OpenAIResponsesClient
        └── OllamaStructuredDecisionClient
        ↓
Structured Output JSON
        ↓
Pydantic + contrôles métier Agent
        ↓
Risk Engine déterministe
        ↓
PaperBroker
```

`LLMModel` reste réservé à Luna/Sol. Le modèle Ollama reste une chaîne configurable. Aucun fallback `OLLAMA -> OPENAI` n'existe.

## Structured Output causal 51.1.1

`build_strategic_plan_schema(CycleDecisionPlanInput)` construit le JSON Schema depuis les couples exacts `(symbol, market_type)` de `market_states`. Les variantes BUY/SELL/HOLD lient simultanément l'identité de marché, l'action et la quantité. Le contrôle métier post-LLM reste présent et fail-closed.

Ollama reçoit `think:false`; `message.content` est la seule sortie décisionnelle et toute clé `thinking` reçue est retirée de l'audit public.

`LLM audit status=SUCCESS` décrit le succès provider/transport, pas l'acceptation Pydantic/Agent/Risk/Broker.

## Smoke réel validé

Configuration :

```text
provider = OLLAMA
model = qwen3.5:9b
base URL = http://localhost:11434
OpenAI API key absente
```

Résultat validé avant 51.2 :

```text
LLM audit category = STRATEGIC_MULTI_MARKET_PLAN
provider = OLLAMA
model = qwen3.5:9b
status = SUCCESS
think = false
OpenAI calls = 0
Cycle status = COMPLETED
Cycle failure = NONE
thinking dans response_output = false
```

Le schema correspond exactement aux couples présents dans `CycleDecisionPlanInput.market_states`.

## Évolution 51.2

Le choix du provider était volontairement process/runtime en 51.1. Le Batch 51.2 ajoute la persistance par Session/Campaign :

```text
llm_provider
ollama_model
ollama_timeout_seconds
```

Les Campaigns créées avant 51.2 restent compatibles et héritent encore du provider/modèle Ollama process lorsque `llm_provider` est absent. `ollama_base_url` et les secrets restent process-level.

Voir `docs/51_2_PROVIDER_LLM_PAR_SESSION.md`.

## ADR historiques actifs

- ADR-381 : provider distinct du modèle OpenAI historique ;
- ADR-382 : provider process/runtime pour les Campaigns 51.1/legacy ;
- ADR-383 : Ollama réutilise `StructuredDecisionClient` ;
- ADR-384 : aucun fallback Ollama vers OpenAI ;
- ADR-385 : tools adaptés, jamais réimplémentés ;
- ADR-386 : nom `OpenAIMultiMarketDecisionProvider` conservé ;
- ADR-387 : schema multi-marché causal dynamique ;
- ADR-388 : `think:false` et audit sans `thinking` ;
- ADR-389 : `LLM audit SUCCESS` reste un statut provider/transport.
