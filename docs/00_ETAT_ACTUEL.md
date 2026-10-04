# 00 — État actuel

## Référence intégrée GitHub

```text
Repository          : Ax-07/AI-Spot-Trader
Branche             : main
HEAD GitHub observé : 842e6bd7f005f1f57bd9b2131d201777020d1d24
Commit              : feat: add futures ticker analytics foundations
```

Le **Batch 47.1 est intégré** dans `main` via `842e6bd7`. Les documents qui le présentaient encore comme « patch préparé, non intégré » sont obsolètes et sont réconciliés par le Batch 47.2.

Décisions désormais intégrées :

```text
Batch 46 / 46.1 => intégré via b219365
Batch 47.1      => intégré via 842e6bd7
ADR-328         => ADOPTÉ
ADR-329         => ADOPTÉ
ADR-330         => ADOPTÉ
ADR-331         => ADOPTÉ
ADR-332         => ADOPTÉ
```

L'intégration GitHub confirme la présence du code. Elle ne permet pas d'inventer une suite locale complète non observée.

## État intégré — Radar jusqu'au Batch 47.1

Le Market Attention Radar reste `market-attention-radar-v6`, strictement informatif, déterministe, causal et read-only. L'exécution demeure SPOT uniquement.

Pipeline intégré avant le Batch 47.2 :

```text
catalogue Kraken
-> scope SPOT / PERPETUAL / ALL
-> métadonnées / filtre capitalisation
-> rotation OHLCV et volume 24h
-> activité adaptative / tendance / liquidité / microstructure canonique
-> pool Structure borné et rotatif
-> cache Structure causal
-> filtres tendance / Structure
-> shortlist finale bornée
-> contexte Futures ticker additif
-> cockpit
```

La Market Structure Batch 45 reste inchangée : timeframes natives `5m / 15m / 1h / 4h`, candles finalisées, pivots confirmés, événements `BOS / CHOCH` descriptifs et filtres `UNKNOWN` fail-closed.

Le Batch 46 utilise une baseline robuste propre à chaque marché et horizon :

```text
baseline = médiane des périodes historiques causales
MAD      = médiane(|x - baseline|)
dispersion robuste = 1,4826 * MAD
score adaptatif = (courant - baseline) / dispersion robuste
```

La cible par défaut est `12` périodes. Le plancher de compatibilité à `6` périodes est intégré. `MAD == 0` bascule explicitement vers `LEGACY_RATIO_FALLBACK` lorsque le ratio est exploitable, sinon `UNAVAILABLE`.

Le Batch 47.1 mutualise un seul snapshot public bulk Kraken Futures `/tickers` pour :

```text
volumeQuote
Open Interest courant
fundingRate courant brut
fundingRatePrediction Kraken
markPrice / indexPrice
serverTime
```

`KrakenDerivativesPublicClient.fetch_tickers()`, `KrakenDerivativesTickerSnapshot`, `KrakenAttentionCatalogue.perpetual_ticker_snapshot_by_market()` et `PerpetualTickerContext` sont intégrés. Aucun champ instantané Futures ne modifie `interest_level`, `candidate_limit`, le ranking canonique/Structure ou la baseline adaptative.

## Batch 47.2 — patch préparé, non intégré

Le Batch 47.2 ajoute **uniquement l'historique Open Interest** et l'infrastructure Analytics Futures qui pourra être réutilisée ultérieurement.

Source publique auditée :

```text
GET https://futures.kraken.com/api/charts/v1/analytics/{venue_symbol}/open-interest
query: since=<epoch secondes>&interval=<secondes>&to=<epoch secondes>
```

Granularités documentées :

```text
60 / 300 / 900 / 1800 / 3600 / 14400 / 43200 / 86400 / 604800 secondes
```

Réponse observée lors du smoke public local PF_XBTUSD :

```text
result.timestamp[]
result.data[] = [[open, high, low, close], ...]
result.more = false
errors = []
```

Le parser Open Interest accepte strictement des buckets OHLC de quatre valeurs finies et non négatives. La valeur historique transmise au scanner est le `close` du bucket ; le scanner n'utilise ce point qu'après `timestamp + interval <= as_of`, ce qui exclut le bucket courant non finalisé. Les formes scalaires ou de longueur inconnue sont rejetées explicitement.

L'unité économique de `openInterest` n'étant pas démontrée dans le contrat public utilisé, le Batch 47.2 conserve des valeurs brutes et relatives à l'historique propre du marché. Aucun champ `open_interest_usd` n'est créé.

Infrastructure préparée :

```text
PerpetualAnalyticsProvider
PerpetualAnalyticsPolicy
PerpetualAnalyticsScanner
PerpetualAnalyticsSnapshot
perpetual_analytics_coverage
```

Policy par défaut :

```text
market_limit_per_refresh = 10
cache_ttl_seconds        = 3600
history_interval_seconds = 3600
history_lookback_seconds = 172800
fetch_concurrency        = 4
baseline_periods         = 12
anomaly_score_threshold = ±2.5
fallback delta relatif  = ±10 % autour de la baseline
```

Le coût réseau est borné à **10 requêtes Open Interest historiques maximum par refresh** avec la policy par défaut. La rotation Analytics possède son propre curseur, indépendant des curseurs OHLCV et Structure. Le cache futur par rapport à `as_of` n'est jamais réutilisé.

Le score OI réutilise directement les primitives Batch 46 `_median_absolute_deviation()` et `_robust_anomaly()` ; aucune deuxième implémentation MAD n'est introduite. Les seules caractéristiques 47.2 sont :

```text
OPEN_INTEREST_EXPANSION
OPEN_INTEREST_CONTRACTION
```

L'OI historique enrichit uniquement les candidats déjà sélectionnés. Il ne peut pas forcer un marché normal dans la shortlist, ne change pas `interest_level` et ne modifie pas le ranking.

Voir `docs/47_2_OPEN_INTEREST_HISTORIQUE.md`.

## Validation connue

Batch 47.1 — validation locale utilisateur connue après extraction de la première livraison :

```text
pnpm typecheck   : PASS
pnpm test        : PASS — 68/68
git diff --check : PASS (avertissements LF/CRLF uniquement)
pytest -q        : 3 FAILURES dans les nouvelles fixtures Batch 47.1, suite arrivée à 100 %
```

Le correctif 47.1.1 aligne les fixtures sur `StructureAwareMarketAttentionFilters`. Une relance complète `pytest -q` post-correctif n'est pas connue dans GitHub et n'est pas inventée ici.

Batch 47.2 — validations réellement exécutées dans l'environnement ChatGPT au moment de la préparation :

```text
python -m py_compile des sources/tests Python Batch 47.2              : PASS
pytest ciblé Batch 47.2 avec stubs du checkout partiel                  : PASS — 37/37
node --test --experimental-strip-types market-attention.test.mjs        : PASS — 26/26
tsc --noEmit --strict ciblé market-attention.ts                         : PASS
typecheck ciblé lib + cockpit avec stubs React/UI                       : PASS
transpile TypeScript ciblé market-attention-dock.tsx                    : PASS
```

Validation locale utilisateur de la première livraison 47.2 :

```text
pytest -q        : PASS — suite arrivée à 100 %
pnpm typecheck   : PASS
pnpm test        : PASS — 72/72
git diff --check : PASS sans erreur ; avertissements LF/CRLF uniquement
smoke Kraken OI  : PASS transport — PF_XBTUSD, interval=3600, more=false
```

Le smoke a révélé que `result.data` utilise réellement des buckets OHLC à quatre valeurs, et non la forme scalaire initialement supposée. Le correctif pré-intégration 47.2 adapte le parser à `[open, high, low, close]`, utilise `close` comme valeur du bucket et ajoute le payload live comme fixture de non-régression. Ce correctif a été revalidé par ChatGPT avec `py_compile` PASS et **33/33 tests parser/client ciblés PASS** dans un harnais de checkout partiel. Après extraction du correctif, une relance locale de `pytest -q` reste requise avant commit ; le frontend n'est pas modifié par ce correctif.
