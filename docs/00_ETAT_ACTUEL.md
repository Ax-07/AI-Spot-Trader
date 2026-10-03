# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 85cbd01be40680a099bc1a251dc919ef3bbc7212
Commit     : fix: correct market attention volume filter
```

Le Batch 43.1 est intégré sur `main` via `85cbd01`. La précédente référence à `3b8bc6b` et l'état « patch proposé, non intégré » étaient obsolètes.

## État intégré — Batch 43.1

Le Market Attention Radar intégré est `market-attention-radar-v6` avec :

- scope runtime `SPOT / PERPETUAL / ALL` ;
- filtres runtime volume 24h et capitalisation ;
- OHLCV, tendance, microstructure et Market Structure issus de Kraken ;
- capitalisation réelle via un provider externe read-only, initialement CoinPaprika ;
- volume 24h `SPOT/USD` calculé causalement sur les candles Kraken 5m finalisées ;
- valeurs de volume non démontrables conservées en `UNKNOWN` et fail-closed lorsqu'un seuil est actif ;
- Radar strictement informatif, sans décision `BUY / SELL / HOLD` et sans connexion Agent/Risk/Broker.

Diagnostics `MarketAttentionOverviewV6.volume_24h_status_counts` :

```text
AVAILABLE
BELOW_THRESHOLD
UNKNOWN_UNSUPPORTED_QUOTE
UNKNOWN_UNSUPPORTED_MARKET_TYPE
UNKNOWN_INSUFFICIENT_HISTORY
UNKNOWN_TECHNICAL_ERROR
```

Voir `docs/43_1_CORRECTIF_FILTRE_VOLUME.md`.

## Batch 43.2 — correctif Radar PERPETUAL

**État : patch proposé dans cette livraison, non intégré à GitHub.**

Audit confirmé au HEAD `85cbd01` :

- le catalogue Kraken sait déjà découvrir les linear perpetuals ;
- le scope `PERPETUAL` est appliqué avant le scan OHLCV ;
- les candles Futures `trade` sont utilisées pour l'activité ;
- la microstructure reste volontairement SPOT-only et `NOT_APPLICABLE` pour les PERP ;
- `Volume Tous` ne supprime pas les PERP : une shortlist vide peut donc venir d'une erreur de données, d'un historique incomplet ou simplement d'une activité sous les critères d'intérêt ;
- avec un seuil volume actif, le code intégré classe en revanche tous les PERP `UNKNOWN_UNSUPPORTED_MARKET_TYPE`, ce qui les élimine systématiquement.

Le patch 43.2 propose :

- récupération bulk des tickers publics Kraken Futures ;
- utilisation directe de `volumeQuote` pour les linear perpetuals cotés USD ;
- aucune conversion inventée de `candle.volume * close` pour les PERP ;
- un seul appel bulk, sans requête par marché ;
- `UNKNOWN_MISSING_QUOTE_VOLUME` si le ticker répond mais ne fournit pas de `volumeQuote` exploitable pour ce marché ;
- `UNKNOWN_TECHNICAL_ERROR` si le snapshot ticker public échoue ;
- message cockpit explicite lorsqu'un seuil volume exclut tous les marchés pour cause de volume inconnu ou sous seuil ;
- régressions dédiées `PERPETUAL + Volume Tous` et `PERPETUAL + Volume >= 100k`.

Voir `docs/43_2_CORRECTIF_RADAR_PERPETUAL.md`.
