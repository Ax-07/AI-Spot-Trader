# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 3b8bc6bcb83604cb20eb5ee27ef1b95fcc4210da
Commit     : docs: close batch 43 documentation
```

Le commit fonctionnel du Batch 43 reste `32320e268722c6e431ae722924bca487ae45d004` (`feat: add market attention volume and market cap filters`). Le commit `3b8bc6b...` ferme uniquement sa documentation.

## État intégré — Batch 43

Le Market Attention Radar intégré est `market-attention-radar-v6` avec :

- scope runtime `SPOT / PERPETUAL / ALL` ;
- filtres runtime volume 24h et capitalisation ;
- OHLCV, tendance, microstructure et Market Structure issus de Kraken ;
- capitalisation réelle via un provider externe read-only, initialement CoinPaprika ;
- Radar strictement informatif, sans décision `BUY / SELL / HOLD` et sans connexion Agent/Risk/Broker.

## Batch 43.1 — correctif filtre Volume 24h

**État : patch proposé, non intégré à GitHub au moment de cette livraison.**

Audit du code intégré :

- `SPOT/USD` peut fournir un volume notionnel 24h démontrable via les candles Kraken 5m ;
- `SPOT` non coté directement en `USD` reste `UNKNOWN` en l'absence de conversion FX explicite ;
- `PERPETUAL` reste `UNKNOWN` tant que l'unité du champ volume des candles Futures n'est pas reliée de façon démontrée au notionnel USD dans le pipeline Radar ;
- lorsqu'un seuil volume est actif, `UNKNOWN` reste fail-closed ;
- l'ancienne fenêtre `as_of - 24h` pouvait écarter une bougie 5m finalisée lorsque `as_of` n'était pas exactement aligné sur une clôture, sous-comptant le volume ;
- le patch ancre la fenêtre sur la dernière clôture 5m finalisée et expose des diagnostics de disponibilité/rejet du volume.

Diagnostics proposés dans `MarketAttentionOverviewV6.volume_24h_status_counts` :

```text
AVAILABLE
BELOW_THRESHOLD
UNKNOWN_UNSUPPORTED_QUOTE
UNKNOWN_UNSUPPORTED_MARKET_TYPE
UNKNOWN_INSUFFICIENT_HISTORY
UNKNOWN_TECHNICAL_ERROR
```

Le contrat reste `market-attention-radar-v6` ; aucune conversion USD implicite n'est ajoutée.

Voir `docs/43_1_CORRECTIF_FILTRE_VOLUME.md`.
