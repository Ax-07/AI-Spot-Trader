# 02 — Architecture technique

## 1. Référence

État intégré actuel :
`main = 4042e0b0e6394de788009229e3dae5924cd732d7`
(`fix: support nested Kraken derivative margin schedules`).

Les Batches 18.1, 18.2 et 18.3 sont intégrés ; l'architecture décrite ci-dessous correspond au
chemin PAPER multi-marché validé comportementalement en Batch 18.3.

## 2. Modules concernés

```text
backend/src/ai_spot_trader/
  agent/
    provider.py            # même Agent : select_market() puis generate_decision()
    prompt.py              # contrat à deux phases, toujours agent-strategy-v4
  domain/
    models.py              # ExecutableMarket / MarketSelectionInput / MarketSelection
    ports.py               # MarketSelectingLLMProvider / ExecutableMarketDataSource
  market/
    execution.py           # routeur typé SPOT/PERPETUAL, fail-closed
  trading/
    engine.py              # orchestration causale sélection -> marché -> décision -> Risk
  core/
    config.py              # PAPER_EXECUTABLE_MARKETS et validation de l'univers
  integrations/kraken/
    derivatives.py         # normalisation Derivatives + schedules de marge imbriqués fail-closed
  persistence/
    models.py              # nouveaux payloads + execution_universe_payload
    runs.py                # run singleton ou multi-marchés honnête
    repository.py          # persistance/digest sélection
    query.py               # lecture/API de la sélection
  analytics/
    paper.py               # replay multi-marchés causal v3
  composition.py           # sources research et execution distinctes
```

Migration :

```text
backend/alembic/versions/0004_multi_market_selection.py
```

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

`OpenAIDecisionProvider` implémente deux méthodes stratégiques :

```text
select_market(MarketSelectionInput) -> MarketSelection
generate_decision(AgentInput)       -> DecisionCandidate
```

Il s'agit du **même objet Agent**, du même modèle Luna/Sol et du même rôle stratégique. Le backend
ne crée pas un scanner Agent puis un trader Agent.

La phase sélection peut utiliser la Responses API avec function calling borné. La phase finale est
un appel structuré direct : les résultats de recherche sont déjà présents dans
`AgentInput.market_selection.tool_traces`.

`store=false` reste inchangé côté OpenAI.

## 5. Univers typé

`ExecutableMarket` est un contrat immuable :

```text
symbol: BASE/QUOTE
market_type: SPOT | PERPETUAL
```

`FUTURE` est refusé dès ce contrat. L'univers est trié et dédupliqué de façon déterministe.

`risk_allowed_pairs` reste une whitelist de symboles. L'univers exécutable est plus précis car il
porte aussi le type du marché.

## 6. Routeur d'exécution

`RoutedExecutableMarketDataSource` ne fait aucune sélection stratégique. Il reçoit le marché déjà
choisi et vérifie :

1. format canonique ;
2. appartenance exacte à l'univers ;
3. type supporté ;
4. routage vers la source d'exécution correcte ;
5. cohérence du snapshot retourné ;
6. pour PERPETUAL : instrument perpetual linéaire réellement représenté.

Erreurs principales :

```text
MarketOutsideExecutableUniverseError
UnsupportedExecutableMarketError
ExecutableMarketSnapshotMismatchError
```

Toutes provoquent un échec technique du cycle, jamais un HOLD artificiel.

## 7. Séparation research / execution

Quatre objets réseau peuvent coexister :

```text
research_spot
research_derivatives      # sans market_sink
execution_spot
execution_derivatives     # market_sink = PaperPortfolioLedger
```

Les deux premiers alimentent uniquement les tools. Les deux derniers ne sont appelés qu'après
`MarketSelection`.

Ainsi une exploration PERPETUAL ne marque jamais une position et n'accumule jamais de funding.

## 8. Portfolio et Derivatives

Avant sélection, le runner capture un portefeuille complet pour le contexte stratégique.
Après acquisition du marché choisi, il le recapture.

Pourquoi : `KrakenDerivativesMarketDataSource` d'exécution peut appeler le `market_sink` lors du
snapshot pour mettre à jour mark price, unrealized P&L et funding d'une position existante.
Agent final et Risk doivent voir cet état, pas l'état antérieur à l'acquisition.

Le catalogue public Derivatives peut exposer des schedules de marge directs ou imbriqués par
région/profil. Le parser aplatit uniquement les feuilles de marge reconnues et les valide toutes
fail-closed. Comme aucun tier privé n'est prouvé par cette API publique, le runtime conserve les
taux publics les plus stricts observés pour `initial_margin_rate` et `maintenance_margin_rate`.

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

Le digest couvre aussi la rationale et les traces. Toute altération de l'artefact rend le modèle
invalide.

Les traces ne sont pas fournies par le LLM : elles viennent du registre read-only contrôlé par
l'application.

## 10. TradingCycleResult et échecs

Nouveaux stages :

```text
SELECTION_INPUT
MARKET_SELECTION
```

Les stages historiques restent présents.

Exemples :

- tool/LLM échoue avant sélection valide -> `MARKET_SELECTION`, traces partielles conservées ;
- sélection valide mais Kraken execution indisponible -> `MARKET`, sélection conservée ;
- snapshot valide mais décision finale incohérente -> `AGENT`, sélection + AgentInput conservés.

## 11. Persistance

`audit_cycles` reçoit :

```text
market_selection_input_payload JSONB NULL
market_selection_payload       JSONB NULL
```

Ces colonnes sont nullable pour les cycles historiques. Le `result_digest` inclut les deux.

Le détail API expose les deux objets. Le résumé de cycle dérive `symbol + market_type` de la
sélection quand aucune décision finale n'existe encore.

## 12. `paper_runs`

`execution_universe_payload JSONB NOT NULL` est ajouté. Migration des anciennes rows :

```text
[{"symbol": ancien_symbol, "market_type": ancien_market_type}]
```

Après backfill :

```text
paper_runs.market_type nullable
paper_runs.symbol      nullable
```

Le modèle applique :

```text
singleton -> projection historique réelle
multi     -> market_type = NULL, symbol = NULL
```

## 13. Analytics v3

Le replay maintient un dictionnaire causal :

```text
spot_prices["BTC/USD"] = dernier MarketState SPOT BTC/USD déjà rencontré
spot_prices["ETH/USD"] = dernier MarketState SPOT ETH/USD déjà rencontré
```

Lorsqu'une position SPOT est valorisée, le dernier mark déjà présent dans le journal est utilisé.
Aucune donnée externe/current-time n'est consultée.

Toutes les quotes doivent rester égales au `paper_settlement_asset`, ce qui évite d'introduire une
conversion FX non auditée.

## 14. Compatibilité

`TradingCycleRunner` garde deux modes exclusifs :

```text
legacy    : market_data + symbol
selection : executable_market_data + executable_markets
```

Le chemin canonique composé utilise le second. Le premier évite de casser les tests et surfaces
mono-marché existants pendant la transition.

## 15. Validation comportementale Batch 18.3

Le smoke réel a confirmé : cross-symbol SPOT, univers mixte chargé, research SPOT + PERPETUAL dans
un même cycle, cycles mixtes SPOT terminés et branche PERPETUAL réelle validée séparément jusqu'à
la décision et Risk. Il n'a pas confirmé une sélection PERPETUAL spontanée depuis l'univers mixte
ni un fill réel.

Un timeout ponctuel de la source SPOT d'exécution au stage `MARKET` a été suivi de plusieurs
cycles `COMPLETED`. Un `LLMTransportError` ponctuel au stage `MARKET_SELECTION` a également été
observé. Ces incidents restent des observations de robustesse, pas des changements d'architecture.

## 16. Ressources et fermeture

Les quatre sources réseau sont enregistrées comme ressources owned du runtime et dédupliquées par
identité avant fermeture. Le routeur lui-même ne possède pas de connexion réseau.
