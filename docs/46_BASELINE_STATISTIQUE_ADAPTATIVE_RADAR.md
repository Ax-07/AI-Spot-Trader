# Batch 46 — Baseline statistique adaptative du Market Attention Radar

## Statut

**Patch proposé, non intégré.**

Base auditée :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 45d41b78c6aac6b4cf9ac3192d295e7a57411441
Commit     : feat: move market structure before radar shortlist
```

Le Batch 45 est bien intégré au HEAD. Les anciens statuts documentaires « proposé, non intégré » sont corrigés dans le même patch documentaire.

## Objectif

Améliorer la détection déterministe des anomalies du Radar afin de répondre à la question :

> « Ce volume, cette amplitude ou cette volatilité sont-ils inhabituels pour ce marché et cet horizon ? »

Le Batch 46 ne prédit pas le prix, n'entraîne aucun modèle, n'utilise aucun P&L pour auto-régler les seuils et ne modifie aucune autorité de trading.

## Faiblesse de la baseline précédente

La baseline existante était déjà causale et robuste sur le centre grâce à la médiane, mais utilisait par défaut seulement `6` périodes historiques et classait principalement l'activité avec des ratios universels :

```text
ELEVATED      : volume_ratio >= 1.40
ACCELERATING  : volume_ratio >= 1.75 et volume_acceleration >= 0.25
VERY_HIGH     : volume_ratio >= 2.50 et volume_acceleration >= 0.50
```

Des seuils analogues étaient utilisés dans plusieurs caractéristiques descriptives.

Conséquence : une variation modeste sur un marché extrêmement stable pouvait rester invisible, tandis qu'une variation comparable sur un marché naturellement erratique pouvait être surclassée.

## Méthodes évaluées

### Médiane + MAD — retenue

Avantages : robuste aux outliers, calcul simple, signé, causal, peu coûteux et explicable par marché/timeframe.

### IQR

Robuste également, mais moins naturel avec seulement 12 périodes et moins direct pour produire un score signé continu comparable entre horizons.

### Percentile empirique

Très lisible pour un ranking, mais résolution grossière avec une petite fenêtre et gestion des ex æquo moins informative pour mesurer l'intensité.

Le Batch 46 retient donc **médiane + MAD normalisé**.

## Taille de baseline

La valeur cible par défaut devient :

```text
baseline_periods = 12
```

Le correctif 46.1 conserve en plus un plancher de compatibilité centralisé :

```text
_MINIMUM_ADAPTIVE_BASELINE_PERIODS = 6
```

`_horizon()` utilise le plus grand nombre de périodes historiques causales complètes disponible entre ce plancher et la cible configurée. Il ne descend jamais sous `min(baseline_periods, 6)` ; en dessous, le diagnostic reste `INSUFFICIENT_HISTORY`.

Le besoin cible reste :

```text
required_target = bars_per_horizon * (baseline_periods + 2)
```

Les `+2` correspondent à la fenêtre courante et à la fenêtre comparable précédente, exclues de la baseline.

Pour H4 avec la cible par défaut :

```text
bars H4 en M5 = 48
required_target = 48 * (12 + 2)
                = 672 candles M5
```

`MarketAttentionPolicy.candle_limit` reste `720`, donc le défaut utilise bien 12 périodes.

Pour une configuration historique limitée à 420 candles M5, H4 dispose de :

```text
floor(420 / 48) - 2 = 6 périodes historiques complètes
required_min = 48 * (6 + 2) = 384 candles M5
```

Le Radar reste donc `AVAILABLE` et exploitable au lieu de devenir `PARTIAL` uniquement parce que la cible statistique a été allongée. `baseline_period_count` expose le nombre effectivement utilisé.

Cette résolution adaptative traite aussi proprement les cibles élevées : si `baseline_periods = 20` mais que le fetch ne permet que 18 périodes H4 complètes, 18 sont utilisées plutôt que de casser rétroactivement la configuration.


## Correctif 46.1 — compatibilité historique des fenêtres H4

La première livraison du Batch 46 exigeait rigidement les 12 périodes cibles sur chaque horizon. Les suites historiques utilisent plusieurs fixtures de 404 à 420 candles M5, dimensionnées pour la baseline antérieure de 6 périodes H4. Cette rigidité rendait H4 `INSUFFICIENT_HISTORY`, puis le snapshot `PARTIAL`, ce qui supprimait les candidats avant l'enrichissement Structure.

Le correctif ne revient pas à une baseline fixe de 6 : il garde 12 comme cible et n'utilise 6 que lorsque l'historique causal disponible ne permet pas davantage. Dès que 672 candles M5 ou plus sont disponibles, H4 utilise bien 12 périodes.

Avant correctif, la validation locale utilisateur a observé 7 échecs backend, tous cohérents avec cette régression de disponibilité ; le frontend était vert à 65/65. Le correctif ajoute des tests dédiés pour 720 candles -> 12 périodes, 420 candles -> 6 périodes et historique inférieur au plancher -> `INSUFFICIENT_HISTORY`.

## Formule

Pour une série historique `x` :

```text
baseline = median(x)
MAD      = median(abs(x - baseline))
```

La dispersion robuste normalisée est :

```text
robust_dispersion = 1.4826 * MAD
```

La constante `1.4826` est centralisée dans `_ROBUST_MAD_NORMALIZATION`. Elle place le MAD sur une échelle approximativement comparable à un écart-type sous une référence gaussienne tout en conservant la résistance de la médiane aux outliers.

Score :

```text
adaptive_score = (current - baseline) / robust_dispersion
```

Le score est signé :

```text
score > 0 => expansion relative au régime historique
score < 0 => contraction relative au régime historique
```

## Gestion du MAD nul et fallback

Un historique parfaitement constant donne `MAD == 0`. Le Batch 46 interdit :

- division par zéro ;
- `Infinity` ;
- score artificiellement gigantesque ;
- epsilon implicite non documenté.

Méthodes exposées :

```text
ROBUST_MAD            : score robuste calculé
LEGACY_RATIO_FALLBACK : MAD inutilisable, ratio historique conservé
UNAVAILABLE           : ni score robuste ni ratio fiable
```

Le fallback reste explicite dans le payload et le cockpit.

## Champs additifs

`ActivityHorizonSnapshot` conserve tous les champs historiques et ajoute :

```text
baseline_volume_mad
volume_anomaly_score
previous_volume_anomaly_score
volume_anomaly_acceleration
volume_anomaly_method

baseline_range_mad
range_anomaly_score
range_anomaly_method

baseline_volatility_mad
volatility_anomaly_score
volatility_anomaly_method
```

`SubthresholdActivitySnapshot` conserve `peak_volume_ratio` et ajoute :

```text
peak_anomaly_score
anomaly_method
```

Le contrat reste `market-attention-radar-v6` ; les extensions sont additives.

## Accélération adaptative

Lorsque deux scores robustes sont disponibles :

```text
volume_anomaly_acceleration = current_score - previous_score
```

Les champs historiques `volume_change` et `volume_acceleration` sont conservés pour diagnostic et fallback.

## Policy déterministe des états d'activité

Seuils centralisés :

```text
ELEVATED                  : score >= 2.0
ACCELERATING              : score >= 3.5 et delta_score >= 1.0
VERY_HIGH                 : score >= 5.0
```

Lorsqu'un horizon est en `ROBUST_MAD`, ces seuils sont prioritaires. En `LEGACY_RATIO_FALLBACK`, les règles historiques de ratio restent utilisées.

Ces valeurs sont une policy expérimentale déterministe et explicable. Elles ne sont ni des constantes « optimales » universelles, ni apprises sur le P&L.

## Caractéristiques descriptives adaptées

### VOLUME_ANOMALY

Score volume robuste `>= 2.0`, sinon ratio historique en fallback.

### VOLATILITY_EXPANSION

Score de range ou de volatilité robuste `>= 2.0`, sinon ratios historiques.

### BREAKOUT_WATCH

La condition de prix et la causalité du breakout restent inchangées. La confirmation par volume/range utilise un score adaptatif `>= 1.5` lorsqu'il existe, sinon le ratio historique.

### REVERSAL_WATCH

Le retournement de signe et les seuils `_MATERIAL_RETURN` restent inchangés. Seule l'évidence volume/range devient adaptative lorsqu'elle est disponible.

### CONSOLIDATING

Une contraction robuste de range ou volatilité `<= -2.0` remplace prioritairement la dépendance au ratio fixe `<= 0.70`. Une expansion volume adaptative forte empêche de qualifier silencieusement l'horizon de compression.

### PRICE_VOLUME_DIVERGENCE

Le volume faible utilise la contraction adaptative lorsqu'elle est disponible ; le volume inhabituellement élevé utilise un score `>= 3.0`. Les seuils de mouvement de prix restent ceux de la doctrine existante.

## Tri déterministe

`_activity_sort_key()` utilise l'intensité du score volume robuste lorsqu'il existe ; sinon il conserve le ratio historique. Le delta adaptatif remplace l'accélération ratio uniquement lorsqu'il est disponible.

Les tie-breakers existants et `candidate_limit` restent en place. Le ranking Structure du Batch 45 réutilise toujours le ranking canonique comme signal principal et reste symétrique hausse/baisse.

## Causalité

Aucune baseline n'inclut :

- la fenêtre courante ;
- la fenêtre comparable précédente comme période de référence ;
- une candle non finalisée ;
- une candle dont `close_time > observed_at` ;
- une donnée future sélectionnée rétrospectivement.

Le pipeline reste déterministe pour les mêmes entrées et le même `observed_at`.

## Exemples synthétiques ancien / nouveau

### A — marché stable, variation réellement inhabituelle

Historique de volume proche de `100`, faible dispersion, courant `130`.

```text
ancien ratio ≈ 1.30 < 1.40
=> NORMAL possible

nouveau : médiane ≈ 100, MAD faible
=> score robuste nettement > 2
=> ELEVATED / anomalie détectée
```

Le Batch 46 corrige un faux négatif typique des seuils universels.

### B — marché erratique, variation ordinaire pour son régime

Historique : `60, 150, 80, 170, ...`, courant `140`.

```text
ancien : ratio potentiellement élevé selon la médiane
nouveau : MAD élevé => score robuste modéré
=> pas automatiquement anormal
```

Le Batch 46 réduit un faux positif typique.

### C — outlier historique

Une seule période extrême dans la baseline n'étire pas fortement la médiane ni le MAD comme le ferait une moyenne/variance classique. La baseline reste représentative du régime dominant.

### D — historique constant

```text
MAD = 0
=> aucun score infini
=> LEGACY_RATIO_FALLBACK si ratio fiable
=> UNAVAILABLE sinon
```

## SPOT et PERPETUAL

Le score adaptatif est un score **relatif intra-marché** sur les volumes de chart existants. Il ne change pas l'unité économique du volume.

Pour les PERP :

- aucune conversion `candle.volume * close` n'est ajoutée ;
- le volume 24h USD du filtre reste `volumeQuote` public Kraken Futures pour les linear/USD ;
- la liquidité PERP reste la décision Batch 44 ;
- aucune capacité d'exécution PERP n'est créée.

## Cockpit

La ligne principale reste compacte.

Le détail candidat OHLCV affiche par timeframe :

```text
ratio volume historique
score volume adaptatif
méthode volume
ratio volatilité historique
score volatilité adaptatif
méthode volatilité
```

Le diagnostic sous-seuil conserve le ratio et affiche le score/méthode adaptatifs lorsqu'ils existent.

## Tests Batch 46 ajoutés

Backend :

```text
backend/tests/test_market_attention_batch46_adaptive_baseline.py
```

Le fichier couvre directement les primitives robustes, baseline par défaut/H4, isolation de la baseline, stable vs erratique, outlier, MAD nul, baseline nulle, états adaptatifs, symétrie directionnelle de l'intensité, SPOT/PERP et tri déterministe. Les suites historiques restent requises pour la non-régression complète des gaps, filtres, coverages, Structure et `candidate_limit`.

Frontend :

```text
frontend/src/lib/market-attention.test.mjs
```

Ajouts : format du score adaptatif, libellé de méthode, lecture d'un payload v6 ancien sans champs Batch 46 et diagnostic sous-seuil adaptatif.

## Validation exécutée par ChatGPT

```text
python -m py_compile backend/src/ai_spot_trader/market/attention.py \
  backend/tests/test_market_attention_batch46_adaptive_baseline.py
=> PASS

node --test --experimental-strip-types frontend/src/lib/market-attention.test.mjs
=> PASS — 19/19

tsc ciblé frontend/src/lib/market-attention.ts
=> PASS

parse TypeScript/TSX ciblé market-attention-dock.tsx
=> PASS
```

Le repository complet et ses dépendances n'étaient pas présents dans le conteneur. ChatGPT n'a donc pas exécuté la suite globale `pytest -q` ni les commandes `pnpm typecheck` / `pnpm test` du projet entier.

## Validation locale requise

```powershell
cd E:\AI-Spot-Trader\backend
pytest -q

cd E:\AI-Spot-Trader\frontend
pnpm typecheck
pnpm test

cd E:\AI-Spot-Trader
git diff --check
git status --short
```

## Invariants préservés

- Radar strictement informatif ;
- aucune décision `BUY / SELL / HOLD` par le Radar ;
- aucun score statistique transformé en ordre ;
- aucune sortie LLM directe vers Kraken ;
- Risk Engine autorité finale ;
- aucune modification Agent / Risk Engine / Broker ;
- SPOT comme seul mode d'exécution actuel ;
- aucune exécution PERP ;
- PAPER ;
- aucune donnée future ;
- aucune sélection rétrospective ;
- aucune modification post-hoc d'une décision ;
- candles finalisées uniquement ;
- Market Structure causale Batch 45 préservée ;
- volume PERP non notionnalisé artificiellement ;
- aucune nouvelle source externe ;
- aucun secret ;
- aucune promesse de rendement.

## Hors périmètre

```text
Open Interest
Funding
Liquidations
CVD
long/short ratio
microstructure Futures
Machine Learning
modèle entraîné
auto-optimisation des seuils à partir du P&L
connexion Radar -> Agent
modification Risk Engine
LIVE
```
