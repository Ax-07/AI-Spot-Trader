# 00 — État actuel

## Référence de clôture Batch 47.4

```text
Repository                    : Ax-07/AI-Spot-Trader
Branche                       : main
HEAD GitHub audité            : 472f3adca1d19822289af47b52b03afab3cda0fb
Commit fonctionnel Batch 47.3 : 12051a7
Clôture Batch 47.3 observée    : ec1cd5d — docs: mark batch 47.3 integrated
Batch 47.4                    : INTÉGRÉ via 472f3ad — feat: add CVD and aggressor analytics
```

Le **Batch 47.4 est intégré sur GitHub `main` via `472f3ad`**. Les deux smokes Kraken réels sont confirmés, le test de régression 47.3 obsolète a été corrigé, puis la suite backend complète a été relancée avec succès avant intégration.

Décisions intégrées récentes :

```text
Batch 45        => intégré via 45d41b7
Batch 46 / 46.1 => intégré via b219365
Batch 47.1      => intégré via 842e6bd7
Batch 47.2      => intégré via c09dd14
Batch 47.3      => intégré via 12051a7
Batch 47.4      => intégré via 472f3ad
ADR-328..344    => ADOPTÉES selon leur batch intégré
```

## Radar intégré jusqu'au Batch 47.4

Le Market Attention Radar reste `market-attention-radar-v6`, strictement informatif, déterministe, causal et read-only. L'exécution de trading demeure SPOT uniquement.

Pipeline canonique :

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

Policy :

```text
market_limit_per_refresh = 10
cache_ttl_seconds        = 3600
history_interval_seconds = 3600
history_lookback_seconds = 172800
fetch_concurrency        = 4
baseline_periods         = 12
```

Les cinq séries Analytics intégrées sont `open-interest`, `funding`, `liquidation-volume`, `cvd` et `aggressor-differential`. Les smokes locaux ont confirmé : Funding en timestamps millisecondes ; Liquidation Volume, CVD et Aggressor Differential en secondes.

## Batch 47.4 — intégré via `472f3ad`

Le patch ajoute exactement `cvd` et `aggressor-differential` dans la rotation/cache Analytics unique. Le budget reste 10 marchés, concurrence 4, plafond théorique 50 appels/refresh.

Smokes locaux utilisateur confirmés le 2026-10-05 :

```text
CVD        : timestamp epoch secondes ; data.buy_volume[], data.sell_volume[], data.cvd[] ; more=false ; errors=[]
Aggressor  : timestamp epoch secondes ; data[] scalaire signé ; more=false ; errors=[]
```

Le payload CVD réel a montré `6` timestamps, `6` buy volumes, `4` sell volumes et `6` valeurs CVD. Le contrat applicatif est donc corrigé : `timestamp[] + cvd[]` doivent être alignés 1:1 ; les side volumes ne sont exposés que si **les deux** tableaux sont complets et alignés. Sinon ils restent `None`, sans padding ni réindexation. Les clés live sont `buy_volume` / `sell_volume`; la variante camelCase reste tolérée pour compatibilité documentaire.

Statistiques conservées : CVD sur `cvd_change`, Aggressor directement, médiane + MAD signé, aucun fallback ratio, seuils descriptifs ±2.5. Aucun impact ranking/shortlist/Agent/Risk/Broker.

Validation locale finale observée avant intégration : backend `python -m pytest -q` PASS à 100 %, frontend `pnpm typecheck` PASS, frontend `pnpm test` PASS 82/82, `git diff --check` PASS hors avertissements LF/CRLF, smokes CVD/Aggressor PASS. Le commit `472f3ad` a ensuite été poussé sur GitHub `main` avec un arbre local propre.

Voir `docs/47_4_CVD_AGGRESSOR_DIFFERENTIAL.md`.

## Validations connues

Batch 47.3 local utilisateur avant intégration :

```text
backend python -m pytest -q : PASS — suite complète à 100 %
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 76/76
git diff --check            : PASS — avertissements LF/CRLF uniquement
smoke Kraken Funding        : PASS — PF_XBTUSD, rate/relativeRate OHLC, timestamps millisecondes, more=false
smoke Kraken Liquidation    : PASS — PF_XBTUSD, scalaires non négatifs, timestamps secondes, more=false
```

Batch 47.4 : **INTÉGRÉ via `472f3ad`** ; smokes live locaux CVD/Aggressor PASS ; backend local `python -m pytest -q` PASS à 100 % après correctif ; frontend local typecheck PASS et tests 82/82 PASS ; `git diff --check` PASS hors avertissements LF/CRLF. Correctif ChatGPT : py_compile PASS, pytest ciblé 47/47 PASS, frontend 47.4 6/6 PASS.
