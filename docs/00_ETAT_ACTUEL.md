# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 32320e268722c6e431ae722924bca487ae45d004
Commit     : feat: add market attention volume and market cap filters
```

## État intégré — Batch 43

Le Market Attention Radar intégré est `market-attention-radar-v6`.

Fonctions actives :

- scope runtime `SPOT / PERPETUAL / ALL` ;
- filtre runtime de volume 24h ;
- filtre runtime de capitalisation réelle par catégories `MICRO / SMALL / MID / LARGE` et bornes numériques ;
- prix, OHLCV, tendance récente, microstructure et Market Structure issus de Kraken ;
- capitalisation réelle fournie par un provider externe read-only, initialement CoinPaprika ;
- volume 24h dérivé causalement des candles Kraken lorsque le notionnel USD est démontré ;
- aucune décision `BUY / SELL / HOLD`, aucun ordre et aucune connexion directe Agent/Risk/Broker.

Pipeline actuel :

```text
catalogue Kraken
-> scope SPOT / PERPETUAL / ALL
-> metadata capitalisation
-> filtre capitalisation
-> scan OHLCV Kraken
-> volume 24h causal
-> filtre volume
-> activité / tendance
-> microstructure
-> Market Structure
-> shortlist informative
```

Distinctions à préserver :

```text
recent_trend     = direction récente
market_structure = géométrie des swings confirmés
market cap       = métadonnée descriptive externe read-only
exécution        = Kraken uniquement, SPOT dans l'état actuel
```

Le Radar reste strictement informatif et `informative_only=True`. L'Agent IA conserve la décision stratégique et le Risk Engine déterministe conserve l'autorité finale.

Voir `docs/43_BATCH_FILTRES_VOLUME_CAPITALISATION.md`.
