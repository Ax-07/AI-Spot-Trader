# Batch 45 — Market Structure en amont et filtres tendance/structure

## Statut

**Intégré sur GitHub `main` via `45d41b7` — `feat: move market structure before radar shortlist`.**

Le patch avait été préparé depuis le HEAD `c4f474c`. La documentation antérieure qui indiquait encore « proposé, non intégré » était devenue obsolète après l'intégration et est réconciliée par le Batch 46.

## Objectif

Rendre la Market Structure utilisable comme source descriptive d'attention **avant la shortlist finale**, afin qu'une dégradation ou un retournement structurel confirmé puisse devenir visible même lorsque `MarketActivityState = NORMAL`.

Le Radar reste strictement informatif. Une structure n'est jamais traduite en `BUY`, `SELL` ou `HOLD` et n'a aucune autorité sur Agent, Risk Engine ou Broker.

## Audit d'origine

### Confirmé

Avant le Batch 45, `StructuredMarketAttentionRadar` recevait un `MarketAttentionOverviewV4` dont la shortlist avait déjà été constituée par activité + microstructure, puis calculait `_market_structure_for_market()` uniquement sur cette shortlist.

Ancien pipeline :

```text
catalogue
-> scope
-> capitalisation
-> rotation OHLCV
-> volume
-> activité / tendance / liquidité
-> microstructure SPOT
-> shortlist canonique
-> Structure 5m / 15m / 1h / 4h uniquement sur la shortlist
```

Un marché pouvait donc présenter `activité NORMAL`, `H1 BEARISH` et `H4 TRANSITION + CHOCH_DOWN` sans être analysé par la Structure si l'ancien sélecteur ne le retenait pas.

### Obsolète depuis l'intégration

- Structure nécessairement post-shortlist ;
- couverture Structure déduite du diagnostic OHLCV ;
- simple régime permanent `BULLISH`/`BEARISH` assimilé à une anomalie par défaut.

## Pipeline intégré

```text
catalogue Kraken
-> scope SPOT / PERPETUAL / ALL
-> métadonnées / filtre capitalisation
-> rotation/cache OHLCV
-> volume 24h / filtre volume
-> activité / tendance / liquidité
-> microstructure SPOT canonique
-> pool Market Structure éligible
-> rotation Structure bornée
-> cache Structure frais
-> filtres tendance / Structure
-> shortlist finale bornée par candidate_limit
-> cockpit
```

Le runtime appelle le niveau v4 après microstructure afin de ne pas exécuter deux pipelines Structure concurrents.

## Pool et policy Structure

Un marché entre dans le pool Structure uniquement après les filtres moins coûteux lorsqu'il possède une activité fraîche/exploitable.

`MarketStructurePolicy` reste la policy géométrique et causale : historique, minimum de candles, pivots gauche/droite, tolérance d'égalité, limite des swings et concurrence de fetch.

`MarketStructureScanPolicy` sépare la responsabilité réseau/cache :

```text
market_limit_per_refresh = 20
cache_ttl_seconds        = 3600
```

La rotation Structure possède un curseur indépendant de la rotation OHLCV.

## Cache et causalité

Le cache conserve directement `MultiTimeframeMarketStructure` et son `observed_at`.

Réutilisation autorisée uniquement si :

```text
cached.observed_at <= as_of
ET as_of - cached.observed_at <= cache_ttl
```

Les analyses natives conservent :

```text
history_as_of(observed_at)
candles finalisées uniquement
close_time <= observed_at
updated_at <= observed_at
pivot visible uniquement après pivot_right_bars clôturées
```

## Diagnostic de couverture Structure

Le payload v6 expose `structure_coverage`, distinct du diagnostic OHLCV :

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
oldest_structure_age_seconds
rotation_within_cache_ttl
status
```

Statuts : `NO_MARKETS`, `COVERED`, `ROTATING`, `TTL_EXPIRED`, `CONFIGURATION_TOO_SLOW`.

Le Radar observe une configuration trop lente mais n'augmente aucune limite automatiquement.

## Attention structurelle par défaut

```text
BULLISH / BEARISH / RANGE / TRANSITION sans événement
=> ne force pas un candidat

BOS_UP / BOS_DOWN / CHOCH_UP / CHOCH_DOWN confirmé
=> peut compléter la shortlist canonique
```

Le classement est directionnellement symétrique. À intérêt canonique identique :

1. timeframe `4h > 1h > 15m > 5m` ;
2. `CHOCH > BOS` à timeframe identique ;
3. critères microstructure/activité canoniques ensuite.

La Structure complète le ranking canonique ; elle ne crée pas un ranking stratégique parallèle.

## Filtres runtime

`StructureAwareMarketAttentionFilters` ajoute :

```text
trend_directions
structure_global_states
structure_5m.states / events
structure_15m.states / events
structure_1h.states / events
structure_4h.states / events
```

Sémantique :

```text
plusieurs valeurs dans un champ       => OR
plusieurs timeframes configurées       => AND
plusieurs familles de filtres          => AND
state + event sur même timeframe       => AND
champ vide                              => aucune contrainte
UNKNOWN / absent / expiré / non couvert => fail-closed si filtre actif
```

Sans filtre tendance/Structure explicite, seuls les candidats canoniques ou un événement Structure confirmé entrent dans le pool final. Avec un filtre explicite, les régimes persistants correspondants peuvent être recherchés volontairement.

## Contrat API et cockpit

Le protocole reste `market-attention-radar-v6`, avec extension additive. Routes conservées :

```text
GET /api/v1/market-attention
GET /api/v1/market-attention/filters
PUT /api/v1/market-attention/filters
PUT /api/v1/market-attention/scope
GET /api/v1/market-attention/history
```

Le cockpit expose les filtres tendance/Structure et distingue un zéro résultat avec couverture Structure incomplète d'un zéro réel avec couverture complète.

## Cas synthétique

```text
activité NORMAL
trend DOWN
H1 BEARISH / BOS_DOWN
H4 TRANSITION / CHOCH_DOWN
```

Le marché peut devenir visible sans ancien candidat activité/microstructure. Le scénario haussier symétrique reçoit la même priorité directionnelle. Aucun code n'est spécifique à PENDLE.

## Validation connue

Validations exécutées par ChatGPT sur le patch avant intégration :

```text
python -m py_compile <fichiers Python modifiés> : PASS
frontend market-attention.test.mjs ciblé       : PASS — 16/16
tsc ciblé market-attention.ts                  : PASS
tsc cockpit ciblé avec stubs                   : PASS
```

Le commit `45d41b7` confirme l'intégration du code. Il ne constitue pas, à lui seul, une preuve d'exécution de la suite complète ; aucune validation complète supplémentaire n'est inventée ici.

## Décisions

Les ADR-325, ADR-326 et ADR-327 sont **adoptés** depuis l'intégration du Batch 45 : séparation géométrie/scan Structure, attention par événements confirmés plutôt que régime permanent, filtres fail-closed avec diagnostic de couverture.

## Invariants préservés

- un seul Agent IA ;
- Radar informatif uniquement ;
- aucun `BUY`, `SELL`, `HOLD` produit par le Radar ;
- Risk Engine autorité finale ;
- aucune sortie Radar directement vers Kraken ;
- aucune modification Agent / Risk Engine / Broker ;
- aucune capacité d'exécution PERP ;
- SPOT/PAPER ;
- causalité stricte ;
- aucune donnée future ;
- aucun secret ;
- aucune promesse de rendement.
