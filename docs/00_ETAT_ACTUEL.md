# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 25dcb5c069a519af8b92ae386f3d21d0aa4db9f3
Commit     : fix: repair perpetual market attention radar
```

Le Batch 43.2 est intégré sur `main` via `25dcb5c`. Il clôt le correctif du Radar PERPETUAL avec filtre de volume.

## État intégré — Batch 43.2

Le Market Attention Radar reste `market-attention-radar-v6`, strictement informatif, déterministe, causal et read-only.

Éléments désormais intégrés :

- scope runtime `SPOT / PERPETUAL / ALL` ;
- filtres runtime volume 24h et capitalisation ;
- volume 24h `SPOT/USD` calculé causalement sur les candles Kraken 5m finalisées ;
- volume 24h des linear perpetuals cotés USD obtenu via le `volumeQuote` public Kraken Futures ;
- un seul appel bulk Futures `/tickers`, sans requête réseau par marché ;
- aucun calcul inventé `candle.volume * close` pour les PERP ;
- diagnostics explicites lorsque le volume PERP est absent ou techniquement indisponible ;
- distinction entre Radar PERP en panne et marché valide sans activité assez inhabituelle ;
- aucune modification Agent / Risk Engine / Broker et aucune capacité d'exécution PERP ajoutée.

Diagnostics `MarketAttentionOverviewV6.volume_24h_status_counts` :

```text
AVAILABLE
BELOW_THRESHOLD
UNKNOWN_UNSUPPORTED_QUOTE
UNKNOWN_UNSUPPORTED_MARKET_TYPE
UNKNOWN_MISSING_QUOTE_VOLUME
UNKNOWN_INSUFFICIENT_HISTORY
UNKNOWN_TECHNICAL_ERROR
```

Voir `docs/43_2_CORRECTIF_RADAR_PERPETUAL.md`.

## Validation connue

Validations exécutées localement avant l'intégration du Batch 43.2 :

```text
backend pytest -q       : PASS
frontend pnpm typecheck : PASS
frontend pnpm test      : PASS — 57/57
git diff --check        : PASS
```
