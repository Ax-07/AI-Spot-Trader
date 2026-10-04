# 09 — Roadmap de développement

## Référence de reprise

```text
Repository              : Ax-07/AI-Spot-Trader
Branche                 : main
HEAD GitHub observé     : 45d41b7
Commit HEAD             : feat: move market structure before radar shortlist
Batch 42                : intégré
Batch 43                : intégré
Batch 43.1              : intégré
Batch 43.2              : intégré
Batch 44                : intégré
Batch 45                : intégré via 45d41b7
Batch 46                : patch proposé, non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve un seul Agent IA stratégique, Kraken comme exchange initial et source d'exécution, le Risk Engine comme autorité finale, un backend indépendant du frontend, le mode PAPER avant tout LIVE, aucune sortie LLM directement exécutable et un Market Attention Radar strictement informatif.

Les capacités PERPETUAL du Radar restent observationnelles uniquement. L'exécution demeure SPOT.

## État intégré jusqu'au Batch 45

Les Batches 28 à 35 ont construit et durci Market Attention. Le Batch 36 a amélioré la terminologie financière. Le Batch 37 a aligné la cadence stratégique sur les clôtures de bougies. Le Batch 38 a ajouté le préfiltrage Kraken et les caractéristiques descriptives. Le Batch 39 a supprimé la couche Web/IA du Radar. Le Batch 40 a ajouté la microstructure Kraken SPOT et le contrat Radar v3. Le Batch 41 a ajouté le scope `SPOT / PERPETUAL / ALL`, les directions récentes et le contrat v4. Le Batch 42 a ajouté la Market Structure multi-timeframe et le contrat v5. Le Batch 43 a ajouté les filtres de volume 24h et de capitalisation réelle avec le contrat v6. Les correctifs 43.1 et 43.2 ont fiabilisé le volume SPOT et PERPETUAL. Le Batch 44 a ajouté la liquidité PERPETUAL et les diagnostics de couverture OHLCV. Le Batch 45 a déplacé la Structure en amont de la shortlist finale avec une rotation/cache dédiés et des filtres tendance/Structure.

## Batch 42 — Market Structure multi-timeframe

**État : intégré.**

- lecture native `5m / 15m / 1h / 4h` ;
- candles finalisées uniquement ;
- pivots confirmés causalement ;
- séquences `HH / HL / LH / LL` ;
- états `BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN` ;
- événements `BOS / CHOCH` descriptifs ;
- aucune décision `BUY / SELL / HOLD`.

`recent_trend` et `market_structure` restent deux notions indépendantes.

## Batch 43 / 43.1 / 43.2 — volume et capitalisation

**État : intégré.**

- `SPOT/USD` : volume 24h dérivé causalement des candles Kraken finalisées ;
- PERPETUAL linear/USD : `volumeQuote` public Kraken Futures ;
- aucune notionnalisation artificielle `candle.volume * close` pour les PERP ;
- capitalisation via provider externe read-only mis en cache ;
- `UNKNOWN` fail-closed lorsqu'un filtre correspondant est actif ;
- aucun appel réseau volume par marché ajouté ;
- aucune conversion implicite d'une quote non USD.

## Batch 44 — liquidité PERPETUAL et couverture OHLCV

**État : intégré.**

- référence de liquidité SPOT canonique conservée ;
- pour les linear perpetuals/USD, réutilisation uniquement du `volumeQuote` 24h validé ;
- percentiles SPOT et PERP séparés ;
- observabilité de couverture/rotation OHLCV : éligibles, frais, expirés, jamais vus, ratio, limites, rotation théorique et compatibilité TTL ;
- aucune auto-correction silencieuse des limites réseau.

## Batch 45 — Structure en amont et filtres tendance/structure

**État : intégré via `45d41b7`.**

Pipeline intégré :

```text
catalogue Kraken
-> scope
-> capitalisation
-> rotation OHLCV
-> volume 24h / filtre volume
-> activité / tendance / liquidité
-> microstructure SPOT canonique
-> pool Market Structure éligible
-> rotation Structure bornée
-> cache Structure frais et causal
-> filtres tendance / Structure
-> shortlist finale bornée
```

Décisions intégrées :

- `MarketStructurePolicy` reste la géométrie causale ; `MarketStructureScanPolicy` porte la rotation/cache ;
- curseur Structure indépendant des curseurs OHLCV ;
- cache futur par rapport à `as_of` jamais réutilisé ;
- sans filtre explicite, les événements confirmés `BOS / CHOCH` peuvent compléter l'attention ;
- un état persistant `BULLISH` ou `BEARISH` ne force pas seul la shortlist ;
- priorité Structure symétrique hausse/baisse, avec timeframes supérieures prioritaires à égalité ;
- filtres runtime : tendance, état global, états et événements `5m / 15m / 1h / 4h` ;
- `OR` dans un champ, `AND` entre familles/timeframes, `state AND event` sur une même timeframe ;
- `UNKNOWN` fail-closed ;
- diagnostic de couverture Structure séparé du diagnostic OHLCV ;
- contrat public conservé en `market-attention-radar-v6`.

Voir `docs/45_STRUCTURE_EN_AMONT_ET_FILTRES_RADAR.md`.

## Batch 46 — baseline statistique adaptative du Radar

**État : patch proposé, non intégré.**

Objectif : mesurer qu'une activité est inhabituelle **pour le marché et l'horizon observés**, plutôt que dépendre principalement de ratios universels.

Méthode retenue : médiane + MAD normalisé.

```text
baseline            = median(history)
MAD                 = median(abs(x - baseline))
robust_dispersion   = 1.4826 * MAD
adaptive_score      = (current - baseline) / robust_dispersion
```

Policy proposée :

```text
baseline_periods             = 12
ELEVATED                     = score >= 2.0
ACCELERATING                 = score >= 3.5 et delta_score >= 1.0
VERY_HIGH                    = score >= 5.0
confirmation descriptive     = score >= 1.5
contraction                  = score <= -2.0
divergence volume forte      = score >= 3.0
```

Ces valeurs sont des seuils expérimentaux déterministes centralisés, pas des optima universels et pas une auto-optimisation issue du P&L.

Le ratio historique reste exposé et sert de fallback explicite lorsque le MAD est nul :

```text
ROBUST_MAD
LEGACY_RATIO_FALLBACK
UNAVAILABLE
```

Le Batch 46 adapte `MarketActivityState`, `VOLUME_ANOMALY`, `VOLATILITY_EXPANSION`, `CONSOLIDATING`, les confirmations de `BREAKOUT_WATCH` / `REVERSAL_WATCH` et `PRICE_VOLUME_DIVERGENCE`. La tendance `_MATERIAL_RETURN`, les pivots, HH/HL/LH/LL, BOS/CHOCH et le ranking Structure ne sont pas modifiés.

Voir `docs/46_BASELINE_STATISTIQUE_ADAPTATIVE_RADAR.md`.

## Validation connue

Batch 45 — validations du patch observées avant intégration :

```text
Python py_compile des fichiers Python modifiés : PASS
frontend market-attention.test.mjs ciblé       : PASS — 16/16
typecheck ciblé market-attention.ts            : PASS
typecheck cockpit ciblé avec stubs             : PASS
```

Batch 46 — validations exécutées par ChatGPT sur le patch préparé :

```text
Python py_compile backend ciblé                 : PASS
exécution helpers robustes extraits du code       : PASS
frontend market-attention.test.mjs ciblé       : PASS — 19/19
typecheck TypeScript ciblé market-attention.ts : PASS
parse TypeScript/TSX ciblé cockpit              : PASS
```

À exécuter localement après extraction : suite backend `pytest -q`, `pnpm typecheck`, `pnpm test`, `git diff --check`, `git status --short`.

## Périmètres ultérieurs possibles

- Open Interest, Funding, Liquidations et CVD ;
- conversion multi-devise du volume derrière une source FX explicite et testée ;
- microstructure Futures si un besoin est démontré ;
- éventuelle utilisation explicite du Radar comme contexte Agent après décision architecturale ;
- évaluation empirique des seuils adaptatifs sans fuite de données ni optimisation rétrospective ;
- LIVE, séparé et ultérieur.

Aucun ranking déterministe stratégique, quota de trades, auto-optimisation par le P&L ou promesse de rendement ne doit être introduit silencieusement.
