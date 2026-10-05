# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les éléments nécessaires à la reprise.

## Principes actifs

Un seul Agent stratégique, Risk Engine autorité finale, aucune sortie LLM directe vers Broker/Kraken, exécution SPOT sans vente d'actif non détenu, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Le Market Attention Radar reste observationnel : il peut prioriser **l'attention**, mais ne prend aucune décision BUY/SELL/HOLD et n'a aucune autorité d'exécution.

## Référence courante

```text
HEAD GitHub réel audité : e972fd9112363b268a53658fe5ce88facbfa7dd7
Clôture Batch 47.4      : e972fd9 — docs: mark batch 47.4 integrated
Commit fonctionnel 47.4: 472f3ad — feat: add CVD and aggressor analytics
Batch 45               : intégré via 45d41b7
Batch 46 / 46.1        : intégré via b219365
Batch 47.1             : intégré via 842e6bd7
Batch 47.2             : intégré via c09dd14
Batch 47.3             : intégré via 12051a7
Batch 47.4             : intégré via 472f3ad
Batch 47.5             : patch proposé, non intégré
```

## Changelog — 2026-10-05 — Batch 47.5 influence multi-analytics sur le ranking — patch proposé

Base auditée : GitHub `main` au HEAD `e972fd9112363b268a53658fe5ce88facbfa7dd7` (`docs: mark batch 47.4 integrated`). Aucun changement fonctionnel n'existe sur `main` après `472f3ad`; `e972fd9` est une clôture documentaire.

Audit :

- **confirmé** : `interest_level` est calculé dans `market/attention.py` avant Analytics ;
- **confirmé** : `_deterministic_radar_sort_key()` place `interest_level` en premier ;
- **confirmé** : la microstructure conserve le niveau d'intérêt comme premier axe dans `_v3_sort_key()` ;
- **confirmé** : la sélection Structure finale place intérêt puis Structure confirmée avant le reste de la clé ;
- **confirmé** : `candidate_limit` vient de `MarketAttentionPolicy` (`10` par défaut, borné `1..30`) et est appliqué avant l'enrichissement Analytics ;
- **confirmé** : le scan Analytics est exécuté avant Structure pour alimenter le cache mais, en 47.4, l'enrichissement Analytics intervient après la shortlist finale ;
- **confirmé** : les cinq séries partagent exactement le même scanner/cache/cursor/sémaphore ;
- **confirmé** : CVD et Aggressor Differential mesurent deux vues du même domaine order-flow agressif et ne doivent pas compter comme deux preuves indépendantes ;
- **confirmé** : OI/Funding/Liquidations/CVD/Aggressor exposent déjà les caractéristiques nécessaires ; aucune nouvelle statistique ou seuil n'est requis ;
- **confirmé** : CVD/Aggressor avec MAD nul ne fabriquent pas de score extrême et restent `UNAVAILABLE` ;
- **obsolète** : les documents de reprise citaient `472f3ad` comme HEAD audité alors que le HEAD réel est `e972fd9` ;
- **manquant avant patch** : politique multi-analytics plafonnée, déduplication order-flow, diagnostics API/cockpit et tests de non-création de candidat ;
- **à décider** : autorité exacte du score Analytics, place dans la clé et traitement des scopes mixtes.

Familles comparées :

1. **aucun impact** : très sûr mais laisse les cinq séries uniquement descriptives ;
2. **tie-break strict** : influence trop souvent inerte à cause de la clé canonique déjà très discriminante ;
3. **bonus/malus sur le score existant** : rejeté, car risque de modifier `interest_level` et l'admission ;
4. **score multi-analytics séparé et plafonné** : **retenu**.

Patch 47.5 :

- ajout d'un `analytics_ranking` optionnel au candidat v6, sans nouvelle version du protocole ;
- score entier `0..4`, un point maximum par famille `OPEN_INTEREST`, `FUNDING`, `LIQUIDATION_VOLUME`, `ORDER_FLOW` ;
- disponibilité seule = 0 ; seules les caractéristiques déjà émises par les statistiques 47.2–47.4 peuvent contribuer ;
- anomalies signées positives/négatives traitées symétriquement comme **attention inhabituelle**, jamais comme direction BUY/SELL ;
- CVD + Aggressor concordants = `+1` total et `order_flow_deduplicated=true` ;
- CVD + Aggressor opposés = `0` pour l'order-flow et `order_flow_conflict=true` ;
- séries absentes, `PARTIAL`, `INSUFFICIENT_HISTORY`, `STALE`, `TECHNICAL_ERROR` ou `NOT_APPLICABLE` = 0 sans pénalité ;
- aucune modification des statistiques, seuils ou policy réseau 47.2–47.4 ;
- aucun nouveau scanner/cache/cursor ; budget 50 appels max/refresh inchangé ;
- aucun changement de `interest_level`, `candidate_limit`, filtres ou population de candidats ;
- score injecté uniquement après intérêt et événement Structure confirmé, avant les critères micro/OHLCV restants ;
- scope `SPOT` inchangé ;
- scope `PERPETUAL` : réordonnancement des PERP déjà présents ;
- scope `ALL` : slots SPOT figés, réordonnancement uniquement entre slots PERP ;
- cockpit : score, composantes, séries utilisées/non retenues, déduplication/conflit, rang avant/après et variation réelle ;
- compatibilité payload legacy : `analytics_ranking` optionnel ;
- aucune dépendance Agent / Risk Engine / Broker, aucune exécution PERP.

### ADR-345 — Le ranking Analytics utilise un score séparé plafonné à quatre familles

**PROPOSÉ — Batch 47.5, non intégré.**

Le score d'attention Analytics est séparé de `interest_level`. Il vaut au maximum 4 car il existe quatre familles sémantiques indépendantes : OI, Funding, Liquidations et Order Flow. La magnitude brute des scores statistiques n'est pas additionnée ; une famille active vaut au plus +1.

### ADR-346 — CVD et Aggressor Differential forment une seule composante order-flow

**PROPOSÉ — Batch 47.5, non intégré.**

Les deux métriques ne sont pas considérées comme deux preuves indépendantes. Concordance = +1 au total ; opposition simultanée = 0 avec diagnostic de conflit. Cette règle supprime la double pondération mécanique.

### ADR-347 — Analytics ne peut ni créer un candidat ni modifier `interest_level`

**PROPOSÉ — Batch 47.5, non intégré.**

Le score n'est appliqué qu'à la shortlist finale déjà retenue par le pipeline canonique. La hiérarchie devient intérêt → Structure confirmée → Analytics → reste de la clé. En `ALL`, SPOT garde ses positions et seuls les PERP se réordonnent entre eux.

### ADR-348 — Une série Analytics indisponible est neutre

**PROPOSÉ — Batch 47.5, non intégré.**

Seul `AVAILABLE` permet l'utilisation d'une caractéristique. Données manquantes, partielles, insuffisantes, périmées ou en erreur contribuent 0 sans malus. Une panne technique ne doit jamais être interprétée comme une information de marché.

### Validation du patch 47.5

Validations réellement exécutées dans l’environnement ChatGPT :

```text
python -m py_compile production + test backend 47.5        : PASS
harnais backend isolé logique ranking 47.5                 : PASS — 15/15 assertions
tsc strict ciblé frontend/src/lib/market-attention.ts      : PASS
tsc syntaxe TS/TSX (--noCheck) lib + cockpit               : PASS
node --test market-attention-batch47_5.test.mjs            : PASS — 4/4
```

Le harnais backend charge le module de production 47.5 avec des dépendances minimales simulées afin de tester score, symétrie, plafond, déduplication/conflit CVD-Aggressor, statuts dégradés, ordre du sort key, scopes SPOT/ALL et invariants d’absence Agent/Risk/Broker. Il ne remplace pas `pytest` sur le checkout complet.

Non exécuté dans l’environnement ChatGPT faute de checkout réseau complet et de `pnpm` disponible : `python -m pytest -q`, `pnpm typecheck`, `pnpm test`, `git diff --check`. Ces validations restent obligatoires localement avant intégration.

---

## Historique intégré antérieur

Les décisions ci-dessous restent intégrées et actives sauf lorsqu'une décision 47.5 proposée les remplace explicitement après validation/intégration.

## Batch 47.4 — CVD + Aggressor Differential — intégré

**Intégré via `472f3adca1d19822289af47b52b03afab3cda0fb`, clôturé documentairement via `e972fd9`.**

- un seul `PerpetualAnalyticsScanner`, `_cache`, `_perpetual_analytics_cursor` et sémaphore global ;
- CVD : `timestamp[] + cvd[]` alignés, side volumes seulement si les deux tableaux sont complets ;
- Aggressor Differential : scalaire signé taker buy − taker sell ;
- CVD analysé sur `cvd_change`, Aggressor directement ;
- médiane/MAD robuste ; aucun fallback ratio pour ces séries signées ;
- seuils descriptifs ±2.5 ;
- cinq séries × 10 marchés = 50 appels Analytics max/refresh, concurrence 4 ;
- contrat API `market-attention-radar-v6` conservé ;
- aucune exécution PERP.

Validation intégrée observée : backend local utilisateur complet PASS à 100 %, frontend typecheck PASS, tests frontend 82/82 PASS, `git diff --check` PASS hors avertissements LF/CRLF, smokes CVD/Aggressor PASS.

### ADR-344 — CVD utilise timestamp + cvd comme contrat historique obligatoire ; side volumes fail-soft

**ADOPTÉ — Batch 47.4 intégré via `472f3ad`.** Side volumes CVD ne sont exposés que si les deux tableaux sont intégralement alignés ; aucune correspondance par index n'est inventée.

### ADR-340 — CVD et Aggressor Differential réutilisent la rotation/cache Analytics unique

**ADOPTÉ — Batch 47.4 intégré via `472f3ad`.** OI, Funding, Liquidation Volume, CVD et Aggressor Differential utilisent exactement la même infrastructure Analytics.

### ADR-341 — L'anomalie CVD porte sur la variation et non sur le niveau cumulatif

**ADOPTÉ — Batch 47.4 intégré via `472f3ad`.** Le niveau `current_cvd` reste observable mais la statistique porte sur `cvd_change`.

### ADR-342 — Les séries order-flow signées utilisent MAD sans fallback ratio

**ADOPTÉ — Batch 47.4 intégré via `472f3ad`.** Lorsque MAD=0, la méthode devient `UNAVAILABLE`, sans score extrême artificiel.

### ADR-343 — CVD et Aggressor restent descriptifs sans autorité de ranking jusqu'au Batch 47.5

**ADOPTÉ — historique 47.4.** Cette règle décrit l'état intégré 47.4 ; le patch 47.5 propose de la remplacer par ADR-345..348 après validation.

## Batch 47.3 — Funding historique + Liquidation Volume — intégré

**Intégré via `12051a7`.** Funding historique et Liquidation Volume réutilisent le scanner Analytics unique. Funding conserve séparément `rate`, `relativeRate` et la prédiction ticker ; Liquidation Volume reste agrégé et non directionnel.

### ADR-337 — OI, Funding et Liquidation Volume partagent une seule rotation/cache Analytics

**ADOPTÉ — Batch 47.3.** Un même marché sélectionné par la rotation peut déclencher les trois séries sous un sémaphore global.

### ADR-338 — Le Funding historique conserve séparément rate, relativeRate et prédiction ticker

**ADOPTÉ — Batch 47.3.** La statistique adaptative porte sur `relativeRate`; aucun fallback ratio n'est utilisé lorsque MAD=0 sur cette série signée.

### ADR-339 — Liquidation Volume reste agrégé, non directionnel et sans autorité de ranking dans 47.3

**ADOPTÉ — historique 47.3.** Aucun split LONG/SHORT n'est inventé.

## Batch 47.2 — historique Open Interest — intégré

**Intégré via `c09dd14`.** Parser OHLC strict, `close` finalisé comme valeur représentative, `more=true` rejeté, rotation/cache Analytics causal et séparé de l'OHLCV/Structure, médiane/MAD Batch 46, aucune conversion USD inventée.

### ADR-333 — Les Analytics Futures historiques utilisent une rotation/cache séparée

**ADOPTÉ — Batch 47.2.** `PerpetualAnalyticsScanner` est le composant canonique à étendre.

### ADR-334 — L'Open Interest est analysé relativement à son propre historique sans unité économique inventée

**ADOPTÉ — Batch 47.2.** `openInterest` reste une valeur Kraken brute.

### ADR-335 — La causalité Analytics applique un délai conservateur d'un intervalle

**ADOPTÉ — Batch 47.2.** Un point n'est consommé qu'après `timestamp + interval <= as_of`.

### ADR-336 — L'OI historique n'a pas d'autorité de ranking dans 47.2

**ADOPTÉ — historique 47.2.** Toute influence multi-analytics est explicitement réservée à une décision ultérieure.

## Batch 47.1 — fondations Futures ticker — intégré

**Intégré via `842e6bd7`.** Un snapshot bulk `/tickers` partagé alimente volume PERP, liquidité PERP et contexte instantané Futures.

### ADR-331 — Le Radar réutilise un snapshot Futures bulk canonique

**ADOPTÉ — Batch 47.1.** Aucun second client Kraken Futures n'est créé pour le contexte ticker.

### ADR-332 — OI/funding instantanés restent descriptifs et leurs unités restent explicites

**ADOPTÉ — Batch 47.1.** Aucun suffixe économique ni pourcentage n'est inventé pour des valeurs dont l'unité n'est pas démontrée.

## Décisions antérieures toujours actives

- **ADR-330 — ADOPTÉ via `b219365`** : cible baseline adaptative 12 périodes, plancher 6.
- **ADR-328 — ADOPTÉ via `b219365`** : anomalie robuste = médiane + MAD normalisé.
- **ADR-329 — ADOPTÉ via `b219365`** : ratios historiques observables, contrat v6 additif.
- **ADR-325 — ADOPTÉ via `45d41b7`** : policy Structure et scan Structure séparés.
- **ADR-326 — ADOPTÉ via `45d41b7`** : événements BOS/CHOCH descriptifs, symétriques.
- **ADR-327 — ADOPTÉ via `45d41b7`** : filtres Structure fail-closed sur UNKNOWN.
- **ADR-323 — ADOPTÉ via `c262d54`** : liquidité PERP via `volumeQuote` USD validé.
- **ADR-324 — ADOPTÉ via `c262d54`** : couverture observée, pas auto-corrigée.
- **ADR-321 — ADOPTÉ via `25dcb5c`** : volume PERP USD via turnover quote public Kraken.
- **ADR-322 — ADOPTÉ via `25dcb5c`** : une shortlist PERP vide n'est pas réparée en abaissant le scoring.
