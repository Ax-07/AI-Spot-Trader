# 02 — Architecture technique

## 1. Référence

État intégré audité avant Batch 18.1 : `main = ca5077af00293ccca9794132ee0dd53a5b339911`, tag `baseline-batch17` identique. Le contenu Batch 18.1 de ce document décrit un patch proposé non encore intégré.

## 2. Modules concernés

```text
backend/src/ai_spot_trader/
  agent/
    openai_client.py       # Responses API + boucle functions bornée
    provider.py            # même Agent stratégique, décision finale stricte
    prompt.py              # règles de recherche read-only
  domain/
    models.py              # AgentToolTrace + DecisionCandidate.tool_traces
  integrations/kraken/
    research.py            # composition provider-specific read-only
  market/
    research.py            # MarketResearchService provider-agnostic
  tools/
    read_only.py           # registry strict, timeout, bornes, traces
    market_research.py     # list_markets / get_market_snapshot
  trading/
    engine.py              # capture traces même en échec Agent
  persistence/
    models.py
    repository.py
    query.py               # traces cycle-level durables
  composition.py           # sources research isolées des sources trading
```

## 3. Flux runtime

```text
                           +------------------------------+
                           |  Kraken public research      |
                           |  Spot + Derivatives          |
                           +---------------+--------------+
                                           |
                                           v
                                  MarketResearchService
                                           |
                                  ReadOnlyToolRegistry
                                           |
                                  list_markets / snapshot
                                           |
                                           v
MarketDataSource -> MarketState -> AgentInput -> OpenAIDecisionProvider
PortfolioLedger -> PortfolioState -----------^          |
                                                        v
                                                 DecisionCandidate
                                                        |
                                                        v
                                                   RiskEngine
                                                        |
                                                 ExecutionIntent
                                                        |
                                                        v
                                                   PaperBroker
```

Il n'existe aucun chemin `tool -> Risk`, `tool -> Broker` ou `tool -> ExecutionIntent`.

## 4. Source de recherche séparée

Les objets réseau de recherche sont différents des objets utilisés par `TradingCycleRunner`.

### SPOT

Un `KrakenMarketDataSource` dédié à la recherche réutilise les mêmes adapters publics et le même `MarketStateBuilder`, mais son cache/historique n'est pas le cache causal du source de trading.

### Derivatives

Un `KrakenDerivativesMarketDataSource` dédié à la recherche est construit **sans `market_sink`**. Les snapshots de recherche ne peuvent donc pas marquer les positions du ledger ni accumuler du funding.

Le catalogue Derivatives utilise directement les `DerivativeInstrument` normalisés du client public, plutôt que le mapping exécutable qui peut privilégier un PERPETUAL en cas de collision de symbole canonique.

## 5. Contrat provider-agnostic

`MarketResearchService` ne dépend pas de Kraken dans sa frontière. Il travaille avec un backend répondant à :

```text
list_markets(market_type?) -> marchés factuels normalisés
snapshot(symbol, market_type) -> MarketState canonique
```

Le service impose tri/pagination déterministes et vérifie la cohérence symbole/type/timestamp.

## 6. Registry read-only

Le registry contient exactement deux fonctions en 18.1 :

```text
list_markets
get_market_snapshot
```

Chaque function possède :

- nom fixe ;
- description factuelle ;
- schéma JSON strict ;
- modèle Pydantic strict ;
- handler async ;
- timeout technique ;
- taille maximale de résultat.

Un nom inconnu ou des arguments non conformes ne sont jamais dispatchés dynamiquement.

## 7. Responses API

Le transport conserve `store=false`. Pour les requêtes structurées avec tools :

```text
input initial = AgentInput sérialisé
        |
        v
Responses API
        |
  function_call ? ---- non ---> output_text JSON final
        |
       oui
        v
validation + tool read-only
        |
AgentToolTrace + function_call_output
        |
replay explicite response.output + tool output
        |
        +----------------------> Responses API suivant
```

`parallel_tool_calls=false` sérialise la boucle. Le budget maximal est compté côté application et n'est pas laissé à la stratégie du modèle.

## 8. Causalité

Un `AgentToolTrace.completed_at` ne peut pas être postérieur à `DecisionCandidate.created_at`. Les `MarketState` des tools vérifient également que leur propre `as_of` n'est pas futur par rapport à l'instant de recherche.

Le runner continue à utiliser **son** `MarketState` initial pour Risk et Broker. Aucun snapshot de recherche ne remplace silencieusement ce snapshot dans Batch 18.1.

## 9. Audit en cas de succès et d'échec

### Succès Agent

Les traces existent dans :

```text
DecisionCandidate.tool_traces
TradingCycleResult.agent_tool_traces
DecisionRecord.payload.tool_traces
CycleRecord.agent_tool_traces_payload
```

Le runner vérifie que les traces cycle-level et décision sont exactement identiques.

### Échec Agent après recherche

`OpenAIResponsesClient` conserve les traces déjà terminées. `OpenAIDecisionProvider` les expose, puis `TradingCycleRunner` les copie dans le `TradingCycleResult(FAILED)` avant persistance. Elles restent donc auditables même sans `DecisionRecord`.

## 10. Identité durable

`SqlAlchemyCycleAuditRepository._result_digest()` inclut `agent_tool_traces`. Le digest couvre ainsi les faits de recherche causaux pour cycles `COMPLETED` et `FAILED`.

La migration `0003_agent_tool_traces` ajoute un JSONB nullable à `audit_cycles`. Les lecteurs exposent ce tableau dans le détail de cycle. Les anciennes lignes nulles sont interprétées comme aucune trace.

## 11. Configuration

Réglages techniques proposés :

```text
AI_SPOT_TRADER_AGENT_TOOL_MAX_CALLS=6
AI_SPOT_TRADER_AGENT_TOOL_TIMEOUT_SECONDS=5
AI_SPOT_TRADER_AGENT_TOOL_MAX_RESULT_BYTES=32768
AI_SPOT_TRADER_AGENT_TOOL_LIST_MARKETS_MAX_LIMIT=50
```

`AGENT_TOOL_MAX_CALLS=0` désactive la boucle de tools et conserve le chemin direct historique. Ces paramètres bornent uniquement ressources et transport ; ils ne créent aucune règle de sélection de marché.

## 12. Fermeture des ressources

Les sources de recherche sont enregistrées parmi les ressources réseau owned par le runtime et sont fermées avec le backend. La composition déduplique par identité pour éviter une fermeture répétée accidentelle.

## 13. Limites 18.1

- recherche cross-symbol autorisée ;
- décision/exécution toujours liée au symbole initial du cycle ;
- snapshot tool seulement SPOT/PERPETUAL ;
- pas d'order book, recent trades, funding historique ou news ;
- pas de tool d'exécution ;
- pas de second agent ;
- pas de scanner/ranking déterministe.
