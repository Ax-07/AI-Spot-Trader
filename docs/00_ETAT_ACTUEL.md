# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : e65940b4c773f0de329648f5f3bb1f8960faa696
Commit     : feat: add market attention scope and trend direction
```

État revérifié le 01/10/2026 au lancement du Batch 42. Le document référençait encore `2a368c76f30373a6b9003324a1a14d8192cc0ad8` et présentait le Batch 41 comme non intégré ; cette information était obsolète.

## Batch 41 — intégré

Le Radar déterministe v4 dispose désormais du scope runtime `SPOT / PERPETUAL / ALL` et d'une tendance récente descriptive `UP / DOWN / NEUTRAL / MIXED / UNKNOWN` par horizon `5m / 15m / 1h / 4h` ainsi que d'une synthèse globale. La microstructure reste SPOT uniquement. Le commit intégré est `e65940b4c773f0de329648f5f3bb1f8960faa696`.

## Batch 42 — patch proposé, non intégré

Le patch Batch 42 ajoute une **Market Structure multi-timeframe** déterministe et causale sur les marchés de la shortlist déjà éligibles au scope actif :

- historiques natifs Kraken `5m / 15m / 1h / 4h` via `CandleStreamService.history_as_of(...)` ;
- profondeur par défaut : 100 candles finalisées par timeframe ;
- pivots confirmés avec fenêtre explicite gauche/droite ;
- classification `HH / HL / LH / LL` ;
- états `BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN` ;
- événements descriptifs `BOS_* / CHOCH_*` lorsque la géométrie confirmée le permet ;
- synthèse multi-timeframe descriptive, sans signal de trading ;
- contrat Radar v5 pour les snapshots enrichis, tout en conservant la compatibilité API avec les snapshots v4 injectés ;
- affichage cockpit séparant clairement tendance récente et structure de marché.

Le Radar reste Kraken-only, déterministe, `informative_only=True`, sans OpenAI, sans recherche Web et sans lien Agent/Risk/Broker.

Voir `docs/42_BATCH_MARKET_STRUCTURE_MULTI_TIMEFRAME.md`.
