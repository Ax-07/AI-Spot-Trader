# Batch 47.4 — CVD + Aggressor Differential

## Statut

**INTÉGRÉ SUR GITHUB `main` VIA `472f3ad` APRÈS VALIDATION LOCALE ET SMOKES RÉELS.**

Base auditée :

```text
Repository           : Ax-07/AI-Spot-Trader
Branche              : main
HEAD GitHub de départ: ec1cd5dc576c8638bff7c7110aa9a0a2292f71ff
Message HEAD         : docs: mark batch 47.3 integrated
Commit fonctionnel 47.3 intégré : 12051a7 — feat: add historical funding and liquidation analytics
Commit fonctionnel 47.4 intégré : 472f3ad — feat: add CVD and aggressor analytics
```

Aucun changement GitHub n'a été effectué directement par ChatGPT. L'intégration a été réalisée localement par l'utilisateur puis poussée sur `main`.

## Objectif

Ajouter les séries publiques Kraken Futures :

```text
cvd
aggressor-differential
```

sans modifier la shortlist ou le ranking et sans créer une nouvelle infrastructure Analytics.

## Audit avant modification

### Confirmé

- `KrakenDerivativesAnalyticsClient` est le client Analytics public canonique ;
- `PerpetualAnalyticsScanner` est l'unique scanner historique Futures ;
- un seul `_cache` et un seul `_perpetual_analytics_cursor` existent ;
- un seul sémaphore global `fetch_concurrency` borne les requêtes d'un refresh ;
- les séries additionnelles sont appelées par nom de méthode avec `getattr`, ce qui permet un comportement fail-soft pour un provider legacy ;
- `PerpetualAnalyticsSnapshot` et `perpetual_analytics_coverage` sont les modèles canoniques ;
- le ranking/shortlist est construit par la chaîne canonique avant l'enrichissement Analytics ;
- Funding et Liquidation Volume 47.3 sont déjà intégrés et utilisent la même rotation/cache.

### Obsolète

- la référence courte de `docs/00_ETAT_ACTUEL.md` pointait encore sur la première clôture documentaire `21cac8f` alors que le HEAD GitHub réel de départ est `ec1cd5d` ;
- la roadmap présentait encore 47.4 uniquement comme batch futur.

### Manquant avant ce patch

- parser Kraken CVD ;
- parser Kraken Aggressor Differential ;
- modèles provider-neutral pour les deux domaines signés ;
- statistiques CVD change et Aggressor ;
- caractéristiques descriptives ;
- couverture à cinq séries ;
- blocs cockpit CVD/Aggressor ;
- tests 47.4 backend/frontend.

### À décider ultérieurement

- influence multi-analytics sur le ranking ;
- pondération ou déduplication CVD/Aggressor ;
- filtres utilisateurs Analytics ;
- utilisation du Radar Futures comme contexte Agent.

Ces points restent réservés au Batch 47.5 ou à une décision explicite ultérieure.

## Source Kraken

Endpoint unique :

```text
GET /api/charts/v1/analytics/{venue_symbol}/{analytics_type}
```

Types utilisés :

```text
cvd
aggressor-differential
```

Paramètres réutilisés :

```text
since
interval
to
```

Aucun endpoint, client HTTP ou transport parallèle n'est créé.

## Contrat CVD retenu

Le smoke réel utilisateur `PF_XBTUSD/cvd` du 2026-10-05 confirme :

```text
result.timestamp[]            : epoch secondes
result.data.buy_volume[]      : décimaux non négatifs
result.data.sell_volume[]     : décimaux non négatifs
result.data.cvd[]             : décimaux signés
result.more                   : false
errors                        : []
```

Point important : dans le payload observé, `timestamp[]`, `buy_volume[]` et `cvd[]` contenaient 6 valeurs tandis que `sell_volume[]` n'en contenait que 4. Les tableaux de volumes latéraux ne portent pas leurs propres timestamps ; il serait donc incorrect de les réindexer, de les compléter ou de supposer que les valeurs manquantes se trouvent à la fin.

Contrat applicatif 47.4 corrigé :

```text
timestamp[] + cvd[] : obligatoirement alignés 1:1, chronologie stricte
buy_volume[]        : diagnostique seulement
sell_volume[]       : diagnostique seulement
```

Le parser accepte les clés live `buy_volume` / `sell_volume` / `cvd` et garde aussi la variante camelCase `buyVolume` / `sellVolume` / `cvd` pour compatibilité documentaire. Les volumes buy/sell sont exposés sur les points uniquement lorsque **les deux** tableaux ont exactement la longueur de `timestamp[]`. Si l'un des deux tableaux est incomplet, le CVD reste exploitable et les champs `buy_volume` / `sell_volume` deviennent `None` pour tous les points du payload. Aucun padding, forward-fill, décalage ou timestamp implicite n'est inventé.

Contraintes conservées :

```text
cvd                     signé et fini
buy/sell si présents    finis et >= 0
more                    = false
errors                  vide
ordre timestamp         strictement croissant
```

### Timestamp CVD

Le smoke réel confirme **epoch secondes**. Cette unité n'est plus provisoire dans le Batch 47.4.

## Contrat Aggressor Differential retenu

Sémantique documentée :

```text
taker buy volume - taker sell volume
```

Le smoke réel utilisateur `PF_XBTUSD/aggressor-differential` confirme :

```text
result.timestamp[] : epoch secondes
result.data[]       : scalaires décimaux signés
result.more         : false
errors              : []
```

La série reste descriptive :

```text
> 0 : pression agressive acheteuse sur l'intervalle
< 0 : pression agressive vendeuse sur l'intervalle
= 0 : équilibre
```

Le parser accepte uniquement une valeur scalaire décimale finie par timestamp. Les formes OHLC/objet ne sont pas acceptées « au cas où ». Kraken décrit l'unité comme la devise de base ; aucun suffixe USD ni conversion n'est ajouté.

### Timestamp Aggressor Differential

Le smoke réel confirme **epoch secondes**. Cette unité n'est plus provisoire dans le Batch 47.4.

## Provider-neutral

Nouveaux points :

```text
PerpetualCvdPoint
  observed_at
  cvd
  buy_volume | None
  sell_volume | None

PerpetualAggressorDifferentialPoint
  observed_at
  value
```

Ils restent séparés de `PerpetualAnalyticsPoint`, qui impose une valeur non négative adaptée à OI/Liquidation Volume.

## Analyse CVD

Le niveau cumulatif reste observable :

```text
current_cvd
previous_cvd
```

L'anomalie porte sur :

```text
cvd_change = current_cvd - previous_cvd
```

Baseline :

```text
baseline_cvd_change = median(changes historiques précédant le changement courant)
MAD = median(abs(change - baseline_cvd_change))
score = (current_change - baseline) / (1.4826 * MAD)
```

Le point courant est exclu de sa propre baseline. Les points futurs et buckets non finalisés sont exclus par la règle causale commune.

Lorsque `MAD == 0` :

```text
method = UNAVAILABLE
score = null
```

Aucun fallback ratio n'est utilisé sur cette série signée.

## Analyse Aggressor Differential

Baseline :

```text
baseline = médiane historique précédant le point courant
MAD = median(abs(value - baseline))
score robuste signé
```

Lorsque `MAD == 0`, aucune sémantique de ratio n'est fabriquée : méthode `UNAVAILABLE`, score absent.

## Seuils descriptifs

Centralisés dans `PerpetualAnalyticsPolicy` :

```text
cvd_anomaly_score_threshold       = 2.5
aggressor_anomaly_score_threshold = 2.5
```

Application symétrique :

```text
CVD positive impulse : score >= +2.5 et cvd_change > 0
CVD negative impulse : score <= -2.5 et cvd_change < 0
Aggressor buy dominance  : score >= +2.5 et current_value > 0
Aggressor sell dominance : score <= -2.5 et current_value < 0
```

Ces seuils sont expérimentaux, descriptifs et non optimisés sur le P&L.

## Caractéristiques

```text
CVD_POSITIVE_IMPULSE
CVD_NEGATIVE_IMPULSE
AGGRESSOR_BUY_DOMINANCE
AGGRESSOR_SELL_DOMINANCE
```

Les paires positives/négatives ont exactement le même seuil absolu.

Aucun nom `BUY_SIGNAL`, `SELL_SIGNAL`, `BULLISH_CVD` ou `BEARISH_CVD` n'est introduit.

## Rotation/cache unique et coût réseau

Avant 47.4 :

```text
3 séries × 10 marchés = 30 requêtes max / refresh
```

Après 47.4 :

```text
5 séries × 10 marchés = 50 requêtes max / refresh
```

Inchangés :

```text
market_limit_per_refresh = 10
fetch_concurrency        = 4
cadence                   = inchangée
```

OI, Funding, Liquidation Volume, CVD et Aggressor Differential partagent :

```text
un seul PerpetualAnalyticsScanner
un seul _perpetual_analytics_cursor
un seul _cache
un seul sémaphore global
une seule policy
```

Aucun cache/cursor par nouvelle série n'est créé.

## Causalité

La règle ADR-335 est conservée :

```text
point exploitable si timestamp + interval <= as_of
requête bornée par to <= as_of
```

Aucun point futur, bucket non finalisé, look-ahead ou sélection post-hoc.

## Statut combiné et fail-soft

Chaque série conserve son propre statut :

```text
AVAILABLE
INSUFFICIENT_HISTORY
STALE
TECHNICAL_ERROR
```

Le snapshot global agrège les cinq séries. Une erreur CVD ne supprime pas OI/Funding/Liquidation/Aggressor, et inversement.

Les providers legacy sans `cvd_history()` ou `aggressor_differential_history()` restent compatibles : les nouvelles séries sont `UNAVAILABLE` au niveau coverage / absentes du snapshot et les anciennes séries continuent d'être analysées.

## Coverage

`series_coverage` contient désormais :

```text
open-interest
funding
liquidation-volume
cvd
aggressor-differential
```

`scanned_market_count` reste un nombre de marchés. `requests_attempted` compte uniquement les méthodes de séries réellement appelées.

## Ranking et shortlist

Aucun changement de ranking en 47.4.

CVD/Aggressor peuvent uniquement enrichir un candidat déjà retenu via :

```text
perpetual_analytics
combined_characteristics
interest_reasons descriptives
cockpit
```

Ils ne peuvent pas :

```text
modifier interest_level
modifier la sort key
modifier candidate_limit
créer un candidat
forcer une shortlist
```

La relation conceptuelle CVD/Aggressor est explicitement reconnue : les deux proviennent de l'order flow agressif. Aucun double bonus n'est créé en 47.4. La décision de combinaison/déduplication est réservée au Batch 47.5.

## Cockpit

Deux blocs sont ajoutés à `Analytics Futures` :

### CVD

```text
CVD courant
variation CVD
variation précédente
baseline variation
MAD
score adaptatif
méthode
buy volume
sell volume
statut
fraîcheur
point Kraken
```

### Aggressor Differential

```text
différentiel courant
précédent
baseline
MAD
variation
score
méthode
statut
fraîcheur
point Kraken
```

Libellés descriptifs :

```text
impulsion CVD positive
impulsion CVD négative
pression agressive acheteuse
pression agressive vendeuse
```

Aucun suffixe `$`, `USD`, `%` ou `contracts` n'est inventé pour CVD. Le texte cockpit mentionne l'unité base de l'Aggressor comme sémantique fournisseur, sans conversion.

## API / protocole

`market-attention-radar-v6` est conservé et étendu additivement. Aucune route REST supplémentaire.

Les champs `cvd` et `aggressor_differential` sont optionnels côté TypeScript afin que les payloads 47.3 restent acceptables.

## Fichiers modifiés/créés

```text
backend/src/ai_spot_trader/integrations/kraken/analytics.py
backend/src/ai_spot_trader/integrations/kraken/attention.py
backend/src/ai_spot_trader/market/perpetual_analytics.py
backend/src/ai_spot_trader/market/attention_perpetual_analytics.py
backend/tests/test_kraken_derivatives_batch47_4_cvd_aggressor.py
backend/tests/test_market_attention_batch47_3_funding_liquidations.py
backend/tests/test_market_attention_batch47_4_cvd_aggressor.py
frontend/src/lib/market-attention.ts
frontend/src/lib/market-attention-batch47_4.test.mjs
frontend/src/components/cockpit/market-attention-dock.tsx
frontend/package.json
docs/00_ETAT_ACTUEL.md
docs/09_ROADMAP_DEVELOPPEMENT.md
docs/10_DECISIONS_ET_CHANGELOG.md
docs/47_4_CVD_AGGRESSOR_DIFFERENTIAL.md
```

## Smokes Kraken

### Exécutés localement par l'utilisateur — PASS

Le 2026-10-05, sur `PF_XBTUSD` :

```text
cvd
  timestamp[]        : 6 valeurs, epoch secondes
  buy_volume[]       : 6 valeurs
  sell_volume[]      : 4 valeurs
  cvd[]              : 6 valeurs signées
  more               : false
  errors             : []

aggressor-differential
  timestamp[]        : 6 valeurs, epoch secondes
  data[]             : 6 scalaires signés
  more               : false
  errors             : []
```

Le smoke CVD constitue une régression fournisseur importante : les side-volume arrays ne sont pas nécessairement alignables. Le correctif 47.4 utilise donc uniquement `timestamp[] + cvd[]` comme série historique obligatoire et rend les volumes latéraux optionnels/fail-soft.

Les tentatives ChatGPT antérieures avaient échoué pour raison d'accès réseau ; elles ne sont pas requalifiées en PASS. Le PASS live provient explicitement de l'exécution locale utilisateur.

## Validation

### Tests réellement exécutés par ChatGPT avant le smoke

```text
python -m py_compile backend patch                       : PASS
pytest statistiques/scanner 47.4 via harnais isolé     : PASS — 16/16
pytest parsers/routes Kraken 47.4 via harnais isolé     : PASS — 22/22
régression logique parsers OI/Funding/Liquidation 47.3 : PASS
node --test market-attention-batch47_4.test.mjs         : PASS — 6/6
tsc --noEmit --strict ciblé market-attention.ts         : PASS
parse/transpile TypeScript ciblé cockpit + lib          : PASS
```

### Première validation locale utilisateur — avant correctif

```text
backend python -m pytest -q : ÉCHEC — 1 seul test 47.3 obsolète
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 82/82
git diff --check            : PASS — avertissements LF/CRLF uniquement
smoke CVD                   : PASS — secondes, snake_case, side arrays de longueurs différentes
smoke Aggressor             : PASS — secondes, scalaires signés
```

L'unique échec backend était `test_scanner_reuses_one_rotation_and_bounds_total_http_concurrency` du Batch 47.3 : il exigeait encore une liste de coverage à 3 séries alors que 47.4 en expose additivement 5. Le correctif met ce test de régression à jour : le provider legacy continue à tenter seulement 3 requêtes, tandis que CVD et Aggressor apparaissent comme `UNAVAILABLE` dans la coverage.

### Correctif après smokes — tests exécutés par ChatGPT

```text
py_compile fichiers backend corrigés                                      : PASS
pytest ciblé parser 47.4 + régression 47.3 + scanner/statistiques 47.4 : PASS — 47/47
node --test market-attention-batch47_4.test.mjs                         : PASS — 6/6
```

Le correctif fourni après les smokes modifie le parser CVD, le modèle CVD provider-neutral, le test parser 47.4, le test de régression 47.3, le texte cockpit et la documentation. La suite complète a ensuite été relancée localement par l’utilisateur et atteint 100 % sans échec.
### Validation locale finale utilisateur — après correctif

```text
backend python -m pytest -q : PASS — suite complète à 100 %
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 82/82
git diff --check            : PASS — avertissements LF/CRLF uniquement
smoke CVD                   : PASS — secondes, snake_case, side arrays de longueurs différentes
smoke Aggressor             : PASS — secondes, scalaires signés
```

Le Batch 47.4 est **intégré sur GitHub `main` via `472f3adca1d19822289af47b52b03afab3cda0fb`**. Après le push, `origin/main` et le HEAD local pointent sur `472f3ad`, et `git status --short` est vide.

Vérification d’intégration observée :

```text
git push origin main   : PASS — ec1cd5d..472f3ad
git status --short     : vide
git log -1 --oneline   : 472f3ad feat: add CVD and aggressor analytics
```

## Invariants préservés

- un seul Agent IA stratégique ;
- Kraken exchange initial ;
- trading/exécution SPOT uniquement ;
- aucune exécution PERPETUAL ;
- aucun short, levier ou margin ;
- Radar strictement informatif ;
- aucune décision `BUY / SELL / HOLD` par Analytics ;
- Risk Engine autorité finale ;
- aucune sortie Radar directe vers Broker ;
- aucune sortie LLM directe vers Kraken ;
- PAPER ;
- aucune donnée future / aucun look-ahead ;
- aucun secret ni clé privée nécessaire pour Analytics ;
- aucune auto-optimisation P&L ;
- aucune promesse de rendement.
