# 02 — Architecture technique

## 1. Référence

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD GitHub audité : 2776fc68fb0ff8c094148a246d22de844ee868c7
Batch 38           : intégré
Batch 39           : patch proposé/local non intégré
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

     -> Market Attention Radar v2 (observation uniquement)
        -> catalogue Kraken
        -> CandleStreamService partagé / OHLCV 5m canoniques
        -> bougies finalisées uniquement
        -> calcul déterministe 5m / 15m / 1h / 4h
        -> activité / volume / prix / range / volatilité / liquidité
        -> caractéristiques descriptives
        -> intérêt LOW / MEDIUM / HIGH / VERY_HIGH
        -> shortlist diversifiée
        -> API read-only /api/v1/market-attention
        -> zéro OpenAI / zéro recherche Web
        -> aucun lien vers Agent / Market Discovery / Risk / Broker
```

Le frontend n'appartient jamais à la chaîne d'exécution. Fermer ou redémarrer le cockpit n'arrête ni le moteur backend ni les streams déjà ouverts.

## 3. Données causales et candles

`CandleStreamService` reste la source canonique partagée. Le Radar ne crée aucun second pipeline OHLC. `MarketActivityAnalyzer` ne retient que les candles `5m` correspondant au marché, explicitement finalisées et dont `close_time <= observed_at`.

Les horizons `15m`, `1h` et `4h` sont calculés à partir de cette base 5m. Les gaps restent explicitement qualifiés ; aucune interpolation de prix n'est inventée.

## 4. Caractéristiques déterministes

Le Radar peut produire : `TRENDING`, `VOLUME_ANOMALY`, `VOLATILITY_EXPANSION`, `BREAKOUT_WATCH`, `REVERSAL_WATCH`, `CONSOLIDATING`, `PRICE_VOLUME_DIVERGENCE`.

Ces caractéristiques et `RadarInterestLevel` sont descriptifs. Ils ne remplacent jamais le jugement de l'Agent stratégique et ne deviennent pas des ordres.

## 5. Isolation de l'Agent

Le Radar n'est pas un deuxième Agent. Il ne possède aucun client LLM, aucune tool loop et aucune recherche Web. L'Agent stratégique reste le seul composant IA chargé de décider `BUY/SELL/HOLD` dans son propre cycle.

## 6. Risk et exécution

Aucun type du Radar n'est accepté directement par Risk ou Broker. Une erreur Radar n'interrompt jamais monitoring, cycle stratégique, Risk ou exécution PAPER.

## 7. API et cockpit

Endpoints read-only :

```text
GET /api/v1/market-attention
GET /api/v1/market-attention/history
```

Le contrat `market-attention-radar-v2` expose l'état, les volumes de scan, les candidats, l'activité, les caractéristiques, l'intérêt et ses raisons, la liquidité, la fraîcheur/qualité, les erreurs et étapes de payload Kraken ainsi que la shortlist.

Le cockpit ne présente plus de source publique, recherche IA, budget Web ou cache de recherche.

## 8. Lifecycle

En composition PAPER, `MarketAttentionRadar` est possédé par le lifespan FastAPI. Il démarre après l'initialisation du runtime et se ferme avant le service candles partagé. Sa seule ressource externe propre est le catalogue Kraken ; aucun client OpenAI n'est construit pour lui.

## 9. Hors périmètre Batch 39

Trades Kraken, carnet L2, spread, profondeur, déséquilibre bid/ask, intensité des trades et slippage théorique sont réservés au Batch 40.
