# 02 — Architecture technique

## 1. Référence

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
Base GitHub avant Batch 19.13         : 18596ac9d4f6554aa4817a9bdb374ab597c2399f
Correctif PAPER PERPETUAL intégré    : fix: harden paper perpetual execution precision
Batch 19.13                          : présent dans cet état et validé
Migration Batch 19.13                : 0006_paper_control_plane -> 0007_multi_decision_cycles
```

Le présent document décrit l'architecture du repository avec le Batch 19.13 appliqué ; le SHA ci-dessus est la base GitHub vérifiée avant ce batch.

## 2. Architecture générale

```text
Next.js cockpit
  -> FastAPI
     -> façade Sessions
        -> Strategy
        -> StrategyRevision(s)
        -> Campaign(s)
        -> paper_run(s) / recovery

     -> Control Plane PostgreSQL
     -> CampaignRuntimeManager
        -> CandleStreamService partagé
           -> StrategicMultiTimeframeContextService
              -> même Agent stratégique
        -> DynamicMarketTradingCycleRunner
           -> MarketDiscoveryCoordinator
              -> MarketResearchService
                 -> KrakenMarketResearchBackend
              -> même Agent pour la watchlist
           -> cycle stratégique canonique
              -> un appel Agent de planification
              -> plan ordonné multi-marchés
              -> boucle séquentielle Decision -> Risk -> Broker éventuel
        -> CapacityEvaluator
        -> RiskEngine
        -> PaperBroker
        -> PaperPortfolioLedger
        -> monitors mark-to-market SPOT/PERPETUAL

     -> audit PostgreSQL
        -> cycle
        -> decisions ordonnées 1:N
        -> risk assessments 1:N
        -> execution intents 1:N
        -> fills

Next.js Marchés / Historique
  -> contrats REST/WS backend uniquement
  -> candles/fills/portfolio/audit persistés
  -> trajectoire ordonnée du cycle
```

Le frontend n'appartient jamais à la chaîne d'exécution. Fermer ou redémarrer le cockpit n'arrête ni le moteur de trading backend ni les streams backend déjà ouverts.

## 3. Sessions et immutabilité

`Session` reste une façade UX, pas une source de vérité concurrente :

```text
Session UX
-> Strategy
-> StrategyRevision(s)
-> Campaign(s)
-> paper_run(s)
```

Création atomique, versioning de configuration, archivage logique, start/stop/resume/run-cycle et recovery restent inchangés dans leur principe. Une Session RUNNING doit être arrêtée avant une modification de configuration.

## 4. Recherche de marché et discovery

`MarketResearchService` reste la frontière canonique de recherche publique Kraken.

```text
Kraken catalogue
-> compatibilité déterministe
-> snapshots causaux
-> candidats factuels
-> même Agent -> watchlist
-> watchlist + positions ouvertes
-> univers remis au cycle stratégique
```

Le filtrage déterministe vérifie uniquement des propriétés techniques/factuelles. Aucun score d'opportunité algorithmique ne remplace le jugement de l'Agent.

En mode `MANUAL`, la discovery est absente et l'univers exécutable est fourni explicitement. En `MANAGEMENT`, aucun refresh IA destiné à de nouvelles ouvertures n'est lancé.

## 5. Données stratégiques causales

`CandleStreamService` reste partagé entre cockpit et runtime Campaign. `StrategicMultiTimeframeContextService` utilise `history_as_of(...)` et le mapping `trading-style-map-v1` pour construire `strategic-mtf-v1`.

Règles conservées :

- SCALP : `1m`, `5m`, `15m`, `30m` ;
- SWING : `1h`, `4h`, `1d` ;
- gaps conservés ;
- aucune interpolation ;
- aucune révision de candle postérieure à `as_of` ;
- contexte borné en taille, nombre de marchés et concurrence.

Le contexte de gestion de position `position-management-v1` et `ExecutionCostContext` restent factuels. Aucun de ces contextes ne génère directement une décision.

## 6. Un seul Agent, un plan décisionnel

La discovery/watchlist peut conserver sa cadence propre. Une fois le contexte du **cycle décisionnel** constitué, le Batch 19.13 utilise un seul appel stratégique pour produire un plan ordonné de décisions sur des marchés distincts.

```text
CycleContext
-> Agent stratégique unique
-> OrderedDecisionPlan
   [D1, D2, ... Dn]
```

Le plan est borné par `max_decisions_per_cycle` : défaut `6`, hard limit `20`.

Le fait de produire plusieurs décisions ne crée pas plusieurs Agents et ne transforme pas Risk en stratégie algorithmique.

## 7. Exécution séquentielle et causale

Le plan est traité strictement dans l'ordre :

```text
portfolio_0
  -> Risk(D1, portfolio_0)
  -> Broker éventuel
  -> portfolio_1
  -> Risk(D2, portfolio_1)
  -> Broker éventuel
  -> portfolio_2
  -> ...
```

Chaque décision suivante voit donc le portefeuille après les exécutions précédentes. Cette propriété est indispensable pour éviter le sur-engagement et pour permettre une rotation de capital causale.

`HOLD` et `REJECT` sont des résultats normaux : ils sont persistés et la boucle continue. `ALLOW`/`MODIFY` peuvent produire un `ExecutionIntent`; aucune sortie Agent ne va directement au Broker.

## 8. Atomicité technique PAPER

Le ledger PAPER est checkpointé au niveau du cycle. Une erreur **technique** Risk ou Broker transforme le cycle en `FAILED` et restaure le checkpoint initial avant persistance de l'échec.

Ainsi, un cycle qui a déjà exécuté D1 puis rencontre un échec Broker sur D2 ne laisse pas la mutation économique de D1 dans le portefeuille PAPER.

Cette atomicité ne s'applique pas à `HOLD` ou `REJECT`, qui ne sont pas des erreurs.

## 9. Persistence d'audit 1:N

Le Batch 19.13 introduit la migration :

```text
0006_paper_control_plane
-> 0007_multi_decision_cycles
```

La cardinalité du cycle devient explicitement :

```text
trading_cycle 1 -> N decisions
trading_cycle 1 -> N risk assessments
trading_cycle 1 -> N execution intents
execution intent -> fills éventuels
```

L'ordre de la trajectoire est conservé pour la relecture. Les anciens cycles/configurations restent compatibles.

La persistence n'invente pas un Risk assessment ou un fill lorsqu'il n'existe pas ; elle conserve les étapes réellement traversées.

## 10. API et cockpit

L'API de détail de cycle et le cockpit Historique exposent une trajectoire ordonnée plutôt qu'un unique bloc Agent/Risk/exécution.

Pour chaque élément, l'UI peut présenter :

```text
ordre
marché
BUY / SELL / HOLD
rationale Agent
résultat Risk
ExecutionIntent éventuel
fills éventuels
```

Le frontend ne réordonne pas la trajectoire et ne recalcule aucune causalité financière.

## 11. Analytics

Les métriques économiques comptent les exécutions/fills réels. Le nombre de décisions du plan n'est pas utilisé comme nombre de trades.

Un `HOLD`, un `REJECT` ou une décision autorisée sans fill ne doit pas gonfler le nombre de trades ni le volume exécuté.

## 12. Correctif PAPER PERPETUAL intégré

Le HEAD `18596ac…` durcit l'exécution PAPER des PERPETUAL :

- notional calculé avec l'ordre canonique `price × quantity × contract_size` ;
- spread/slippage réconciliés avec le coût adverse exact attendu par `Fill` ;
- quantités Risk rabattues vers le bas sur le quantum provider-derived ;
- minimums, plafond de notional, marge et `reduce_only` revalidés après normalisation ;
- rollback du ledger audité préservé en cas d'échec Broker.

## 13. Monitoring / mark-to-market

Les monitors SPOT et PERPETUAL restent des boucles techniques déterministes indépendantes du cycle stratégique. Ils n'appellent pas le LLM et n'altèrent pas le plan.

Leur rôle reste la valorisation PAPER : marks, P&L latent, exposition, marge, liquidation et funding selon le marché.

## 14. Candles et streaming

Le domaine `CandleKey` / `Candle` reste inchangé dans ses invariants : timestamps UTC, cohérence OHLC, volume non négatif, aucune candle future, gaps non synthétisés, finalisation explicite.

Le frontend consomme exclusivement les endpoints/backend WebSocket et n'ouvre aucune connexion stratégique parallèle à Kraken.

## 15. Lifecycle FastAPI

Le `CandleStreamService` reste possédé par le lifespan FastAPI et partagé avec les runtimes Campaign. Le runtime Campaign est fermé avant le service candles partagé.

Les cadences restent distinctes :

1. monitoring / mark-to-market ;
2. cycle stratégique IA multi-décisions ;
3. discovery / watchlist IA ;
4. streaming marché / candles sans LLM.

## 16. Hors périmètre actuel

- LIVE ;
- FUTURE daté exécutable ;
- multi-quote/FX sans conversion canonique ;
- persistence durable des candles sans besoin démontré ;
- ranking stratégique déterministe ;
- Risk/P&L parallèle côté frontend ;
- second Agent ;
- fermeture automatique liée au style ;
- promesse de rendement.
