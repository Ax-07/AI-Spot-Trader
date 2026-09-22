# 01 — Project Master

## 1. Rôle

AI Spot Trader est une application expérimentale de trading crypto PAPER pilotée par **un seul Agent IA stratégique**. Le backend est l'application de trading ; le frontend est un cockpit de contrôle et de visualisation.

Référence intégrée au début du Batch 18.1 : GitHub `main` au commit `ca5077af00293ccca9794132ee0dd53a5b339911`. Le Batch 18.1 décrit ci-dessous est un **patch proposé non intégré** tant qu'il n'a pas été validé localement, commité et poussé.

## 2. Invariants fonctionnels

### Globaux

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- PAPER uniquement ;
- décisions `BUY`, `SELL`, `HOLD` ;
- GPT-5.6 Luna par défaut, Sol sélectionnable ;
- cible expérimentale +4 %/jour = métrique de recherche, jamais garantie ni obligation de trader ;
- Risk Engine déterministe avec autorité finale ;
- seul Risk produit un `ExecutionIntent` ;
- aucune sortie LLM ni aucun tool ne déclenche directement Broker/Kraken ;
- frais, spread, slippage et funding Derivatives restent pris en compte ;
- toutes les décisions et recherches causales sont auditables ;
- aucun secret dans prompts, logs ou fichiers versionnés ;
- aucun look-ahead ;
- backend indépendant du frontend.

### SPOT

- aucun short ;
- aucun levier/margin ;
- `SELL` ne peut réduire qu'un actif effectivement détenu.

### Derivatives

- LONG/SHORT uniquement sur instruments compatibles ;
- le levier est déterministe/configuré, jamais choisi par le LLM ;
- Risk contrôle marge, exposition, liquidation, `reduce_only` et anti-reversal ;
- exécution PAPER actuelle : perpetual linéaire, marge ISOLATED ;
- futures datés, contrats inverses et CROSS restent non exécutables dans le runtime actuel.

## 3. Pipeline de confiance

```text
Kraken public data
      |
      +-------------------------> MarketResearchService
      |                                   |
      |                              read-only tools
      |                                   |
      v                                   v
 MarketState -----------------------> AgentInput --> Agent
      ^                                              |
      |                                        BUY/SELL/HOLD
 PortfolioState complet                              |
                                                     v
                                                Risk Engine
                                         ALLOW/MODIFY/REJECT
                                                     |
                                              ExecutionIntent
                                                     |
                                                     v
                                               Paper Broker
                                                     |
                                                Fill + ledger
                                                     |
                                                     v
                                            TradingCycleResult
                                                     |
                                        audit PostgreSQL / analytics
```

Le chemin d'exécution reste unique : `Market -> Agent -> Risk -> PaperBroker`. La recherche est une source de faits supplémentaire pour le même Agent, pas une stratégie parallèle.

## 4. Contrats de marché

`MarketState` est le snapshot canonique utilisé par le cycle et par Risk/Broker. `MarketStateBuilder` calcule les statistiques descriptives multi-horizon déjà existantes : fraîcheur, min/max, range, rendement et volatilité réalisée.

Le Batch 18.1 introduit `MarketResearchService`, qui expose ces faits sans dupliquer les calculs. Il reçoit un backend provider-specific mais renvoie des modèles provider-agnostic bornés.

### `list_markets`

- catalogue factuel, tri déterministe ;
- pagination par `cursor` + `limit` ;
- SPOT depuis `KrakenPairRegistry` ;
- Derivatives depuis les instruments publics normalisés ;
- aucun score, ranking, top-N stratégique ou filtre momentum.

### `get_market_snapshot`

- symbole + type de marché explicites ;
- SPOT/PERPETUAL dans Batch 18.1 ;
- réutilisation des sources canoniques et du `MarketStateBuilder` ;
- retourne prix, timestamps, fraîcheur, fenêtres descriptives et, pour PERPETUAL, instrument/mark/index/funding ;
- aucune donnée postérieure à la décision ne peut être retenue dans la trace causale.

`FUTURE` peut apparaître dans le catalogue, mais son snapshot n'est pas exposé en 18.1 car le source Derivatives exécutable actuel résout volontairement les collisions canoniques en faveur du perpetual linéaire.

## 5. Agent et tool loop

Le prompt reste identifié `agent-strategy-v4` et les rationales restent en français. L'Agent peut :

- décider immédiatement sans tool ;
- appeler un tool ;
- enchaîner plusieurs recherches ;
- choisir les symboles examinés ;
- arrêter lui-même ses recherches et produire sa décision finale.

Les contraintes de boucle sont **non stratégiques** : elles bornent coût, latence et taille, mais ne disent pas à l'Agent quel marché préférer.

La Responses API conserve `store=false`. Quand un `function_call` est reçu, l'application :

1. valide strictement le nom et les arguments ;
2. exécute le tool read-only sous timeout ;
3. normalise et borne le résultat ;
4. crée une trace causale ;
5. rejoue explicitement les éléments de sortie précédents avec un `function_call_output` portant le même `call_id`.

`parallel_tool_calls=false` évite les appels concurrents dans un même tour. Les tools sont déclarés `strict=true` avec `additionalProperties=false`.

## 6. Limitation volontaire du Batch 18.1

L'Agent peut rechercher `ETH/USD`, `SOL/USD` ou un autre marché, mais la décision finale doit toujours respecter :

```text
DecisionCandidate.symbol == AgentInput.market_state.symbol
```

Le runner continue donc à acquérir un seul `MarketState` causal pour son `paper_symbol`, qui reste le seul symbole pouvant atteindre Risk/Broker. Le Batch 18.2 devra déplacer le choix de marché **avant** la construction du `MarketState` exécutable afin de garder une causalité correcte.

## 7. PortfolioState

`PortfolioState` reste complet dans `AgentInput` : balances, positions SPOT et toutes les `derivative_positions`. Une recherche sur un autre symbole ne filtre ni ne réécrit le portefeuille.

## 8. Erreurs et fail-closed

Les pannes de données au sein d'un tool (réseau, payload fournisseur, symbole inconnu, timeout, résultat trop volumineux) deviennent un résultat d'outil sanitizé et auditable que l'Agent peut constater. Les détails sensibles/raw ne sont jamais renvoyés.

En revanche, un tool non enregistré, des arguments malformed ou un dépassement du budget global constituent une violation technique de la boucle et font échouer le stade Agent. Ce type d'échec n'est jamais converti en HOLD.

## 9. Audit causal des tools

Chaque recherche terminée produit un `AgentToolTrace` :

- `call_id` ;
- nom du tool ;
- arguments validés/sanitizés ;
- `started_at` / `completed_at` ;
- statut `SUCCESS|ERROR` ;
- type d'erreur sanitizé ;
- résultat normalisé borné ;
- SHA-256 déterministe du résultat canonique.

Les traces d'une décision sont aussi attachées à `DecisionCandidate`. Pour couvrir un échec **après** des recherches mais **avant** une décision valide, elles existent également au niveau de `TradingCycleResult` et sont persistées sur `audit_cycles.agent_tool_traces_payload` via la migration `0003_agent_tool_traces`.

Le digest global du cycle inclut explicitement les traces. Deux cycles identiques hors recherches mais ayant des traces différentes n'ont donc pas la même identité durable.

## 10. Séparation research/trading Kraken

La composition construit des sources de recherche dédiées séparées des sources de trading. Cela évite qu'une recherche :

- modifie l'état/cache du source de marché canonique du cycle ;
- marque un ledger Derivatives ;
- accumule du funding dans le portefeuille ;
- affecte un futur `MarketState` de trading par effet de bord.

Le source Derivatives de recherche est construit sans `market_sink`. Aucune clé Kraken privée n'est nécessaire.

## 11. Risk et Broker

Aucun tool du registry n'importe ou n'appelle `RiskEngine`, `PaperBroker` ou `ExecutionIntent`. Les tools ne peuvent donc ni autoriser, ni modifier, ni exécuter une position.

Risk conserve toutes les règles SPOT/Derivatives existantes. En particulier, un HOLD reste `ALLOW` sans intent, le SPOT reste sans short et l'anti-reversal Derivatives reste déterministe.

## 12. Persistance et migration

La chaîne de migrations devient :

```text
0001_audit_journal
  -> 0002_paper_runs
  -> 0003_agent_tool_traces
```

`0003` ajoute une colonne JSONB nullable `audit_cycles.agent_tool_traces_payload`. Le nullable conserve la compatibilité avec les cycles historiques qui n'avaient aucune notion de tools.

## 13. Dette / décisions futures

- Batch 18.2 : sélection causale du symbole exécutable et construction du bon `MarketState` avant décision/Risk ;
- décider si une version explicite de politique de tools doit entrer dans `ExperimentManifest` avant toute comparaison expérimentale pré/post tools ;
- ne pas ajouter order book, recent trades ou funding historique sans besoin mesuré ;
- ne pas prétendre supporter des snapshots FUTURE génériques tant que le mapping provider/exécution n'est pas séparé proprement.

## 14. LIVE

LIVE reste hors périmètre. Il nécessitera un batch séparé avec adaptateur privé, permissions minimales sans retrait, idempotence, réconciliation, recovery et activation explicite.
