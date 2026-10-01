# 02 — Architecture technique

## 1. Référence

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD GitHub audité : 6d263be5edb589723101c32065ad68434b0b64f1
Batch 39           : intégré
Batch 40           : intégré
```

## 2. Architecture générale

```text
Next.js cockpit
  -> FastAPI
     -> Control Plane / runtime PAPER
        -> CandleStreamService partagé
        -> Agent IA stratégique unique
        -> Risk Engine déterministe
        -> Paper Broker / Portfolio

     -> Market Attention Radar v3 (observation uniquement)
        -> MarketAttentionRadar v2 canonique
           -> catalogue Kraken
           -> CandleStreamService partagé / OHLCV 5m canoniques
        -> couche d'enrichissement microstructure SPOT
           -> GET /0/public/Depth
           -> GET /0/public/Trades
           -> calculs déterministes bornés
        -> shortlist enrichie
        -> API read-only /api/v1/market-attention
        -> zéro OpenAI / zéro recherche Web
        -> aucun lien vers Agent / Market Discovery / Risk / Broker
```

Le frontend n'appartient jamais à la chaîne d'exécution.

## 3. Données causales et candles

`CandleStreamService` reste la source OHLCV canonique partagée. `MarketActivityAnalyzer` ne retient que les candles `5m` finalisées dont `close_time <= observed_at`. Le Batch 40 ne duplique pas ce pipeline.

## 4. Microstructure Kraken SPOT

`KrakenSpotMicrostructureProvider` étend le client REST public existant et réutilise la normalisation des erreurs transport/API. Deux endpoints publics sont utilisés :

- `/0/public/Depth` avec `assetVersion=1` et un nombre borné de niveaux ;
- `/0/public/Trades` avec `assetVersion=1` et un nombre borné de trades.

`MarketMicrostructureAnalyzer` calcule sans I/O : meilleur bid/ask, mid, spread, profondeur base/quote, profondeur par bandes en bps, déséquilibre, cadence récente des trades, baseline, ratio d'activité, statistiques de taille, couverture du côté fournisseur et slippage théorique.

Les niveaux L2 non ordonnés sont triés et les prix dupliqués agrégés. Les valeurs invalides restent des erreurs de payload ; aucune métrique n'est inventée.

## 5. Côté des trades

Le marqueur de côté fourni par Kraken est normalisé uniquement pour les valeurs connues `b/s`. Une valeur inconnue reste `None`. Les métriques `buy_volume_base`, `sell_volume_base` et `buy_sell_imbalance` ne sont calculées que lorsque **100 %** des trades de la fenêtre récente possèdent un côté fournisseur connu. Il n'existe aucune inférence d'agresseur par heuristique prix/tick.

## 6. Slippage théorique

Le calcul parcourt les asks pour une acquisition hypothétique et les bids pour une cession hypothétique. Il calcule VWAP, écart absolu/bps, volume base consommé, profondeur quote disponible et `insufficient_depth`.

Il n'appelle jamais Broker/Risk/Agent et ne construit aucun ordre. Les notionnels sont exprimés dans la devise cotée du marché.

## 7. Fail-soft

La microstructure est additive :

- carnet indisponible + trades valides -> `PARTIAL` ;
- trades indisponibles + carnet valide -> `PARTIAL` ;
- deux sources indisponibles avec erreur -> `ERROR` microstructure ;
- cache ancien -> `STALE` ;
- PERPETUAL -> `NOT_APPLICABLE` pour la nouvelle couche ;
- OHLCV valide conservé dans tous ces cas.

## 8. Score et shortlist

Le niveau Batch 39 reste la base. Une hausse forte d'intensité, un déséquilibre L2 ou une pression transactionnelle descriptive peuvent renforcer l'attention. Un spread large, une profondeur faible ou un slippage élevé peuvent réduire le rang d'intérêt d'un signal apparent. Aucune de ces règles n'émet une action stratégique.

La diversification par régime de liquidité du Batch 39 est conservée.

## 9. Coût et cadence

`MicrostructurePolicy` borne par défaut : 100 niveaux L2, 1 000 trades, 24 marchés SPOT par refresh, concurrence 4, refresh 300 s, TTL 900 s. Le sous-scan SPOT est rotatif. Le Radar n'interroge donc pas chaque endpoint pour chaque marché à chaque seconde.

## 10. API et cockpit

Le contrat `market-attention-radar-v3` ajoute les métriques microstructure et leurs diagnostics. Le cockpit affiche les mesures de manière descriptive et rappelle qu'elles sont informatives.

## 11. Lifecycle

`MicrostructureMarketAttentionRadar` est possédé par le lifespan FastAPI. Il ferme son client microstructure puis la couche Radar v2/catalogue ; le service candles partagé est fermé ensuite par le lifespan.

## 12. Isolation

Aucun module Batch 40 Market Attention n'importe Agent, Risk, Broker, OpenAI ou outil Web. Le Radar reste read-only et `informative_only=True`.
