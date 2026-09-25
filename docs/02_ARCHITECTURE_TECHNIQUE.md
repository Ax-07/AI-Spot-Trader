# 02 — Architecture technique

## 1. Référence

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
Référence d'audit avant cette fusion documentaire : a254df4d56208c4472bb97b9b80077ad0856f9cd
Référence fonctionnelle Batch 19.6B : a446628918a614d2ae0ac3b55243881aad5ef410
Référence fonctionnelle Batch 19.7  : 8b969b434916d89f6b6aa127c3bac9c27e990966
Référence fonctionnelle Batch 19.8  : f3a8eae8528648c07723aa97350852428254acc7
```

Les Batches 19.1 à 19.8 sont intégrés. Le présent document décrit l'architecture fonctionnelle intégrée jusqu'au Batch 19.8.

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

Next.js vue Marchés
  -> contrats REST/WS backend uniquement
  -> cache client mémoire borné
  -> Lightweight Charts
  -> fills persistés pour markers
  -> portefeuille backend pour overlays de position
```

Le frontend n'est jamais dans la chaîne d'exécution trading. Fermer ou redémarrer le cockpit n'arrête ni le moteur de trading backend ni les streams backend déjà ouverts.

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

Au shutdown, `CandleStreamService` ferme ses tasks/provider puis le runtime trading poursuit son cleanup canonique.

Les cadences restent distinctes :

1. monitoring / mark-to-market ;
2. cycle stratégique IA ;
3. discovery / watchlist IA ;
4. streaming marché / candles sans LLM.

## 20. Persistence / audit

Aucune migration SQL n'est introduite par 19.6A, 19.6B, 19.7 ou 19.8 pour les candles, charts, overlays ou façade Session.

Le cache candles n'est pas utilisé comme source de vérité d'exécution, Risk, portfolio ou décision Agent.

Les faits durables restent portés par les tables canoniques Strategy/Revision/Campaign/paper_run/audit. La façade Session ne duplique pas cet état.

## 21. Hors périmètre actuel

Restent hors de l'état intégré :

- LIVE ;
- support d'exécution FUTURE daté ;
- multi-quote/FX sans contrat de conversion canonique ;
- persistence durable des candles sans besoin démontré ;
- ranking stratégique déterministe ;
- calcul Risk/P&L parallèle côté frontend ;
- second Agent ou contournement du Risk Engine.
