# 09 — Roadmap de développement

## Référence de reprise

```text
Repository              : Ax-07/AI-Spot-Trader
Branche                 : main
Base GitHub auditée     : c09dd14cab31233f635ff535cbf0298ba3f2bd51
Commit fonctionnel 47.3 : 12051a7 — feat: add historical funding and liquidation analytics
Batch 43.2              : intégré
Batch 44                : intégré
Batch 45                : intégré via 45d41b7
Batch 46 / 46.1         : intégré via b219365
Batch 47.1              : intégré via 842e6bd7
Batch 47.2              : intégré via c09dd14
Batch 47.3              : validé localement, commit fonctionnel 12051a7
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch ; `12051a7` est le commit fonctionnel de référence du Batch 47.3.

## Invariants de roadmap

AI Spot Trader conserve un seul Agent IA stratégique, Kraken comme exchange initial, le Risk Engine comme autorité finale, un backend indépendant du frontend, le mode PAPER avant tout LIVE et aucune sortie LLM directement exécutable.

Le Market Attention Radar reste strictement informatif. Les capacités PERPETUAL sont observationnelles uniquement ; l'exécution demeure SPOT.

## État intégré récent

### Batch 43.2 — volume PERPETUAL

**Intégré.** `volumeQuote` Kraken Futures est la source 24h des linear perpetuals/USD. Aucune notionnalisation artificielle de `candle.volume`.

### Batch 44 — liquidité PERPETUAL et couverture

**Intégré.** Percentiles SPOT/PERP séparés et diagnostic de rotation/couverture OHLCV, sans auto-tuning silencieux.

### Batch 45 — Structure en amont

**Intégré via `45d41b7`.** Rotation/cache Structure séparés, événements `BOS/CHOCH`, filtres tendance/Structure et `UNKNOWN` fail-closed. Contrat `market-attention-radar-v6` conservé.

### Batch 46 / 46.1 — baseline adaptative

**Intégré via `b219365`.** Médiane + MAD normalisé, cible 12 périodes et plancher de compatibilité à 6 périodes. Les ratios historiques restent visibles et servent de fallback explicite lorsque le MAD est nul.

### Batch 47.1 — fondations Futures ticker

**Intégré via `842e6bd7`.** Un snapshot bulk `/tickers` canonique alimente volume PERP, liquidité PERP et contexte instantané Futures (`openInterest`, funding brut/prédit, mark/index), sans impact stratégique.

### Batch 47.2 — historique Open Interest + infrastructure Analytics

**Intégré via `c09dd14`.** Une seule infrastructure historique Futures :

```text
PerpetualAnalyticsProvider
PerpetualAnalyticsPolicy
PerpetualAnalyticsScanner
PerpetualAnalyticsSnapshot
perpetual_analytics_coverage
```

Source : `GET /api/charts/v1/analytics/{symbol}/open-interest`.

Le smoke réel a confirmé des buckets OHLC `[open, high, low, close]`; le `close` finalisé est la valeur représentative. Rotation/cache indépendants de l'OHLCV et de Structure, causalité `timestamp + interval <= as_of`, baseline médiane/MAD réutilisant les primitives Batch 46. Caractéristiques : `OPEN_INTEREST_EXPANSION` / `OPEN_INTEREST_CONTRACTION`.

L'OI historique reste descriptif : aucune influence sur `interest_level`, `candidate_limit`, ranking ou création de candidat.

Voir `docs/47_2_OPEN_INTEREST_HISTORIQUE.md`.

## Batch 47.3 — Funding historique + Liquidation Volume

**État : validé localement, commit fonctionnel `12051a7`, clôture documentaire prête pour le push final.**

Périmètre strict :

```text
funding historique
liquidation-volume
```

Architecture : réutiliser le **même** `PerpetualAnalyticsScanner`, le même curseur marché, le même cache, la même causalité et la même policy réseau que 47.2. Aucun scanner parallèle par série.

Audit fournisseur retenu :

- Funding : `result.data.rate[]` et `result.data.relativeRate[]`, buckets OHLC signés ;
- `rate` absolu/raw et `relativeRate` restent explicitement séparés ;
- `fundingRatePrediction` ticker reste distinct et n'est jamais traité comme funding historique réalisé ;
- Liquidation Volume : total agrégé par intervalle, sans direction native démontrée ; aucun champ long/short ;
- formes acceptées pour `liquidation-volume` : scalaire ou OHLC générique, valeurs finies/non négatives ;
- `more=true` reste rejeté explicitement.

Statistiques intégrées :

```text
Funding relatif    : baseline médiane + MAD + score signé, seuil ±2.5
Liquidation volume : baseline médiane + MAD + score, seuil +3.0
Fallback liquidation MAD nul : ratio >= 2.0 lorsque la baseline est non nulle
```

Caractéristiques :

```text
FUNDING_POSITIVE_EXTREME
FUNDING_NEGATIVE_EXTREME
LIQUIDATION_VOLUME_SPIKE
```

Le coût réseau reste borné par `market_limit_per_refresh=10` et `fetch_concurrency=4`. Trois séries impliquent au maximum 30 appels Analytics par refresh avec les valeurs par défaut.

Aucun filtre utilisateur Funding/Liquidation n'est ajouté. Le cockpit expose les données et la couverture par série. Le ranking canonique reste calculé avant enrichissement Analytics.

Voir `docs/47_3_FUNDING_LIQUIDATION_VOLUME.md`.

## Batches suivants

```text
47.4 : CVD + aggressor-differential
47.5 : évaluer explicitement une éventuelle influence multi-analytics sur le ranking
```

47.4 doit réutiliser l'infrastructure Analytics partagée ; aucune nouvelle rotation indépendante ne doit être créée sans décision architecturale explicite.

47.5 est le premier batch autorisé à discuter une éventuelle influence de ces Analytics sur le ranking. Aucune autorité stratégique n'est anticipée silencieusement.

## Validation connue

Batch 47.2 — avant intégration :

```text
backend pytest -q       : PASS — suite arrivée à 100 %
frontend pnpm typecheck : PASS
frontend pnpm test      : PASS — 72/72
git diff --check        : PASS hors avertissements LF/CRLF
smoke PF_XBTUSD OI      : PASS — OHLC, more=false
```

Batch 47.3 — validation finale :

```text
python -m py_compile ciblé                         : PASS
pytest ciblé Batch 47.3                            : PASS — 23/23 après correctif timestamp Funding
backend python -m pytest -q                        : PASS — suite complète à 100 %
frontend pnpm typecheck                            : PASS
frontend pnpm test                                 : PASS — 76/76
git diff --check                                   : PASS — avertissements LF/CRLF uniquement
smoke Kraken Funding PF_XBTUSD                     : PASS — rate/relativeRate OHLC, timestamp ms
smoke Kraken Liquidation Volume PF_XBTUSD          : PASS — data[] scalaire, timestamp s
```

Le correctif d'unité du timestamp Funding est inclus dans le commit fonctionnel `12051a7`.

## Périmètres ultérieurs possibles

- microstructure Futures si le besoin est démontré ;
- conversion multi-devise derrière une source FX explicite et testée ;
- éventuelle utilisation du Radar comme contexte Agent après décision architecturale ;
- LIVE séparé et ultérieur.

Aucun bot algorithmique traditionnel, quota de trades, optimisation post-hoc ou promesse de rendement ne doit être introduit silencieusement.
