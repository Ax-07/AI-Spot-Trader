# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **PAPER** sur Kraken, pilotée par **un seul Agent IA stratégique**. L'Agent recherche, sélectionne un marché exécutable puis propose `BUY`, `SELL` ou `HOLD`. Le **Risk Engine déterministe** conserve l'autorité finale : seul Risk peut produire un `ExecutionIntent`, ensuite exécuté par le `PaperBroker`.

> Objectif expérimental : rechercher une performance élevée, avec une cible de travail de +4 %/jour. Ce n'est ni une promesse ni une garantie de rendement.

## Référence auditée — Batch 19.2

```text
repository : Ax-07/AI-Spot-Trader
branche    : main
HEAD base  : 01ca1e857947d969556481e5593c5712d137f5ad
message    : docs: finalize Batch 19.1 integration state
```

Le Batch 19.1 est intégré. Le Batch 19.2 est livré comme patch local à valider/intégrer explicitement par l'opérateur.

## Invariants

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- PAPER uniquement ;
- SPOT sans short, levier ni marge ;
- PERPETUAL linéaire LONG/SHORT, marge `ISOLATED` ;
- levier configuré/déterministe, jamais choisi par le LLM ;
- aucune sortie LLM -> Broker ;
- aucun tool -> Broker/Risk ;
- Risk autorise, modifie ou refuse et garde l'autorité finale ;
- comptabilité et mark-to-market canoniques dans le backend ;
- aucun secret dans les prompts, Campaigns, réponses UI ou fichiers versionnés ;
- aucun replay LLM/Risk/Broker/Fill lors du recovery ;
- aucun look-ahead ;
- toutes les décisions, dont `HOLD`, restent auditables ;
- le backend reste indépendant du frontend.

Principe : **l'Agent propose. Le Risk Engine autorise, modifie ou refuse.**

## Pipeline canonique

```text
PaperSpotMarkToMarketMonitor -----------+
PaperDerivativeMarkToMarketMonitor -----+
                                        |
PortfolioState marqué                   |
        |                               |
        v                               |
MarketSelectionInput                    |
        |                               |
        v                               |
OpenAIDecisionProvider (Agent unique)   |
        |\                              |
        | +--> tools read-only Kraken   |
        v                               |
MarketSelection                         |
        |                               |
        v                               |
RoutedExecutableMarketDataSource -------+
        |
        v
MarketState canonique exact -> mark ledger
        |
        v
AgentInput -> même Agent -> BUY / SELL / HOLD
        |
        v
RiskEngine -> ALLOW / MODIFY / REJECT
        |
        v
ExecutionIntent éventuel -> PaperBroker -> Fill
        |
        v
PaperPortfolioLedger -> audit PostgreSQL + snapshot durable
```

Le frontend n'appartient pas à cette chaîne d'exécution.

## Comptabilité et mark-to-market SPOT

La comptabilité Batch 19.1 utilise un coût économique moyen pondéré :

```text
average_entry_price = remaining_cost_basis / quantity
```

Le coût restant inclut les débits cash BUY réels, frais inclus. Les SELL libèrent la base au prorata et réalisent le P&L sur le crédit cash net. Spread/slippage sont déjà dans le prix de fill et ne sont jamais ajoutés deux fois.

Le Batch 19.2 ajoute le mark-to-market :

```text
mark_price     = dernier prix ticker Kraken causal
market_value   = quantity * mark_price
unrealized_pnl = market_value - remaining_cost_basis
```

Le P&L latent n'est produit que si la base de coût est complète. Un mark absent ou périmé devient explicitement indisponible. Les positions legacy peuvent être valorisées au marché sans inventer de P&L latent.

Le backend peut également exposer cash, valeur SPOT, P&L réalisé/latent, equity et exposition au niveau portefeuille. Le frontend affiche ces valeurs sans les recalculer.

## Monitoring backend sans LLM

Le mark-to-market possède des cadences techniques indépendantes du cycle stratégique :

```text
AI_SPOT_TRADER_PAPER_MARK_TO_MARKET_CADENCE_SECONDS=5
AI_SPOT_TRADER_PAPER_DERIVATIVE_MARK_TO_MARKET_CADENCE_SECONDS=15
AI_SPOT_TRADER_PAPER_MARK_TO_MARKET_TIMEOUT_SECONDS=5
AI_SPOT_TRADER_PAPER_MARK_TO_MARKET_STALE_AFTER_SECONDS=30
```

Le monitor ne peut ni sélectionner un trade, ni appeler Risk, ni appeler Broker. Il reste lié au runtime backend actif, pas au navigateur.

## Control Plane et cockpit

`Strategy`, `StrategyRevision`, `Campaign` et `paper_run` conservent leurs rôles : configuration/stratégie immuable d'un côté, lifetime d'exécution/recovery de l'autre.

Le cockpit permet notamment de créer/configurer des tests PAPER, activer/reprendre une Campaign, lancer un cycle ou le moteur autonome, lire les positions et l'historique. Fermer le frontend n'arrête ni le moteur backend ni le monitoring du runtime actif.

## Recovery

`paper-ledger-recovery-v1` restaure le snapshot canonique sans replay Agent/Risk/Broker/Fill. Les champs 19.2 sont persistés dans le JSON `PortfolioState`, sans migration SQL supplémentaire.

Un mark restauré est toujours soumis à la règle de fraîcheur courante. Un snapshot historique incapable d'établir le P&L réalisé global conserve cette valeur inconnue ; aucun historique n'est fabriqué.

## API principales

Sous `/api/v1`, le Control Plane expose Strategies, Campaigns, prompt preview, paper runs, moteur, portfolio, audit et analytics. Les commandes moteur restent :

```text
POST /api/v1/engine/run-cycle
POST /api/v1/engine/start
POST /api/v1/engine/stop
```

## Persistence PostgreSQL

```text
0001_create_audit_journal
-> 0002_add_paper_runs
-> 0003_agent_tool_traces
-> 0004_multi_market_selection
-> 0005_paper_run_recovery
-> 0006_paper_control_plane
```

Aucune migration SQL supplémentaire n'est requise par les Batches 19.1/19.2 ; les nouveaux champs portefeuille sont dans les snapshots JSON existants.

## Suite de la roadmap

- 19.3 : mode gestion à exposition saturée et économie d'appels IA ;
- 19.4 : discovery/watchlist dynamique et auditée ;
- 19.5 : explicabilité IA/Risk ;
- 19.6A/19.6B : candles/streaming puis vue Marchés/charts.

Le détail est dans `docs/09_ROADMAP_DEVELOPPEMENT.md` et `docs/11_AMELIORATIONS_PLANIFIEES.md`.
