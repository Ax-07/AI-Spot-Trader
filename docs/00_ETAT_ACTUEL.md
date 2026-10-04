# 00 — État actuel

## Référence de clôture Batch 47.3

```text
Repository                    : Ax-07/AI-Spot-Trader
Branche                       : main
Référence GitHub auditée       : 21cac8f24a06ec997a0e70730309b9541ae04544
Base Batch 47.3 auditée       : c09dd14cab31233f635ff535cbf0298ba3f2bd51
Commit fonctionnel Batch 47.3 : 12051a7
Clôture documentaire initiale : 21cac8f
```

Le **Batch 47.3 est intégré sur GitHub `main` via le commit fonctionnel `12051a7`**, avec première clôture documentaire `21cac8f`. Le Batch 47.2 reste intégré via `c09dd14`.

Décisions intégrées récentes :

```text
Batch 45        => intégré via 45d41b7
Batch 46 / 46.1 => intégré via b219365
Batch 47.1      => intégré via 842e6bd7
Batch 47.2      => intégré via c09dd14
Batch 47.3      => intégré via 12051a7, première clôture documentaire 21cac8f
ADR-328..339    => ADOPTÉES selon leur batch intégré/validé
```

L'intégration GitHub confirme la présence du code. Elle ne constitue pas une preuve de tests locaux non observés.

## Radar intégré jusqu'au Batch 47.3

Le Market Attention Radar reste `market-attention-radar-v6`, strictement informatif, déterministe, causal et read-only. L'exécution de trading demeure SPOT uniquement.

Pipeline intégré :

```text
catalogue Kraken
-> scope SPOT / PERPETUAL / ALL
-> métadonnées / filtre capitalisation
-> rotation OHLCV et volume 24h
-> activité adaptative / tendance / liquidité / microstructure canonique
-> pool Analytics Futures historique borné et rotatif
-> pool Structure borné et rotatif
-> filtres tendance / Structure
-> shortlist finale canonique
-> enrichissement Futures ticker + Analytics
-> cockpit
```

Le Batch 47.2 ajoute l'historique **Open Interest** et l'infrastructure Analytics Futures générique :

```text
KrakenDerivativesAnalyticsClient
PerpetualAnalyticsProvider
PerpetualAnalyticsPolicy
PerpetualAnalyticsScanner
PerpetualAnalyticsSnapshot
perpetual_analytics_coverage
```

Policy intégrée 47.2 :

```text
market_limit_per_refresh = 10
cache_ttl_seconds        = 3600
history_interval_seconds = 3600
history_lookback_seconds = 172800
fetch_concurrency        = 4
baseline_periods         = 12
```

Le smoke Kraken réel du Batch 47.2 a confirmé pour `PF_XBTUSD/open-interest` :

```text
result.timestamp[]
result.data[] = [[open, high, low, close], ...]
result.more = false
```

Le parser utilise strictement le `close` d'un bucket OHLC finalisé. L'OI historique reste brut, n'est pas converti implicitement en USD et n'a aucune autorité de ranking.

## Batch 47.3 — intégré via `12051a7`

Objectif : ajouter exactement deux séries historiques en réutilisant **la même rotation/cache Analytics** :

```text
funding
liquidation-volume
```

Audit Kraken retenu :

- `funding` possède un schéma dédié `data.rate[]` + `data.relativeRate[]`, chaque série étant composée de buckets OHLC ;
- `rate` et `relativeRate` restent séparés ; aucun champ n'est confondu avec `fundingRatePrediction` du ticker ni présenté comme funding futur réalisé ;
- `liquidation-volume` représente un volume total agrégé de positions liquidées par intervalle ; aucun split LONG/SHORT n'est inventé ;
- le schéma générique Analytics autorise scalaire ou OHLC ; le parser 47.3 accepte seulement ces formes démontrées, avec valeurs finies et non négatives pour les liquidations ;
- `more=true` reste fail-closed afin de ne pas masquer une page tronquée ni dépasser silencieusement le budget réseau.

Statistiques descriptives ajoutées :

```text
Funding relatif    : médiane + MAD + score robuste signé
Liquidation volume : médiane + MAD + score robuste, spike uniquement
```

Caractéristiques additives :

```text
FUNDING_POSITIVE_EXTREME
FUNDING_NEGATIVE_EXTREME
LIQUIDATION_VOLUME_SPIKE
```

Elles n'influencent pas `interest_level`, `candidate_limit`, la shortlist canonique ni le ranking. Elles ne peuvent pas créer seules un candidat.

La rotation reste `10` marchés maximum par refresh. Avec trois séries historiques (`open-interest`, `funding`, `liquidation-volume`), le plafond théorique devient **30 requêtes publiques Analytics par refresh**, avec concurrence globale toujours bornée à `4` par défaut.

Le cockpit expose les trois séries ainsi qu'une couverture par série. Aucun filtre utilisateur Funding/Liquidation n'est ajouté.

Voir `docs/47_3_FUNDING_LIQUIDATION_VOLUME.md`.

## Validations connues

Batch 47.2 avant intégration, observées localement par l'utilisateur :

```text
backend pytest -q       : PASS — suite arrivée à 100 %
frontend pnpm typecheck : PASS
frontend pnpm test      : PASS — 72/72
git diff --check        : PASS — avertissements LF/CRLF uniquement
smoke Kraken OI         : PASS — PF_XBTUSD, OHLC, more=false
```

Batch 47.3 dans l'environnement ChatGPT de préparation :

```text
python -m py_compile backend ciblé                         : PASS
pytest ciblé Batch 47.3 avec stubs du checkout partiel     : PASS — 23/23 après correctif timestamp Funding
smoke compatibilité logique Batch 47.2 OI                 : PASS
tsc --noEmit --strict ciblé market-attention.ts           : PASS
typecheck ciblé cockpit avec stubs React/UI               : PASS
node --test market-attention-batch47_3.test.mjs           : PASS — 4/4
```

Validations locales utilisateur Batch 47.3 avant intégration :

```text
backend python -m pytest -q : PASS — suite complète à 100 % sous le .venv Python >= 3.12
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 76/76
git diff --check            : PASS — avertissements LF/CRLF uniquement
smoke Kraken Funding        : PASS — PF_XBTUSD, rate/relativeRate OHLC, timestamps millisecondes, more=false
smoke Kraken Liquidation    : PASS — PF_XBTUSD, scalaires non négatifs, timestamps secondes, more=false
```

Le smoke Funding a mis en évidence l'unité milliseconde de `result.timestamp[]`; le correctif parser + test de régression est inclus dans le commit fonctionnel `12051a7`. La suite backend complète a été relancée ensuite avec succès sous le `.venv` Python >= 3.12.
