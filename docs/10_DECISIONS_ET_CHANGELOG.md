# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent disponibles dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les références nécessaires à la reprise.

## Principes actifs

Un seul Agent IA stratégique. Le Risk Engine déterministe conserve l'autorité finale. Aucune sortie LLM ne déclenche directement Broker/Kraken.

L'exécution courante est **PAPER uniquement** :

- SPOT exécutable sans short, levier ni marge ;
- PERPETUAL Kraken linéaire exécutable en LONG/SHORT sous contrôle Risk ;
- FUTURE daté non exécutable ;
- LIVE indisponible tant qu'un batch séparé ne l'active pas explicitement.

Le Market Attention Radar priorise **l'attention**. Depuis 49.2 il fournit l'univers candidat au même Agent ; depuis 49.3 il fournit aussi un contexte causal borné. Le Radar ne décide jamais BUY/SELL/HOLD et n'a aucune autorité Risk/Broker.

L'observabilité 49.4 et l'observabilité stratégique 50.2 sont strictement read-only : elles lisent les faits PAPER persistés et ne reviennent jamais dans le pipeline Agent/Risk/Broker.

Le Batch 50.1 fournit la mémoire stratégique structurée des positions ouvertes. Cette mémoire n'est ni une conversation LLM ni une chaîne de pensée cachée. Elle est causale, bornée, durable et remise au **même** appel stratégique.

## Référence courante

```text
HEAD GitHub vérifié 50.2      : ebb859c4ed83aada1c0bf3edf17ece85336849b9
Commit                         : feat: add persistent strategic thesis memory
Batch 49.4 intégré             : 2e552cb — feat: add paper trading observability
Batch 49.3 intégré             : d08cd31 — feat: expose causal radar analytics context to agent
Batch 49.2 intégré             : f0d4f94 — feat: feed radar shortlist into agent universe
Batch 49.1 intégré             : 3194fce — feat: activate perpetual paper trading
Batch 50.1 intégré             : ebb859c4 — feat: add persistent strategic thesis memory
Batch 50.2                     : patch livré — validation/intégration à faire
```

État intégré 50.1 communiqué à la clôture : `1217 passed, 2 warnings`, migration PostgreSQL `0008 strategic_thesis_state` appliquée, working tree propre après push.

---

## Changelog — 2026-10-05 — Batch 50.2 observabilité et cockpit des thèses stratégiques — patch livré

Base GitHub auditée : `ebb859c4ed83aada1c0bf3edf17ece85336849b9` (`feat: add persistent strategic thesis memory`).

### Audit confirmé

- `audit_cycles.strategic_thesis_state_payload` est déjà le snapshot canonique des thèses actives après cycle `COMPLETED` ;
- `decision_plan_payload.thesis_updates` conserve déjà les propositions/révisions de l'Agent ;
- `CycleAuditDetail` exposait les plans et trajectoires économiques, mais pas encore le snapshot de thèses ;
- le routeur `analytics.py` possède déjà la résolution de lineage `paper_run` et le parcours ordonné des cycles ;
- le cockpit Historique est le point opérateur canonique pour les faits Agent/Risk/PAPER ;
- aucune nouvelle table ni migration n'est nécessaire ;
- aucune dépendance Risk/Broker/LLM n'est nécessaire à la projection.

### Architecture retenue

**Option B — endpoint read-only dédié, implémenté dans le routeur Analytics existant.**

```text
audit_cycles.strategic_thesis_state_payload
+ decision_plan_payload.thesis_updates
+ paper_run lineage
+ états de portefeuille persistés
        ↓
StrategicThesisObservabilityReport
        ↓
GET /api/v1/strategic-theses
        ↓
cockpit Historique
```

Le choix d'un endpoint dédié évite de surcharger davantage `EconomicHistoryResponse` avec une responsabilité stratégique distincte, tout en réutilisant la même infrastructure de lecture et la même lineage PAPER.

### Projection active

La vue active est dérivée uniquement de faits persistés :

- dernier `strategic_thesis_state_payload` d'un cycle `COMPLETED` dans la lineage ;
- dernier portefeuille durable d'un cycle `COMPLETED` ;
- identité stricte `(symbol, market_type, side)` ;
- SPOT reste `LONG` uniquement ;
- une exposition ouverte sans thèse correspondante reste `UNAVAILABLE_LEGACY` ;
- aucune ancienne `rationale` n'est utilisée.

Une fermeture économique retire donc la thèse de la vue active si le snapshot du cycle ne la contient plus.

### Historique causal

Les révisions proviennent uniquement des `thesis_updates` persistées. Pour chaque révision, la projection consulte :

1. le snapshot durable précédent ;
2. le snapshot du **même cycle** s'il est `COMPLETED` ;
3. les faits Risk/fills de la décision alignée.

Aucun snapshot futur n'est utilisé pour requalifier une révision passée.

États d'audit exposés :

```text
ACTIVE_COMMITTED
RETIRED_COMMITTED
PROPOSED_NOT_ACTIVATED
FAILED_CYCLE
UNAVAILABLE_LEGACY
```

Ces états décrivent uniquement la relation entre proposition, cycle et mémoire durable. Ils ne constituent aucune règle de trading.

### Sémantique opérateur

- `HOLD` peut apparaître comme revue avec zéro fill ;
- un `Risk REJECT` de nouvelle entrée peut apparaître comme `PROPOSED_NOT_ACTIVATED`, jamais comme thèse active ;
- une réduction partielle conserve la thèse si le snapshot actif la conserve ;
- une fermeture complète retire la thèse active mais conserve la révision finale ;
- un cycle `FAILED` reste visible comme audit et ne remplace jamais l'état actif ;
- `INVALIDATED` et `COMPLETED` ne signifient jamais `SELL` ;
- `WEAKENING` n'impose aucune réduction ;
- Risk reste l'autorité finale sur l'exécution.

### API et cockpit

Nouvel endpoint :

```text
GET /api/v1/strategic-theses?paper_run_id=<uuid>&history_limit=100
```

Le contrat expose les positions/thèses actives, la lineage consultée, un `as_of`, l'historique borné et le nombre total de révisions.

Le cockpit Historique ajoute une section indépendante avec :

- loading / error / empty ;
- carte active par position ;
- SPOT/PERPETUAL et LONG/SHORT explicites ;
- statut, horizon, création, activation, dernière revue ;
- résumé de thèse, faits de support, conditions d'invalidation ;
- message legacy explicite ;
- historique causal des révisions ;
- rappel permanent de l'autorité finale du Risk Engine.

Le frontend ne reconstruit aucune thèse et ne recalcule aucune règle stratégique.

### Validation exécutée dans l'environnement ChatGPT

```text
python -m py_compile (fichiers Python du patch)                  : PASS
pytest ciblé projection 50.2 avec contrats minimaux              : PASS — 9 passed
node --test --experimental-strip-types strategic-theses.test.mjs : PASS — 3 passed
tsc ciblé src/lib/strategic-theses.ts                            : PASS
```

La suite complète du repository, `pnpm typecheck`, le test frontend complet et `git diff --check` restent à exécuter après extraction dans le checkout réel.

## ADR-377 — 50.2 utilise un endpoint dédié, sans nouvelle persistence

**ADOPTÉ — patch Batch 50.2, intégration à valider.**

Options comparées :

1. étendre `/api/v1/economic-history` : simple côté cockpit mais mélange économie/P&L et continuité stratégique ;
2. **endpoint `/api/v1/strategic-theses` dans le routeur Analytics existant : retenu** ;
3. détourner un endpoint d'audit générique : contrat moins explicite pour l'opérateur.

Aucune table d'historique supplémentaire n'est créée.

## ADR-378 — L'historique de thèse est causal et local au cycle

**ADOPTÉ — patch Batch 50.2, intégration à valider.**

Une révision est comparée uniquement au snapshot précédent et au snapshot du même cycle. Les états futurs ne peuvent pas rétroagir sur son classement historique.

## ADR-379 — Une proposition non activée reste distincte d'une thèse active

**ADOPTÉ — patch Batch 50.2, intégration à valider.**

Un `thesis_update` associé à une entrée rejetée ou non remplie peut rester visible comme audit `PROPOSED_NOT_ACTIVATED` lorsque les faits le déterminent sans ambiguïté. Il n'apparaît jamais dans les positions/thèses actives.

## ADR-380 — Le cockpit est une fenêtre read-only sur la mémoire 50.1

**ADOPTÉ — patch Batch 50.2, intégration à valider.**

Le frontend formate les données du backend et ne reconstitue ni thèse, ni règle BUY/SELL/HOLD, ni relation économique absente. `UNAVAILABLE_LEGACY` reste explicitement inconnu.

---

## Changelog — 2026-10-05 — Batch 50.1 mémoire de thèse stratégique — intégré

Commit intégré : `ebb859c4ed83aada1c0bf3edf17ece85336849b9` (`feat: add persistent strategic thesis memory`).

Validation intégrée communiquée : `1217 passed, 2 warnings`; migration PostgreSQL `0008_strategic_thesis_state` appliquée.

### Architecture 50.1

**Extension additive des faits de cycle + projection canonique.**

La colonne nullable `audit_cycles.strategic_thesis_state_payload` contient le snapshot des thèses encore actives après chaque cycle `COMPLETED`. Les révisions proposées par l'Agent sont conservées dans `decision_plan_payload` via `CycleDecisionPlan.thesis_updates`.

Contrat Agent du même appel :

```text
status
horizon
thesis_summary
supporting_facts[]
invalidation_conditions[]
review_summary
```

Statuts : `NEW / CONFIRMED / WEAKENING / INVALIDATED / COMPLETED`.

Règles de lifecycle :

- exposition inexistante -> entrée Agent -> Risk -> fill réel -> thèse active ;
- Risk REJECT ou absence de fill sur ouverture -> aucune thèse active ;
- position existante + HOLD/augmentation/réduction partielle -> thèse révisée/conservée ;
- fermeture complète -> suppression du snapshot actif, révision finale auditée ;
- legacy -> `UNAVAILABLE_LEGACY`, jamais reconstruit depuis `rationale` ;
- cycle `FAILED` -> aucun état stratégique promu ;
- recovery -> lineage explicite `resumed_from_paper_run_id`.

## ADR-371 — La source de vérité 50.1 est portée par les cycles

**ADOPTÉ — intégré via `ebb859c4`.** Snapshot canonique dans `audit_cycles` + révisions dans le plan. Pas de table parallèle.

## ADR-372 — La thèse est produite dans le même appel Agent

**ADOPTÉ — intégré via `ebb859c4`.** Aucun Agent mémoire et aucun second appel stratégique.

## ADR-373 — Une thèse proposée n'est active qu'après exposition économique réelle

**ADOPTÉ — intégré via `ebb859c4`.** REJECT/absence de fill sur ouverture n'active rien.

## ADR-374 — Legacy reste explicitement inconnu

**ADOPTÉ — intégré via `ebb859c4`.** `UNAVAILABLE_LEGACY`, sans reconstruction des rationales.

## ADR-375 — INVALIDATED/COMPLETED n'ont aucune sémantique d'ordre automatique

**ADOPTÉ — intégré via `ebb859c4`.** La sortie stratégique reste BUY/SELL/HOLD, ensuite contrôlée par Risk.

## ADR-376 — Les cycles FAILED ne promeuvent jamais la mémoire stratégique

**ADOPTÉ — intégré via `ebb859c4`.** Seuls les cycles `COMPLETED` peuvent remplacer le snapshot actif.

---

## Changelog — Batch 49.4 observabilité décisions/performance PAPER — intégré

Commit : `2e552cbaf1b8ffcae9244c1fb472f1ee8fb0f193`.

Décisions actives :

- `PaperAnalyticsReport` reste la source canonique de l'equity/P&L/coûts/drawdown/exposition ;
- `PaperObservabilityReport` est une projection opérateur read-only ;
- décisions, intents, fills et trades restent des compteurs distincts ;
- identité `(symbol, market_type)` ;
- P&L brut/net SPOT/PERP reste `null` sans attribution causale exacte ;
- aucune rétroaction sur Agent/Risk/Broker.

Validation intégrée : `1195 passed, 2 warnings`, frontend typecheck/test PASS.

ADR actifs : `ADR-366` à `ADR-370`.

---

## Changelog — Batch 49.3 contexte Radar / Analytics causal — intégré

Commit : `d08cd31e6a795a8beb09530c2bc9a3f32f94fe35`.

`RadarAnalyticsStrategicContext` reste strict, borné et causal ; même snapshot que Discovery ; score 47.5 descriptif ; données dégradées explicites ; aucun second appel Agent.

ADR actifs : `ADR-361` à `ADR-365`.

---

## Changelog — Batch 49.2 Radar shortlist vers univers Agent — intégré

Commit : `f0d4f94d2ed9b8f02eadb7ea021aa3fc817c973b`.

`MarketDiscoveryCoordinator` reste la frontière canonique. Les Campaigns dynamiques utilisent `RADAR_SHORTLIST`, revalident catalogue/scope/whitelist, échouent fermées pour les nouvelles ouvertures si Radar indisponible et préservent la gestion des positions existantes.

ADR actifs : `ADR-357` à `ADR-360`.

---

## Changelog — Batch 49.1 PERPETUAL PAPER — intégré

Commit : `3194fce620f5e31672c6b52ef8986daddeea3a25`.

PAPER officiel SPOT + PERPETUAL linéaire ; `FUTURE` daté non exécutable ; levier/marge/exposition contrôlés par Risk ; `PaperBroker` et ledger gèrent `DerivativePosition`, funding et P&L ; aucun retournement direct contournant `reduce_only`.

ADR actifs : `ADR-353` à `ADR-356`.

---

## Décisions Analytics 47.5 / observabilité 48 toujours actives

- score 47.5 entier `0..4` ;
- quatre familles : `OPEN_INTEREST`, `FUNDING`, `LIQUIDATION_VOLUME`, `ORDER_FLOW` ;
- CVD + Aggressor = une seule composante order-flow ;
- disponibilité seule = 0 ;
- données absentes/dégradées = 0 sans malus ;
- signes positifs/négatifs symétriques pour l'attention ;
- `interest_level` et `candidate_limit` inchangés ;
- aucune création de candidat par Analytics ;
- observabilité 48 calculée à la demande ;
- `rank_change=0` distinct de l'absence de donnée ;
- aucune calibration post-hoc.

Références : `docs/47_5_MULTI_ANALYTICS_RANKING.md`, `docs/48_OBSERVABILITE_RANKING_ANALYTICS.md` et historique Git.
