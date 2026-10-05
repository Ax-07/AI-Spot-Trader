# 00 — État actuel

## Référence de reprise — Batch 47.5 préparé, non intégré

```text
Repository                     : Ax-07/AI-Spot-Trader
Branche                        : main
HEAD GitHub réel audité        : e972fd9112363b268a53658fe5ce88facbfa7dd7
Clôture documentaire Batch 47.4: e972fd9 — docs: mark batch 47.4 integrated
Commit fonctionnel Batch 47.4 : 472f3ad — feat: add CVD and aggressor analytics
Batch 47.5                     : PATCH PROPOSÉ — NON INTÉGRÉ
```

Le **Batch 47.4 reste l'état intégré de GitHub `main`**. Le présent patch Batch 47.5 n'est pas encore intégré et doit être validé localement avant commit/push.

Décisions intégrées récentes :

```text
Batch 45        => intégré via 45d41b7
Batch 46 / 46.1 => intégré via b219365
Batch 47.1      => intégré via 842e6bd7
Batch 47.2      => intégré via c09dd14
Batch 47.3      => intégré via 12051a7
Batch 47.4      => intégré via 472f3ad, clôturé documentairement via e972fd9
ADR-328..344    => ADOPTÉES selon leur batch intégré
```

## Radar intégré avant application de 47.5

Le Market Attention Radar reste `market-attention-radar-v6`, strictement informatif, déterministe, causal et read-only. L'exécution de trading demeure SPOT uniquement.

Pipeline intégré 47.4 :

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

Infrastructure Analytics canonique à préserver :

```text
KrakenDerivativesAnalyticsClient
PerpetualAnalyticsProvider
PerpetualAnalyticsPolicy
PerpetualAnalyticsScanner
PerpetualAnalyticsSnapshot
perpetual_analytics_coverage
```

Policy réseau inchangée dans le patch 47.5 :

```text
market_limit_per_refresh = 10
cache_ttl_seconds        = 3600
history_interval_seconds = 3600
history_lookback_seconds = 172800
fetch_concurrency        = 4
baseline_periods         = 12
```

Les cinq séries Analytics restent `open-interest`, `funding`, `liquidation-volume`, `cvd` et `aggressor-differential`. Elles partagent toujours un seul scanner/cache/cursor/sémaphore. Budget théorique : 5 × 10 = 50 appels Analytics max/refresh.

## Batch 47.5 — patch proposé

Audit :

- **confirmé** : `interest_level` et `candidate_limit` sont décidés avant l'enrichissement Analytics ;
- **confirmé** : la sélection finale Structure est canonique avant l'enrichissement 47.4 ;
- **confirmé** : CVD et Aggressor Differential sont sémantiquement redondants comme order flow agressif ;
- **obsolète** : les documents citaient encore `472f3ad` comme HEAD audité alors que le HEAD réel est `e972fd9` ;
- **manquant avant patch** : politique multi-analytics bornée, déduplication et diagnostics de ranking ;
- **décidé dans le patch** : aucune création de candidat par Analytics et aucune modification de `interest_level`.

Décision proposée : **score multi-analytics séparé, plafonné à 4, appliqué seulement aux PERP déjà retenus**.

```text
Open Interest       : 0 ou +1
Funding             : 0 ou +1
Liquidation Volume  : 0 ou +1
Order Flow          : 0 ou +1 (CVD + Aggressor dédupliqués)
TOTAL               : 0..4
```

Une série ne contribue que si elle est `AVAILABLE` et possède déjà une caractéristique 47.2–47.4 active. Disponibilité seule = 0. `INSUFFICIENT_HISTORY`, `STALE`, `TECHNICAL_ERROR`, `PARTIAL` ou absence = 0 sans pénalité.

Les métriques signées sont symétriques pour **l'attention**, pas pour le trading : un extrême positif ou négatif peut contribuer de façon identique. CVD + Aggressor concordants valent au maximum +1 ; s'ils sont actifs mais opposés, la composante order-flow vaut 0 et le conflit est diagnostiqué.

Hiérarchie proposée :

```text
interest_level
-> événement Structure confirmé
-> analytics_ranking.score
-> critères microstructure / activité / liquidité restants
-> symbole déterministe
```

En scope `ALL`, les positions SPOT sont figées et seuls les PERP peuvent échanger leurs positions entre eux. Le diagnostic `analytics_ranking` expose aussi le rang global avant/après et `rank_change`, afin que l’impact réellement observé soit visible même lorsqu’il est nul. Le patch ne change ni Agent, ni Risk Engine, ni Broker, ni exécution SPOT/PERP.

Voir `docs/47_5_MULTI_ANALYTICS_RANKING.md`.

## Validations connues

État intégré Batch 47.4 avant ce patch : backend local utilisateur `python -m pytest -q` PASS à 100 %, frontend `pnpm typecheck` PASS, frontend `pnpm test` PASS 82/82, `git diff --check` PASS hors avertissements LF/CRLF, smokes CVD/Aggressor PASS.

Validation ChatGPT du patch 47.5 : `py_compile` production + test backend PASS ; harnais backend isolé 15/15 PASS ; typecheck strict ciblé `market-attention.ts` PASS ; parsing TS/TSX lib + cockpit PASS ; test frontend Batch 47.5 4/4 PASS. Les suites complètes `python -m pytest -q`, `pnpm typecheck`, `pnpm test` et `git diff --check` restent à exécuter localement sur le checkout complet avant intégration. Ne jamais considérer 47.5 intégré tant que l'utilisateur n'a pas validé puis poussé le commit.
