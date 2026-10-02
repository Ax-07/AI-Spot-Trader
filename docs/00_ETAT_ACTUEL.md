# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 003dae8dbfdc052edbad5bfde2c23fa24852eace
Commit     : feat: add multi-timeframe market structure
```

État revérifié après intégration du Batch 42.

## Batch 41 — intégré

Le Radar déterministe v4 dispose du scope runtime `SPOT / PERPETUAL / ALL` et d'une tendance récente descriptive `UP / DOWN / NEUTRAL / MIXED / UNKNOWN` par horizon `5m / 15m / 1h / 4h`, avec synthèse globale. La microstructure reste SPOT uniquement. Commit : `e65940b4c773f0de329648f5f3bb1f8960faa696`.

## Batch 42 — intégré

Le Batch 42 ajoute une **Market Structure multi-timeframe** déterministe et causale sur les marchés de la shortlist :

- historiques natifs Kraken `5m / 15m / 1h / 4h` via `CandleStreamService.history_as_of(...)` ;
- profondeur par défaut : 100 candles finalisées par timeframe ;
- pivots confirmés causalement ;
- classification `HH / HL / LH / LL` ;
- états `BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN` ;
- événements descriptifs `BOS_* / CHOCH_*` ;
- synthèse multi-timeframe descriptive ;
- contrat Radar v5 ;
- cockpit séparant tendance récente et structure de marché.

Distinction à préserver :

```text
recent_trend     = lecture récente de direction
market_structure = géométrie des swings confirmés
```

Le Radar reste Kraken-only, déterministe, `informative_only=True`, sans OpenAI, sans recherche Web, sans décision stratégique, sans signal `BUY / SELL / HOLD`, sans ordre Kraken et sans connexion directe Agent/Risk/Broker. L'observation `SPOT / PERPETUAL / ALL` du Radar ne modifie pas l'invariant d'exécution SPOT du projet.

Voir `docs/42_BATCH_MARKET_STRUCTURE_MULTI_TIMEFRAME.md`.
