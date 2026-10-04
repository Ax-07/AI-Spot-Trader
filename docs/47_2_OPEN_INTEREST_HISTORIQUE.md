# Batch 47.2 — Open Interest historique

## Statut

**INTÉGRÉ sur GitHub `main` via `c09dd14` — `feat: add historical open interest analytics`.**

Base précédente : Batch 47.1 `842e6bd7`.

Les ADR-333, ADR-334, ADR-335 et ADR-336 sont **ADOPTÉES** puisque leur architecture est confirmée par le code intégré.

## Objectif

Ajouter l'historique Open Interest Kraken Futures et poser une infrastructure Analytics générique réutilisable par les batches suivants, sans donner à ces données d'autorité stratégique.

## Source Kraken

```text
GET https://futures.kraken.com/api/charts/v1/analytics/{venue_symbol}/open-interest
query:
  since=<epoch secondes>
  interval=<secondes>
  to=<epoch secondes>
```

Intervalles documentés :

```text
60 / 300 / 900 / 1800 / 3600 / 14400 / 43200 / 86400 / 604800
```

Smoke réel observé avant intégration sur `PF_XBTUSD` :

```text
result.timestamp[]
result.data[] = [[open, high, low, close], ...]
result.more = false
errors = []
```

Cette observation a corrigé l'hypothèse initiale d'une série scalaire.

## Parser intégré

`KrakenDerivativesAnalyticsClient.fetch_open_interest_history()` réutilise le transport Futures public canonique.

Le parser :

- exige `result.timestamp[]`, `result.data[]` et `result.more` ;
- rejette les erreurs provider ;
- exige autant de timestamps que de buckets ;
- rejette `more=true` afin de ne pas masquer une page tronquée ;
- exige exactement quatre valeurs OHLC par bucket ;
- exige des valeurs finies et non négatives ;
- contrôle `low <= open/close <= high` ;
- exige un ordre temporel strict ;
- utilise uniquement le quatrième élément, `close`, comme valeur historique représentative.

Aucune unité économique absente du contrat n'est inventée. En particulier, aucun champ `open_interest_usd` n'est créé.

## Infrastructure intégrée

```text
KrakenDerivativesAnalyticsClient
KrakenMarketAnalyticsPoint
PerpetualAnalyticsProvider
PerpetualAnalyticsPolicy
PerpetualAnalyticsScanner
PerpetualAnalyticsSnapshot
PerpetualAnalyticsCoverageDiagnostics
perpetual_analytics_coverage
```

La rotation Analytics possède son propre curseur et son propre cache. Elle ne réutilise ni le curseur OHLCV ni le curseur Structure.

Policy :

```text
market_limit_per_refresh = 10
cache_ttl_seconds        = 3600
history_interval_seconds = 3600
history_lookback_seconds = 172800
fetch_concurrency        = 4
baseline_periods         = 12
data_stale_after_seconds = 7200
anomaly_score_threshold  = ±2.5
fallback OI              = ratio >= 1.10 ou <= 0.90 si MAD nul
```

Le coût réseau 47.2 est borné à 10 requêtes OI historiques maximum par refresh avec la policy par défaut.

## Causalité

L'appel utilise `to <= as_of`. Un point n'est exploité que si :

```text
timestamp + history_interval_seconds <= as_of
```

Cette règle conservatrice empêche l'utilisation du bucket courant non finalisé et est formalisée par l'ADR-335.

## Statistique Open Interest

Le Batch 47.2 réutilise les primitives Batch 46 :

```text
baseline          = median(historique causal hors courant)
MAD               = median(abs(x - baseline))
robust dispersion = 1.4826 * MAD
score OI          = (current - baseline) / robust dispersion
```

Caractéristiques :

```text
OPEN_INTEREST_EXPANSION
OPEN_INTEREST_CONTRACTION
```

Si `MAD == 0`, le fallback ratio historique reste explicite. Aucun score artificiel extrême n'est fabriqué.

## Autorité fonctionnelle

L'Open Interest historique :

```text
n'influence pas interest_level
n'influence pas candidate_limit
n'influence pas le ranking canonique
ne peut pas créer seul un candidat
```

Le parent construit la shortlist canonique avant enrichissement Analytics. OI complète seulement `combined_characteristics`, `interest_reasons`, le détail candidat et les diagnostics de couverture.

Aucune modification Agent, Risk Engine, Broker ou capacité d'exécution PERPETUAL.

## Cockpit

Le contrat reste `market-attention-radar-v6` avec champs additifs :

- `perpetual_analytics` sur un candidat PERPETUAL ;
- `perpetual_analytics_coverage` au niveau overview ;
- bloc `Open Interest historique` dans le détail Futures Kraken.

Aucun filtre utilisateur OI n'est ajouté.

## Validation observée avant intégration

Validation locale utilisateur :

```text
backend pytest -q       : PASS — suite arrivée à 100 %
frontend pnpm typecheck : PASS
frontend pnpm test      : PASS — 72/72
git diff --check        : PASS — avertissements LF/CRLF uniquement
smoke Kraken OI         : PASS — PF_XBTUSD, OHLC, more=false
```

Le correctif parser déclenché par le smoke a également été validé dans l'environnement ChatGPT avec `py_compile` et tests ciblés parser/client.

## Décisions

### ADR-333 — Rotation/cache Analytics séparée

**ADOPTÉ — intégré via `c09dd14`.**

Les Analytics Futures historiques disposent d'une rotation/cache séparée de l'OHLCV et de Structure. Les extensions suivantes doivent réutiliser cette infrastructure.

### ADR-334 — OI relatif à son propre historique, sans unité économique inventée

**ADOPTÉ — intégré via `c09dd14`.**

L'OI reste une valeur Kraken brute et est comparé à sa propre baseline robuste.

### ADR-335 — Délai causal conservateur d'un intervalle

**ADOPTÉ — intégré via `c09dd14`.**

Seuls les points dont `timestamp + interval <= as_of` sont consommés.

### ADR-336 — OI historique sans autorité de ranking

**ADOPTÉ — intégré via `c09dd14`.**

Le ranking et la shortlist sont déterminés avant l'enrichissement OI. Toute influence multi-analytics est réservée au Batch 47.5.

## Suite

```text
47.3 : funding historique + liquidation-volume
47.4 : CVD + aggressor-differential
47.5 : éventuelle influence multi-analytics sur le ranking, à décider explicitement
```
