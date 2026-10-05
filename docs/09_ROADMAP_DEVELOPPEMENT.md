# 09 — Roadmap de développement

## Référence de reprise

```text
Repository                  : Ax-07/AI-Spot-Trader
Branche                     : main
HEAD GitHub réel audité     : e972fd9112363b268a53658fe5ce88facbfa7dd7
Clôture 47.4                : e972fd9 — docs: mark batch 47.4 integrated
Commit fonctionnel 47.4     : 472f3ad — feat: add CVD and aggressor analytics
Batch 43.2                  : intégré
Batch 44                    : intégré
Batch 45                    : intégré via 45d41b7
Batch 46 / 46.1             : intégré via b219365
Batch 47.1                  : intégré via 842e6bd7
Batch 47.2                  : intégré via c09dd14
Batch 47.3                  : intégré via 12051a7
Batch 47.4                  : intégré via 472f3ad
Batch 47.5                  : patch proposé, non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve un seul Agent IA stratégique, Kraken comme exchange initial, le Risk Engine comme autorité finale, un backend indépendant du frontend, le mode PAPER avant tout LIVE et aucune sortie LLM directement exécutable.

Le Market Attention Radar reste informatif. Les capacités PERPETUAL sont observationnelles uniquement ; l'exécution demeure SPOT.

## État intégré récent

### Batch 43.2 — volume PERPETUAL

**Intégré.** `volumeQuote` Kraken Futures est la source 24h des linear perpetuals/USD. Aucune notionnalisation artificielle de `candle.volume`.

### Batch 44 — liquidité PERPETUAL et couverture

**Intégré.** Percentiles SPOT/PERP séparés et diagnostic de rotation/couverture OHLCV, sans auto-tuning silencieux.

### Batch 45 — Structure en amont

**Intégré via `45d41b7`.** Rotation/cache Structure séparés, événements `BOS/CHOCH`, filtres tendance/Structure et `UNKNOWN` fail-closed. Contrat `market-attention-radar-v6` conservé.

### Batch 46 / 46.1 — baseline adaptative

**Intégré via `b219365`.** Médiane + MAD normalisé, cible 12 périodes et plancher de compatibilité à 6 périodes. Les ratios historiques restent observables et servent de fallback uniquement pour les métriques où cette sémantique est explicitement admise.

### Batch 47.1 — fondations Futures ticker

**Intégré via `842e6bd7`.** Un snapshot bulk `/tickers` canonique alimente volume PERP, liquidité PERP et contexte instantané Futures, sans impact stratégique.

### Batch 47.2 — historique Open Interest + infrastructure Analytics

**Intégré via `c09dd14`.** Une seule infrastructure historique Futures (`PerpetualAnalyticsScanner`, policy, cache, rotation, coverage). `OPEN_INTEREST_EXPANSION` / `OPEN_INTEREST_CONTRACTION` sont descriptifs et causaux.

### Batch 47.3 — Funding historique + Liquidation Volume

**Intégré via `12051a7`.** Funding relatif signé et Liquidation Volume agrégé réutilisent exactement l'infrastructure Analytics 47.2. Aucun split long/short inventé.

### Batch 47.4 — CVD + Aggressor Differential

**Intégré via `472f3ad`, clôture documentaire `e972fd9`.** CVD sur variation, Aggressor signé, médiane/MAD, aucun fallback ratio pour ces séries signées, cinq séries dans le même scanner/cache/cursor/sémaphore. Budget : 50 appels max/refresh, concurrence 4.

La règle intégrée 47.4 reste : aucun impact Analytics sur ranking/shortlist/Agent/Risk/Broker.

Voir `docs/47_4_CVD_AGGRESSOR_DIFFERENTIAL.md`.

## Batch 47.5 — influence multi-analytics sur le ranking

**Patch proposé, non intégré.**

Audit des quatre familles de solutions :

1. aucun impact : sûr mais n'exploite pas les caractéristiques désormais robustes ;
2. tie-break strict : trop souvent inerte ;
3. bonus/malus sur le score existant : rejeté, car il pourrait modifier `interest_level` et l'admission ;
4. score multi-analytics séparé et plafonné : **retenu**.

Politique proposée :

```text
OPEN_INTEREST      0/1
FUNDING            0/1
LIQUIDATION_VOLUME 0/1
ORDER_FLOW         0/1 (CVD + Aggressor dédupliqués)
TOTAL              0..4
```

Règles :

- disponibilité seule ne rapporte rien ;
- séries non `AVAILABLE` = neutres, jamais pénalisantes ;
- signes positifs/négatifs = symétriques pour l'attention ;
- CVD + Aggressor concordants = +1 total ; opposés = 0 et conflit diagnostiqué ;
- aucun changement de `interest_level`, `candidate_limit` ou population de candidats ;
- insertion du score après niveau d'intérêt et Structure confirmée ;
- scope SPOT inchangé ; scope ALL conserve les positions SPOT et ne réordonne que les slots PERP ;
- API v6 étendue additivement ; cockpit explicite ;
- aucune modification Agent/Risk/Broker ou exécution.

Voir `docs/47_5_MULTI_ANALYTICS_RANKING.md`.

## Validation connue

Batch 47.4 intégré : backend local utilisateur complet PASS à 100 %, frontend typecheck PASS, tests 82/82 PASS, `git diff --check` PASS hors avertissements LF/CRLF, smokes CVD/Aggressor PASS.

Batch 47.5 : les validations réellement exécutées par ChatGPT sont consignées dans `docs/10_DECISIONS_ET_CHANGELOG.md`. La suite complète backend/frontend et `git diff --check` doivent être relancés localement après extraction avant intégration.

## Périmètres ultérieurs possibles

- calibrage futur uniquement si des observations causales le justifient, sans optimisation post-hoc P&L ;
- microstructure Futures si le besoin est démontré ;
- conversion multi-devise derrière une source FX explicite et testée ;
- éventuelle utilisation du Radar comme contexte Agent après décision architecturale séparée ;
- LIVE séparé et ultérieur.

Aucun bot algorithmique traditionnel, quota de trades, optimisation post-hoc ou promesse de rendement ne doit être introduit silencieusement.
