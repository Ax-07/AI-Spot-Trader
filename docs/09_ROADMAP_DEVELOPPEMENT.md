# 09 — Roadmap de développement

## Référence de reprise

```text
Repository                  : Ax-07/AI-Spot-Trader
Branche                     : main
HEAD GitHub audité Batch 48 : 4278a5c732b9636b06144ff58e8485b3350a2c0d
Batch 45                    : intégré via 45d41b7
Batch 46 / 46.1             : intégré via b219365
Batch 47.1                  : intégré via 842e6bd7
Batch 47.2                  : intégré via c09dd14
Batch 47.3                  : intégré via 12051a7
Batch 47.4                  : intégré via 472f3ad
Clôture documentaire 47.4   : e972fd9
Batch 47.5                  : intégré via d988de4
Clôture documentaire 47.5   : 4278a5c
Batch 48                    : patch proposé, non intégré à GitHub à la livraison
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve :

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- Risk Engine comme autorité finale ;
- backend indépendant du frontend ;
- PAPER avant tout LIVE ;
- exécution SPOT uniquement ;
- aucune sortie LLM directement exécutable ;
- aucune exécution PERPETUAL ;
- aucun secret versionné ;
- aucune optimisation post-hoc.

Le Market Attention Radar reste un **outil de priorisation d'attention**, jamais un moteur BUY/SELL/HOLD.

## État intégré récent

### Batch 45 — Structure en amont

**Intégré via `45d41b7`.** Rotation/cache Structure séparés, événements BOS/CHOCH, filtres tendance/Structure et `UNKNOWN` fail-closed. Contrat `market-attention-radar-v6` conservé.

### Batch 46 / 46.1 — baseline adaptative

**Intégré via `b219365`.** Médiane + MAD normalisé, cible 12 périodes et fallback ratio uniquement pour les métriques où cette sémantique est justifiée.

### Batch 47.1 — fondations Futures ticker

**Intégré via `842e6bd7`.** Snapshot bulk `/tickers` partagé pour volume/liquidité/contexte Futures, sans impact stratégique.

### Batch 47.2 — historique Open Interest

**Intégré via `c09dd14`.** Infrastructure Analytics historique canonique avec rotation/cache/concurrence bornés et causalité explicite.

### Batch 47.3 — Funding historique + Liquidation Volume

**Intégré via `12051a7`.** Funding relatif signé et Liquidation Volume agrégé réutilisent le même scanner Analytics.

### Batch 47.4 — CVD + Aggressor Differential

**Intégré via `472f3ad`, clôturé documentairement via `e972fd9`.** CVD sur variation, Aggressor signé, MAD robuste, aucun fallback ratio pour les séries signées. Cinq séries partagent le même scanner/cache/cursor/sémaphore.

### Batch 47.5 — influence multi-analytics bornée sur le ranking

**Intégré via `d988de4`, clôturé documentairement via `4278a5c`.**

Décision architecturale :

```text
score séparé 0..4
= OI 0/1
+ Funding 0/1
+ Liquidations 0/1
+ Order Flow 0/1
```

CVD et Aggressor Differential forment une seule composante `ORDER_FLOW`. Ils ne peuvent jamais fournir +2.

Règles intégrées :

- score calculé uniquement sur les PERP déjà retenus ;
- `interest_level` inchangé ;
- `candidate_limit` inchangé ;
- aucune création/suppression de candidat ;
- données absentes/dégradées neutres ;
- signes positifs/négatifs symétriques pour l'attention ;
- priorité : intérêt -> Structure -> Analytics -> reste de la clé ;
- `SPOT` inchangé ;
- en `ALL`, positions SPOT figées ;
- contrat API v6 étendu additivement ;
- diagnostics cockpit explicites ;
- aucun impact direct Agent/Risk/Broker.

Voir `docs/47_5_MULTI_ANALYTICS_RANKING.md`.

## Batch 48 — observabilité du ranking Analytics

**Patch préparé sur le HEAD `4278a5c`; non intégré à GitHub au moment de la livraison.**

Objectif : mesurer le comportement réel du ranking 47.5 avant toute nouvelle pondération ou toute exposition à l'Agent.

Décision proposée et implémentée dans le patch :

```text
historique Radar borné existant
-> agrégation read-only à la demande
-> endpoint observability dédié
-> cockpit compact
```

Pas de nouvelle persistence et pas de second buffer. La persistence SQL actuelle reste réservée à ses responsabilités PAPER/audit économique.

Mesures ajoutées :

- distribution score `0..4` ;
- contribution des quatre familles ;
- statuts des cinq séries ;
- fréquence de reranking applicable/effectif ;
- snapshots applicables sans mouvement ;
- `rank_change` direction/moyenne/max ;
- déduplications et conflits CVD/Aggressor ;
- PERP sans Analytics exploitable ;
- ventilation par scope ;
- couverture descriptive par marché ;
- fenêtre et taille d'échantillon explicites.

Nouvelle route additive :

```text
GET /api/v1/market-attention/observability?limit=96
```

Le score, l'admission, `interest_level`, `candidate_limit`, Agent, Risk et Broker restent inchangés.

Voir `docs/48_OBSERVABILITE_RANKING_ANALYTICS.md`.

## Validation connue

### Batch 47.5 intégré

```text
backend python -m pytest -q : PASS — suite complète à 100 %
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 86/86
git diff --check            : PASS — avertissements LF/CRLF uniquement
push GitHub main            : PASS — d988de4 puis clôture 4278a5c
```

### Batch 48 — patch proposé

ChatGPT a exécuté sur le nouveau module autonome :

```text
python -m pytest -q tests/test_market_attention_batch48_analytics_observability.py
12 passed
```

Les validations complètes restent obligatoires localement après extraction :

```text
python -m pytest -q
pnpm typecheck
pnpm test
git diff --check
```

## Suite après Batch 48

Ne pas modifier les poids du ranking tant qu'une fenêtre d'observation suffisante n'a pas été collectée et interprétée séparément de tout P&L futur.

Périmètres futurs possibles, uniquement via batch séparé et après resynchronisation :

- décider si une persistence durable du diagnostic Radar est réellement nécessaire ;
- protocole d'analyse offline sans look-ahead ;
- évolution éventuelle des pondérations, uniquement sur justification documentée ;
- microstructure Futures ;
- conversion multi-devise derrière une source FX explicite ;
- utilisation éventuelle du Radar comme contexte Agent, via décision architecturale séparée ;
- LIVE séparé et ultérieur.
