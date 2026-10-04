# Batch 47.2 — Open Interest historique et infrastructure Analytics Futures

## Statut

**Patch préparé, non intégré.**

Base auditée :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 842e6bd7f005f1f57bd9b2131d201777020d1d24
Commit     : feat: add futures ticker analytics foundations
```

Le Batch 47.1 est intégré à ce HEAD. Les mentions documentaires antérieures indiquant « patch préparé, non intégré » pour 47.1 ainsi que `ADR-331/332 PROPOSÉ` étaient obsolètes.

## Objectif strict

Le Batch 47.2 introduit **une seule série Futures historique** :

```text
OPEN INTEREST
```

et l'infrastructure commune de rotation/cache/coverage qui pourra être réutilisée par les Batches suivants.

Hors périmètre : funding historique, liquidation-volume, CVD, aggressor-differential, long/short ratio, microstructure Futures, filtre utilisateur OI, autorité de ranking OI, Agent/Risk Engine utilisant l'OI et exécution PERPETUAL.

## Source Kraken auditée

Contrat public retenu :

```text
GET https://futures.kraken.com/api/charts/v1/analytics/{venue_symbol}/open-interest
```

Paramètres documentés :

```text
since    : int64, epoch secondes, obligatoire
interval : résolution en secondes, obligatoire
to       : int64, epoch secondes, optionnel
```

Résolutions documentées :

```text
60
300
900
1800
3600
14400
43200
86400
604800
```

Schéma générique officiel audité : la documentation décrit `timestamp` comme `integer[]`, `more` comme booléen et `data` via une union de sous-formes Analytics incluant `Ohlc`.

Le smoke public local réalisé sur `PF_XBTUSD` avec `interval=3600` a confirmé la forme réellement utilisée par `open-interest` :

```json
{
  "result": {
    "timestamp": [1791122400, 1791126000],
    "data": [
      ["2113.6645", "2115.6165", "2109.5432", "2112.2841"],
      ["2112.2841", "2144.3341", "2109.0608", "2142.3721"]
    ],
    "more": false
  },
  "errors": []
}
```

La continuité observée (`open` du bucket suivant égal au `close` précédent) et l'encadrement par `high` / `low` confirment l'interprétation OHLC `[open, high, low, close]`. Le parser 47.2 exige donc désormais **exactement quatre valeurs par bucket**, toutes finies et non négatives, avec `low <= open/close <= high`. Le `close` est la valeur transmise à la série provider-neutral `PerpetualAnalyticsPoint.value`. Les quatre composantes sont conservées dans `KrakenMarketAnalyticsPoint` pour validation et diagnostic.

Une forme scalaire, une longueur différente, un OHLC incohérent ou un objet inconnu est rejeté explicitement. Le parser exige également des timestamps epoch secondes entiers, des longueurs `timestamp/data` identiques, un ordre temporel strictement croissant et, lorsque le champ racine `errors` est présent, une liste vide.

`more=true` est rejeté en Batch 47.2. La raison est volontaire : le coût réseau est borné à une requête OI par marché sélectionné et une page tronquée ne doit pas être interprétée silencieusement comme une baseline complète. Une pagination bornée pourra être décidée ultérieurement si les conditions réelles de rétention/page l'exigent.

La documentation publique auditée ne démontre pas de garantie de rétention exploitable par le projet ; aucune durée n'est inventée dans la policy.

## Unité Open Interest

Le contrat utilisé ne démontre pas une unité économique permettant de nommer la série `open_interest_usd`.

Décision :

```text
open_interest
open_interest_unit = non supposée
```

L'analyse est relative à l'historique propre du marché. Aucune conversion USD, notionnalisation ou facteur de contrat n'est appliqué à l'historique OI dans ce batch.

## Client et provider

Le transport reste dans `integrations/kraken/`.

Le patch ajoute une extension spécialisée du client Futures public canonique :

```text
KrakenDerivativesAnalyticsClient(KrakenDerivativesPublicClient)
```

`KrakenAttentionCatalogue` instancie cette extension **comme son unique client Futures public**. Elle hérite donc de `/instruments`, `/tickers`, ticker individuel et chart mark du client canonique tout en ajoutant `fetch_open_interest_history()`. Aucun deuxième `httpx.AsyncClient` Futures n'est créé dans le Radar.

Le Radar ne connaît pas HTTP. Il dépend de :

```text
PerpetualAnalyticsProvider.open_interest_history(...)
```

et le catalogue adapte les points Kraken vers :

```text
PerpetualAnalyticsPoint(observed_at, value)
```

Cette séparation prépare l'accueil de futures séries sans faire remonter les détails Kraken dans `market/`.

## Policy Analytics

`PerpetualAnalyticsPolicy` centralise :

```text
market_limit_per_refresh = 10
cache_ttl_seconds        = 3600
history_interval_seconds = 3600
history_lookback_seconds = 172800
fetch_concurrency        = 4
baseline_periods         = 12
data_stale_after_seconds = 7200
anomaly_score_threshold  = 2.5
fallback_expansion_ratio = 1.10
fallback_contraction_ratio = 0.90
```

Le lookback par défaut de 48h est une décision applicative conservatrice destinée à obtenir 12 points de baseline à intervalle 1h avec marge ; il ne constitue pas une affirmation de rétention Kraken.

## Coût réseau borné

Batch 47.2 n'interroge qu'une seule série : `open-interest`.

Avec la policy par défaut :

```text
market_limit_per_refresh = 10
analytics types          = 1
requests_max_per_refresh = 10
fetch_concurrency        = 4
```

La policy n'augmente jamais automatiquement la limite ou la concurrence lorsque la couverture est lente. Le diagnostic expose ce problème explicitement.

Le snapshot bulk `/tickers` du Batch 47.1 reste mutualisé et n'est pas remplacé par des requêtes ticker individuelles.

## Pool éligible et insertion pipeline

L'Analytics OI est exécutée après le pipeline canonique de collecte/filtrage peu coûteux. La population est obtenue via `_fresh_activities(as_of)` puis limitée aux :

```text
market_type == PERPETUAL
status == AVAILABLE
```

`_fresh_activities()` applique déjà le scope courant, la capitalisation et, lorsqu'il est actif, le filtre volume.

Le pipeline logique est :

```text
catalogue
-> scope
-> capitalisation
-> OHLCV
-> volume
-> activité adaptative / tendance / liquidité / microstructure
-> pool PERPETUAL Analytics éligible
-> rotation/cache Open Interest
-> Structure canonique
-> shortlist canonique
-> enrichissement OI des candidats déjà sélectionnés
```

Dans l'implémentation, le hook `_scan_structure()` du Radar Batch 47.2 déclenche la rotation OI immédiatement avant le scan Structure, une fois le cache d'activité filtré disponible. Le parent Batch 45 conserve ensuite seul la construction de la Structure et de la shortlist finale. Les résultats OI ne sont lus pour l'enrichissement qu'après cette shortlist : Structure et OI ne dépendent pas l'un de l'autre, et l'OI ne participe pas au ranking.

## Rotation indépendante

`PerpetualAnalyticsScanner` possède :

```text
_perpetual_analytics_cursor
```

Le tri est déterministe par `symbol` dans le pool PERPETUAL. Le curseur est indépendant :

- des curseurs OHLCV SPOT/PERP ;
- du curseur Structure.

`market_limit_per_refresh` borne le nombre de marchés sélectionnés à chaque refresh.

## Cache causal

Le cache est indexé par `ExecutableMarket` et contient `PerpetualAnalyticsSnapshot`.

Réutilisation uniquement si :

```text
cached.observed_at <= as_of
AND
as_of - cached.observed_at <= cache_ttl
```

Un snapshot dont `observed_at > as_of` n'est jamais réutilisé.

Les statuts exposés sont :

```text
AVAILABLE
PARTIAL
NOT_APPLICABLE
INSUFFICIENT_HISTORY
STALE
TECHNICAL_ERROR
```

SPOT => `NOT_APPLICABLE`. Un marché jamais couvert retourne un snapshot `PARTIAL`. Une erreur d'un marché produit `TECHNICAL_ERROR` pour ce marché sans arrêter les autres requêtes de la rotation.

## Causalité et finalisation

L'appel provider utilise toujours :

```text
since = as_of - history_lookback
until = as_of
```

Kraken documente le timestamp en secondes et l'intervalle, mais le contrat public audité ne démontre pas une sémantique de clôture permettant d'affirmer qu'un point portant le timestamp `t` est finalisé à `t`.

Le Batch 47.2 applique donc une règle conservatrice :

```text
point utilisable si point.timestamp + interval <= as_of
```

Conséquences :

- aucun point futur ;
- aucun point de l'intervalle courant ;
- le point courant utilisé dans le score est lui-même finalisé selon cette règle ;
- le point courant est exclu de sa propre baseline.

Cette prudence peut induire un intervalle de retard mais évite le look-ahead tant que la sémantique fournisseur n'est pas démontrée plus précisément.

## Statistiques Open Interest

Le Batch 47.2 réutilise directement les primitives Batch 46 :

```text
_median_absolute_deviation()
_robust_anomaly()
ActivityAnomalyMethod
```

Formule :

```text
current  = dernier point causal finalisé
previous = point causal précédent
history  = points causaux avant current
baseline = median(derniers baseline_periods de history)
MAD      = median(abs(x - baseline))
robust_dispersion = 1.4826 * MAD
score = (current - baseline) / robust_dispersion
```

Le snapshot expose notamment :

```text
current_open_interest
previous_open_interest
baseline_open_interest
baseline_open_interest_mad
open_interest_change
open_interest_change_ratio
open_interest_anomaly_score
open_interest_anomaly_method
baseline_period_count
history_point_count
freshness_seconds
```

`open_interest_change_ratio` mesure la variation relative courant/précédent. Le score adaptatif mesure le **niveau** courant par rapport au régime historique. Les deux notions restent distinctes.

### Seuil robuste

Seuil symétrique :

```text
OPEN_INTEREST_EXPANSION   si score >= +2.5
OPEN_INTEREST_CONTRACTION si score <= -2.5
```

Aucune asymétrie haussière/baisse n'est introduite.

### MAD nul

Si `MAD == 0`, `_robust_anomaly()` n'invente aucun score infini et renvoie `LEGACY_RATIO_FALLBACK` si le ratio courant/baseline est exploitable.

Fallback 47.2 :

```text
current / baseline >= 1.10 -> OPEN_INTEREST_EXPANSION
current / baseline <= 0.90 -> OPEN_INTEREST_CONTRACTION
```

Il s'agit d'un delta symétrique de ±10 % autour de 1.0, documenté comme fallback et non comme seuil optimal universel.

## Couverture Analytics Futures

Le diagnostic `perpetual_analytics_coverage` est distinct de :

```text
coverage              # OHLCV
structure_coverage    # Structure
```

Il expose :

```text
eligible_market_count
fresh_market_count
expired_market_count
unseen_market_count
scanned_market_count
coverage_ratio
effective_market_limit
estimated_refreshes_per_full_rotation
estimated_full_rotation_seconds
cache_ttl_seconds
oldest_snapshot_age_seconds
rotation_within_cache_ttl
requests_attempted
requests_failed
status
```

Statuts :

```text
NO_MARKETS
COVERED
ROTATING
TTL_EXPIRED
CONFIGURATION_TOO_SLOW
```

`CONFIGURATION_TOO_SLOW` est purement diagnostique : aucun changement automatique de limites réseau n'est effectué.

## Impact shortlist volontairement limité

Le contrat v6 reste additif :

```text
candidate.perpetual_analytics
perpetual_analytics_coverage
```

L'OI historique peut ajouter aux candidats déjà retenus :

```text
OPEN_INTEREST_EXPANSION
OPEN_INTEREST_CONTRACTION
raison descriptive associée
```

Mais Batch 47.2 ne modifie pas :

```text
interest_level
candidate_limit
ranking canonique
ranking Structure
MarketStructurePolicy
MarketStructureScanPolicy
baseline adaptative OHLCV Batch 46
```

Un marché normal ne peut donc pas entrer dans la shortlist uniquement à cause de l'OI.

La route FastAPI inclut explicitement `MarketAttentionOverviewV6Analytics` en tête de l'union publique afin que les champs additifs ne soient pas supprimés par une sérialisation vers le modèle v6 Structure plus étroit.

## Cockpit

La ligne principale des candidats reste inchangée.

Dans le détail `Futures Kraken`, une sous-partie `Open Interest historique` affiche :

```text
OI courant historique
OI précédent
variation brute
variation relative
baseline médiane
MAD
score adaptatif
méthode
caractéristique
fraîcheur
point Kraken
snapshot Analytics
statut
```

Aucune unité OI non démontrée n'est affichée.

Un bloc global `Couverture Analytics Futures` affiche la rotation, la couverture, le TTL et les requêtes tentées/échouées afin de distinguer :

```text
aucune anomalie OI
```

de :

```text
univers OI encore partiellement couvert
```

## Tests du patch

### Client/parser Kraken

```text
endpoint /analytics/{venue_symbol}/open-interest
venue_symbol
interval
since/to epoch secondes
payload OHLC live valide
close du bucket utilisé comme valeur historique
historique vide
forme scalaire / longueur OHLC inconnue rejetées
OHLC incohérent rejeté
payload/troncature/provider errors invalides
timestamps invalides
NaN / Infinity
valeur négative
ordre temporel incohérent
HTTP error
JSON invalide
```

### Statistiques et rotation/cache

```text
SPOT NOT_APPLICABLE
baseline médiane
MAD / score robuste
MAD nul / fallback explicite
historique insuffisant
outlier historique
expansion / contraction symétriques
current exclu de baseline
point futur/courant non finalisé exclu
rotation déterministe
market_limit_per_refresh
fetch_concurrency
cache frais
cache expiré
cache futur jamais réutilisé
erreur isolée par marché
requests_attempted / requests_failed
coverage complète / rotation / CONFIGURATION_TOO_SLOW
```

### Frontend

```text
payload 47.1 sans analytics compatible
snapshot OI complet
historique insuffisant
erreur technique
SPOT N/A
score positif/négatif
méthode MAD/fallback
coverage Analytics
```

## Validation réellement exécutée par ChatGPT

Au moment de la préparation du patch :

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
git status       : 16 fichiers Batch 47.2 attendus
```

Le smoke HTTP public read-only `PF_XBTUSD/open-interest` a également réussi côté transport et a retourné six buckets horaires, `more=false`, `errors=[]`. Il a surtout révélé que `data` est OHLC et non scalaire ; cette observation a déclenché le correctif pré-intégration documenté ci-dessus.

Validation réellement exécutée par ChatGPT **après** correction du parser OHLC :

```text
python -m py_compile analytics.py + test parser/client : PASS
pytest parser/client Batch 47.2 avec stubs ciblés       : PASS — 33/33
```

Le checkout complet n'étant pas disponible dans l'environnement ChatGPT, la suite backend complète doit être relancée localement après extraction de ce correctif. Le frontend n'est pas modifié par le correctif OHLC.

## Hors périmètre 47.3+

```text
47.3 : funding historique, liquidation-volume
47.4 : CVD, aggressor-differential
47.5 : décision éventuelle sur l'influence multi-analytics du ranking
long/short ratio
microstructure Futures
filtres OI utilisateur
Agent utilisant l'OI
Risk Engine utilisant l'OI
exécution PERPETUAL
```

## Invariants préservés

- un seul Agent IA stratégique ;
- Radar strictement informatif ;
- aucune décision BUY / SELL / HOLD ;
- aucune décision long / short ;
- Risk Engine autorité finale ;
- exécution SPOT uniquement ;
- aucune exécution PERPETUAL ;
- aucun levier ni margin ;
- PAPER ;
- aucune donnée future ;
- aucun look-ahead ;
- aucune optimisation rétrospective ;
- API Kraken publique uniquement ;
- aucune clé Kraken privée ;
- aucune modification Agent / Risk Engine / Broker ;
- aucun secret ;
- aucune promesse de rendement.
