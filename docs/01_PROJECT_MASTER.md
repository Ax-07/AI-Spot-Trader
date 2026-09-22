# 01 — Project Master

## 1. Rôle

AI Spot Trader est une application expérimentale de trading crypto PAPER pilotée par **un seul
Agent IA stratégique**. Le backend est l'application de trading ; le frontend est un cockpit de
contrôle et de visualisation.

Référence intégrée actuelle : GitHub `main` au commit
`4042e0b0e6394de788009229e3dae5924cd732d7`
(`fix: support nested Kraken derivative margin schedules`). Les Batches 18.1, 18.2 et 18.3 y sont
intégrés.

## 2. Invariants fonctionnels

### Globaux

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- PAPER uniquement ;
- décisions finales `BUY`, `SELL`, `HOLD` ;
- GPT-5.6 Luna par défaut, Sol sélectionnable ;
- cible expérimentale +4 %/jour = métrique de recherche, jamais garantie ;
- Risk Engine déterministe avec autorité finale ;
- seul Risk produit un `ExecutionIntent` ;
- aucune sortie LLM ni aucun tool ne déclenche directement Broker/Kraken ;
- frais, spread, slippage et funding restent pris en compte ;
- décisions, recherches et sélections causales sont auditables ;
- aucun secret dans prompts, logs ou fichiers versionnés ;
- aucun look-ahead ;
- backend indépendant du frontend.

### SPOT

- aucun short ;
- aucun levier/margin ;
- `SELL` ne peut réduire qu'un actif détenu/disponible.

### Derivatives

- uniquement les `PERPETUAL` linéaires supportés sont exécutables ;
- LONG/SHORT permis sous contrôle Risk ;
- levier déterministe/configuré, jamais choisi par le LLM ;
- Risk contrôle marge, exposition, liquidation, `reduce_only` et anti-reversal ;
- marge `ISOLATED` ;
- futures datés, contrats inverses et CROSS restent non exécutables ;
- les métadonnées publiques Kraken sont normalisées fail-closed, y compris les
  `marginSchedules` imbriqués ; faute de tier privé prouvable, les marges publiques les plus
  strictes restent la référence conservatrice.

## 3. Pipeline de confiance Batch 18.2+

```text
PortfolioState complet
        |
        v
MarketSelectionInput
        |
        v
Agent unique + tools read-only optionnels
        |
        v
MarketSelection
        |
        v
validation déterministe de l'univers exécutable
        |
        v
MarketState canonique exact du marché sélectionné
        |
        v
AgentInput final -> même Agent -> BUY / SELL / HOLD
        |
        v
Risk Engine -> ALLOW / MODIFY / REJECT
        |
        v
ExecutionIntent éventuel -> PaperBroker -> Fill
        |
        v
journal PostgreSQL / analytics
```

La stratégie de sélection appartient à l'Agent. Les composants déterministes ne calculent aucun
ranking, score d'opportunité ou signal d'achat/vente.

## 4. Marché découvrable, recherchable et exécutable

Ces ensembles sont distincts :

```text
univers Kraken découvert
>= univers Agent recherchable
>=/!= univers PAPER exécutable configuré
>= univers finalement autorisable par Risk
```

`list_markets` peut montrer des instruments non exécutables. `get_market_snapshot` reste une
capacité de recherche factuelle. Aucun résultat de tool ne devient automatiquement un marché de
trading.

L'univers exécutable est un tuple de `ExecutableMarket(symbol, market_type)` limité à :

- `SPOT` ;
- `PERPETUAL` linéaire.

`FUTURE` daté reste non exécutable.

## 5. Configuration de l'univers

Variable :

```text
AI_SPOT_TRADER_PAPER_EXECUTABLE_MARKETS=["SPOT:BTC/USD","PERPETUAL:ETH/USD"]
```

`paper_symbol` et `paper_market_type` restent un bootstrap de compatibilité. Quand l'univers est
omis, le runtime redevient un singleton équivalent au comportement historique. Quand il est
fourni, le bootstrap doit y appartenir mais ne fixe plus le marché des cycles.

Contraintes :

- ordre canonique déterministe ;
- aucun doublon `symbol + market_type` ;
- chaque symbole doit appartenir à `risk_allowed_pairs` ;
- quote commune égale à `paper_settlement_asset` ;
- présence d'un PERPETUAL => configuration Derivatives complète obligatoire.

La quote commune reste une limitation explicite : aucune conversion FX implicite n'est introduite.

## 6. Sélection stratégique explicite

`MarketSelectionInput` contient :

- `cycle_id` ;
- timestamp causal ;
- `PortfolioState` complet ;
- univers exécutable typé ;
- agressivité et contexte expérimental éventuel.

Le même `OpenAIDecisionProvider` exécute `select_market()`. Il peut appeler les tools read-only ou
sélectionner directement un marché dans l'univers fourni.

Le résultat `MarketSelection` persiste :

- `selection_id` ;
- `cycle_id` ;
- `selected_at` ;
- `symbol` ;
- `market_type` ;
- `rationale` ;
- `AgentToolTrace[]` ;
- `selection_digest` SHA-256 déterministe.

Le LLM ne fournit pas lui-même les identifiants, timestamps, traces ou digest : l'application les
contrôle.

## 7. Acquisition du MarketState exécutable

Après sélection, `RoutedExecutableMarketDataSource` vérifie :

- symbole canonique ;
- couple exact présent dans l'univers ;
- type `SPOT` ou `PERPETUAL` ;
- cohérence du snapshot retourné ;
- pour PERPETUAL : contexte dérivé présent, instrument réellement perpetual et contrat linéaire.

Le snapshot retourné devient **l'unique `MarketState`** utilisé ensuite par Agent, Risk et Broker.
Aucun snapshot de recherche n'est promu silencieusement vers l'exécution.

## 8. PortfolioState

La sélection reçoit un `PortfolioState` complet. Après l'acquisition du marché sélectionné, le
runner recapture le portefeuille avant la décision finale.

Cette seconde capture est importante pour les Derivatives : la source d'exécution peut marquer
une position déjà ouverte et accumuler le funding avant que l'Agent et Risk évaluent l'état.

Les sources de recherche n'ont aucun droit de modifier le ledger.

## 9. Décision finale

Le même Agent reçoit ensuite `AgentInput` contenant :

- le `MarketState` exécutable exact ;
- le `PortfolioState` complet ;
- le `MarketSelection`, donc aussi les recherches causales ;
- l'agressivité et le contexte expérimental.

Dans le chemin multi-marché, la phase finale ne relance pas de tools : elle raisonne sur les
recherches de sélection déjà enregistrées et le nouveau `MarketState` canonique. Cela évite qu'un
contexte de recherche postérieur au snapshot d'exécution soit mélangé implicitement au cycle.

Contraintes finales :

```text
DecisionCandidate.symbol      == MarketState.symbol
DecisionCandidate.market_type == MarketState.market_type
```

## 10. Risk et Broker

Risk reçoit exactement la décision, le `MarketState` sélectionné et le portefeuille complet.
Toutes les règles SPOT/Derivatives existantes restent actives.

Le Broker reçoit le même `MarketState` que Risk. Les fills doivent référencer son
`market_state_id`, son timestamp de pricing et son prix de référence.

## 11. Causalité temporelle

Le pipeline vérifie notamment :

```text
selection portfolio.as_of <= selection_input.created_at
trace.completed_at         <= selection.selected_at
selection.selected_at      <= final AgentInput.created_at
market_state.as_of         <= final AgentInput.created_at
AgentInput.created_at      <= DecisionCandidate.created_at
DecisionCandidate.created_at <= RiskAssessment.assessed_at
```

Aucun prix ou tool call postérieur à la décision finale n'est utilisable comme contexte causal.

## 12. Audit durable

`TradingCycleResult` porte aussi :

```text
market_selection_input
market_selection
```

La migration `0004` ajoute deux payloads nullable sur `audit_cycles`. Les anciennes rows restent
compatibles avec `NULL`.

Une panne :

- pendant la recherche : conserve les traces terminées ;
- après la sélection mais avant le snapshot exécutable : conserve entrée + sélection ;
- après snapshot mais avant décision : conserve aussi l'`AgentInput` final.

Le digest global du cycle couvre ces artefacts.

## 13. `paper_runs`

Le contrat historique `market_type + symbol` ne suffit pas pour un run multi-marchés.
`0004` ajoute donc `execution_universe_payload` et rend les deux colonnes historiques nullables.

- singleton : les colonnes historiques gardent la vraie paire/type ;
- multi-marchés : elles sont `NULL` ;
- aucun faux marqueur `MULTI`.

Les rows existantes sont backfillées vers un univers singleton lors de la migration.

## 14. Analytics

L'analytics passe à `paper-analytics-v3` lorsque plusieurs marchés distincts apparaissent dans le
journal. Les positions SPOT sont valorisées par le dernier mark SPOT causal durable connu pour
chaque `BASE/settlement_asset`.

Un mark absent provoque une erreur de données explicite. Aucune requête marché actuelle n'est
faite pendant le replay et aucun look-ahead n'est possible.

## 15. Compatibilité

Le runner conserve le mode historique `market_data + symbol` pour les tests/consommateurs
existants. Le provider conserve aussi le chemin historique sans `MarketSelection`, y compris sa
boucle de tools optionnelle.

La composition PAPER canonique utilise le chemin multi-marché.

## 16. Validation comportementale connue

Le Batch 18.3 a confirmé le cross-symbol SPOT, le chargement/research d'un univers mixte
SPOT/PERPETUAL et la branche PERPETUAL réelle en singleton jusqu'à la décision et Risk. Il n'a pas
observé de sélection PERPETUAL spontanée depuis l'univers mixte ni de fill réel ; ces absences ne
sont pas transformées en validation.

## 17. LIVE

LIVE reste hors périmètre. Il nécessitera un batch séparé avec adaptateur privé, permissions
minimales sans retrait, idempotence, réconciliation, recovery et activation explicite.
