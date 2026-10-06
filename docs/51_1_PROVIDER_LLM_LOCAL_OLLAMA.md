# Batch 51.1 / 51.1.1 — Provider LLM local Ollama et durcissement du contrat

## Objet

Le Batch 51.1 permet au **même Agent stratégique canonique** d'utiliser OpenAI ou un modèle local servi par Ollama. Le Batch 51.1.1 ne change ni la doctrine de trading ni l'Agent : il durcit le contrat Structured Outputs après un smoke test réel avec `qwen3.5:9b`.

Base intégrée auditée :

```text
GitHub main : e5887da5e8e6ebf0fa739a041c0226a6fed940dd
Commit      : feat: add strategic thesis observability
```

État local 51.1 préservé :

```text
aeaf04f49aa103ad55410dbbdc60d37ed23ee060
feat: add local Ollama LLM provider
parent: e5887da5e8e6ebf0fa739a041c0226a6fed940dd
```

## Architecture canonique

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
Pydantic
        ↓
contrôles métier Agent
        ↓
Risk Engine déterministe
        ↓
PaperBroker
```

Le transport LLM n'a aucune autorité Broker/Risk. Le provider local ne transforme jamais directement sa réponse en ordre.

## Configuration 51.1

Provider :

```text
OPENAI
OLLAMA
```

`LLMModel` reste réservé à Luna/Sol pour préserver les contrats historiques. Le modèle local reste une chaîne indépendante, par exemple :

```text
AI_SPOT_TRADER_LLM_PROVIDER=OLLAMA
AI_SPOT_TRADER_OLLAMA_BASE_URL=http://localhost:11434
AI_SPOT_TRADER_OLLAMA_MODEL=qwen3.5:9b
AI_SPOT_TRADER_OLLAMA_TIMEOUT_SECONDS=60
```

Le choix du provider reste process/runtime dans 51.1. La persistance et l'UX par Session/Campaign restent hors périmètre et relèvent du futur 51.2.

Aucun fallback silencieux `OLLAMA -> OPENAI` n'existe. En mode Ollama, une clé OpenAI vide est valide pour le chemin stratégique local.

## Smoke test réel ayant motivé 51.1.1

Configuration :

```text
provider = OLLAMA
model = qwen3.5:9b
base_url = http://localhost:11434
OpenAI API key absente
```

Résultat transport :

```text
category = STRATEGIC_MULTI_MARKET_PLAN
provider = OLLAMA
model = qwen3.5:9b
status = SUCCESS
latency ≈ 50.7 s
```

Le cycle a ensuite échoué au stade Agent :

```text
error_type = AgentContractViolationError
timed_out = false
```

Univers causal réel :

```text
ACE/USD         PERPETUAL
ANTHROPICX/USD  PERPETUAL
ASTER/USD       PERPETUAL
```

Sortie du modèle :

```text
BTC/USD  SPOT
ETH/USD  SPOT
BTC/USD  PERPETUAL
ETH/USD  PERPETUAL
```

Le contrôle métier de `planner.py` a donc correctement refusé le plan. Ce contrôle est conservé.

## 51.1.1 — Schema causal dynamique

Avant 51.1.1, le schema multi-marché était statique : `symbol` était un simple `string` et `market_type` un enum indépendant. Une sortie pouvait donc respecter le JSON Schema tout en visant un marché absent du cycle.

Le correctif introduit :

```text
build_strategic_plan_schema(CycleDecisionPlanInput)
```

Le schema est construit à partir des couples exacts de `market_states`. Pour un univers :

```text
ACE/USD PERPETUAL
BTC/USD SPOT
```

les seules identités structurées possibles sont :

```text
ACE/USD PERPETUAL
BTC/USD SPOT
```

et jamais :

```text
ACE/USD SPOT
BTC/USD PERPETUAL
```

La contrainte est appliquée dans les variantes de décision elles-mêmes afin d'éviter un produit cartésien artificiel entre deux enums indépendants.

Pour chaque couple causal, les variantes restent :

```text
BUY  -> proposed_quantity > 0
SELL -> proposed_quantity > 0
HOLD -> proposed_quantity = null
```

Le contrat `thesis_update` reste inchangé. Pydantic reste inchangé. Le contrôle métier post-schema reste présent : si un provider ignore malgré tout le schema et retourne un marché hors univers, le cycle échoue toujours fermé avant Risk.

Cette contrainte de transport ne choisit aucun marché à la place de l'Agent et ne calcule aucun signal stratégique.

## Thinking Ollama

Pour les appels structurés AI Spot Trader, `/api/chat` reçoit désormais explicitement :

```json
{
  "think": false
}
```

Ollama documente ce paramètre pour désactiver le thinking sur les modèles compatibles. `message.content` reste la seule sortie décisionnelle exploitée.

Par défense en profondeur, l'audit public supprime toute clé `thinking` reçue dans une réponse provider avant de conserver `response_output`. Une éventuelle chaîne de pensée détaillée n'est donc ni nécessaire au contrat applicatif ni exposée dans le cockpit.

Aucun changement de prompt stratégique n'est utilisé pour compenser le problème.

## Observabilité

L'audit LLM 51.1 expose notamment :

```text
provider
model
status
error_type
latency_ms
```

La sémantique de `status` est volontairement transport/provider :

```text
SUCCESS = l'appel LLM s'est terminé au niveau transport/provider
ERROR   = l'appel LLM/transport a échoué
```

`SUCCESS` ne signifie pas :

- validation Pydantic réussie ;
- validation métier Agent réussie ;
- Risk ALLOW/MODIFY ;
- ordre Broker ;
- fill ;
- cycle `COMPLETED`.

Il est donc cohérent d'observer un audit LLM `SUCCESS` puis un `AgentContractViolationError`. Le correctif conserve cette séparation plutôt que de mélanger deux couches d'état.

## Timeouts

Deux budgets distincts existent :

```text
ollama_timeout_seconds
cycle_agent_timeout_seconds
```

`ollama_timeout_seconds` borne une requête transport Ollama. `cycle_agent_timeout_seconds` borne l'ensemble du stade Agent qui englobe l'appel LLM, le parsing, Pydantic, les contrôles métier et éventuellement les tools.

La règle opérationnelle est donc :

```text
cycle_agent_timeout_seconds > budget Ollama réellement nécessaire
```

avec une marge raisonnable pour les traitements Agent. Le smoke réel à environ `50.7 s` montre qu'un timeout Agent de `30–35 s` n'est pas compatible avec cette machine/modèle.

51.1.1 ne hardcode pas une grosse valeur partout : le timeout transport reste configurable et le budget Agent doit être ajusté au niveau Session/Campaign. La persistance/UX dédiée reste réservée à 51.2.

## Tools read-only

Ollama continue d'utiliser les définitions projetées depuis `ReadOnlyToolRegistry`. Les handlers, validation Pydantic des arguments, timeouts, tailles maximales et budgets d'appels restent canoniques. Aucune capacité supplémentaire n'est inventée par le provider local.

## Validation repository attendue

Après extraction du ZIP à la racine :

```powershell
Push-Location backend
python -m pytest -q
Pop-Location

Push-Location frontend
pnpm typecheck
pnpm test
Pop-Location

git diff --check
git status --short
```

## Smoke Ollama minimal

Vérifier Ollama et le modèle :

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
ollama list
```

Test direct du transport structuré avec thinking désactivé :

```powershell
$body = @{
    model = "qwen3.5:9b"
    stream = $false
    think = $false
    messages = @(
        @{ role = "user"; content = "Réponds uniquement avec un objet JSON où ok vaut true." }
    )
    format = @{
        type = "object"
        properties = @{ ok = @{ type = "boolean" } }
        required = @("ok")
        additionalProperties = $false
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
    -Method Post `
    -Uri http://localhost:11434/api/chat `
    -ContentType "application/json" `
    -Body $body
```

Pour le vrai cycle applicatif, utiliser `OLLAMA`, `qwen3.5:9b`, une clé OpenAI vide, puis vérifier :

1. audit `provider=OLLAMA`, `model=qwen3.5:9b` ;
2. requête auditée avec `think=false` ;
3. aucune clé `thinking` dans `response_output` ;
4. le JSON Schema audit expose uniquement les couples de `market_states` du cycle ;
5. le plan final reste dans ce même univers ;
6. aucun appel OpenAI ;
7. aucun `AgentContractViolationError` dû à un marché inventé ;
8. les protections métier restent fail-closed si une sortie invalide contourne artificiellement le schema dans un test.

## Limites connues

- le provider reste process/runtime en 51.1 ;
- le chat opérateur reste volontairement non configuré sous Ollama ;
- la qualité stratégique et le tool calling dépendent du modèle local et du matériel ;
- `think:false` réduit le raisonnement explicite du modèle : ce batch privilégie le contrat applicatif structuré et l'absence de chaîne de pensée persistée ;
- aucune amélioration automatique, fine-tuning ou apprentissage par backtest n'est introduit ;
- le vrai smoke applicatif reste une validation locale, non simulable depuis l'environnement ChatGPT.

## ADR 51.1 / 51.1.1

- ADR-381 : provider LLM distinct du modèle OpenAI historique ;
- ADR-382 : provider process/runtime en 51.1 ;
- ADR-383 : Ollama réutilise `StructuredDecisionClient` ;
- ADR-384 : aucun fallback Ollama vers OpenAI ;
- ADR-385 : tools adaptés, jamais réimplémentés ;
- ADR-386 : nom `OpenAIMultiMarketDecisionProvider` conservé comme dette de compatibilité ;
- ADR-387 : schema multi-marché causal dynamique ;
- ADR-388 : appels Ollama structurés avec `think:false` et audit sans `thinking` ;
- ADR-389 : `LLM audit SUCCESS` reste un statut transport/provider.
