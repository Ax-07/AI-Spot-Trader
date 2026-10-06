# Batch 51.1 — Provider LLM local / Ollama

## Objectif

Le Batch 51.1 permet au **même Agent stratégique canonique** d'utiliser OpenAI ou un modèle local servi par Ollama. Il ne crée ni second Agent, ni seconde stratégie, ni voie d'exécution parallèle.

Le batch ne modifie pas le Risk Engine, le Broker PAPER, le Radar, `CycleDecisionPlanInput`, les contextes multi-timeframe, la mémoire de thèse ni la sémantique `BUY` / `SELL` / `HOLD`.

Base GitHub auditée :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : e5887da5e8e6ebf0fa739a041c0226a6fed940dd
Commit     : feat: add strategic thesis observability
```

## Architecture

La frontière existante est réutilisée :

```text
StrategicThesisContextDecisionProvider
        ↓
MultiTimeframeDecisionProvider
        ↓
OpenAIMultiMarketDecisionProvider  ← nom historique conservé
        ↓
StrategyInstructionsClient / StructuredDecisionClient
        ├── OpenAIResponsesClient
        └── OllamaStructuredDecisionClient
        ↓
JSON textuel
        ↓
validation Pydantic canonique
        ↓
DecisionCandidate / CycleDecisionPlan
        ↓
Risk Engine
        ↓
PaperBroker
```

Le changement `OPENAI` / `OLLAMA` remplace uniquement le transport/moteur LLM.

## Pourquoi `LLMProviderKind` est séparé de `LLMModel`

`LLMModel` représente historiquement les modèles OpenAI Luna/Sol et participe à des contrats Campaign/expérience existants. L'élargir à des chaînes Ollama arbitraires aurait changé sa sémantique et augmenté le risque de casser les snapshots/digests historiques.

Le Batch 51.1 ajoute donc :

```text
LLMProviderKind.OPENAI
LLMProviderKind.OLLAMA
```

et conserve séparément :

```text
AI_SPOT_TRADER_LLM_MODEL=gpt-5.6-luna
AI_SPOT_TRADER_OLLAMA_MODEL=qwen3.5:9b
```

Le nom du modèle Ollama est configurable ; `qwen3.5:9b` est seulement le candidat initial par défaut.

## Périmètre de configuration 51.1

Le provider est une **configuration process/runtime** dans ce batch. Il n'est pas encore ajouté au snapshot immuable d'une Campaign.

Cela évite :

- une migration de la version de configuration Campaign ;
- une modification silencieuse des digests historiques ;
- une ambiguïté entre le modèle OpenAI persisté et le moteur local effectif.

Le sélecteur UX/persisté `OpenAI / Local` est réservé au Batch 51.2.

Configuration OpenAI :

```env
AI_SPOT_TRADER_LLM_PROVIDER=OPENAI
AI_SPOT_TRADER_LLM_MODEL=gpt-5.6-luna
AI_SPOT_TRADER_OPENAI_API_KEY=<secret-local>
```

Configuration Ollama :

```env
AI_SPOT_TRADER_LLM_PROVIDER=OLLAMA
AI_SPOT_TRADER_OLLAMA_BASE_URL=http://localhost:11434
AI_SPOT_TRADER_OLLAMA_MODEL=qwen3.5:9b
AI_SPOT_TRADER_OLLAMA_TIMEOUT_SECONDS=60
```

En mode `OLLAMA`, `AI_SPOT_TRADER_OPENAI_API_KEY` n'est pas requise.

## Structured outputs

`OllamaStructuredDecisionClient` appelle :

```text
POST /api/chat
```

avec :

- `stream=false` ;
- le modèle configuré ;
- les instructions système et l'input utilisateur ;
- le JSON Schema canonique transmis dans `format` ;
- aucun paramètre de sampling spécifique imposé par 51.1 ; le batch change le transport, pas la doctrine stratégique.

Le provider local ne transforme pas la réponse en objet métier lui-même. Il extrait uniquement le contenu textuel. Les parseurs et modèles Pydantic existants restent responsables de la validation finale.

Conséquence : une réponse JSON invalide, une propriété manquante, une action inconnue, une quantité invalide ou un contrat de thèse incorrect est refusé avant d'atteindre Risk/Broker.

## Tools read-only

Le Batch 51.1 conserve les tools Agent existants.

Les définitions canoniques exposées par `ReadOnlyToolRegistry` sont adaptées au format Ollama :

```text
Responses/OpenAI definition
        ↓ conversion de forme uniquement
Ollama function tool
        ↓
appel modèle
        ↓
ReadOnlyToolRegistry.execute(...)
```

Les propriétés de sécurité restent celles de l'existant :

- arguments validés ;
- handlers read-only ;
- timeout par tool ;
- résultat borné en taille ;
- budget maximal d'appels ;
- traces d'outils conservées.

Aucune capacité n'est simulée si le modèle Ollama choisi ne sait pas correctement appeler les tools : la requête échoue ou produit une sortie rejetée.

## Erreurs et fail-closed

Le client Ollama réutilise les familles d'erreurs LLM existantes :

- timeout -> `LLMTimeoutError` ;
- transport/réseau -> `LLMNetworkError` ;
- HTTP 429 -> `LLMRateLimitError` ;
- HTTP 5xx -> `LLMServerError` ;
- HTTP permanent, dont modèle absent/404 -> `LLMHTTPError` ;
- enveloppe de réponse incohérente -> `LLMProviderError` ;
- JSON métier invalide -> `LLMOutputValidationError` dans la couche Agent.

Il n'existe **aucun fallback automatique d'Ollama vers OpenAI**.

Une erreur du provider local reste une erreur au stade Agent. Elle n'est jamais convertie en ordre et ne contourne jamais le Risk Engine.

## Chat opérateur

Le chat opérateur existant est encore typé autour du provider OpenAI. Pour éviter une extension de périmètre et surtout tout appel OpenAI implicite, le Batch 51.1 le laisse **non configuré en mode `OLLAMA`**.

Le moteur de trading stratégique local fonctionne indépendamment du chat. Le support du chat local pourra être traité explicitement dans un batch ultérieur.

## Observabilité

Le store LLM process-local existant reste l'unique store de traces LLM. Il est enrichi avec :

```text
provider      OPENAI | OLLAMA
model         modèle réellement demandé
status        SUCCESS | ERROR
error_type    type d'erreur sanitizé
latency_ms    latence de l'appel transport
```

Les secrets ne sont pas ajoutés à l'audit. Les headers HTTP d'authentification OpenAI ne sont jamais persistés.

Le cockpit LLM affiche ces métadonnées sans reconstruire de logique métier.

## Dette de nommage

`OpenAIMultiMarketDecisionProvider` et `OpenAIDecisionProvider` portent des noms devenus trop spécifiques alors que leur logique centrale est désormais provider-agnostique.

Ils sont conservés dans 51.1 pour limiter le rayon de migration et préserver la compatibilité. Un renommage mécanique pourra être fait dans un batch dédié, sans mélanger cette opération avec l'introduction du transport local.

## Validation locale Ollama

Vérifier que le serveur répond :

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

Vérifier/installer le modèle candidat :

```powershell
ollama pull qwen3.5:9b
ollama list
```

Smoke test structuré minimal :

```powershell
$body = @{
    model = "qwen3.5:9b"
    stream = $false
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

## Validation exécutée dans l’environnement ChatGPT

Exécuté réellement :

```text
python -m compileall sur le code/test 51.1                       : PASS
harnais HTTP MockTransport Ollama (structured/tools/network)     : PASS
harnais HTTP MockTransport OpenAI (audit succès/erreur/latence)  : PASS
git diff --cached --check sur un staging du patch root-relative  : PASS
```

La suite complète du repository et une vraie inférence Ollama ne sont pas disponibles dans cet environnement.

## Validation repository attendue

Après extraction du ZIP à la racine du repository :

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

## Limites connues du Batch 51.1

- provider choisi au niveau process/runtime, pas encore par Session/Campaign ;
- chat opérateur non disponible sous Ollama ;
- qualité réelle du structured output et du tool calling dépend du modèle Ollama installé ;
- aucune vraie inférence Ollama n'est considérée validée tant que le smoke test local n'a pas été exécuté ;
- les protocoles d'expérience historiques restent fondés sur `LLMModel` OpenAI ; la comparaison expérimentale OpenAI/local est hors périmètre ;
- aucun entraînement, fine-tuning, auto-tuning ou comparaison de performance n'est introduit.
