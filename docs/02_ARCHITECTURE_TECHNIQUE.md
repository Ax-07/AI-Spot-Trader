# 02 — Architecture technique

## 1. Référence

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD audité: b4f1e50f22164c7d019d11d930485733c01c6711
Batch 19.13                          : intégré
Correctif PAPER PERPETUAL            : intégré dans b4f1e50
Migration Batch 19.13                : 0006_paper_control_plane -> 0007_multi_decision_cycles
```

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

     -> audit LLM process-local borné
        -> frontière OpenAIResponsesClient
        -> payload Responses API exact
        -> output fournisseur exact utile à l'inspection
        -> corrélation cycle/discovery/session
        -> API lecture seule /api/v1/llm-audit

Next.js Marchés / Historique / Réglages > Inspecteur LLM
  -> contrats backend uniquement
  -> aucune autorité d'exécution
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

`MarketResearchService` reste la frontière canonique de recherche publique Kraken. Le filtrage déterministe vérifie uniquement des propriétés techniques/factuelles. Aucun score d'opportunité algorithmique ne remplace le jugement de l'Agent.

En mode `MANUAL`, la discovery est absente et l'univers exécutable est fourni explicitement. En `MANAGEMENT`, aucun refresh IA destiné à de nouvelles ouvertures n'est lancé.

## 5. Données stratégiques causales

`CandleStreamService` reste partagé entre cockpit et runtime Campaign. `StrategicMultiTimeframeContextService` utilise `history_as_of(...)` et le mapping `trading-style-map-v1` pour construire `strategic-mtf-v1`.

Règles conservées : SCALP `1m/5m/15m/30m`, SWING `1h/4h/1d`, gaps conservés, aucune interpolation, aucune révision postérieure à `as_of`, contexte borné. `position-management-v1` et `ExecutionCostContext` restent factuels.

## 6. Un seul Agent, un plan décisionnel

La discovery/watchlist peut conserver sa cadence propre. Une fois le contexte du cycle constitué, un seul appel stratégique produit un plan ordonné sur des marchés distincts. `max_decisions_per_cycle` vaut `6` par défaut et possède une limite dure de `20`.

## 7. Exécution séquentielle et causale

Chaque décision est évaluée par Risk contre le portefeuille résultant des décisions précédentes. `HOLD` et `REJECT` restent des résultats normaux et auditables. `ALLOW`/`MODIFY` peuvent produire un `ExecutionIntent`; aucune sortie Agent ne va directement au Broker.

## 8. Atomicité technique PAPER

Le ledger PAPER est checkpointé au niveau du cycle. Une erreur technique Risk ou Broker transforme le cycle en `FAILED` et restaure le checkpoint initial avant persistance de l'échec.

## 9. Persistence d'audit 1:N

La migration `0007_multi_decision_cycles` conserve plusieurs décisions, évaluations Risk et intentions d'exécution dans leur ordre. La persistence n'invente pas un Risk assessment ou un fill lorsqu'il n'existe pas.

## 10. API et cockpit

L'API de détail de cycle et le cockpit Historique exposent la trajectoire ordonnée Agent -> Risk -> exécution. Le frontend ne réordonne pas la trajectoire et ne recalcule aucune causalité financière.

## 11. Analytics

Les métriques économiques comptent les exécutions/fills réels. Le nombre de décisions du plan n'est pas utilisé comme nombre de trades.

## 12. PAPER PERPETUAL

SPOT et PERPETUAL linéaire sont supportés en PAPER selon la configuration. SPOT reste sans short/levier/marge. Les contrôles PERPETUAL de marge, levier, exposition, liquidation et `reduce_only` restent déterministes. FUTURE daté reste interdit.

## 13. Monitoring / mark-to-market

Les monitors SPOT et PERPETUAL restent des boucles techniques déterministes indépendantes du cycle stratégique. Ils n'appellent pas le LLM et n'altèrent pas le plan.

## 14. Candles et streaming

Le domaine `CandleKey` / `Candle` conserve timestamps UTC, cohérence OHLC, volume non négatif, aucune candle future, gaps non synthétisés et finalisation explicite. Le frontend consomme exclusivement les endpoints/backend WebSocket.

## 15. Lifecycle FastAPI

Le `CandleStreamService` reste possédé par le lifespan FastAPI et partagé avec les runtimes Campaign. Le runtime Campaign est fermé avant le service candles partagé.

## 16. Hors périmètre actuel

- LIVE ;
- FUTURE daté exécutable ;
- multi-quote/FX sans conversion canonique ;
- ranking stratégique déterministe ;
- Risk/P&L parallèle côté frontend ;
- second Agent ;
- promesse de rendement.

## 17. Inspecteur LLM en lecture seule

`OpenAIResponsesClient` est la frontière canonique d'instrumentation. L'audit enregistre uniquement le dictionnaire `request` passé au body JSON de `/responses`, jamais les headers HTTP. La clé OpenAI reste donc confinée à `_post()` et n'entre pas dans la trace.

Pour une tool loop, chaque requête Responses API est enregistrée séparément et ordonnée. L'output `function_call` du fournisseur est visible dans l'entrée correspondante ; la requête suivante contient exactement le `function_call_output` ajouté par le registre read-only.

Le store est process-local et borné (200 entrées, 512 Kio par entrée). Il est volontairement best-effort : toute exception de l'instrumentation est absorbée à la frontière OpenAI et ne change jamais le résultat stratégique ou conversationnel. Cette première version ne crée pas de migration PostgreSQL afin de ne pas rendre le moteur dépendant d'une persistence d'observabilité supplémentaire.
