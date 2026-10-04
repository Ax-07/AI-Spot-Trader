# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les éléments nécessaires à la reprise.

## Principes actifs

Un seul Agent stratégique, Risk Engine autorité finale, aucune sortie LLM directe vers Broker/Kraken, exécution SPOT sans vente d'actif non détenu, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Market Attention Radar reste strictement observationnel et ne prend aucune décision de trading.

## Référence courante

```text
HEAD GitHub observé : 842e6bd7f005f1f57bd9b2131d201777020d1d24
Commit HEAD         : feat: add futures ticker analytics foundations
Batch 43.2          : intégré
Batch 44            : intégré
Batch 45            : intégré via 45d41b7
Batch 46 / 46.1     : intégré via b219365
Batch 47.1          : intégré via 842e6bd7
Batch 47.2          : patch préparé, non intégré
```

## Changelog — 2026-10-04 — Batch 47.2 historique Open Interest — proposé

Base auditée : GitHub `main` au HEAD `842e6bd7`.

Audit de reprise :

- **confirmé** : `842e6bd7` est le HEAD réel observé de `main` et intègre les fondations Futures ticker du Batch 47.1 ;
- **obsolète** : les statuts documentaires présentant Batch 47.1 et ADR-331/332 comme proposés/non intégrés ;
- **confirmé** : `fetch_tickers()` reste le chemin bulk canonique pour le volume PERP, la liquidité PERP et les données Futures instantanées ;
- **confirmé** : la rotation/cache Structure Batch 45 est indépendante et ne doit pas être détournée pour les Analytics Futures ;
- **confirmé** : les helpers Batch 46 `_median_absolute_deviation()` et `_robust_anomaly()` constituent la primitive statistique canonique à réutiliser ;
- **confirmé** : le pipeline filtré expose déjà via `_fresh_activities(...)` la population ayant passé scope, capitalisation et filtre volume ;
- **confirmé via documentation Kraken publique** : la Market Analytics Open Interest utilise `GET /api/charts/v1/analytics/{symbol}/open-interest`, `since`/`to` en epoch secondes et `interval` en secondes ; le schéma générique expose `timestamp[]`, `data[]` et `more` ;
- **confirmé par smoke public local PF_XBTUSD** : `data` est une série de buckets OHLC `[open, high, low, close]`, `more=false` et `errors=[]` sur l'échantillon observé ;
- **manquant dans le contrat public audité** : une unité économique explicite permettant de nommer l'OI `USD`, ainsi qu'une garantie de rétention exploitable ; aucune n'est inventée ;
- **à décider ultérieurement** : pagination multi-requêtes lorsque `more=true`, historique funding/liquidations/CVD/aggressor et influence multi-analytics sur le ranking.

Patch Batch 47.2 :

- ajout d'une extension Market Analytics du client Futures public canonique, réutilisée par le même `KrakenAttentionCatalogue` ; aucun second transport HTTP Futures n'est créé ;
- ajout d'un parser strict `timestamp[] + data[] + more` pour `open-interest` ; après le smoke live, le parser exige des buckets OHLC `[open, high, low, close]`, valide leurs bornes et utilise `close` comme valeur historique du bucket ;
- validation des timestamps epoch secondes, valeurs finies/non négatives, ordre temporel strict et formes de payload ;
- `more=true` rejeté explicitement afin de ne pas utiliser silencieusement une page tronquée ni dépasser le budget réseau du batch ;
- ajout de `PerpetualAnalyticsProvider`, `PerpetualAnalyticsPolicy`, `PerpetualAnalyticsScanner`, `PerpetualAnalyticsSnapshot` et d'un diagnostic de couverture séparé ;
- curseur Analytics indépendant des curseurs OHLCV et Structure ;
- cache causal : un snapshot futur relativement à `as_of` n'est jamais réutilisé ;
- pool OI limité aux PERPETUAL `AVAILABLE` ayant déjà passé les filtres moins coûteux ;
- policy par défaut : 10 marchés/refresh, TTL 1h, intervalle OI 1h, lookback 48h, concurrence 4, baseline 12 périodes ;
- coût réseau maximal par défaut : 10 requêtes historiques OI par refresh ;
- causalité conservatrice : `to <= as_of` et utilisation d'un point historique seulement après un intervalle complet suivant son timestamp, faute de sémantique de clôture plus précise démontrée dans le contrat public audité ;
- réutilisation directe du MAD Batch 46 : `baseline=median`, `MAD`, dispersion `1.4826*MAD`, score signé ;
- seuil robuste symétrique `±2.5` ; fallback MAD nul basé sur un delta relatif de `±10 %` autour de la baseline (`ratio >= 1.10` / `<= 0.90`) ;
- caractéristiques descriptives uniquement `OPEN_INTEREST_EXPANSION` et `OPEN_INTEREST_CONTRACTION` ;
- aucune conversion USD de l'OI et aucun suffixe d'unité inventé ;
- shortlist canonique calculée avant enrichissement OI : aucune modification de `interest_level`, `candidate_limit`, ranking canonique/Structure ou baseline OHLCV ;
- OI historique visible uniquement comme enrichissement des candidats déjà retenus et dans le cockpit ;
- ajout `perpetual_analytics_coverage` au payload v6 additif et prise en charge explicite par la route FastAPI afin d'éviter une sérialisation vers le modèle v6 Structure plus étroit ;
- aucune modification Agent / Risk Engine / Broker et aucune capacité d'exécution PERP.

Validation réellement exécutée dans l'environnement ChatGPT au moment de la préparation :

```text
python -m py_compile sources/tests Python Batch 47.2              : PASS
pytest ciblé Batch 47.2 avec stubs du checkout partiel            : PASS — 37/37
node --test --experimental-strip-types market-attention.test.mjs  : PASS — 26/26
tsc --noEmit --strict ciblé market-attention.ts                   : PASS
typecheck ciblé lib + cockpit avec stubs React/UI                 : PASS
transpile TypeScript ciblé market-attention-dock.tsx              : PASS
```

Validation locale utilisateur de la première livraison 47.2 :

```text
pytest -q        : PASS — suite arrivée à 100 %
pnpm typecheck   : PASS
pnpm test        : PASS — 72/72
git diff --check : PASS sans erreur ; avertissements LF/CRLF uniquement
smoke PF_XBTUSD  : transport PASS, OHLC confirmé, more=false
```

Le smoke a invalidé l'hypothèse préparatoire d'une série scalaire et déclenché un correctif pré-intégration du parser uniquement. Validation ChatGPT du correctif : `python -m py_compile` PASS et **33/33 tests parser/client ciblés PASS** avec stubs minimaux. Une relance locale de `pytest -q` est requise après extraction de ce correctif avant intégration.

## ADR-333 — Les Analytics Futures historiques utilisent une rotation/cache séparée

**PROPOSÉ — Batch 47.2, non intégré.**

Les séries Analytics Futures historiques ne réutilisent ni le curseur OHLCV ni le curseur Structure. `PerpetualAnalyticsScanner` possède un curseur déterministe, un cache causal, une concurrence bornée et un diagnostic de couverture séparé. Les futures séries 47.3/47.4 doivent réutiliser cette infrastructure plutôt que créer des rotations parallèles non coordonnées.

## ADR-334 — L'Open Interest est analysé relativement à son propre historique sans unité économique inventée

**PROPOSÉ — Batch 47.2, non intégré.**

`openInterest` reste une valeur Kraken brute. Aucun `open_interest_usd` n'est créé. L'analyse compare le point courant à une baseline médiane propre au marché et réutilise le MAD normalisé Batch 46. Cette approche permet une détection relative sans supposer une unité économique absente du contrat public audité.

## ADR-335 — La causalité Analytics applique un délai conservateur d'un intervalle

**PROPOSÉ — Batch 47.2, non intégré.**

Le contrat Market Analytics documente les timestamps en epoch secondes et l'intervalle, mais le document audité ne démontre pas une sémantique de clôture suffisamment précise pour consommer le timestamp courant comme point finalisé. Le Batch 47.2 accepte donc uniquement les points dont `timestamp + interval <= as_of`. Cette règle peut être assouplie ultérieurement uniquement sur preuve fournisseur explicite et testée.

## ADR-336 — L'OI historique n'a pas d'autorité de ranking en Batch 47.2

**PROPOSÉ — Batch 47.2, non intégré.**

Le ranking canonique et la shortlist finale sont construits avant l'enrichissement OI. Les caractéristiques OI peuvent compléter `combined_characteristics` et `interest_reasons` d'un candidat déjà retenu, mais ne modifient ni `interest_level`, ni `candidate_limit`, ni la clé de tri. Une influence multi-analytics éventuelle est réservée au Batch 47.5.

## Changelog — 2026-10-04 — Batch 47.1 fondations Futures ticker — intégré

Commit intégré : `842e6bd7` (`feat: add futures ticker analytics foundations`).

Audit de préparation historique :

- `b219365` était la base pré-47.1 et contenait la baseline adaptative Batch 46 ainsi que le plancher `_MINIMUM_ADAPTIVE_BASELINE_PERIODS = 6` ;
- `KrakenDerivativesPublicClient` était déjà le client Futures public canonique ;
- le chemin PAPER individuel normalisait déjà `fundingRate` via `fundingRate / (mark_price * contract_size)` ;
- l'utilisation historique/scorée d'Open Interest, funding, liquidations, CVD ou aggressor-differential restait hors 47.1.

Batch 47.1 intégré :

- ajout de `KrakenDerivativesPublicClient.fetch_tickers()` ;
- ajout du modèle interne strict `KrakenDerivativesTickerSnapshot` ;
- parser bulk commun de `serverTime`, `symbol`, `markPrice`, `indexPrice`, `volumeQuote`, `openInterest`, `fundingRate`, `fundingRatePrediction`, `suspended`, `postOnly` ;
- suppression de la dépendance Radar à la méthode privée `_get_json` ;
- conservation de `volumeQuote` comme volume 24h USD uniquement pour les linear perpetuals cotés USD ;
- conservation séparée de `funding_rate_raw`, `funding_rate_relative` et `funding_rate_prediction_raw` ;
- aucun suffixe `USD` inventé pour `openInterest` ;
- aucun affichage `%` des valeurs funding brutes/prédites ;
- ajout de `PerpetualTickerContext` avec statuts `AVAILABLE`, `PARTIAL`, `NOT_APPLICABLE`, `TECHNICAL_ERROR` ;
- un même snapshot bulk alimente volume PERP, liquidité PERP et contexte Futures dans le refresh Radar ;
- fallback conservé pour les providers de test/compatibilité n'exposant que `volume_24h_usd_by_market()` ;
- panne ticker fail-soft sans filtre volume, fail-closed pour le volume PERP lorsqu'un seuil volume actif exige `volumeQuote` ;
- ajout additif `perpetual_ticker` aux candidats v6 ;
- aucune modification d'`interest_level`, `candidate_limit`, ranking canonique/Structure, percentiles de liquidité ou baseline adaptative ;
- cockpit : section `Futures Kraken` uniquement dans le détail PERPETUAL ;
- contrat public conservé en `market-attention-radar-v6` ;
- aucune modification Agent / Risk Engine / Broker et aucune capacité d'exécution PERP.

Validations connues de la première livraison 47.1 :

```text
ChatGPT : Python py_compile ciblé                         PASS
ChatGPT : pytest parser/client bulk avec stubs           PASS — 23/23
ChatGPT : smoke local catalogue partagé                  PASS
ChatGPT : frontend market-attention.test.mjs ciblé       PASS — 22/22
ChatGPT : typecheck ciblé market-attention.ts            PASS
ChatGPT : parse/transpile ciblé market-attention-dock    PASS
Utilisateur : pnpm typecheck                             PASS
Utilisateur : pnpm test                                  PASS — 68/68
Utilisateur : git diff --check                           PASS (LF/CRLF uniquement)
Utilisateur : pytest -q première livraison               3 FAILURES de fixtures Batch 47.1
```

Le correctif 47.1.1 aligne les fixtures de test sur `StructureAwareMarketAttentionFilters` sans modifier la logique de production. Une relance complète backend post-correctif n'est pas documentée comme PASS et n'est pas inventée.

## ADR-331 — Le Radar réutilise un snapshot Futures bulk canonique

**ADOPTÉ — Batch 47.1 intégré via `842e6bd7`.**

Le client Futures public canonique expose `fetch_tickers()`. Le Radar ne multiplie pas les appels `/tickers` pour le volume, l'Open Interest et le funding. Dans un cycle logique, le snapshot partagé alimente les usages descriptifs et le `volumeQuote` déjà retenu par les Batches 43.2/44.

Aucun second client Kraken Futures n'est créé pour ce snapshot bulk.

## ADR-332 — OI/funding instantanés restent descriptifs et leurs unités restent explicites

**ADOPTÉ — Batch 47.1 intégré via `842e6bd7`.**

`openInterest`, `fundingRate` et `fundingRatePrediction` sont conservés comme valeurs Kraken brutes lorsque leur unité d'affichage n'est pas démontrée. Le taux relatif normalisé existant est stocké séparément lorsqu'il peut être calculé. La prédiction est identifiée comme prévision Kraken, jamais comme funding futur réalisé.

Ces champs n'entrent dans aucun ranking, aucun `interest_level` et aucun filtre de shortlist en 47.1.

## Changelog — 2026-10-04 — Correctif Batch 46.1 compatibilité baseline H4 — intégré

Le code du correctif est présent dans `main` via `b219365` avec le Batch 46.

Validation locale de la première livraison Batch 46 : `pytest -q` avait révélé 7 échecs de non-régression, tandis que `pnpm typecheck`, `pnpm test` (65/65) et `git diff --check` étaient corrects.

Cause : `baseline_periods = 12` était appliqué comme exigence rigide à chaque horizon. Les fixtures historiques de 404–420 candles M5 ne fournissaient que 6 périodes historiques H4 après exclusion de `previous` et `current`, alors qu'elles étaient valides avant Batch 46. H4 devenait `INSUFFICIENT_HISTORY`, le snapshot `PARTIAL`, puis les candidats disparaissaient avant Structure.

Correctif intégré :

- cible statistique par défaut maintenue à `12` périodes ;
- plancher de compatibilité centralisé à `6` périodes ;
- `_horizon()` choisit le plus grand nombre causal de périodes complètes disponible entre le plancher et la cible ;
- avec 720 candles M5 : H4 utilise 12 périodes ;
- avec 420 candles M5 : H4 utilise 6 périodes ;
- sous le plancher : `INSUFFICIENT_HISTORY` reste explicite ;
- `baseline_period_count` continue d'exposer le nombre réellement utilisé ;
- aucune modification du scoring MAD, des filtres, de Structure, des sources volume 24h ou de la liquidité PERP.

L'intégration GitHub confirme la présence du code et des tests dédiés ; elle ne constitue pas une preuve d'une suite locale complète post-commit non observée.

## ADR-330 — La baseline adaptative distingue cible statistique et plancher de compatibilité

**ADOPTÉ — Batch 46/46.1 intégré via `b219365`.**

`baseline_periods` reste la cible maximale de l'analyse robuste. Le Radar peut utiliser moins de périodes uniquement lorsque l'historique causal disponible est insuffisant pour la cible mais atteint le plancher déterministe de 6 périodes. Cette dégradation est bornée, observable via `baseline_period_count` et ne réintroduit aucune donnée future.

## Changelog — 2026-10-04 — Batch 46 baseline statistique adaptative — intégré

Commit intégré : `b219365` (`feat: add adaptive statistical radar baseline`).

- audit confirmé : `MarketActivityAnalyzer` est le composant canonique unique de l'activité ; aucun analyseur parallèle n'est créé ;
- baseline cible d'activité portée de `6` à `12` périodes historiques ; H4 utilise 12 périodes lorsque l'historique le permet et le correctif 46.1 conserve un plancher compatible à 6 périodes ;
- adoption d'une baseline robuste par marché et timeframe : médiane, MAD, dispersion `1.4826 * MAD`, score signé ;
- ajout des méthodes explicites `ROBUST_MAD`, `LEGACY_RATIO_FALLBACK`, `UNAVAILABLE` ;
- aucun score artificiel lorsque `MAD == 0` ; le ratio historique reste diagnostic et fallback déterministe ;
- ajout des scores volume, range et volatilité ainsi que du score volume précédent et du delta de score ;
- `MarketActivityState` utilise le score robuste en priorité et la logique ratio historique uniquement en fallback ;
- seuils adaptatifs centralisés : `2.0`, `3.5 + delta 1.0`, `5.0`, confirmation `1.5`, contraction `-2.0`, divergence volume forte `3.0` ;
- `VOLUME_ANOMALY`, `VOLATILITY_EXPANSION`, `CONSOLIDATING`, les confirmations `BREAKOUT_WATCH` / `REVERSAL_WATCH` et `PRICE_VOLUME_DIVERGENCE` deviennent adaptatifs lorsque le MAD est exploitable ;
- `_MATERIAL_RETURN`, `TrendDirection`, Market Structure, HH/HL/LH/LL, BOS/CHOCH, rotation/cache Structure et filtres Batch 45 ne sont pas modifiés ;
- les tris canoniques réutilisent l'intensité adaptative disponible et restent déterministes ; le ranking Structure reste additif et symétrique hausse/baisse ;
- `SubthresholdActivitySnapshot` conserve `peak_volume_ratio` et ajoute `peak_anomaly_score` / méthode ;
- contrat `market-attention-radar-v6` conservé avec champs additifs ;
- cockpit : détails OHLCV enrichis avec ratio historique, score adaptatif et méthode sans alourdir la ligne principale ;
- aucune modification des sources volume 24h SPOT/PERP ni de la liquidité Batch 44 ; aucune notionnalisation artificielle des chart candles PERP ;
- aucune modification Agent / Risk Engine / Broker et aucune capacité LIVE ou PERP exécutable.

Validations observées sur le patch avant intégration :

```text
Python py_compile backend ciblé                 : PASS
exécution helpers robustes extraits du code     : PASS
frontend market-attention.test.mjs ciblé        : PASS — 19/19
typecheck TypeScript ciblé market-attention.ts  : PASS
parse TypeScript/TSX ciblé cockpit              : PASS
```

Validation locale utilisateur de la première livraison : `pnpm typecheck` PASS, `pnpm test` PASS 65/65, `git diff --check` sans erreur ; `pytest -q` avait révélé 7 régressions de shortlist, traitées par le correctif 46.1 intégré dans `b219365`.

## ADR-328 — L'anomalie d'activité utilise une médiane et un MAD normalisé

**ADOPTÉ — Batch 46 intégré via `b219365`.**

Formule :

```text
baseline          = median(history)
MAD               = median(abs(x - baseline))
robust_dispersion = 1.4826 * MAD
adaptive_score    = (current - baseline) / robust_dispersion
```

La constante `1.4826` est centralisée et nommée. Elle normalise le MAD sur une échelle comparable à un écart-type sous une référence gaussienne sans abandonner la robustesse médiane.

Le score est signé : positif = expansion par rapport au régime historique du marché/horizon ; négatif = contraction.

Si `MAD == 0`, le Radar ne divise pas par zéro et ne fabrique pas de score extrême. Il bascule explicitement vers `LEGACY_RATIO_FALLBACK` si le ratio est valide, sinon `UNAVAILABLE`.

Les seuils du Batch 46 constituent une policy déterministe expérimentale et explicable. Ils ne sont pas présentés comme un optimum universel et ne sont jamais auto-optimisés à partir du P&L.

## ADR-329 — Le ratio historique reste observable et le contrat v6 reste additif

**ADOPTÉ — Batch 46 intégré via `b219365`.**

Les champs historiques `volume_ratio`, `range_expansion_ratio`, `volatility_expansion_ratio`, `volume_change` et `volume_acceleration` restent exposés pour diagnostic, compatibilité et fallback.

Les nouveaux champs robustes sont additifs. Aucun bump mécanique du protocole v6 n'est introduit tant que les routes et la sémantique générale restent compatibles.

## Changelog — 2026-10-03 — Batch 45 Structure en amont et filtres — intégré

Commit intégré : `45d41b7` (`feat: move market structure before radar shortlist`).

- déplacement de la Structure avant la shortlist finale sans scan Structure illimité ;
- rotation/cache Structure séparés des curseurs OHLCV ;
- cache causal : aucun snapshot futur réutilisé ;
- événements `BOS / CHOCH` confirmés capables de compléter l'attention ;
- régimes persistants non transformés en anomalies permanentes ;
- filtres tendance/Structure avec `OR` intra-champ et `AND` inter-familles/timeframes ;
- `UNKNOWN` fail-closed ;
- diagnostic de couverture Structure séparé ;
- protocole v6 conservé ;
- aucune modification Agent/Risk/Broker.

Les validations connues du patch avant intégration restent : Python `py_compile` PASS, test frontend ciblé 16/16 PASS, typecheck ciblé lib PASS, typecheck cockpit ciblé avec stubs PASS. Aucune validation complète supplémentaire n'est inventée.

## ADR-325 — Géométrie Structure et policy de scan séparées

**ADOPTÉ — Batch 45.**

`MarketStructurePolicy` porte la causalité/géométrie. `MarketStructureScanPolicy` porte `market_limit_per_refresh` et `cache_ttl_seconds`. Le curseur Structure est indépendant des curseurs OHLCV.

## ADR-326 — Attention structurelle par événements confirmés

**ADOPTÉ — Batch 45.**

Par défaut, un régime `BULLISH / BEARISH / RANGE / TRANSITION` sans événement ne force pas la shortlist. Un `BOS_UP / BOS_DOWN / CHOCH_UP / CHOCH_DOWN` confirmé peut compléter l'attention. Le ranking reste directionnellement symétrique.

## ADR-327 — Filtres Structure fail-closed et zéro résultat explicable

**ADOPTÉ — Batch 45.**

`UNKNOWN`, absence, expiration ou non-couverture échouent à un filtre Structure actif. Le cockpit distingue une couverture incomplète d'une couverture complète sans correspondance.

## Changelog — 2026-10-03 — Batch 44 liquidité PERPETUAL et couverture — intégré

Commit fonctionnel intégré : `c262d54` (`feat: add perpetual liquidity and radar coverage diagnostics`).

- référence SPOT/USD canonique conservée ;
- linear perpetual/USD : liquidité fondée uniquement sur `volumeQuote` 24h public déjà validé ;
- percentiles SPOT/PERP séparés ;
- `UNKNOWN` lorsque la donnée fiable manque ;
- diagnostic de couverture/rotation OHLCV sans auto-correction silencieuse.

## ADR-323 — Liquidité PERPETUAL via `volumeQuote` USD validé

**ADOPTÉ — Batch 44.**

Le Radar ne notionnalise jamais les chart candles PERP par `candle.volume * close`. Une donnée non démontrée reste `LiquidityRegime.UNKNOWN`.

## ADR-324 — La couverture est observée, pas auto-corrigée

**ADOPTÉ — Batch 44.**

Les diagnostics exposent la capacité théorique de rotation avant expiration du cache, mais le Radar n'augmente pas automatiquement cadence, limites ou concurrence réseau.

## Changelog — 2026-10-03 — Batch 43.2 correctif Radar PERPETUAL — intégré

Commit intégré : `25dcb5c` (`fix: repair perpetual market attention radar`).

- `PERPETUAL + Volume Tous` conservé ;
- `volumeQuote` bulk Kraken Futures pour les linear perpetuals cotés USD ;
- aucune requête par marché ;
- aucune formule inventée sur `candle.volume` ;
- diagnostics `UNKNOWN_*` explicites ;
- aucune capacité d'exécution PERP.

## ADR-321 — Volume PERPETUAL USD via turnover quote public Kraken

**ADOPTÉ — Batch 43.2.**

Pour les linear perpetuals cotés directement en USD, `volumeQuote` constitue le volume 24h USD. Les quotes non USD ne sont pas converties implicitement.

## ADR-322 — Une shortlist PERPETUAL vide n'est pas réparée en abaissant le scoring

**ADOPTÉ — Batch 43.2.**

Si le catalogue et les données sont valides mais qu'aucune activité n'est assez inhabituelle, une shortlist vide est un résultat normal et explicable.
