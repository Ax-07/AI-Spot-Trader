# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent disponibles dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les références nécessaires à la reprise.

## Principes actifs

Un seul Agent IA stratégique. Le Risk Engine déterministe conserve l'autorité finale. Aucune sortie LLM ne déclenche directement Broker/Kraken. L'exécution reste SPOT uniquement, en PAPER tant que le passage LIVE n'est pas explicitement décidé.

Le Market Attention Radar est observationnel : il peut prioriser **l'attention**, mais il ne décide jamais BUY/SELL/HOLD et ne possède aucune autorité d'exécution.

## Référence courante

```text
Base GitHub auditée       : d988de42dd684b597a78a6ce1d6d32a86147bf37
Batch 47.4 fonctionnel    : 472f3ad — feat: add CVD and aggressor analytics
Clôture 47.4              : e972fd9 — docs: mark batch 47.4 integrated
Batch 47.5 fonctionnel    : d988de4 — feat: add bounded multi-analytics radar ranking
Batch 47.5                : INTÉGRÉ ET VALIDÉ
```

## Changelog — 2026-10-05 — Batch 47.5 multi-analytics ranking — intégré

Base d'audit initiale du développement : `e972fd9112363b268a53658fe5ce88facbfa7dd7`.

Commit fonctionnel intégré : `d988de42dd684b597a78a6ce1d6d32a86147bf37` (`feat: add bounded multi-analytics radar ranking`).

### Audit confirmé

- `interest_level` est calculé avant l'enrichissement Analytics ;
- la clé canonique place le niveau d'intérêt en premier ;
- la sélection Structure finale conserve intérêt puis Structure avant le reste de la clé ;
- `candidate_limit` vient de `MarketAttentionPolicy` (`10` par défaut, borné `1..30`) ;
- les Analytics sont scannées avant Structure mais enrichissaient historiquement la shortlist après admission ;
- les cinq séries partagent exactement le même scanner/cache/cursor/sémaphore ;
- CVD et Aggressor Differential appartiennent au même domaine order-flow agressif ;
- OI/Funding/Liquidations/CVD/Aggressor fournissaient déjà les caractéristiques nécessaires ;
- les statuts dégradés et le MAD nul sur séries signées étaient déjà explicitement représentés.

### Familles comparées

1. aucun impact Analytics : sûr mais purement descriptif ;
2. tie-break strict : trop souvent inerte ;
3. bonus/malus sur le score existant : rejeté car susceptible de modifier `interest_level` et l'admission ;
4. score multi-analytics séparé et plafonné : **retenu et intégré**.

### Patch intégré

- ajout additif d'`analytics_ranking` au candidat v6 ;
- score entier `0..4` ;
- quatre familles indépendantes : `OPEN_INTEREST`, `FUNDING`, `LIQUIDATION_VOLUME`, `ORDER_FLOW` ;
- disponibilité seule = 0 ;
- seules les caractéristiques 47.2–47.4 actives et `AVAILABLE` peuvent contribuer ;
- anomalies positives/négatives signées symétriques pour l'attention ;
- CVD + Aggressor concordants = +1 maximum, avec déduplication diagnostiquée ;
- CVD + Aggressor opposés = 0 sur order-flow, avec conflit diagnostiqué ;
- données absentes, partielles, insuffisantes, stale, technical error ou N/A = 0 sans malus ;
- aucune modification des seuils/statistiques 47.2–47.4 ;
- aucun nouveau scanner/cache/cursor ;
- budget réseau maximal inchangé à 50 appels Analytics/refresh ;
- `interest_level` inchangé ;
- `candidate_limit` inchangé ;
- aucun filtre ou candidat créé par Analytics ;
- score injecté après intérêt et Structure confirmée, avant le reste de la clé ;
- `SPOT` inchangé ;
- en `ALL`, slots SPOT figés et réordonnancement seulement entre PERP ;
- cockpit enrichi avec score, composantes, statuts, déduplication/conflit, rang avant/après et `rank_change` ;
- compatibilité legacy conservée car `analytics_ranking` est optionnel ;
- aucune modification Agent / Risk Engine / Broker ;
- aucune exécution PERPETUAL.

## ADR-345 — Score Analytics séparé et plafonné à quatre familles

**ADOPTÉ — Batch 47.5 intégré via `d988de4`.**

Le score d'attention Analytics est distinct de `interest_level`. Il vaut au maximum 4 : OI, Funding, Liquidations et Order Flow valent chacun au plus +1.

La magnitude brute des scores statistiques n'est pas additionnée. Cette règle borne l'influence et évite qu'une série extrême domine arbitrairement le classement.

## ADR-346 — CVD et Aggressor Differential forment une seule composante order-flow

**ADOPTÉ — Batch 47.5 intégré via `d988de4`.**

CVD et Aggressor Differential ne sont pas deux preuves indépendantes.

```text
un seul actif            -> +1
deux actifs concordants  -> +1 total
deux actifs opposés      -> 0 + conflit diagnostiqué
```

Cette décision élimine la double pondération mécanique de l'order flow agressif.

## ADR-347 — Analytics ne peut ni créer un candidat ni modifier `interest_level`

**ADOPTÉ — Batch 47.5 intégré via `d988de4`.**

Le score est appliqué uniquement à des PERP déjà présents dans la shortlist finale.

Hiérarchie :

```text
interest_level
-> Structure confirmée
-> analytics_ranking.score
-> reste de la clé canonique
```

En scope `ALL`, les positions SPOT restent fixes.

## ADR-348 — Une série Analytics indisponible est neutre

**ADOPTÉ — Batch 47.5 intégré via `d988de4`.**

Seul le statut `AVAILABLE` permet d'utiliser une caractéristique. Données absentes, `PARTIAL`, `INSUFFICIENT_HISTORY`, `STALE`, `TECHNICAL_ERROR` ou `NOT_APPLICABLE` contribuent 0 sans malus.

Une panne technique ne devient jamais une information de marché.

## Validation finale 47.5

Validations ciblées exécutées pendant la préparation du patch :

```text
python -m py_compile production + test backend 47.5 : PASS
harnais backend isolé ranking 47.5                  : PASS — 15/15
tsc strict ciblé market-attention.ts                : PASS
tsc syntaxe lib + cockpit                           : PASS
node --test test frontend 47.5                      : PASS — 4/4
```

Validation complète exécutée localement par l'utilisateur avant intégration :

```text
git diff --check    : PASS — warnings LF -> CRLF uniquement
python -m pytest -q : PASS — suite backend complète à 100 %
pnpm typecheck      : PASS
pnpm test           : PASS — 86/86
git push origin main: PASS — e972fd9..d988de4
git status --short  : vide après push
```

Warnings connus, non bloquants et hors périmètre :

- dépréciations dans les dépendances de test FastAPI/Starlette ;
- warning Node `MODULE_TYPELESS_PACKAGE_JSON`.

Aucun test non exécuté n'est déclaré PASS.

---

## Décisions antérieures toujours actives

### Batch 47.4

**Intégré via `472f3ad`, clôturé documentairement via `e972fd9`.**

- cinq séries Analytics dans un scanner/cache/cursor/sémaphore uniques ;
- CVD analysé sur `cvd_change` ;
- Aggressor Differential signé ;
- MAD robuste ;
- aucun fallback ratio pour les séries signées ;
- 50 appels max/refresh, concurrence 4 ;
- aucune exécution PERP.

ADR-343 (« CVD/Aggressor sans autorité de ranking jusqu'au Batch 47.5 ») reste une décision historique décrivant l'état 47.4 et est désormais remplacée pour l'état courant par ADR-345..348.

### Batch 47.3

**Intégré via `12051a7`.** Funding relatif signé et Liquidation Volume agrégé réutilisent l'infrastructure Analytics canonique. Aucun split LONG/SHORT n'est inventé.

### Batch 47.2

**Intégré via `c09dd14`.** `PerpetualAnalyticsScanner` est l'infrastructure historique canonique. Open Interest est analysé relativement à sa propre baseline sans unité économique inventée.

### Batch 47.1

**Intégré via `842e6bd7`.** Snapshot Futures bulk canonique partagé ; OI/funding instantanés restent explicitement distincts des historiques.

### Baseline / Structure / liquidité

- ADR-330 — cible baseline adaptative 12 périodes, plancher 6 ;
- ADR-328 — anomalie robuste médiane + MAD ;
- ADR-329 — ratios historiques observables ;
- ADR-325 — policy/scan Structure séparés ;
- ADR-326 — BOS/CHOCH descriptifs et symétriques ;
- ADR-327 — filtres Structure fail-closed sur UNKNOWN ;
- ADR-323 — liquidité PERP via `volumeQuote` USD validé ;
- ADR-324 — couverture observée, jamais auto-corrigée ;
- ADR-321 — volume PERP USD via turnover quote Kraken ;
- ADR-322 — une shortlist PERP vide n'est pas réparée en abaissant le scoring.
