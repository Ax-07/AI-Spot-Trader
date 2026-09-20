# 02 — Architecture technique

## 1. Objet

Ce document décrit l'architecture technique courante d'AI Spot Trader. Il complète `01_PROJECT_MASTER.md` sans remplacer les décisions produit.

---

## 2. Vue d'ensemble

```text
+--------------------------+
| Frontend cockpit         |
| Next.js / TS / shadcn    |
+------------+-------------+
             |
       REST / WebSocket
             |
+------------v-------------+
| FastAPI API              |
+------------+-------------+
             |
+------------v------------------------------------------+
| Backend trading                                      |
|                                                       |
| Kraken -> observations -> MarketState                 |
| PortfolioState ---------> Agent -> DecisionCandidate  |
|                                   |                   |
|                                   v                   |
|                              Risk Engine               |
|                                   |                   |
|                         RiskAssessment/Intent          |
|                                   |                   |
| MarketState -----------------> Paper Broker            |
|                                   |                   |
|                          Fill + portfolio ledger       |
+-------------------------------------------------------+
```

Le backend est un service autonome ; le frontend n'est jamais l'ordonnanceur du moteur.

---

## 3. Découpage backend après application du Batch 07

```text
backend/src/ai_spot_trader/
  agent/
    __init__.py
    errors.py
    openai_client.py
    prompt.py
    provider.py
  api/
  broker/
    errors.py
    paper.py
    pricing.py
  core/
    clock.py
    config.py
    runtime.py
  domain/
    enums.py
    models.py
    ports.py
    symbols.py
  integrations/kraken/
  market/
    errors.py
    state.py
  portfolio/
    errors.py
    ledger.py
  risk/
    __init__.py
    engine.py
    errors.py
    policy.py
  main.py
```

Responsabilités :

- `domain` : contrats canoniques fournisseur-agnostiques ;
- `integrations/kraken` : I/O et structures spécifiques Kraken uniquement ;
- `market` : historique et snapshots déterministes ;
- `portfolio` : état mutable PAPER mémoire ;
- `broker/pricing.py` : estimation PAPER pure partagée ;
- `broker/paper.py` : exécution PAPER et mutation du ledger ;
- `risk` : évaluation déterministe sans effets de bord ;
- `agent` : transformation d'un `AgentInput` en `DecisionCandidate`, sans exécution.

---

## 4. Contrats de domaine

Les contrats sont Pydantic stricts, `extra="forbid"`, timestamps aware normalisés UTC et valeurs financières en `Decimal`.

### DecisionCandidate

BUY/SELL exigent une `proposed_quantity > 0`. HOLD interdit toute quantité. Cette quantité est la proposition stratégique amont.

### RiskAssessment

- `ALLOW` conserve la quantité demandée ;
- `MODIFY` réduit strictement la quantité ;
- `REJECT` n'autorise aucune quantité et possède au moins une raison ;
- HOLD peut être `ALLOW` sans quantité ni intent.

### ExecutionIntent

PAPER uniquement, BUY/SELL uniquement, quantité positive et corrélation au `RiskAssessment`.

---

## 5. Frontière Agent / fournisseur LLM

Le port `LLMProvider` reste inchangé :

```python
async def generate_decision(self, agent_input: AgentInput) -> DecisionCandidate: ...
```

`OpenAIDecisionProvider` implémente structurellement ce port. Il dépend seulement de :

- `StructuredDecisionClient` ;
- `LLMModel` ;
- `Clock` ;
- une factory UUID de décision ;
- contrats domaine/symboles.

Il ne dépend pas de Risk, Broker, Kraken, FastAPI, PostgreSQL ou d'un scheduler.

### Métadonnées contrôlées par l'application

Le fournisseur LLM n'émet pas `decision_id`, `cycle_id` ni `created_at`.

```text
LLM output              application envelope
----------              --------------------
action       ----+
symbol       ----+----> DecisionCandidate
quantity     ----+      decision_id <- UUID factory
rationale    ----+      cycle_id    <- AgentInput
                       created_at   <- Clock
```

Cette frontière évite de faire confiance au LLM pour la corrélation technique ou la chronologie.

---

## 6. Contrat structuré fournisseur

Le JSON Schema envoyé à OpenAI impose :

```text
object
  action: BUY | SELL | HOLD
  symbol: string non vide
  proposed_quantity: number | null
  rationale: string | null
required: les 4 champs
additionalProperties: false
```

Toutes les clés sont requises pour respecter le mode Structured Outputs strict ; `null` représente l'absence métier de quantité/rationale.

La sortie texte structurée est reparsée par l'application avec conservation exacte des nombres via `Decimal`, puis validée par un modèle Pydantic interne strict. Ce modèle n'est pas un second contrat métier : le seul objet exposé au reste du moteur reste `DecisionCandidate`.

Aucune réparation silencieuse n'est admise. Une quantité JSON fournie comme chaîne, un champ inconnu ou une incohérence BUY/SELL/HOLD provoque une erreur explicite.

---

## 7. Adapter OpenAI Responses API

`OpenAIResponsesClient` est un adapter HTTP minimal autour de :

```text
POST /v1/responses
model = gpt-5.6-luna | gpt-5.6-sol
text.format.type = json_schema
text.format.strict = true
store = false
```

Le client recherche exactement un `output_text` non vide dans une réponse `status=completed`.

Sont rejetés comme erreurs fournisseur :

- statut incomplet ;
- absence de liste `output` ;
- refus fournisseur ;
- zéro ou plusieurs fragments `output_text` ;
- réponse HTTP non JSON ou enveloppe non objet.

Les erreurs réseau/HTTP sont distinguées des erreurs d'enveloppe. Leur message n'inclut jamais le body distant ni la clé API.

Aucun retry n'est implémenté au Batch 07. Une policy de retry pourra être ajoutée ultérieurement uniquement si un besoin réel est démontré.

---

## 8. Prompt versionné

`agent/prompt.py` expose :

```text
AGENT_PROMPT_VERSION = agent-luna-v1
AGENT_SYSTEM_PROMPT
```

Le prompt contient uniquement des règles stratégiques et de sécurité stables ; aucun secret, aucune clé, aucune instruction d'ordre Kraken et aucun tool-calling.

Le `AgentInput` complet est transmis comme JSON au champ `input`. Aucune donnée de marché supplémentaire n'est récupérée par l'agent.

---

## 9. Limitation au symbole du MarketState

Avant de construire un `DecisionCandidate`, le provider vérifie :

```text
LLM.symbol == AgentInput.market_state.symbol
```

Le `MarketState.symbol` doit également respecter la forme canonique `BASE/QUOTE` avant l'appel LLM. Une divergence est une violation de frontière Agent et non une opportunité de normalisation silencieuse.

Le Risk Engine garde indépendamment ses contrôles de symbole, whitelist et cohérence marché.

---

## 10. Chronologie Agent et no look-ahead

Avant l'appel LLM :

```text
MarketState.as_of    <= AgentInput.created_at
PortfolioState.as_of <= AgentInput.created_at
```

Après l'appel :

```text
AgentInput.created_at <= DecisionCandidate.created_at
```

Ces contrôles utilisent uniquement les snapshots fournis. L'agent ne fait aucun lookup Kraken ou refresh caché.

---

## 11. Configuration et secrets

`Settings` expose désormais :

```text
llm_model: LLMModel = gpt-5.6-luna
openai_api_key: SecretStr | None
openai_base_url: str = https://api.openai.com/v1
openai_timeout_seconds: float = 30
```

La clé reste optionnelle au niveau process afin que healthcheck, tests et composants non-LLM puissent démarrer sans secret. La construction d'un `OpenAIResponsesClient` réel exige en revanche une clé non vide.

`.env.example` ne contient qu'un emplacement vide. Aucun `.env` réel ne doit être versionné ou livré.

---

## 12. Dépendances externes

Aucune nouvelle dépendance runtime au Batch 07. `httpx`, déjà utilisé dans le projet, suffit pour l'adapter REST officiel.

Ce choix évite une dépendance inutile tout en gardant le client injectable. L'architecture ne dépend pas d'une classe SDK OpenAI spécifique et peut donc être testée intégralement hors réseau.

---

## 13. Market State, Portfolio, Risk et Broker

Les composants des Batches 04 à 06 restent inchangés :

- `MarketStateBuilder` : contexte déterministe ;
- `PaperPortfolioLedger` : état PAPER ;
- `estimate_paper_execution` : mathématique coûts partagée ;
- `RiskEngine` : décision de sécurité ;
- `PaperBroker` : intégrité finale d'exécution.

Le Batch 07 ne les appelle jamais depuis l'agent.

---

## 14. Orchestration asynchrone

Les I/O externes LLM sont asynchrones. Le provider `generate_decision` est donc async conformément au port existant.

Le Batch 07 ne crée aucune boucle, tâche de fond ou scheduler. L'orchestration complète reste au Batch 08.

---

## 15. Persistance, API et frontend

Aucune persistance, migration, route FastAPI de trading, WebSocket cockpit ou modification frontend n'est introduite au Batch 07.

---

## 16. Tests et reproductibilité

Les tests injectent :

- un `StructuredDecisionClient` fake ;
- un `Clock` fixe ;
- une factory UUID fixe ;
- `httpx.MockTransport` pour l'adapter Responses API.

Ils ne dépendent ni d'Internet, ni d'un compte OpenAI, ni d'une clé réelle. Ils vérifient aussi statiquement que le package `agent` n'importe pas Risk, Broker, Kraken ou FastAPI.

---

## 17. Qualité architecturale

Chaque batch doit préserver : séparation des responsabilités, contrats testables, dépendances fournisseur confinées, calculs financiers `Decimal`, no-look-ahead, testabilité offline, aucune stratégie déterministe cachée, mutations atomiques et remplacement Luna/Sol par configuration sans refonte métier.
