# 00 — État actuel

## Référence de reprise — Batch 47.5 intégré

```text
Repository                       : Ax-07/AI-Spot-Trader
Branche                          : main
Base GitHub auditée pour clôture : d988de42dd684b597a78a6ce1d6d32a86147bf37
Batch 47.4 fonctionnel           : 472f3ad — feat: add CVD and aggressor analytics
Clôture documentaire Batch 47.4 : e972fd9 — docs: mark batch 47.4 integrated
Batch 47.5 fonctionnel           : d988de4 — feat: add bounded multi-analytics radar ranking
Batch 47.5                       : INTÉGRÉ ET VALIDÉ LOCALEMENT
```

Le **Batch 47.5 est intégré sur GitHub `main` via `d988de4`**. L'arbre local utilisateur était propre immédiatement après le push (`git status --short` vide) et `origin/main` pointait sur le même commit.

## Radar intégré jusqu'au Batch 47.5

Le Market Attention Radar reste `market-attention-radar-v6`, déterministe, causal, informatif et read-only. Il ne prend aucune décision BUY/SELL/HOLD et n'a aucune autorité d'exécution.

L'exécution demeure SPOT uniquement. Aucun short, levier, margin, future ou perpetual n'est exécuté.

Pipeline canonique :

```text
catalogue Kraken
-> scope SPOT / PERPETUAL / ALL
-> métadonnées / filtre capitalisation
-> rotation OHLCV et volume 24h
-> activité adaptative / tendance / liquidité / microstructure canonique
-> rotation/cache Analytics Futures historique
-> rotation/cache Market Structure
-> filtres tendance / Structure
-> shortlist finale canonique
-> enrichissement Futures ticker + Analytics
-> reranking Analytics borné des PERP déjà retenus
-> cockpit
```

## Infrastructure Analytics canonique

Les cinq séries historiques restent :

```text
open-interest
funding
liquidation-volume
cvd
aggressor-differential
```

Elles partagent toujours exactement :

```text
1 PerpetualAnalyticsScanner
1 _perpetual_analytics_cursor
1 _cache
1 sémaphore global
1 PerpetualAnalyticsPolicy
```

Policy réseau inchangée :

```text
market_limit_per_refresh = 10
cache_ttl_seconds        = 3600
history_interval_seconds = 3600
history_lookback_seconds = 172800
fetch_concurrency        = 4
baseline_periods         = 12
```

Budget théorique maximal : **5 séries × 10 marchés = 50 appels Analytics par refresh**.

## Batch 47.5 — décision intégrée

La famille retenue est un **score multi-analytics séparé, plafonné et explicable**, et non un bonus injecté dans `interest_level`.

Score :

```text
OPEN_INTEREST       : 0 ou +1
FUNDING             : 0 ou +1
LIQUIDATION_VOLUME  : 0 ou +1
ORDER_FLOW          : 0 ou +1
TOTAL               : 0..4
```

Règles intégrées :

- disponibilité seule ne rapporte aucun point ;
- seules les caractéristiques déjà validées par 47.2–47.4 peuvent contribuer ;
- séries absentes, `PARTIAL`, `INSUFFICIENT_HISTORY`, `STALE`, `TECHNICAL_ERROR` ou `NOT_APPLICABLE` = 0 sans pénalité ;
- les anomalies signées positives/négatives sont symétriques pour **l'attention**, jamais interprétées comme BUY/SELL ;
- CVD + Aggressor Differential appartiennent à une seule famille `ORDER_FLOW` ;
- concordance CVD/Aggressor = +1 maximum et déduplication diagnostiquée ;
- opposition simultanée = 0 pour `ORDER_FLOW` et conflit diagnostiqué ;
- aucun changement de `interest_level` ;
- aucun changement de `candidate_limit` ;
- aucune création ou suppression de candidat par Analytics.

Hiérarchie PERPETUAL :

```text
interest_level
-> événement Structure confirmé
-> analytics_ranking.score
-> critères microstructure / activité / liquidité restants
-> symbole déterministe
```

Scopes :

- `SPOT` : classement inchangé ;
- `PERPETUAL` : réordonnancement possible entre PERP déjà retenus ;
- `ALL` : positions SPOT figées ; seuls les slots PERP peuvent être réordonnés entre eux.

Le diagnostic additif `analytics_ranking` expose notamment le score `0..4`, les composantes, les séries retenues/non retenues, la déduplication/conflit order-flow, le rang avant/après et `rank_change`.

## Invariants préservés

- un seul Agent IA stratégique ;
- Risk Engine déterministe avec autorité finale ;
- aucune sortie LLM directement exécutable ;
- aucune dépendance du Radar vers Agent/Risk/Broker ;
- PAPER ;
- exécution SPOT uniquement ;
- aucune exécution PERPETUAL ;
- frais/spread/slippage conservés ;
- journalisation des décisions ;
- aucun secret versionné ;
- aucun look-ahead ;
- aucune optimisation post-hoc sur le P&L.

## Validation finale Batch 47.5

Validation locale utilisateur exécutée après extraction du patch et avant intégration :

```text
git diff --check       : PASS — aucun défaut whitespace ; avertissements LF -> CRLF uniquement
python -m pytest -q    : PASS — suite backend complète à 100 %
pnpm typecheck         : PASS
pnpm test              : PASS — 86/86
git status --short     : propre après push
git log -1 --oneline   : d988de4 feat: add bounded multi-analytics radar ranking
```

Warnings observés mais non bloquants :

- dépréciations `fastapi/starlette` dans les dépendances de test ;
- `MODULE_TYPELESS_PACKAGE_JSON` côté Node lors des tests TypeScript.

Aucun de ces warnings n'a provoqué d'échec et aucun correctif hors périmètre n'a été ajouté silencieusement.

Voir `docs/47_5_MULTI_ANALYTICS_RANKING.md`.
