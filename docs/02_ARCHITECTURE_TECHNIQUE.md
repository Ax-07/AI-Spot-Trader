# 02 — Architecture technique

## 1. Référence

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
Référence fonctionnelle Batch 19.6B : a446628918a614d2ae0ac3b55243881aad5ef410
Référence fonctionnelle Batch 19.7  : 8b969b434916d89f6b6aa127c3bac9c27e990966
Référence fonctionnelle Batch 19.8  : f3a8eae8528648c07723aa97350852428254acc7
Correctif fonctionnel post-19.8      : 0d964624a641aad509f5728264f873c1a837af97
Référence fonctionnelle Batch 19.9A : 4b6a851addea74d72af2c433827c935a87d4bc04
Sync documentaire post-19.9A        : a4f841c7c23e3af1b44a9cbb104ccc44d5cad2d9
HEAD GitHub / Batch 19.9B           : 88be7d50111c2e6210225071d3f1af3f7f07b4f0
```

Les Batches 19.1 à 19.9B sont intégrés. Le présent document décrit l'architecture fonctionnelle intégrée après le Batch 19.9B.

## 2. Architecture générale

```text
Next.js cockpit
  -> FastAPI
     -> façade utilisateur Sessions
        -> Strategy = identité technique stable
        -> StrategyRevision(s) immuables
        -> Campaign(s) immuables/versionnées
        -> paper_run(s) / recovery

     -> Control Plane PostgreSQL
     -> CampaignRuntimeManager
        -> CandleStreamService partagé
           -> StrategicMultiTimeframeContextService
              -> MultiTimeframeDecisionProvider
                 -> même Agent stratégique
        -> TradingEngine
        -> AuditedTradingCycleRunner
        -> DynamicMarketTradingCycleRunner
           -> MarketDiscoveryCoordinator
              -> MarketResearchService
                 -> KrakenMarketResearchBackend
              -> même Agent stratégique pour la watchlist
           -> TradingCycleRunner canonique
        -> CapacityEvaluator
        -> RiskEngine
        -> PaperBroker
        -> PaperPortfolioLedger
        -> monitors mark-to-market SPOT/PERPETUAL

     -> CandleStreamService
        -> KrakenCandleProvider
           -> SPOT REST OHLC + WS v2 OHLC
           -> PERPETUAL Futures charts + WS public trade
        -> CandleCache borné
        -> API historique / WebSocket cockpit
        -> history_as_of(...) pour le contexte stratégique

Next.js vue Marchés
  -> contrats REST/WS backend uniquement
  -> cache client mémoire borné
  -> Lightweight Charts
  -> fills persistés pour markers
  -> portefeuille backend pour overlays de position
```

Le `CandleStreamService` représenté dans les deux branches du schéma est une **même instance backend partagée**, pas deux services. Le frontend n'est jamais dans la chaîne d'exécution trading. Fermer ou redémarrer le cockpit n'arrête ni le moteur de trading backend ni les streams backend déjà ouverts.

## 3. Sessions — façade utilisateur intégrée 19.8

`Session` est le concept principal du parcours utilisateur, sans devenir une nouvelle table ni une source de vérité concurrente.

```text
Session UX
-> Strategy
-> StrategyRevision(s)
-> Campaign(s)
-> paper_run(s)
```

Règles intégrées :

- l'identité de Session est la `Strategy` ;
- la création Session persiste atomiquement Strategy + révision 1 + Campaign ;
- modifier le prompt crée une nouvelle `StrategyRevision` ;
- modifier la configuration crée une nouvelle `Campaign` ;
- renommer modifie uniquement le nom de Strategy ;
- supprimer côté UX archive la Strategy ;
- les statuts Session sont dérivés des faits persistés et du runtime ;
- `stop` ferme explicitement la boucle, le runtime et le `paper_run` ;
- `resume` reste explicite après historique/restart ;
- aucune table SQL `sessions` n'est ajoutée.

Le mode normal du cockpit masque les concepts techniques Strategy/Revision/Campaign. Le Control Plane technique reste disponible en mode avancé.

## 4. Recherche de marché et discovery

`MarketResearchService` reste la frontière canonique de recherche publique Kraken. La discovery ne crée aucun scanner stratégique parallèle.

```text
Kraken catalogue
-> compatibilité déterministe
-> rotation bornée de marchés à sonder
-> snapshots de recherche causaux
-> candidats factuels
-> même Agent -> watchlist
-> watchlist + positions ouvertes
-> RoutedExecutableMarketDataSource
```

Le filtrage déterministe vérifie uniquement des propriétés techniques ou factuelles. Aucun indicateur n'est transformé en score stratégique d'opportunité.

## 5. `MarketDiscoveryPolicy` et modes de marchés Session

La policy persiste les bornes de discovery dans la Campaign. `MarketDiscoveryCoordinator` maintient un cache process-local du catalogue, du curseur de probe, de la dernière watchlist stratégique valide et de l'audit associé.

Le refresh est borné par timeout. Une erreur Kraken, LLM ou validation déclenche le fallback documenté vers la dernière watchlist valide, puis vers le bootstrap si nécessaire. En `MANAGEMENT`, aucune révision IA de watchlist destinée à de nouvelles ouvertures n'est lancée.

Deux modes sont exposés par la façade Session :

- `AUTOMATIC_AI` : `market_discovery` est présent ; le bootstrap sert de point de départ/fallback et l'Agent peut choisir une watchlist parmi les marchés techniquement admissibles ;
- `MANUAL` : `market_discovery = null` et l'univers exécutable est fourni explicitement par l'utilisateur.

Dans les deux modes, le même Agent conserve BUY / SELL / HOLD et le Risk Engine reste l'autorité finale.

## 6. Même Agent IA et exécution canonique

`OpenAIWatchlistSelector` réutilise la même instance d'Agent stratégique. La sélection d'une watchlist ne crée aucun `ExecutionIntent`.

`DynamicMarketTradingCycleRunner` prépare l'univers puis délègue au runner de trading canonique. Risk, Broker et validations causales ne sont pas dupliqués. Les positions ouvertes restent toujours dans l'univers gérable.

Depuis 19.9B, `MultiTimeframeDecisionProvider` décore ce même Agent pour Market Selection et la décision finale. Il ne constitue pas un second Agent : il enrichit les inputs avec le snapshot candles stratégique puis délègue à `OpenAIDecisionProvider`.

## 7. Monitoring / mark-to-market

Les monitors SPOT et PERPETUAL restent des boucles techniques déterministes, indépendantes du cycle stratégique et de la discovery. Ils n'appellent pas le LLM et ne modifient pas la watchlist.

Leur rôle est la valorisation PAPER : marks, P&L latent, exposition, marge, liquidation et funding selon le type de marché.

## 8. Explicabilité intégrée 19.5

L'explicabilité est une projection de lecture à partir des faits déjà persistés. Elle sépare contexte/discovery, sélection de marché, Agent, Risk et exécution PAPER. Elle ne recalcule ni stratégie, ni Risk, ni P&L et n'invente aucune rationale absente.

La vue Marchés 19.6B réutilise cette projection lorsqu'un marker de fill est sélectionné. Aucun lien causal supplémentaire n'est fabriqué dans le frontend.

## 9. Domaine candle canonique — 19.6A

Le domaine de présentation marché reste distinct du domaine stratégique :

```text
CandleKey = canonical symbol + MarketType + CandleTimeframe
Candle    = open_time + close_time + OHLCV + is_final + updated_at
```

Règles :

- symbole canonique `BASE/QUOTE` en uppercase ;
- timestamps timezone-aware et normalisés UTC ;
- `close_time = open_time + timeframe` ;
- une candle finalisée ne peut pas être disponible avant sa clôture ;
- cohérence OHLC validée ;
- volume non négatif ;
- aucune candle avec `open_time` future n'entre dans le cache ;
- les trous temporels restent des trous : aucune candle n'est synthétisée.

Le champ `is_final` distingue explicitement la candle courante mutable d'une candle clôturée.

## 10. Timeframes bornés

SPOT : `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`, `15d`.

PERPETUAL : `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `12h`, `1d`, `1w`.

Un timeframe non supporté pour le type de marché est rejeté avant abonnement fournisseur. FUTURE daté reste hors périmètre d'exécution.

## 11. Historique initial et limites fournisseur

### SPOT

`KrakenPublicRestClient` conserve son API historique et ajoute une lecture OHLCV dédiée au cockpit. L'endpoint Spot OHLC fournit au maximum 720 rows ; le backend ne prétend donc pas fournir 1000 candles Spot à partir d'un seul appel.

La dernière row retournée est conservée comme candle courante non finalisée dans le contrat chart.

### PERPETUAL

Le provider réutilise le catalogue `KrakenDerivativesPublicClient` pour résoudre le `venue_symbol` d'un PERPETUAL linéaire puis interroge l'endpoint public Futures charts `mark/<venue>/<resolution>`.

La cible de requête est bornée à 1000 rows, mais la profondeur effective reste celle réellement retournée par Kraken. Aucun row manquant n'est inventé.

## 12. Cache backend

`CandleCache` est process-local et borné. Il n'ajoute aucune table SQL.

Pour chaque `CandleKey` :

- ordre chronologique garanti ;
- déduplication par `open_time` ;
- remplacement d'une candle courante par une version plus récente ;
- une candle finalisée ne peut pas être rétrogradée en candle courante ;
- profondeur maximale bornée, 1000 par défaut ;
- aucune croissance mémoire non bornée.

La persistence durable des candles n'est pas justifiée à l'état intégré : PostgreSQL reste réservé aux faits métier/audit qui doivent survivre au process.

## 13. Streaming Kraken SPOT

`KrakenOhlcWebSocketClient` réutilise l'infrastructure publique WebSocket Kraken existante et le même protocole de connexion abstrait.

Il :

- souscrit au canal v2 `ohlc` pour un symbole/timeframe ;
- met à jour la candle courante ;
- marque la candle précédente finalisée lorsque l'intervalle suivant apparaît ;
- rejette symbole/timeframe incohérents ;
- envoie un unsubscribe best-effort au cleanup ;
- ferme toujours la connexion détenue par le générateur.

La reconnexion globale et le backfill appartiennent au hub `CandleStreamService`.

## 14. Streaming Kraken PERPETUAL

Kraken Futures ne fournit pas un flux OHLC public équivalent au canal Spot v2 utilisé ici. Le provider réutilise donc le WebSocket public Futures `trade` et agrège uniquement les trades réellement reçus pour construire la candle courante.

À la transition d'intervalle, la candle précédente est finalisée. Si aucun trade n'existe pour un intervalle, aucune candle synthétique n'est créée.

Après reconnexion ou gap détecté, le hub demande un backfill au endpoint Futures charts puis fusionne et déduplique avant de poursuivre le flux.

## 15. `CandleStreamService`

Le service est propriétaire backend des streams :

```text
premier besoin sur une CandleKey
-> backfill REST
-> création d'un seul task provider pour cette clé
-> fan-out vers N consommateurs cockpit
-> cache partagé
```

Propriétés :

- un seul stream provider par clé ;
- nombre total de streams actifs borné ;
- queues consommateurs bornées ;
- backfill initial et après reconnexion ;
- détection d'un trou avant une update et tentative de recovery ;
- merge/déduplication avant publication ;
- statut `connected`, `stale`, `last_update_at`, `last_error` ;
- fermeture de tous les tasks et transports au shutdown backend.

Le Batch 19.9B ajoute `history_as_of(...)` comme lecture stratégique causale du même cache/provider. Une candle n'est retenue que si sa révision était disponible à `as_of`; une finale doit aussi être clôturée à `as_of`. Les backfills historiques ne reconstruisent pas artificiellement une candle active passée à partir de son état actuel.

## 16. API cockpit candles

Le backend expose :

```text
GET /api/v1/markets/candles
GET /api/v1/markets/candles/status
WS  /api/v1/markets/candles/stream
```

Le GET retourne l'historique canonique et le statut technique. Le WebSocket envoie d'abord un snapshot, puis les updates provenant du hub partagé.

Le frontend consomme exclusivement ces contrats et n'ouvre aucune seconde connexion directe à Kraken.

## 17. Vue Marchés — 19.6B

La vue Marchés intégrée :

- construit son univers depuis la watchlist effective lorsque disponible, sinon depuis le bootstrap actif, puis réinjecte les positions ouvertes ;
- charge un seul marché/timeframe actif à la fois ;
- maintient un cache mémoire client borné ;
- nettoie socket, listeners et timers au changement ou démontage ;
- rend chandeliers, volume et markers de fills via Lightweight Charts ;
- affiche les faits position SPOT/PERPETUAL depuis `/portfolio` ;
- recharge `/cycles/{cycle_id}` pour le détail explicable d'un fill ;
- ne calcule ni P&L, ni exposition, ni liquidation, ni stratégie à partir des candles.

Les markers proviennent uniquement des fills persistés. Les candles ne servent jamais à inférer un ordre, une clôture ou une causalité.

## 18. Overlays de position — 19.7

Le Batch 19.7 ajoute les overlays de position canoniques au chart Marchés :

- prix moyen d'entrée lorsqu'une position et une valeur canonique sont disponibles ;
- mark backend lorsqu'il est disponible ;
- liquidation pour PERPETUAL lorsqu'elle est disponible.

Les lignes sont de simples projections visuelles de faits portefeuille backend. Le frontend ne recalcule ni prix moyen, ni mark, ni liquidation, ni P&L.

Le lifecycle du chart retire ou remplace les lignes lors d'un changement de marché, timeframe ou position afin d'éviter de conserver une donnée d'un contexte précédent.

Référence fonctionnelle : `8b969b434916d89f6b6aa127c3bac9c27e990966`.

## 19. Lifecycle FastAPI

Le service de candles est créé dans le lifespan FastAPI avec les URLs/timeouts Kraken présents dans `Settings`. Aucun nouveau secret ni paramètre stratégique n'est introduit.

Depuis 19.9B, `CampaignRuntimeManager` reçoit l'instance partagée de `CandleStreamService`. La composition Campaign l'utilise pour construire `StrategicMultiTimeframeContextService`, mais le runtime Campaign n'en devient pas propriétaire.

Ordre de shutdown intégré :

```text
FastAPI lifespan shutdown
-> runtime.close()
   -> fermeture du Campaign runtime actif le cas échéant
-> resolved_candle_service.aclose()
   -> fermeture des tasks/streams/provider candles partagés
```

Cet ordre est volontaire : un Campaign runtime peut encore lire le service candles partagé pendant son cleanup. Le `CandleStreamService` ne doit donc pas être fermé avant le runtime Campaign.

Les cadences restent distinctes :

1. monitoring / mark-to-market ;
2. cycle stratégique IA ;
3. discovery / watchlist IA ;
4. streaming marché / candles sans LLM.

## 20. Persistence / audit

Aucune migration SQL n'est introduite par 19.6A, 19.6B, 19.7, 19.8, 19.9A ou 19.9B pour les candles, charts, overlays, façade Session ou contexte multi-timeframes.

Le cache candles n'est pas utilisé comme source de vérité d'exécution, Risk ou portfolio. Pour la décision Agent, il fournit uniquement des faits de marché causaux via le contexte `strategic-mtf-v1`.

Les payloads persistés `MarketSelectionInput` et `AgentInput` embarquent le contexte multi-timeframes optionnel lorsqu'il existe. Les anciens payloads et Campaigns sans `trading_style` restent valides.

Les faits durables restent portés par les tables canoniques Strategy/Revision/Campaign/paper_run/audit. La façade Session ne duplique pas cet état.

## 21. Hors périmètre actuel

Restent hors de l'état intégré :

- LIVE ;
- support d'exécution FUTURE daté ;
- multi-quote/FX sans contrat de conversion canonique ;
- persistence durable des candles sans besoin démontré ;
- ranking stratégique déterministe ;
- calcul Risk/P&L parallèle côté frontend ;
- second Agent ou contournement du Risk Engine ;
- fermeture automatique liée au style de trading.

## 22. Batch 19.9A — Overlay Trading Style et coûts Agent

Le Batch 19.9A étend la configuration JSON de Campaign sans migration SQL et sans augmenter `paper-control-plane-config-v1`. Les champs optionnels `trading_style` et `trading_style_mapping_version` sont omis du payload canonique lorsqu'ils sont absents ; les Campaigns historiques gardent donc leur digest précédent.

Flux de contexte 19.9A :

```text
CampaignConfiguration
  -> TradingStyleContext (trading-style-map-v1)
  -> ExecutionCostContext (fee/spread/slippage PAPER)
  -> MarketDiscoveryInput
  -> MarketSelectionInput
  -> AgentInput
```

`DynamicMarketTradingCycleRunner` conserve ces deux contextes et les retransmet au `TradingCycleRunner` canonique qu'il reconstruit. Il n'existe aucun second Agent ni pipeline stratégique parallèle. Les faits structurés restent auditables dans les inputs/audits persistés.

Le mapping v1 est purement stratégique :

- `SCALP` préfère `1m`, `5m`, `15m`, `30m` ;
- `SWING` préfère `1h`, `4h`, `1d` ;
- aucune préférence de timeframe ne devient une contrainte Risk ni un timer de sortie.

La composition d'instructions ajoute des sections canoniques dérivées des contextes structurés. En leur absence, les Campaigns historiques conservent la composition legacy. `agent-contract-v1` n'est pas modifié.

Le Batch 19.9B consomme désormais ces préférences pour construire le contexte candles stratégique ; il ne redéfinit pas le mapping SCALP/SWING.

## 23. Batch 19.9B — Contexte stratégique multi-timeframes

Raccordement intégré :

```text
CampaignRuntimeManager
-> CandleStreamService partagé
-> StrategicMultiTimeframeContextService
-> MultiTimeframeDecisionProvider
-> même Agent stratégique
```

`StrategicMultiTimeframeContextService` produit `strategic-mtf-v1` à partir de `TradingStyleContext.preferred_timeframes`. Les profondeurs d'historique sont des bornes de volume, pas un second mapping stratégique : `1m=12`, `5m=12`, `15m=10`, `30m=8`, `1h=16`, `4h=12`, `1d=10`.

Le contexte est borné à 32 marchés, 128 KiB JSON et 4 lectures concurrentes. Pour chaque timeframe il expose notamment la disponibilité `AVAILABLE` / `PARTIAL` / `MISSING`, la couverture, les gaps, stale, la dernière candle et des statistiques OHLCV descriptives. Aucun gap n'est interpolé.

Causalité : `history_as_of(...)` exclut les révisions `updated_at > as_of`; une candle finale requiert `close_time <= as_of`; une candle active n'est utilisable que si sa révision exacte était déjà connue à `as_of`. Une révision actuelle ne sert jamais à rétro-projeter artificiellement l'état d'une candle active passée.

Snapshot de cycle : le contexte est construit à `MarketSelectionInput.created_at`, attaché à Market Selection puis conservé par `MultiTimeframeDecisionProvider` et réutilisé inchangé pour l'`AgentInput` final. Le fallback legacy single-market avec style explicite construit le contexte à `AgentInput.created_at`.

Discovery reste volontairement légère avant cet enrichissement. `ExecutionCostContext` demeure séparé. Risk Engine, broker, contrats de sortie Agent et règles de décision restent inchangés : aucune statistique technique ne déclenche directement BUY, SELL ou HOLD.
