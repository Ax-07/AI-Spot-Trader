# 00 — État actuel

## Référence de reprise — Batch 48 intégré

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
Base GitHub auditée pour clôture   : ebb664c538f7a77ffe1a51ef4a44536a83cb484e
Clôture documentaire Batch 47.5    : 4278a5c — docs: mark batch 47.5 integrated
Batch 48 fonctionnel               : ebb664c — feat: add analytics ranking observability
Batch 48                           : INTÉGRÉ ET VALIDÉ LOCALEMENT
```

Le **Batch 48 est intégré sur GitHub `main` via `ebb664c`**. L'arbre local utilisateur était propre immédiatement après le push (`git status --short` vide) et `origin/main` pointait sur le même commit.

## Radar intégré jusqu'au Batch 48

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
-> historique Radar borné
-> observabilité Analytics agrégée à la demande
-> cockpit
```

## Ranking Analytics intégré — Batch 47.5

Score inchangé dans le Batch 48 :

```text
OPEN_INTEREST       : 0 ou +1
FUNDING             : 0 ou +1
LIQUIDATION_VOLUME  : 0 ou +1
ORDER_FLOW          : 0 ou +1
TOTAL               : 0..4
```

CVD + Aggressor Differential restent une seule famille `ORDER_FLOW`.

Hiérarchie PERPETUAL inchangée :

```text
interest_level
-> événement Structure confirmé
-> analytics_ranking.score
-> critères microstructure / activité / liquidité restants
-> symbole déterministe
```

Scopes inchangés :

- `SPOT` : classement inchangé ;
- `PERPETUAL` : réordonnancement possible uniquement entre PERP déjà retenus ;
- `ALL` : positions SPOT figées, seuls les slots PERP peuvent être réordonnés entre eux.

## Batch 48 — observabilité du comportement réel

Le Batch 48 ajoute une agrégation **read-only, descriptive et causale** du ranking Analytics sans toucher à sa logique.

Décision architecturale intégrée : réutiliser l'historique Radar process-local déjà borné, au lieu d'ajouter une seconde `deque` ou une nouvelle persistence.

Avec la policy par défaut :

```text
refresh_seconds = 300
history_limit   = 96
```

la profondeur nominale maximale est d'environ huit heures tant que le backend reste actif.

Route additive intégrée :

```text
GET /api/v1/market-attention/observability?limit=96
```

Schéma :

```text
analytics-ranking-observability-v1
```

Métriques principales :

- distribution score `0..4` ;
- contribution réelle des quatre familles ;
- santé des cinq séries par statut ;
- snapshots où le reranking est applicable/effectif/sans mouvement ;
- candidats montés/descendus/inchangés ;
- distribution exacte de `rank_change` et moyenne/max de `abs(rank_change)` ;
- déduplications et conflits CVD/Aggressor ;
- PERP sans aucune série `AVAILABLE` ;
- ventilation SPOT/PERPETUAL/ALL ;
- couverture descriptive par marché ;
- fenêtre temporelle et taille d'échantillon explicites.

Le cockpit possède un dock compact séparé qui lit uniquement cette route backend. Fermer le frontend n'affecte pas le moteur ni l'historique backend.

Limite assumée : l'historique Radar n'est pas durable. Un redémarrage backend remet la fenêtre d'observation à zéro. Aucune nouvelle base/table n'a été ajoutée.

## Invariants préservés

- un seul Agent IA stratégique ;
- Risk Engine déterministe avec autorité finale ;
- aucune sortie LLM directement exécutable ;
- aucune dépendance du Radar vers Agent/Risk/Broker ;
- PAPER ;
- exécution SPOT uniquement ;
- aucune exécution PERPETUAL ;
- score Analytics `0..4` inchangé ;
- aucun changement de `interest_level` ;
- aucun changement de `candidate_limit` ;
- aucune création/suppression de candidat par Analytics ;
- aucun secret versionné ;
- aucun look-ahead ;
- aucune optimisation post-hoc sur le P&L.

## Validation finale Batch 48

Validation locale utilisateur exécutée après extraction du patch et avant intégration :

```text
python -m pytest -q : PASS — 1155 passed, 2 warnings
pnpm typecheck      : PASS
pnpm test           : PASS — 86/86
git diff --check    : PASS — aucun défaut whitespace ; avertissements LF -> CRLF uniquement
git push origin main: PASS — 4278a5c..ebb664c
git status --short  : vide après push
git log -1 --oneline: ebb664c feat: add analytics ranking observability
```

Warnings observés mais non bloquants :

- `StarletteDeprecationWarning` dans `fastapi.testclient` ;
- dépréciation `anyio.abc.BlockingPortal` dans `starlette.testclient` ;
- warning Node `MODULE_TYPELESS_PACKAGE_JSON`.

Aucun de ces warnings n'a provoqué d'échec et aucun correctif hors périmètre n'a été ajouté silencieusement.

Voir `docs/48_OBSERVABILITE_RANKING_ANALYTICS.md`.
