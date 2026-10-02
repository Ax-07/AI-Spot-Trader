# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : f5de73270c23c6c4e2a6114ac78b3e57c17c65b1
Commit     : docs: close batch 42 documentation
```

Le commit fonctionnel du Batch 42 reste `003dae8dbfdc052edbad5bfde2c23fa24852eace`. Le HEAD absolu de `main` a ensuite avancé avec la clôture documentaire du Batch 42.

## État intégré — Batch 42

Le Market Attention Radar intégré est `market-attention-radar-v5` :

- déterministe et `informative_only=True` ;
- scope runtime `SPOT / PERPETUAL / ALL` ;
- tendance récente `5m / 15m / 1h / 4h` ;
- Market Structure native `5m / 15m / 1h / 4h` ;
- pivots confirmés `HH / HL / LH / LL` ;
- états `BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN` et synthèse multi-timeframe ;
- événements descriptifs `BOS / CHOCH` ;
- microstructure SPOT ;
- aucun signal `BUY / SELL / HOLD`, aucun ordre Kraken, aucune connexion directe Agent/Risk/Broker.

Distinction à préserver :

```text
recent_trend     = direction récente
market_structure = géométrie des swings confirmés
```

## Batch 43 — patch proposé, non intégré

Le patch Batch 43 ajoute des filtres runtime de **volume 24h** et de **capitalisation réelle** au Radar, avec contrat proposé `market-attention-radar-v6`.

Architecture proposée :

```text
prix / OHLCV / tendance / structure / microstructure = Kraken
volume 24h USD                                        = dérivé causalement des candles Kraken lorsque l'unité USD est prouvée
market cap / circulating supply / rank               = provider metadata externe read-only
provider initial                                      = CoinPaprika
trading / exécution                                   = Kraken uniquement
```

Principes du patch :

- capitalisation filtrée avant le scan OHLCV lorsque la métadonnée est disponible ;
- volume 24h filtré après le scan OHLCV mais avant microstructure et Market Structure ;
- aucune conversion implicite pour un marché dont le notionnel USD n'est pas démontré ;
- cache long et fail-soft du provider de métadonnées ;
- changement de filtres sans redémarrage backend ;
- snapshot transitoire vidé lors d'un changement de filtres afin de ne pas présenter l'ancienne shortlist comme actuelle ;
- aucune autorité stratégique donnée à la source externe.

Le Batch 43 n'est pas intégré tant que les validations locales complètes n'ont pas été exécutées puis le patch explicitement poussé par l'utilisateur.

Voir `docs/43_BATCH_FILTRES_VOLUME_CAPITALISATION.md`.
