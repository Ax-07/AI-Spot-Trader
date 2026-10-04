# 09 — Roadmap de développement

## Référence de reprise

```text
Repository                  : Ax-07/AI-Spot-Trader
Branche                     : main
HEAD GitHub audité          : ec1cd5dc576c8638bff7c7110aa9a0a2292f71ff
Commit fonctionnel 47.3     : 12051a7 — feat: add historical funding and liquidation analytics
Clôture 47.3 observée       : ec1cd5d — docs: mark batch 47.3 integrated
Batch 43.2                  : intégré
Batch 44                    : intégré
Batch 45                    : intégré via 45d41b7
Batch 46 / 46.1             : intégré via b219365
Batch 47.1                  : intégré via 842e6bd7
Batch 47.2                  : intégré via c09dd14
Batch 47.3                  : intégré via 12051a7
Batch 47.4                  : VALIDÉ LOCALEMENT, prêt à intégrer sur main
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

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

**Intégré via `b219365`.** Médiane + MAD normalisé, cible 12 périodes et plancher de compatibilité à 6 périodes. Les ratios historiques restent visibles et servent de fallback explicite lorsque le MAD est nul pour les métriques où cette sémantique est valable.

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

**Intégré sur GitHub `main` via le commit fonctionnel `12051a7`.**

Périmètre strict :

```text
funding historique
liquidation-volume
```

Architecture : même `PerpetualAnalyticsScanner`, même curseur marché, même cache, même causalité et même policy réseau que 47.2. Aucun scanner parallèle par série.

Audit fournisseur retenu :

- Funding : `result.data.rate[]` et `result.data.relativeRate[]`, buckets OHLC signés ;
- `rate` absolu/raw et `relativeRate` restent explicitement séparés ;
- `fundingRatePrediction` ticker reste distinct et n'est jamais traité comme funding historique réalisé ;
- Liquidation Volume : total agrégé par intervalle, sans direction native démontrée ; aucun champ long/short ;
- `more=true` reste rejeté explicitement.

Statistiques intégrées :

```text
Funding relatif    : baseline médiane + MAD + score signé, seuil ±2.5
Liquidation volume : baseline médiane + MAD + score, seuil +3.0
Fallback liquidation MAD nul : ratio >= 2.0 lorsque la baseline est non nulle
```

Trois séries impliquent au maximum 30 appels Analytics par refresh avec `market_limit_per_refresh=10` et `fetch_concurrency=4`.

Voir `docs/47_3_FUNDING_LIQUIDATION_VOLUME.md`.

## Batch 47.4 — CVD + Aggressor Differential

**État : validé localement, prêt à intégrer ; GitHub `main` reste à la clôture 47.3 avant commit.**

Périmètre : `cvd` + `aggressor-differential`, toujours dans le même `PerpetualAnalyticsScanner`, cache, curseur et sémaphore global. 5 séries × 10 marchés = 50 requêtes max/refresh ; `fetch_concurrency=4` inchangé.

Contrats live confirmés :

- CVD : timestamps secondes ; clés `buy_volume`, `sell_volume`, `cvd` ; `cvd[]` signé et aligné aux timestamps ; side arrays potentiellement de longueurs différentes ;
- side volumes CVD exposés uniquement lorsque les deux tableaux sont complets et alignés ; sinon `None`, sans inférence ;
- Aggressor Differential : timestamps secondes, `data[]` scalaire signé, sémantique taker buy − taker sell ;
- `more=false`, `errors=[]` sur les deux smokes PF_XBTUSD.

Analyse : CVD sur `cvd_change`, Aggressor directement, médiane + MAD, aucun fallback ratio pour ces séries signées, seuils descriptifs ±2.5. Caractéristiques `CVD_POSITIVE_IMPULSE`, `CVD_NEGATIVE_IMPULSE`, `AGGRESSOR_BUY_DOMINANCE`, `AGGRESSOR_SELL_DOMINANCE`. Aucun impact ranking, shortlist ou exécution.

Validation locale finale observée après correctif : backend `python -m pytest -q` PASS à 100 %, frontend typecheck PASS, tests frontend 82/82 PASS, `git diff --check` PASS hors avertissements LF/CRLF et smokes CVD/Aggressor PASS. Le batch est prêt à être commité puis poussé.

Voir `docs/47_4_CVD_AGGRESSOR_DIFFERENTIAL.md`.

## Batch suivant

```text
47.5 : évaluer explicitement une éventuelle influence multi-analytics sur le ranking
```

47.5 est le premier batch autorisé à discuter pondération/déduplication OI/Funding/Liquidations/CVD/Aggressor. CVD et Aggressor provenant tous deux de l'order flow agressif, aucune double pondération n'est introduite en 47.4.

## Validation connue

Batch 47.3 — validation finale :

```text
backend python -m pytest -q                        : PASS — suite complète à 100 %
frontend pnpm typecheck                            : PASS
frontend pnpm test                                 : PASS — 76/76
git diff --check                                   : PASS — avertissements LF/CRLF uniquement
smoke Kraken Funding PF_XBTUSD                     : PASS — rate/relativeRate OHLC, timestamp ms
smoke Kraken Liquidation Volume PF_XBTUSD          : PASS — data[] scalaire, timestamp s
```

Batch 47.4 — smokes Kraken locaux PASS ; backend local complet PASS à 100 % après correctif ; frontend local typecheck PASS et tests 82/82 PASS ; `git diff --check` PASS hors avertissements LF/CRLF. Correctif ciblé ChatGPT : 47/47 PASS + frontend 47.4 6/6 PASS. Prêt à intégrer.

## Périmètres ultérieurs possibles

- microstructure Futures si le besoin est démontré ;
- conversion multi-devise derrière une source FX explicite et testée ;
- éventuelle utilisation du Radar comme contexte Agent après décision architecturale ;
- LIVE séparé et ultérieur.

Aucun bot algorithmique traditionnel, quota de trades, optimisation post-hoc ou promesse de rendement ne doit être introduit silencieusement.
