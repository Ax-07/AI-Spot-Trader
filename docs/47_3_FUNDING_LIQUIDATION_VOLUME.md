# Batch 47.3 — Funding historique + Liquidation Volume

## Statut

**PATCH PRÉPARÉ, NON INTÉGRÉ.**

Base GitHub auditée :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : c09dd14cab31233f635ff535cbf0298ba3f2bd51
Commit     : feat: add historical open interest analytics
```

Le Batch 47.2 est intégré via `c09dd14`. Les ADR-333 à ADR-336 sont donc considérées ADOPTÉES.

## Objectif strict

Ajouter exactement deux séries Kraken Futures historiques :

```text
funding
liquidation-volume
```

Le Batch réutilise l'infrastructure Analytics 47.2. Il ne crée ni nouvelle rotation indépendante, ni nouveau transport Kraken Futures.

Hors périmètre : CVD, aggressor-differential, long/short ratio, top traders, orderbook Analytics, liquidity/slippage Analytics, future basis, filtres Funding/Liquidation, ranking multi-analytics, Agent/Risk Engine, exécution PERPETUAL.

## Audit Kraken

Endpoint commun :

```text
GET https://futures.kraken.com/api/charts/v1/analytics/{venue_symbol}/{analytics_type}
```

Paramètres :

```text
since    : epoch secondes
interval : résolution en secondes
to       : epoch secondes, optionnel dans le contrat mais toujours borné par le Radar
```

Intervalles autorisés :

```text
60 / 300 / 900 / 1800 / 3600 / 14400 / 43200 / 86400 / 604800
```

Le contrat générique expose :

```text
result.timestamp[]
result.data
result.more
errors[]
```

### Funding

Le schéma public Funding est dédié :

```text
result.data.rate[]
result.data.relativeRate[]
```

Les deux séries contiennent des buckets OHLC de quatre nombres. Elles sont signées. Le smoke réel `PF_XBTUSD` du 2026-10-04 confirme que `result.timestamp[]` est exprimé en **millisecondes epoch** pour cet endpoint Funding ; le parser normalise explicitement cette unité.

Sémantique conservée :

- `rate` = série absolue/raw fournie par Kraken ;
- `relativeRate` = taux relatif fourni par Kraken ;
- `fundingRatePrediction` du ticker 47.1 reste une prévision distincte ;
- aucune valeur historique n'est renommée « funding réalisé » sans preuve fournisseur correspondante.

Le signe du funding est descriptif : positif signifie le côté long payeur, négatif le côté short payeur. Cette information ne constitue pas une instruction de trading.

### Liquidation Volume

Kraken décrit `liquidation-volume` comme le volume/valeur total des positions futures forcées à la clôture sur l'intervalle.

Aucune dimension native démontrée ne permet de renommer une composante LONG ou SHORT. Le modèle reste donc strictement agrégé :

```text
current_volume
previous_volume
baseline_volume
volume_change
volume_change_ratio
```

Aucun champ `long_liquidations`, `short_liquidations` ou équivalent n'est créé.

Le smoke réel `PF_XBTUSD` du 2026-10-04 confirme `result.timestamp[]` en **secondes epoch** et `result.data[]` sous forme de scalaires non négatifs pour `liquidation-volume`. Le schéma générique Analytics permet par ailleurs une donnée scalaire ou un bucket OHLC. Le parser accepte ces deux formes uniquement :

- scalaire fini et non négatif ;
- OHLC de quatre valeurs finies/non négatives et cohérentes ;
- pour OHLC, `close` devient la valeur représentative ;
- aucune composante OHLC n'est interprétée comme un côté de liquidation.

L'unité/currency n'étant pas figée dans le contrat exploité, le cockpit n'ajoute pas de suffixe USD inventé.

## Smokes publics

Smokes read-only exécutés localement par l'utilisateur le 2026-10-04 sur `PF_XBTUSD` :

```text
funding            : PASS — data.rate[] OHLC, data.relativeRate[] OHLC, timestamp en millisecondes, more=false, errors=[]
liquidation-volume : PASS — data[] scalaire non négatif, timestamp en secondes, more=false, errors=[]
```

Le smoke Funding a révélé une divergence d'unité de timestamp par rapport aux séries génériques : Funding utilise des millisecondes alors que Liquidation Volume utilise des secondes. Le correctif Batch 47.3 normalise donc explicitement Funding en millisecondes sans modifier Open Interest ni Liquidation Volume.

## Architecture

```text
PerpetualAnalyticsMarketAttentionRadar
  -> PerpetualAnalyticsScanner
      -> KrakenAttentionCatalogue
          -> KrakenDerivativesAnalyticsClient
              -> open-interest
              -> funding
              -> liquidation-volume
```

Un seul curseur sélectionne les marchés. Un seul cache `PerpetualAnalyticsSnapshot` contient les résultats des séries attendues. La concurrence HTTP de toutes les séries partage le même sémaphore.

Le catalogue expose :

```text
open_interest_history()
funding_history()
liquidation_volume_history()
```

Compatibilité 47.2 : un provider historique/test qui n'expose que `open_interest_history()` continue à fonctionner ; les séries non exposées ne deviennent pas implicitement des erreurs OI.

## Budget réseau

Policy 47.2 conservée :

```text
market_limit_per_refresh = 10
cache_ttl_seconds        = 3600
history_interval_seconds = 3600
history_lookback_seconds = 172800
fetch_concurrency        = 4
baseline_periods         = 12
```

Pour le provider Kraken de production, chaque marché sélectionné peut nécessiter trois appels Analytics :

```text
open-interest
funding
liquidation-volume
```

Plafond théorique par défaut :

```text
10 marchés × 3 séries = 30 requêtes / refresh
```

La concurrence simultanée reste bornée à `4`. Le scanner n'augmente pas automatiquement la limite ou la concurrence.

`requests_attempted` / `requests_failed` comptent désormais les appels de série réellement tentés ; `scanned_market_count` reste un nombre de marchés.

## Causalité

L'ADR-335 reste inchangée :

```text
point utilisable si timestamp + interval <= as_of
```

La requête est bornée par `to=as_of`. Les timestamps doivent être strictement croissants. `more=true` est rejeté afin de ne pas consommer silencieusement un historique tronqué ni dépasser le budget réseau prévu.

## Funding — statistiques

La statistique adaptative est calculée sur `relativeRate`, plus comparable historiquement que la série absolue/raw :

```text
baseline_relative = median(relativeRate historique hors courant)
MAD               = median(abs(relativeRate - baseline_relative))
dispersion        = 1.4826 * MAD
score             = (current_relative - baseline_relative) / dispersion
```

Seuil descriptif :

```text
score >= +2.5 et current_relative > 0
  => FUNDING_POSITIVE_EXTREME

score <= -2.5 et current_relative < 0
  => FUNDING_NEGATIVE_EXTREME
```

Aucun fallback ratio n'est utilisé lorsque `MAD == 0` sur la série signée Funding. La méthode devient `UNAVAILABLE` plutôt que de fabriquer une division ou une sémantique ratio trompeuse.

Le `rate` absolu/raw, sa valeur précédente et sa baseline médiane restent observables séparément.

## Liquidation Volume — statistiques

La série agrégée est non négative :

```text
baseline = median(volume historique hors courant)
MAD      = median(abs(volume - baseline))
score    = (current - baseline) / (1.4826 * MAD)
```

Seuil :

```text
score >= +3.0
  => LIQUIDATION_VOLUME_SPIKE
```

Lorsque `MAD == 0`, le fallback `current / baseline >= 2.0` est possible uniquement si `baseline > 0`. Une baseline zéro ne produit pas de ratio artificiel.

Aucune caractéristique de « liquidation faible » n'est créée dans ce batch.

## Modèle API additif

`PerpetualAnalyticsSnapshot` conserve tous les champs OI 47.2 et ajoute :

```text
open_interest_status
funding
liquidation_volume
```

`funding` expose notamment :

```text
status
current_rate
previous_rate
baseline_rate
current_relative_rate
previous_relative_rate
baseline_relative_rate
baseline_relative_rate_mad
relative_rate_change
relative_rate_anomaly_score
relative_rate_anomaly_method
```

`liquidation_volume` expose notamment :

```text
status
current_volume
previous_volume
baseline_volume
baseline_volume_mad
volume_change
volume_change_ratio
volume_anomaly_score
volume_anomaly_method
```

`PerpetualAnalyticsCoverageDiagnostics` ajoute `series_coverage` avec les comptes `AVAILABLE`, `INSUFFICIENT_HISTORY`, `STALE`, `TECHNICAL_ERROR`, `UNAVAILABLE` pour chaque série.

Le protocole reste `market-attention-radar-v6` : extension additive uniquement.

## Autorité et ranking

Le parent calcule toujours la shortlist canonique avant l'enrichissement Analytics. Les nouvelles caractéristiques peuvent seulement être ajoutées à un candidat existant :

```text
FUNDING_POSITIVE_EXTREME
FUNDING_NEGATIVE_EXTREME
LIQUIDATION_VOLUME_SPIKE
```

Elles :

```text
n'influencent pas interest_level
n'influencent pas candidate_limit
n'influencent pas la clé de ranking
ne créent pas seules un candidat
```

Toute éventuelle influence multi-analytics reste réservée au Batch 47.5.

## Cockpit

Dans le détail PERPETUAL :

- Open Interest historique 47.2 conservé ;
- Funding historique : raw/absolu séparé du relatif, score relatif et méthode ;
- Liquidation Volume : total agrégé seulement ;
- caractéristiques Analytics ;
- couverture par série dans le bloc global Analytics Futures ;
- compteur de requêtes et rappel du budget 3 séries.

Aucun nouveau filtre utilisateur.

## Tests ajoutés

Backend :

```text
backend/tests/test_kraken_derivatives_batch47_3_funding_liquidations.py
backend/tests/test_market_attention_batch47_3_funding_liquidations.py
```

Frontend :

```text
frontend/src/lib/market-attention-batch47_3.test.mjs
```

Le script `pnpm test` inclut ce nouveau fichier.

## Validation réellement exécutée

Dans l'environnement ChatGPT après le correctif timestamp Funding :

```text
python -m py_compile parser + test Batch 47.3                  : PASS
pytest ciblé Batch 47.3 avec stubs du checkout partiel         : PASS — 23/23
smoke logique de compatibilité OI Batch 47.2                   : PASS
tsc --noEmit --strict ciblé market-attention.ts                : PASS
typecheck ciblé cockpit avec stubs React/UI                    : PASS
node --test market-attention-batch47_3.test.mjs                : PASS — 4/4
```

Localement par l'utilisateur avant le correctif timestamp Funding :

```text
backend python -m pytest -q : PASS — suite complète à 100 %
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 76/76
git diff --check            : PASS — avertissements LF/CRLF uniquement
smoke Kraken Funding        : PASS — PF_XBTUSD, OHLC, timestamp ms, more=false
smoke Kraken Liquidation    : PASS — PF_XBTUSD, scalaire, timestamp s, more=false
```

Après extraction du ZIP correctif, seule la revalidation backend complète et `git diff --check` restent obligatoires avant commit/push ; aucun fichier frontend n'est modifié par le correctif.

## Décisions proposées

### ADR-337 — Rotation/cache Analytics unique

OI, Funding et Liquidation Volume partagent une seule rotation/cache, avec un sémaphore commun.

### ADR-338 — Funding absolu/raw, relatif et prédiction restent distincts

La statistique porte sur `relativeRate`. Le raw historique et la prédiction ticker restent séparés et observables.

### ADR-339 — Liquidation Volume reste agrégé et descriptif

Aucune direction LONG/SHORT n'est inventée et aucune autorité de ranking n'est introduite.

## Suite prévue

```text
47.4 : CVD + aggressor-differential
47.5 : éventuelle influence multi-analytics sur le ranking, à décider explicitement
```
