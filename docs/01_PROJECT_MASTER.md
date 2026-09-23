# 01 — Project Master

## 1. Rôle

AI Spot Trader est une application expérimentale de trading crypto PAPER pilotée par **un seul
Agent IA stratégique**. Le backend est l'application de trading ; le frontend est un cockpit de
contrôle et de visualisation.

Commit d'intégration code du Batch 18.6 :
`9642ec394357fe1e1807b538a2353bdc6d062f46`
(`feat: add durable PAPER ledger recovery`). Le Batch 18.6 est intégré.

Référence de démarrage du Batch 18.6 : `70457125c5a238fe9b798463081c8769d8879d5e`, avec
`84548d23efda0b0a8e2c1350bacc830c1de34140` comme dernier commit code intégré à ce moment-là.

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

## 13. `paper_runs` et recovery durable

Le contrat historique `market_type + symbol` ne suffit pas pour un run multi-marchés.
`0004` ajoute donc `execution_universe_payload` et rend les deux colonnes historiques nullables.

- singleton : les colonnes historiques gardent la vraie paire/type ;
- multi-marchés : elles sont `NULL` ;
- aucun faux marqueur `MULTI`.

Les rows existantes sont backfillées vers un univers singleton lors de la migration.

Le Batch 18.6 ajoute via `0005_paper_run_recovery` :

```text
resumed_from_paper_run_id
recovery_version = paper-ledger-recovery-v1
initial_portfolio_payload
current_portfolio_payload
```

Le `paper_run_id` reste une identité de session backend ; un restart crée donc un nouveau run relié
à son prédécesseur au lieu de réouvrir une ligne historique. Le dernier `PortfolioState` durable
est la source de vérité du restart.

## 14. Analytics

L'analytics passe à `paper-analytics-v3` lorsque plusieurs marchés distincts apparaissent dans le
journal. Les positions SPOT sont valorisées par le dernier mark SPOT causal durable connu pour
chaque `BASE/settlement_asset`.

Un mark absent provoque une erreur de données explicite. Aucune requête marché actuelle n'est
faite pendant le replay et aucun look-ahead n'est possible.

Le recovery 18.6 ne rejoue pas les décisions pour reconstruire le runtime : le cash net déjà payé,
les inventaires SPOT et les champs de position PERPETUAL sont restaurés depuis le `PortfolioState`
durable. Pour les métriques, `paper_analytics_for_run()` suit explicitement la chaîne
`resumed_from_paper_run_id` et rejoue les cycles des ancêtres dans l'ordre, ce qui préserve P&L,
frais, funding, drawdown et compteurs cumulés malgré le changement de `paper_run_id`.

## 15. Protocole expérimental multi-marché — Batch 18.5

Les protocoles historiques restent séparés :

```text
paper-experiment-v1  agressivité contrôlée historique
paper-experiment-v2  comparaison Luna/Sol historique
paper-experiment-v3  comparaison Luna/Sol multi-marché avec environnement Agent versionné
```

`paper-experiment-v3` ajoute à l'identité contrôlée :

- tuple exact et ordonné `ExecutableMarket(symbol, market_type)` ;
- `market_selection_protocol_version` ;
- état tools de la phase sélection et de la phase finale ;
- digest SHA-256 des définitions `ReadOnlyToolRegistry.openai_tools` effectivement exposées ;
- `max_tool_calls` ;
- timeout tools ;
- taille maximale des résultats ;
- maximum du paramètre `limit` de `list_markets` lu depuis le schéma effectif.

Le chemin canonique représenté par v3 fixe : tools possibles en sélection, aucun tool en décision
finale. Le `experiment_group_digest` inclut tous ces facteurs et exclut uniquement `llm_model` et
`replicate_index`.

Le provider refuse avant appel LLM un manifeste v3 dont modèle, prompt, protocole de sélection,
capacité/bornes tools ou phase active ne correspondent pas au runtime. Le runner refuse avant le
premier appel Agent un univers typé différent du manifeste.

`experiment_manifest=None` reste valide pour un run PAPER ordinaire.

## 16. Compatibilité

Le runner conserve le mode historique `market_data + symbol` pour les tests/consommateurs
existants. Le provider conserve aussi le chemin historique sans `MarketSelection`, y compris sa
boucle de tools optionnelle.

La composition PAPER canonique utilise le chemin multi-marché.

Les payloads v1/v2 restent lisibles sans champ v3 ajouté lors de leur sérialisation normale, et
leurs digests historiques restent calculés sur leurs champs historiques uniquement.

## 17. Validation comportementale connue

Le Batch 18.3 a confirmé le cross-symbol SPOT, le chargement/research d'un univers mixte
SPOT/PERPETUAL et la branche PERPETUAL réelle en singleton jusqu'à la décision et Risk. Il n'a pas
observé de sélection PERPETUAL spontanée depuis l'univers mixte ni de fill réel ; ces absences ne
sont pas transformées en validation.

Le Batch 18.5 versionne ce comportement existant ; il ne constitue pas une nouvelle campagne
Luna/Sol et ne change aucune règle de sélection, Risk ou Broker.

## 18. Recovery/restart durable PAPER — Batch 18.6 intégré

Le recovery ne rejoue **aucune** décision historique. La frontière durable est :

```text
checkpoint ledger mémoire
-> cycle Agent/Risk/Broker
-> résultat FAILED : rollback checkpoint, puis audit du failure
-> résultat COMPLETED : audit graph + current_portfolio_payload dans une transaction
-> commit PostgreSQL
-> état mémoire conservé
```

Si l'écriture durable échoue ou si un replay idempotent n'insère aucun nouveau cycle, le checkpoint
mémoire est restauré. Ainsi, une mutation Broker/funding non commitée ne survit pas comme état
runtime.

Au démarrage :

```text
latest paper_run compatible
-> current_portfolio_payload (v1)
   ou migration prudente depuis le dernier cycle COMPLETED legacy
-> validation PortfolioState + univers
-> nouveau paper_run lié par resumed_from_paper_run_id
-> restore PaperPortfolioLedger
```

Fail-closed : univers différent, snapshot invalide, run legacy sans état reconstructible ou run
legacy terminant par un cycle `FAILED` ambigu. Aucun fill, intent ou appel LLM historique n'est
réémis.

Validation locale de l'intégration 18.6 : migration PostgreSQL `0004 -> 0005` OK, 75 tests ciblés,
468 tests backend complets, Ruff OK, mypy OK sur 79 fichiers source et `git diff --check` sans erreur.

Le Batch 18.6 conserve `paper-experiment-v1/v2/v3`, `experiment_manifest=None`,
`agent-strategy-v4`, les règles Risk et le Broker PAPER existants.

## 19. LIVE

LIVE reste hors périmètre. Il nécessitera un batch séparé avec adaptateur privé, permissions
minimales sans retrait, idempotence, réconciliation, recovery et activation explicite.
