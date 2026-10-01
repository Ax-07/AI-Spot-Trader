# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 2a368c76f30373a6b9003324a1a14d8192cc0ad8
Commit     : docs: mark batch 40 as integrated
```

État revérifié le 01/10/2026 au lancement du Batch 41. Le document référençait encore le commit applicatif Batch 40 `6d263be5edb589723101c32065ad68434b0b64f1`; le HEAD GitHub réel ci-dessus prime.

## Batch 40 — intégré

Le Radar déterministe v3 combine OHLCV Kraken via `CandleStreamService` et microstructure publique SPOT bornée (`/Depth`, `/Trades`). Il reste strictement informatif, fail-soft, sans OpenAI, sans Web et sans dépendance Agent/Risk/Broker.

## Batch 41 — patch proposé, non intégré

Le patch Batch 41 ajoute au Radar :

- un scope runtime `SPOT / PERPETUAL / ALL`, `ALL` par défaut ;
- filtrage du catalogue éligible **avant** rotation et scan OHLCV ;
- filtrage logique des caches, compteurs, liquidité et shortlist selon le scope actif ;
- microstructure toujours SPOT uniquement, sans appel `/Depth` ou `/Trades` en scope `PERPETUAL` ;
- direction déterministe `UP / DOWN / NEUTRAL / MIXED / UNKNOWN` par horizon `5m/15m/1h/4h` ;
- synthèse de tendance globale multi-timeframe ;
- cohérence de `MarketCharacteristic.TRENDING` avec cette même synthèse ;
- contrat public `market-attention-radar-v4` ;
- contrôle cockpit `SPOT / PERP / TOUS` pilotant réellement le backend.

Le Batch 41 reste informatif : aucune tendance ne constitue `BUY`, `SELL`, `LONG`, `SHORT` ou `HOLD`.

Voir `docs/41_BATCH_RADAR_SCOPE_ET_TENDANCE.md`.
