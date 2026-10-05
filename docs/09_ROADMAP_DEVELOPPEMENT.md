# 09 — Roadmap de développement

## Référence de reprise

```text
Repository                  : Ax-07/AI-Spot-Trader
Branche                     : main
Base GitHub auditée         : d988de42dd684b597a78a6ce1d6d32a86147bf37
Batch 45                    : intégré via 45d41b7
Batch 46 / 46.1             : intégré via b219365
Batch 47.1                  : intégré via 842e6bd7
Batch 47.2                  : intégré via c09dd14
Batch 47.3                  : intégré via 12051a7
Batch 47.4                  : intégré via 472f3ad
Clôture documentaire 47.4   : e972fd9
Batch 47.5                  : intégré via d988de4
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

**Intégré via `d988de4`.**

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

## Validation intégrée Batch 47.5

```text
backend python -m pytest -q : PASS — suite complète à 100 %
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 86/86
git diff --check            : PASS — avertissements LF/CRLF uniquement
push GitHub main            : PASS — d988de4
arbre local après push      : propre
```

Les warnings Node `MODULE_TYPELESS_PACKAGE_JSON` et les dépréciations de dépendances de test FastAPI/Starlette sont connus mais non bloquants ; ils n'ont pas été mélangés au Batch 47.5.

## Suite

Le Batch 47.5 clôt la sous-série d'intégration initiale des cinq Futures Analytics dans le Radar.

Le prochain batch doit être décidé séparément après resynchronisation. Toute évolution de pondération devra s'appuyer sur des observations causales et reproductibles, sans optimisation rétrospective du P&L et sans transformer le Radar en bot algorithmique traditionnel.

Périmètres futurs possibles, uniquement si justifiés :

- observation/calibrage du comportement du score Analytics ;
- microstructure Futures ;
- conversion multi-devise derrière une source FX explicite ;
- utilisation éventuelle du Radar comme contexte Agent, via décision architecturale séparée ;
- LIVE séparé et ultérieur.
