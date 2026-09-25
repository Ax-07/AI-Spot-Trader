# 02 — Architecture technique

## 1. Référence

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
Référence fonctionnelle intégrée Batch 19.6A : 3c53af3bdb1ef53c574e26afe9b6178a374d9f06
```

Les Batches 19.1 à 19.6A sont intégrés. Le Batch 19.6A a été validé localement puis intégré sur GitHub `main` au commit `3c53af3bdb1ef53c574e26afe9b6178a374d9f06`.

## 2. Architecture générale

```text
Next.js cockpit
  -> FastAPI
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

     -> CandleStreamService (19.6A)
        -> KrakenCandleProvider
           -> SPOT REST OHLC + WS v2 OHLC
           -> PERPETUAL Futures charts + WS public trade
        -> CandleCache borné
        -> API historique / WebSocket cockpit
```

Le frontend n'est jamais dans la chaîne d'exécution trading. Le service de candles appartient au processus backend et ne dépend pas du lifecycle d'un onglet cockpit.

## 3. Recherche de marché et discovery

`MarketResearchService` reste la frontière canonique de recherche publique Kraken. La discovery 19.4 ne crée aucun scanner stratégique parallèle.

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

Le filtrage déterministe vérifie uniquement des propriétés techniques/factuelles. Aucun indicateur n'est transformé en score d'opportunité.

## 4. `MarketDiscoveryPolicy` et coordinateur

La policy persiste les bornes de discovery dans la Campaign. `MarketDiscoveryCoordinator` maintient un cache process-local du catalogue, du curseur de probe, de la dernière watchlist stratégique valide et de l'audit associé.

Le refresh est borné par timeout. Une erreur Kraken, LLM ou validation déclenche le fallback documenté vers la dernière watchlist valide, puis vers le bootstrap si nécessaire. En `MANAGEMENT`, aucune révision IA de watchlist n'est lancée.

## 5. Même Agent IA et exécution canonique

`OpenAIWatchlistSelector` réutilise la même instance d'Agent stratégique. La sélection d'une watchlist ne crée aucun `ExecutionIntent`.

`DynamicMarketTradingCycleRunner` prépare l'univers puis délègue au runner de trading canonique. Risk/Broker/validations causales ne sont pas dupliqués. Les positions ouvertes restent toujours dans l'univers gérable.

## 6. Monitoring / mark-to-market

Les monitors SPOT et PERPETUAL restent des boucles techniques déterministes, indépendantes du cycle stratégique et de la discovery. Ils n'appellent pas le LLM et ne modifient pas la watchlist.

Leur rôle est la valorisation PAPER : marks, P&L latent, exposition, marge/liquidation/funding selon le type de marché.

## 7. Explicabilité 19.5

L'explicabilité est une projection de lecture à partir des faits déjà persistés. Elle sépare contexte/discovery, sélection de marché, Agent, Risk et exécution PAPER. Elle ne recalcule ni stratégie, ni Risk, ni P&L et n'invente aucune rationale absente.

## 8. Domaine candle canonique — 19.6A

Le Batch 19.6A introduit un domaine de présentation marché distinct du domaine stratégique :

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

Le champ `is_final` explicite la distinction entre candle courante mutable et candle clôturée.

## 9. Timeframes bornés

Les timeframes sont un ensemble explicite, pas une valeur libre.

SPOT supporté par 19.6A : `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`, `15d` selon l'endpoint Kraken OHLC.

PERPETUAL supporté par 19.6A : `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `12h`, `1d`, `1w` selon Kraken Futures charts.

Un timeframe non supporté pour le type de marché est rejeté avant abonnement fournisseur. FUTURE daté reste hors périmètre.

## 10. Historique initial et limites fournisseur

### SPOT

`KrakenPublicRestClient` conserve son API close-only existante pour les consommateurs historiques et ajoute une lecture OHLCV dédiée au cockpit. L'endpoint Spot OHLC fournit au maximum 720 rows ; le backend ne prétend donc pas fournir 1000 candles Spot à partir d'un seul appel.

La dernière row retournée est conservée comme candle courante non finalisée au lieu d'être supprimée dans le contrat chart.

### PERPETUAL

Le provider réutilise le catalogue `KrakenDerivativesPublicClient` pour résoudre le `venue_symbol` d'un PERPETUAL linéaire puis interroge le endpoint public Futures charts `mark/<venue>/<resolution>`.

La cible de requête est bornée à 1000 rows, mais la profondeur effective reste celle réellement retournée par Kraken. Aucun row manquant n'est inventé.

## 11. Cache backend

`CandleCache` est process-local et borné. Il n'ajoute aucune table SQL.

Pour chaque `CandleKey` :

- ordre chronologique garanti ;
- déduplication par `open_time` ;
- remplacement d'une candle courante par une version plus récente ;
- une candle finalisée ne peut pas être rétrogradée en candle courante ;
- profondeur maximale bornée, 1000 par défaut ;
- aucune croissance mémoire non bornée.

La persistence durable des candles n'est pas justifiée pour 19.6A : PostgreSQL reste réservé aux faits métier/audit qui doivent survivre au process.

## 12. Streaming Kraken SPOT

`KrakenOhlcWebSocketClient` réutilise l'infrastructure publique WebSocket Kraken existante et le même protocole de connexion abstrait.

Il :

- souscrit au canal v2 `ohlc` pour un symbole/timeframe ;
- met à jour la candle courante ;
- marque la candle précédente finalisée lorsque l'intervalle suivant apparaît ;
- rejette symbole/timeframe incohérents ;
- envoie un unsubscribe best-effort au cleanup ;
- ferme toujours la connexion détenue par le générateur.

La reconnexion globale et le backfill appartiennent au hub `CandleStreamService`, afin de ne pas dupliquer cette politique dans chaque adaptateur.

## 13. Streaming Kraken PERPETUAL

Kraken Futures ne fournit pas un flux OHLC public équivalent au canal Spot v2 utilisé ici. Le provider 19.6A réutilise donc le WebSocket public Futures `trade` et agrège uniquement les trades réellement reçus pour construire la candle courante.

À la transition d'intervalle, la candle précédente est finalisée. Si aucun trade n'existe pour un intervalle, aucune candle synthétique n'est créée.

Après reconnexion ou gap détecté, le hub demande un backfill au endpoint Futures charts puis fusionne/déduplique avant de poursuivre le flux.

## 14. `CandleStreamService`

Le service est le propriétaire backend des streams :

```text
premier besoin sur une CandleKey
-> backfill REST
-> création d'un seul task provider pour cette clé
-> fan-out vers N consommateurs cockpit
-> cache partagé
```

Propriétés :

- un seul stream provider par clé ;
- nombre total de streams actifs borné, 32 par défaut ;
- queues consommateurs bornées ;
- backfill initial et après reconnexion ;
- détection d'un trou avant une update et tentative de recovery ;
- merge/déduplication avant publication ;
- statut `connected`, `stale`, `last_update_at`, `last_error` ;
- fermeture de tous les tasks et transports au shutdown backend.

Un client cockpit qui se déconnecte est retiré du fan-out, mais le stream backend déjà démarré reste propriétaire du backend jusqu'au shutdown. Fermer/redémarrer le frontend n'arrête ni le moteur de trading ni la collecte déjà ouverte.

## 15. API cockpit 19.6A

Le backend expose :

```text
GET /api/v1/markets/candles
GET /api/v1/markets/candles/status
WS  /api/v1/markets/candles/stream
```

Le GET retourne l'historique canonique et le statut technique. Le WebSocket envoie d'abord un snapshot, puis les updates de candles provenant du hub partagé.

Le futur Batch 19.6B consommera ces contrats ; il ne doit pas ouvrir une seconde connexion directe à Kraken.

## 16. Lifecycle FastAPI

Le service de candles est créé dans le lifespan FastAPI avec les URLs/timeouts Kraken déjà présents dans `Settings`. Aucun nouveau secret ni paramètre stratégique n'est introduit.

Au shutdown : CandleStreamService ferme ses tasks/provider, puis le runtime trading poursuit son cleanup canonique.

Les cadences restent distinctes :

1. monitoring / mark-to-market ;
2. cycle stratégique IA ;
3. discovery / watchlist IA ;
4. streaming marché / candles sans LLM.

## 17. Persistence / audit

Aucune migration SQL en 19.6A. L'audit trading 19.4/19.5 reste inchangé. Le cache candles n'est pas utilisé comme source de vérité d'exécution, de Risk, de portfolio ou de décision Agent.

## 18. Hors périmètre 19.6A

Restent hors du batch : vue Marchés complète, Lightweight Charts, onglets frontend définitifs, markers BUY/SELL/fills, overlays position/liquidation, nouvelle logique stratégique IA, ranking algorithmique, modification Risk et LIVE.
