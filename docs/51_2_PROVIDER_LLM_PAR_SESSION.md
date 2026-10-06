# Batch 51.2 — Provider LLM et configuration Ollama par Session

## Objet

Le Batch 51.2 déplace le **choix opérateur du provider stratégique** du niveau process vers le snapshot `CampaignConfiguration`, sans créer de second Agent et sans modifier Risk/Broker.

Base auditée :

```text
GitHub main : 7e2ce2821660c9be7f5ffdfe053244d56fae7986
Commit      : fix: harden causal Ollama decision contract
```

Les Batch 51.1 (`aeaf04f`) et 51.1.1 (`7e2ce28`) sont déjà intégrés. Le smoke réel `qwen3.5:9b` est validé avant ce batch.

## Diagnostic confirmé

Avant 51.2 :

- `Settings.llm_provider` décide du transport pour tout le processus ;
- `CampaignConfiguration.llm_model` persiste Luna/Sol ;
- `ollama_model` et `ollama_timeout_seconds` viennent uniquement de `Settings` ;
- deux Sessions ne peuvent donc pas conserver des providers différents dans le même backend ;
- `ollama_base_url` est déjà une propriété d'infrastructure backend et n'a pas besoin d'être dupliquée dans chaque Campaign.

La persistence Campaign est un JSON canonique et le digest provient de `CampaignConfiguration.canonical_payload()`. Les champs historiques optionnels utilisent déjà `exclude_if=None`, ce qui permet une extension additive sans migration SQL ni réécriture des anciens snapshots.

## Contrat persisté 51.2

Champs ajoutés :

```text
llm_provider: OPENAI | OLLAMA | null
ollama_model: string | null
ollama_timeout_seconds: positive float | null
```

`llm_model` reste inchangé et réservé aux modèles OpenAI :

```text
gpt-5.6-luna
gpt-5.6-sol
```

Pour `OLLAMA`, le modèle local reste une chaîne libre normalisée, par exemple `qwen3.5:9b`.

Aucun de ces éléments n'est ajouté à la Campaign :

```text
OPENAI_API_KEY
clé/secret Kraken
ollama_base_url
openai_base_url
```

## Résolution effective

La résolution est centralisée dans `agent/client_factory.py` :

```text
Campaign explicite 51.2
    llm_provider != null
        ↓
provider Campaign

Campaign legacy
    llm_provider absent/null
        ↓
Settings.llm_provider
```

Puis :

```text
OPENAI
  model   = CampaignConfiguration.llm_model
  key     = Settings.openai_api_key
  baseURL = Settings.openai_base_url
  timeout = Settings.openai_timeout_seconds

OLLAMA explicite
  model   = CampaignConfiguration.ollama_model
  baseURL = Settings.ollama_base_url
  timeout = CampaignConfiguration.ollama_timeout_seconds
            ?? Settings.ollama_timeout_seconds

OLLAMA legacy
  model   = Settings.ollama_model
  baseURL = Settings.ollama_base_url
  timeout = Settings.ollama_timeout_seconds
```

Il n'existe aucun fallback croisé :

```text
Campaign OLLAMA -> Ollama ou erreur
Campaign OPENAI -> OpenAI ou erreur
```

Une clé OpenAI présente ne peut pas détourner une Campaign OLLAMA. Une Campaign OPENAI sans clé échoue fermée.

## Compatibilité historique et digest

Les nouveaux champs ont :

```python
default=None
exclude_if=lambda value: value is None
```

Une ancienne Campaign chargée depuis un payload sans champs 51.2 reste donc sérialisée **sans** ces champs. Son `canonical_payload()` et son digest historique restent identiques.

L'édition d'une Session legacy accepte également ce provider absent. Le frontend affiche alors « provider hérité du runtime » et ne sérialise pas `OPENAI` par défaut. Une duplication legacy réutilise le snapshot source existant et conserve donc l'absence historique.

Une **nouvelle** Session via l'API 51.2 doit au contraire posséder un `llm_provider` explicite.

## Timeouts

Deux budgets restent distincts :

```text
ollama_timeout_seconds
= timeout d'un appel transport Ollama

cycle_agent_timeout_seconds
= enveloppe de tout le stade Agent
```

Pour une Campaign Ollama :

```text
cycle_agent_timeout_seconds > effective_ollama_timeout_seconds
```

est vérifié. Cette contrainte élimine une incohérence manifeste mais **ne garantit pas** le budget d'une boucle qui effectue plusieurs appels LLM/tools.

Aucune grosse valeur globale n'est introduite automatiquement et aucune valeur personnalisée n'est réécrite lors d'un changement de provider dans l'UI.

## Runtime et Operator Chat

Le pipeline stratégique reste :

```text
même Agent stratégique
        ↓
OpenAIMultiMarketDecisionProvider (nom legacy)
        ↓
StrategyInstructionsClient
        ↓
StructuredDecisionClient
        ↓
OpenAIResponsesClient OU OllamaStructuredDecisionClient
        ↓
Pydantic + contrôles métier Agent
        ↓
Risk Engine
        ↓
PaperBroker
```

Le chat opérateur n'est pas porté vers Ollama dans ce batch. Il est construit seulement si le **provider effectif de la Campaign** est OpenAI. Une Campaign Ollama n'obtient donc ni chat OpenAI caché ni fallback.

## UX

`SimpleConfigurator` est la surface canonique du cockpit. Elle expose :

- OpenAI / Ollama local ;
- Luna / Sol uniquement sous OpenAI ;
- modèle local texte sous Ollama ;
- timeout transport Ollama sous Ollama ;
- timeout Agent dans la configuration avancée avec explication de sa portée ;
- état « hérité du runtime » pour une Session legacy.

Les valeurs Ollama saisies restent dans l'état du formulaire lors d'un aller-retour de provider. Pour une Campaign OpenAI, elles ne sont pas persistées comme paramètres actifs inutilisés.

## Tests ajoutés

Backend `test_batch51_2_session_llm_provider.py` couvre notamment :

- persistance OpenAI/Ollama ;
- modèle/timeout Ollama ;
- absence de secrets/base URLs Campaign ;
- digest legacy ;
- création 51.2 explicite et édition legacy ;
- round-trip persistence SQLite du snapshot ;
- héritage provider process pour legacy ;
- deux providers différents dans un même process ;
- non-construction du mauvais transport ;
- Ollama sans clé OpenAI ;
- OpenAI sans clé fail-closed ;
- modèle vide, timeout non positif et incohérence Agent/Ollama ;
- aucun fallback provider.

Frontend `session-config-batch51_2.test.mjs` couvre :

- défaut nouvelle Session ;
- édition legacy sans réécriture ;
- sérialisation OpenAI/Ollama ;
- modèle/timeout locaux ;
- validations ;
- round-trip des valeurs Ollama personnalisées.

Les contrats Structured Output 51.1.1, le Risk Engine et le pipeline PAPER ne sont pas modifiés.

## Smoke local attendu

### Session Ollama

Créer/éditer une Session :

```text
provider = OLLAMA
ollama_model = qwen3.5:9b
ollama_timeout_seconds < cycle_agent_timeout_seconds
```

Sans `OPENAI_API_KEY`, démarrer un cycle puis vérifier :

```text
Cycle status = COMPLETED
LLM audit provider = OLLAMA
LLM audit model = qwen3.5:9b
think = false
response_output ne contient aucun thinking
OpenAI calls = 0
plan limité aux couples de market_states
```

### Session OpenAI

Sans lancer d'appel payant uniquement pour le test, les tests/composition doivent confirmer :

```text
provider Campaign = OPENAI
OpenAIResponsesClient sélectionné
OllamaStructuredDecisionClient non sélectionné
model = llm_model du snapshot Campaign
```

## Limites

- aucune migration automatique des Campaigns historiques ;
- `ollama_base_url` reste process-level ;
- chat opérateur Ollama hors périmètre ;
- aucun nouveau provider, fine-tuning, RAG ou multi-agent ;
- qualité stratégique Ollama et smoke réel restent dépendants du modèle/matériel local.

## Correctif de validation — corrélation Session dans l’audit LLM

Le smoke runtime 51.2 a confirmé `OLLAMA / qwen3.5:9b / SUCCESS`, mais l’enregistrement `STRATEGIC_MULTI_MARKET_PLAN` portait uniquement le `cycle_id`; `session_id` restait nul. Cela empêchait le filtre `/api/v1/llm-audit?session_id=...` de retrouver l’appel malgré une décision effectivement visible dans l’historique persistant.

Le wrapper stratégique canonique `StrategicThesisContextDecisionProvider` reçoit maintenant l’identité Session (`campaign.strategy_id`) à la composition de Campaign et ouvre `llm_audit_context(session_id=..., cycle_id=...)` autour de l’unique appel stratégique au delegate. Ce correctif est purement d’observabilité : il ne modifie ni le provider résolu, ni le payload stratégique, ni Risk, ni Broker.

Validation attendue après redémarrage du backend et nouveau cycle :

```text
category = STRATEGIC_MULTI_MARKET_PLAN
provider = OLLAMA
model = qwen3.5:9b
status = SUCCESS
session_id = <UUID de la Session>
cycle_id = <UUID du cycle>
```

Le filtre par Session doit alors retourner cet enregistrement.
