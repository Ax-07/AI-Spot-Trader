# 02 — Architecture technique

## 1. Référence

Base GitHub auditée au démarrage du Batch 18.5 :

```text
HEAD réel main = 5cc2e2897d9a1dccba325f8a543b208360c6120d
docs: record batch 18.3 behavioral validation

dernier commit code validé = 4042e0b0e6394de788009229e3dae5924cd732d7
fix: support nested Kraken derivative margin schedules
```

Les Batches 18.1, 18.2 et 18.3 sont intégrés. Le Batch 18.5 est un patch proposé jusqu'à validation,
commit et push ; il ne doit pas être présenté comme un HEAD GitHub déjà intégré.

## 2. Modules concernés

```text
backend/src/ai_spot_trader/
  agent/
    provider.py            # même Agent + validation runtime des manifestes v3
    prompt.py              # contrat à deux phases, toujours agent-strategy-v4
  domain/
    models.py              # ExperimentAgentProtocolSnapshot + univers typé v3
    experiments.py         # digests version-aware v1/v2/v3
    ports.py               # MarketSelectingLLMProvider / ExecutableMarketDataSource
  experiments/
    protocol.py            # builders v1/v2/v3 et snapshot effectif Agent/tools
    comparison.py          # comparaisons Luna/Sol v2 ou v3, sans ranking
  tools/
    read_only.py           # digest des définitions OpenAI + bornes introspectables
  market/
    execution.py           # routeur typé SPOT/PERPETUAL, fail-closed
  trading/
    engine.py              # univers v3 vérifié avant le premier appel Agent
  core/
    config.py              # PAPER_EXECUTABLE_MARKETS et bornes tools existantes
  integrations/kraken/
    derivatives.py         # normalisation Derivatives fail-closed
  persistence/
    ...                    # persistance JSON existante, aucune migration 18.5
  analytics/
    paper.py               # paper-analytics-v3 multi-marchés causal
  composition.py           # sources research et execution distinctes
```

Aucune migration Alembic n'est ajoutée par 18.5.

## 3. Flux runtime causal

```text
                         +-------------------------------+
                         | Kraken public research        |
                         | instances dédiées             |
                         +---------------+---------------+
                                         |
                                 MarketResearchService
                                         |
                                  ReadOnlyToolRegistry
                                         |
                                         v
PortfolioLedger -> MarketSelectionInput -> OpenAIDecisionProvider.select_market()
                                         |
                                         v
                                  MarketSelection
                                         |
                                         v
                         RoutedExecutableMarketDataSource
                           /                         \
                    execution SPOT            execution Derivatives
                           \                         /
                            +------> MarketState <---+
                                         |
PortfolioLedger ------------------------>| recapture complète
                                         v
                                     AgentInput
                                         |
                                         v
                         OpenAIDecisionProvider.generate_decision()
                                         |
                                         v
                                  DecisionCandidate
                                         |
                                         v
                                     RiskEngine
                                         |
                                  ExecutionIntent ?
                                         |
                                         v
                                    PaperBroker
```

## 4. Un seul Agent, deux phases

`OpenAIDecisionProvider` implémente :

```text
select_market(MarketSelectionInput) -> MarketSelection
generate_decision(AgentInput)       -> DecisionCandidate
```

Il s'agit du **même objet Agent**, du même modèle Luna/Sol et du même rôle stratégique. La phase
sélection peut utiliser le function calling borné. Le chemin causal final est un appel structuré
direct sans nouveaux tools ; il réutilise les traces de sélection.

## 5. Univers typé

`ExecutableMarket` est immuable :

```text
symbol: BASE/QUOTE
market_type: SPOT | PERPETUAL
```

`FUTURE` est refusé. L'univers est trié et dédupliqué de façon déterministe. En v3, ce tuple exact
fait partie de l'identité expérimentale ; deux univers ayant les mêmes symboles mais des types de
marché différents ne sont pas comparables.

## 6. Routeur d'exécution

`RoutedExecutableMarketDataSource` ne fait aucune sélection stratégique. Il reçoit le marché déjà
choisi et vérifie format, appartenance exacte, type supporté, cohérence du snapshot et, pour les
PERPETUAL, contrat linéaire réellement représenté. Une erreur provoque un échec technique, jamais
un HOLD artificiel.

## 7. Séparation research / execution

Les sources research n'ont aucun `market_sink`; les sources execution sont appelées seulement après
`MarketSelection`. Une exploration PERPETUAL ne peut donc ni marquer le ledger ni accumuler du
funding.

## 8. Portfolio et Derivatives

Le runner capture un portefeuille complet avant la sélection puis le recapture après acquisition du
marché choisi. Cela garantit que mark, unrealized P&L et funding causaux d'une position dérivée
existante sont visibles par l'Agent final et Risk.

## 9. Artefact MarketSelection

```text
selection_id
cycle_id
selected_at
symbol
market_type
rationale
tool_traces[]
selection_digest
```

Le digest couvre rationale et traces. Les traces viennent du registre contrôlé par l'application,
pas du LLM.

## 10. Protocole expérimental v3

`ExperimentManifest` conserve son identité historique pour v1/v2 et reçoit un champ optionnel
`agent_protocol`, omis de la sérialisation lorsqu'il est absent. Cela évite d'altérer les payloads
historiques.

Pour `paper-experiment-v3`, `agent_protocol` contient :

```text
executable_markets
market_selection_protocol_version
selection_phase.tools_enabled
selection_phase.max_tool_calls
final_decision_phase.tools_enabled
final_decision_phase.max_tool_calls
tool_definitions_digest
tool_timeout_seconds
tool_max_result_bytes
list_markets_max_limit
```

Le chemin v3 canonique impose `final_decision_phase.tools_enabled = false`.

## 11. Identité de la capacité tools

`ReadOnlyToolRegistry.openai_tools` reste la source de définition réellement transmise au LLM.
Le registre expose désormais `openai_tools_digest`, calculé avec le JSON canonique des définitions
triées. Une modification de nom, description ou schéma modifie donc automatiquement l'identité.

Les bornes qui affectent la recherche sont aussi persistées séparément :

- budget maximal de calls ;
- timeout ;
- taille maximale de résultat ;
- maximum de `list_markets.limit`, introspecté dans le schéma effectif.

Cela évite de dépendre d'un simple numéro manuel pouvant diverger silencieusement du contrat
présenté au modèle.

## 12. Digests et groupes contrôlés

v1 et v2 continuent d'utiliser leurs payloads historiques. Le champ v3 est explicitement exclu des
digests historiques et, lorsqu'il vaut `None`, de leur sérialisation normale.

En v3, le digest du groupe exclut seulement :

```text
llm_model
replicate_index
```

Il inclut le protocole v3 lui-même, l'univers typé, le prompt versionné, Risk/coûts/analytics/source,
la politique de sélection, la capacité tools et ses bornes. Une dérive sur un de ces facteurs
produit un autre `experiment_group_digest`.

## 13. Validation avant appel LLM

Lorsqu'un manifeste v3 est présent :

1. le runner vérifie avant le cycle que son univers `ExecutableMarket[]` est exactement celui du
   manifeste ;
2. le provider valide le digest, le modèle et `agent-strategy-v4` ;
3. il vérifie la version active du protocole de sélection ;
4. il compare présence/budget des tools au runtime ;
5. si les tools sont actifs, il compare digest des définitions, timeout, taille résultat et limite
   `list_markets` ;
6. la décision finale v3 exige le chemin causal avec `MarketSelection` et aucun tool final.

Une incohérence lève une erreur avant l'appel LLM concerné.

## 14. Persistance et compatibilité

Le manifeste est déjà inclus dans les payloads JSON durables de `AgentInput` et
`MarketSelectionInput`. La v3 n'ajoute donc aucune colonne PostgreSQL.

Compatibilité :

```text
experiment_manifest = None  -> PAPER normal inchangé
paper-experiment-v1         -> lecture/digest historique
paper-experiment-v2         -> lecture/digest historique Luna/Sol
paper-experiment-v3         -> nouveau contrat multi-marché
```

Le runner conserve aussi le mode legacy `market_data + symbol`; v3 est réservé au chemin causal de
sélection typée.

## 15. Analytics et causalité

`paper-analytics-v3` reste le défaut des nouvelles expériences multi-marchés. Aucun calcul de
performance, aucune règle Risk/Broker et aucun mécanisme de valorisation ne sont modifiés par ce
batch.

L'ordre causal demeure :

```text
MarketSelectionInput
-> tools éventuels
-> MarketSelection
-> MarketState execution
-> AgentInput final
-> DecisionCandidate
-> RiskAssessment
-> ExecutionIntent éventuel
-> Fill éventuel
```

## 16. Hors périmètre 18.5

Pas de recovery/restart ledger, retries réseau/LLM, nouvelle donnée research, campagne Luna/Sol,
scanner/ranking/opportunity score, multi-quote/FX, FUTURE daté, LIVE, changement de prompt
stratégique ni modification des règles Risk/Broker.
