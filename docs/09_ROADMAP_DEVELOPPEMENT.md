# 09 — Roadmap de développement

## Référence de reprise

```text
Repository              : Ax-07/AI-Spot-Trader
Branche                 : main
HEAD GitHub observé     : 842e6bd7f005f1f57bd9b2131d201777020d1d24
Commit HEAD             : feat: add futures ticker analytics foundations
Batch 42                : intégré
Batch 43                : intégré
Batch 43.1              : intégré
Batch 43.2              : intégré
Batch 44                : intégré
Batch 45                : intégré via 45d41b7
Batch 46 / 46.1         : intégré via b219365
Batch 47.1              : intégré via 842e6bd7
Batch 47.2              : patch préparé, non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve un seul Agent IA stratégique, Kraken comme exchange initial et source d'exécution, le Risk Engine comme autorité finale, un backend indépendant du frontend, le mode PAPER avant tout LIVE, aucune sortie LLM directement exécutable et un Market Attention Radar strictement informatif.

Les capacités PERPETUAL du Radar restent observationnelles uniquement. L'exécution demeure SPOT.

## État intégré jusqu'au Batch 47.1

Les Batches 28 à 35 ont construit et durci Market Attention. Le Batch 36 a amélioré la terminologie financière. Le Batch 37 a aligné la cadence stratégique sur les clôtures de bougies. Le Batch 38 a ajouté le préfiltrage Kraken et les caractéristiques descriptives. Le Batch 39 a supprimé la couche Web/IA du Radar. Le Batch 40 a ajouté la microstructure Kraken SPOT et le contrat Radar v3. Le Batch 41 a ajouté le scope `SPOT / PERPETUAL / ALL`, les directions récentes et le contrat v4. Le Batch 42 a ajouté la Market Structure multi-timeframe et le contrat v5. Le Batch 43 a ajouté les filtres de volume 24h et de capitalisation réelle avec le contrat v6. Les correctifs 43.1 et 43.2 ont fiabilisé le volume SPOT et PERPETUAL. Le Batch 44 a ajouté la liquidité PERPETUAL et les diagnostics de couverture OHLCV. Le Batch 45 a déplacé la Structure en amont de la shortlist finale avec une rotation/cache dédiés et des filtres tendance/Structure. Le Batch 46 a introduit une baseline statistique adaptative médiane/MAD, avec cible 12 périodes et plancher de compatibilité à 6 périodes. Le Batch 47.1 a intégré un snapshot Futures public bulk canonique partagé pour le volume PERP, la liquidité PERP et le contexte instantané OI/funding/mark/index.

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

**État : intégré via `b219365`.**

Objectif : mesurer qu'une activité est inhabituelle **pour le marché et l'horizon observés**, plutôt que dépendre principalement de ratios universels.

Méthode intégrée : médiane + MAD normalisé.

```text
baseline            = median(history)
MAD                 = median(abs(x - baseline))
robust_dispersion   = 1.4826 * MAD
adaptive_score      = (current - baseline) / robust_dispersion
```

Policy intégrée :

```text
baseline_periods             = 12 (cible)
minimum adaptive baseline    = 6 périodes
ELEVATED                     = score >= 2.0
ACCELERATING                 = score >= 3.5 et delta_score >= 1.0
VERY_HIGH                    = score >= 5.0
confirmation descriptive     = score >= 1.5
contraction                  = score <= -2.0
divergence volume forte      = score >= 3.0
```

Le ratio historique reste exposé et sert de fallback explicite lorsque le MAD est nul :

```text
ROBUST_MAD
LEGACY_RATIO_FALLBACK
UNAVAILABLE
```

Le Batch 46 adapte `MarketActivityState`, `VOLUME_ANOMALY`, `VOLATILITY_EXPANSION`, `CONSOLIDATING`, les confirmations de `BREAKOUT_WATCH` / `REVERSAL_WATCH` et `PRICE_VOLUME_DIVERGENCE`. La tendance `_MATERIAL_RETURN`, les pivots, HH/HL/LH/LL, BOS/CHOCH et le ranking Structure ne sont pas modifiés.

Voir `docs/46_BASELINE_STATISTIQUE_ADAPTATIVE_RADAR.md`.

## Batch 47.1 — fondations Futures ticker

**État : intégré via `842e6bd7`.**

Objectif : disposer d'un snapshot Futures public canonique et partagé avant toute série Analytics historique.

```text
KrakenDerivativesPublicClient.fetch_tickers()
-> KrakenDerivativesTickerSnapshot[]
-> KrakenAttentionCatalogue.perpetual_ticker_snapshot_by_market()
-> volumeQuote / liquidité / contexte Futures
```

Champs instantanés retenus lorsque présents :

```text
markPrice
indexPrice
volumeQuote
openInterest
fundingRate
fundingRatePrediction
suspended
postOnly
serverTime
```

Décisions intégrées :

- un seul appel bulk `/tickers` dans le chemin Radar pour volume, liquidité et contexte Futures ;
- `volumeQuote` conserve la sémantique Batch 43.2/44 ;
- Open Interest et funding restent descriptifs, sans score historique ni impact de ranking ;
- funding brut, taux relatif interne existant et prédiction Kraken sont distingués ;
- aucun format `%` n'est appliqué aux valeurs brutes/prédites sans unité démontrée ;
- `PerpetualTickerContext` ajoute les statuts `AVAILABLE / PARTIAL / NOT_APPLICABLE / TECHNICAL_ERROR` ;
- panne ticker fail-soft sauf comportement fail-closed déjà existant du filtre volume PERP actif ;
- protocole public maintenu en `market-attention-radar-v6` ;
- cockpit enrichi dans le détail PERPETUAL uniquement.

Voir `docs/47_1_FONDATIONS_FUTURES_TICKER.md`.

## Batch 47.2 — historique Open Interest + infrastructure Analytics Futures

**État : patch préparé, non intégré.**

Périmètre strict : une seule série historique, `open-interest`.

Source publique auditée :

```text
GET https://futures.kraken.com/api/charts/v1/analytics/{venue_symbol}/open-interest
since    : epoch secondes
interval : secondes
[to]     : epoch secondes
```

Granularités documentées : `60 / 300 / 900 / 1800 / 3600 / 14400 / 43200 / 86400 / 604800` secondes. Le smoke public local PF_XBTUSD a confirmé `result.timestamp[]`, `result.more=false` et une série `result.data[]` de buckets OHLC `[open, high, low, close]`. Le parser 47.2 utilise le `close` de chaque bucket finalisé et rejette les formes scalaires/inconnues.

Architecture du patch :

```text
Radar
-> PerpetualAnalyticsProvider
-> KrakenAttentionCatalogue
-> extension du client Futures public canonique
-> Market Analytics public Open Interest
```

Le Radar utilise un scanner dédié :

```text
PerpetualAnalyticsScanner
_perpetual_analytics_cursor
cache[ExecutableMarket]
perpetual_analytics_coverage
```

La rotation Analytics est indépendante des curseurs OHLCV et Structure. Les analytics ne sont demandées que pour les PERPETUAL dont l'activité est `AVAILABLE` après scope, capitalisation et filtre volume déjà appliqués. Structure et OI restent indépendants.

Policy proposée :

```text
market_limit_per_refresh = 10
cache_ttl_seconds        = 3600
history_interval_seconds = 3600
history_lookback_seconds = 172800
fetch_concurrency        = 4
baseline_periods         = 12
data_stale_after_seconds = 7200
anomaly_score_threshold = ±2.5
fallback                 = ±10 % autour de la baseline
```

Coût réseau maximal par défaut : **10 appels OI historiques par refresh**. `more=true` est rejeté explicitement dans 47.2 afin de ne pas masquer une page tronquée ni dépasser silencieusement ce budget ; une stratégie de pagination bornée pourra être décidée si elle devient nécessaire.

Causalité : l'appel utilise `to <= as_of`. Comme le contrat public audité ne documente pas explicitement la sémantique de clôture des timestamps Analytics, le scanner applique volontairement un délai conservateur d'un intervalle avant d'utiliser un point dans la baseline.

Baseline OI : réutilisation des helpers Batch 46, aucune deuxième implémentation MAD.

```text
baseline OI          = median(historique causal hors point courant)
MAD                  = median(abs(x - baseline))
robust dispersion    = 1.4826 * MAD
score OI             = (current - baseline) / robust dispersion
expansion robuste    = score >= +2.5
contraction robuste  = score <= -2.5
fallback MAD nul     = current / baseline >= 1.10 ou <= 0.90
```

Les caractéristiques 47.2 sont uniquement :

```text
OPEN_INTEREST_EXPANSION
OPEN_INTEREST_CONTRACTION
```

Impact shortlist volontairement limité : la rotation OI est insérée juste avant le scan Structure, mais le parent calcule seul la shortlist canonique et l'OI n'est lu qu'après cette sélection pour enrichir les candidats déjà présents. Il ne change pas `interest_level`, `candidate_limit` ni la clé de ranking et ne force jamais seul un marché normal dans la shortlist.

Cockpit : sous-partie `Open Interest historique` dans `Futures Kraken` et bloc global `Couverture Analytics Futures`. Aucun filtre utilisateur OI n'est ajouté.

Voir `docs/47_2_OPEN_INTEREST_HISTORIQUE.md`.

## Batches 47.3 à 47.5 — Analytics Futures historiques suivants

**État : réservé / non implémenté dans 47.2.**

Périmètres réservés :

```text
47.3 : funding historique, liquidation-volume
47.4 : CVD, aggressor-differential
47.5 : évaluation d'une éventuelle influence déterministe multi-analytics sur le ranking
```

Toute influence future devra réutiliser l'infrastructure de rotation/cache/coverage du Batch 47.2 plutôt que créer des scanners parallèles indépendants.

## Validation connue

Batch 45 — validations du patch observées avant intégration :

```text
Python py_compile des fichiers Python modifiés : PASS
frontend market-attention.test.mjs ciblé       : PASS — 16/16
typecheck ciblé market-attention.ts            : PASS
typecheck cockpit ciblé avec stubs             : PASS
```

Batch 46 — validations observées avant intégration :

```text
Python py_compile backend ciblé                 : PASS
exécution helpers robustes extraits du code     : PASS
frontend market-attention.test.mjs ciblé        : PASS — 19/19
typecheck TypeScript ciblé market-attention.ts  : PASS
parse TypeScript/TSX ciblé cockpit              : PASS
```

Batch 47.1 — validations connues : frontend local `pnpm typecheck` PASS, `pnpm test` PASS 68/68 et `git diff --check` PASS ; la première suite backend complète avait 3 échecs de fixtures Batch 47.1, corrigés par 47.1.1. Aucune relance backend complète post-correctif n'est inventée.

Batch 47.2 — validations réellement exécutées par ChatGPT au moment de la préparation :

```text
Python py_compile des sources/tests Python modifiés                  : PASS
pytest ciblé Batch 47.2 avec stubs du checkout partiel              : PASS — 37/37
frontend market-attention.test.mjs ciblé                            : PASS — 26/26
typecheck strict ciblé market-attention.ts                          : PASS
typecheck ciblé lib + cockpit avec stubs React/UI                   : PASS
transpile TypeScript ciblé market-attention-dock.tsx                : PASS
```

Validation locale utilisateur de la première livraison 47.2 : backend `pytest -q` PASS à 100 %, `pnpm typecheck` PASS, `pnpm test` PASS **72/72**, `git diff --check` sans erreur hors avertissements LF/CRLF. Le smoke public PF_XBTUSD a confirmé le transport et `more=false`, mais a révélé la forme OHLC réelle de `data`.

Le correctif pré-intégration parse désormais strictement `[open, high, low, close]` et utilise le `close` comme valeur historique. Validation ChatGPT du correctif : `py_compile` PASS et test parser/client ciblé **33/33 PASS** avec stubs minimaux du checkout partiel. Après extraction du correctif, relancer au minimum `pytest -q`, `git diff --check` et `git status --short` avant commit. Le frontend n'étant pas modifié par le correctif, les résultats locaux `pnpm typecheck` / `pnpm test` restent ceux de la première livraison.

## Périmètres ultérieurs possibles

- Analytics Futures historiques Batches 47.3+ ;
- conversion multi-devise du volume derrière une source FX explicite et testée ;
- microstructure Futures si un besoin est démontré ;
- éventuelle utilisation explicite du Radar comme contexte Agent après décision architecturale ;
- évaluation empirique des seuils adaptatifs sans fuite de données ni optimisation rétrospective ;
- LIVE, séparé et ultérieur.

Aucun ranking déterministe stratégique, quota de trades, auto-optimisation par le P&L ou promesse de rendement ne doit être introduit silencieusement.
