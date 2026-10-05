# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent disponibles dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les références nécessaires à la reprise.

## Principes actifs

Un seul Agent IA stratégique. Le Risk Engine déterministe conserve l'autorité finale. Aucune sortie LLM ne déclenche directement Broker/Kraken.

L'exécution courante est **PAPER uniquement** :

- SPOT exécutable sans short, levier ni marge ;
- PERPETUAL Kraken linéaire exécutable en LONG/SHORT sous contrôle Risk ;
- FUTURE daté non exécutable ;
- LIVE indisponible tant qu'un batch séparé ne l'active pas explicitement.

Le Market Attention Radar priorise **l'attention**. Depuis le Batch 49.2 intégré, il fournit l'univers candidat au même Agent stratégique. Le Batch 49.3 ajoute une projection de faits Radar/Analytics causaux et bornés pour cet univers. Le Radar ne décide jamais BUY/SELL/HOLD et ne possède aucune autorité Risk ou Broker.

L'observabilité 49.4 est strictement read-only : elle mesure les faits PAPER persistés et ne revient jamais dans le pipeline Agent/Risk/Broker.

Le Batch 50.1 ajoute une mémoire stratégique structurée des positions ouvertes. Cette mémoire n'est ni une conversation LLM, ni une chaîne de pensée cachée. Elle est causale, bornée, durable et remise au **même** appel stratégique.

## Référence courante

```text
HEAD GitHub de base 50.1     : 8a0054091c39079dfc5d2c5a9504470b2fbf9493
Clôture documentaire 49.4    : 8a005409 — docs: close batch 49.4 integration
Batch 49.4 intégré            : 2e552cb — feat: add paper trading observability
Batch 49.3 intégré            : d08cd31 — feat: expose causal radar analytics context to agent
Batch 49.2 intégré            : f0d4f94 — feat: feed radar shortlist into agent universe
Batch 49.1 intégré            : 3194fce — feat: activate perpetual paper trading
Batch 50.1                    : patch livré — validation/intégration à faire
```

## Changelog — 2026-10-05 — Batch 50.1 mémoire de thèse stratégique — patch livré

Base GitHub auditée : `8a0054091c39079dfc5d2c5a9504470b2fbf9493` (`docs: close batch 49.4 integration`).

### Audit confirmé

- `CycleDecisionPlanInput` contient déjà portefeuille, marchés, agressivité, coûts, multi-timeframes et contexte Radar/Analytics ;
- `CycleDecisionPlan` est produit par un seul appel `generate_decision_plan(...)` ;
- les décorateurs MTF et Radar enrichissent l'entrée puis délèguent une seule fois ;
- `AuditedTradingCycleRunner` restaure le ledger lors d'un cycle `FAILED` puis persiste l'audit ;
- `SqlAlchemyCycleAuditRepository.record(...)` commit déjà atomiquement le cycle et `paper_runs.current_portfolio_payload` ;
- le recovery PAPER relie explicitement les runs via `resumed_from_paper_run_id` ;
- les anciennes `rationale` ne constituent pas une source fiable de thèse historique.

### Architecture retenue

**Option C — extension additive des faits de cycle + projection canonique.**

La nouvelle colonne nullable `audit_cycles.strategic_thesis_state_payload` contient le snapshot des thèses encore actives après chaque cycle `COMPLETED`. Les révisions proposées par l'Agent sont conservées dans `decision_plan_payload` via `CycleDecisionPlan.thesis_updates`.

Ce choix évite une table métier parallèle tout en conservant :

- lecture rapide de l'état actif ;
- historique immuable des revues ;
- atomicité avec le cycle/portefeuille ;
- recovery déterministe par lineage ;
- compatibilité des anciens cycles avec colonne `NULL`.

### Contrat Agent 50.1

Le schéma Structured Outputs du **même appel** contient, par décision, `thesis_update` :

```text
status
horizon
thesis_summary
supporting_facts[]
invalidation_conditions[]
review_summary
```

Statuts :

```text
NEW / CONFIRMED / WEAKENING / INVALIDATED / COMPLETED
```

`BUY`/`SELL` requièrent une révision structurée. Un `HOLD` sur une position ouverte requiert une revue structurée ; un `HOLD` sans position peut laisser `thesis_update=null`.

`INVALIDATED` et `COMPLETED` sont descriptifs. Ils ne sont jamais traduits en `SELL` automatique.

### Activation et lifecycle

- exposition inexistante -> entrée Agent proposée -> Risk -> fill réel -> thèse active ;
- Risk REJECT ou intent sans fill et aucune exposition économique -> aucune thèse active ;
- position existante + HOLD/augmentation/réduction partielle -> thèse révisée et conservée si l'exposition reste du même côté ;
- fermeture complète -> suppression du snapshot actif ; la révision finale reste dans l'audit du plan ;
- position historique sans mémoire -> `UNAVAILABLE_LEGACY` ; aucune ancienne `rationale` n'est transformée en thèse fictive ;
- adoption legacy éventuelle -> nouvelle thèse de gestion créée à partir du cycle courant uniquement ;
- cycle `FAILED` -> aucun nouvel état stratégique promu.

### Recovery et causalité

Le contexte du prochain cycle lit le dernier cycle `COMPLETED` du run courant. Si aucun n'existe, il remonte exclusivement `resumed_from_paper_run_id` jusqu'au premier snapshot disponible ou à un état legacy.

Les timestamps d'une thèse/revue doivent être `<=` à la frontière du contexte puis `<= CycleDecisionPlanInput.created_at`. `BTC/USD SPOT`, `BTC/USD PERPETUAL LONG` et `BTC/USD PERPETUAL SHORT` restent des identités distinctes.

### Invariants préservés

- aucun second Agent ;
- aucun second appel stratégique ;
- aucun changement Risk/Broker ;
- aucune exécution directe depuis la thèse ;
- aucune règle déterministe stop-loss/take-profit/temps/P&L/score ;
- aucun look-ahead ;
- aucun hidden chain-of-thought persisté ;
- PAPER uniquement ;
- frontend non modifié dans 50.1 ;
- Prompt Cache OpenAI hors périmètre.

## ADR-371 — La source de vérité 50.1 est une projection additive portée par les cycles

**ADOPTÉ — patch Batch 50.1, intégration à valider.**

Options comparées :

1. table dédiée de thèses : contrat clair mais nouvelle responsabilité persistante parallèle ;
2. reconstruction intégrale depuis les rationales/audits : rejetée, implicite et incapable de distinguer proprement état actif/historique ;
3. **snapshot canonique additif dans `audit_cycles` + revues dans le plan : retenu**.

Motifs : atomicité avec le cycle existant, recovery simple, compatibilité legacy et absence de second store métier.

## ADR-372 — La thèse est produite dans le même appel Agent

**ADOPTÉ — patch Batch 50.1, intégration à valider.**

`StrategicThesisContextDecisionProvider` lit le contexte durable, l'attache à `CycleDecisionPlanInput`, revalide puis délègue une seule fois. Il n'existe aucun `Agent trading -> Agent mémoire`.

## ADR-373 — Une thèse proposée n'est active qu'après exposition économique réelle

**ADOPTÉ — patch Batch 50.1, intégration à valider.**

Un REJECT Risk ou une absence de fill sur une ouverture n'active rien. L'activation est corrélée au portefeuille effectivement engagé après exécution.

## ADR-374 — Legacy reste explicitement inconnu

**ADOPTÉ — patch Batch 50.1, intégration à valider.**

Une position ouverte antérieure à 50.1 sans snapshot correspondant est exposée comme `UNAVAILABLE_LEGACY`. Aucune ancienne rationale n'est utilisée pour fabriquer une motivation historique.

## ADR-375 — INVALIDATED/COMPLETED n'ont aucune sémantique d'ordre automatique

**ADOPTÉ — patch Batch 50.1, intégration à valider.**

Les statuts sont des descriptions de la thèse. La sortie stratégique reste `BUY / SELL / HOLD`, ensuite contrôlée par Risk.

## ADR-376 — Les cycles FAILED ne promeuvent jamais la mémoire stratégique

**ADOPTÉ — patch Batch 50.1, intégration à valider.**

La projection active est écrite uniquement sur un cycle `COMPLETED`. Les cycles `FAILED` conservent leur audit mais ne remplacent pas le dernier snapshot durable.

---

## Changelog — 2026-10-05 — Batch 49.4 observabilité décisions/performance PAPER — intégré

Base GitHub auditée au démarrage : `e7d605aa2b6393516c0ccd391cd4d11193c18671` (`docs: close batch 49.3 integration`).

Commit intégré : `2e552cbaf1b8ffcae9244c1fb472f1ee8fb0f193` (`feat: add paper trading observability`).

### Audit confirmé

- `PaperAnalyticsReport` est la source canonique de l'equity, du P&L brut/net, des coûts d'exécution, du funding, du drawdown et de l'exposition globale ;
- `EconomicHistoryReport` réutilise ces métriques et ajoute P&L réalisé/latent, opérations, turnover, coûts, cadence et effets économiques ;
- `CycleAuditDetail.decision_results` conserve déjà les trajectoires multi-décisions ;
- `CycleAuditSummary` expose déjà les compteurs BUY/SELL/HOLD, ALLOW/MODIFY/REJECT, intents/fills ;
- le cockpit Historique consomme déjà `/api/v1/economic-history` ;
- aucune nouvelle persistence n'est nécessaire.

### Architecture intégrée 49.4

Une projection dédiée `PaperObservabilityReport` est ajoutée au-dessus de l'historique économique canonique et des audits persistés :

```text
PaperAnalyticsReport
-> EconomicHistoryReport
-> PaperObservabilityReport
```

La projection est attachée additivement à `EconomicHistoryResponse.observability`. Aucun nouvel endpoint n'est créé.

### Métriques intégrées

- breakdowns `TOTAL`, `SPOT`, `PERPETUAL` ;
- funnel Agent -> Risk -> exécution ;
- décisions avec/sans fill ;
- fills et trades économiques distincts ;
- ventilation stricte par `(symbol, market_type)` ;
- notionnel, frais, spread, slippage, funding, coûts, P&L réalisé ;
- exposition et P&L latent terminaux lorsque la persistence permet une attribution exacte ;
- liste explicite des métriques indisponibles.

### Honnêteté économique

Le P&L brut/net global est copié du rapport canonique et ne change pas.

Le Batch 49.4 **n'attribue pas** `gross_pnl` ou `net_pnl` entre SPOT et PERPETUAL car la persistence actuelle ne fournit pas une décomposition historique exacte des variations d'equity par type de marché. Ces champs restent `null` pour les breakdowns SPOT/PERP.

Le funding conserve la convention existante : négatif = coût, positif = bénéfice. La ventilation PERPETUAL réutilise le funding canonique global ; la ventilation par marché combine funding réalisé des fills et `cumulative_funding` terminal lorsque cette attribution est disponible. Un funding SPOT non nul est rejeté comme incohérence de données.

### UI intégrée

Le cockpit Historique ajoute :

- cartes TOTAL/SPOT/PERP ;
- funnel Agent/Risk/exécution ;
- table par identité `(symbol, market_type)` ;
- indication des métriques volontairement non attribuées.

Le frontend ne recalcule aucun P&L ni coût.

### Validation intégrée

```text
backend python -m pytest -q : PASS — 1195 passed, 2 warnings
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 89/89
git diff --check            : PASS — avertissements LF/CRLF uniquement
git status --short          : PASS — working tree propre après push
push GitHub main            : PASS — 2e552cb
```

Les warnings Node `MODULE_TYPELESS_PACKAGE_JSON` restent non bloquants.

## ADR-366 — L'observabilité 49.4 est une projection dédiée au-dessus des sources canoniques

**ADOPTÉ — Batch 49.4 intégré via `2e552cb`.**

Options comparées :

1. étendre directement `PaperAnalyticsReport` : rejeté, mélange du moteur économique canonique et de la projection opérateur ;
2. charger toutes les nouvelles vues dans `EconomicHistorySummary` : possible mais contrat trop chargé ;
3. **projection `PaperObservabilityReport` dédiée, attachée à Economic History : retenue** ;
4. nouvelle persistence/pipeline : rejeté, inutile.

Motifs : aucune duplication du ledger, aucune migration, source de vérité inchangée, contrat additif et testable.

## ADR-367 — Le P&L brut/net par type reste indisponible sans attribution causale exacte

**ADOPTÉ — Batch 49.4 intégré via `2e552cb`.**

`TOTAL.gross_pnl` et `TOTAL.net_pnl` restent canoniques. `SPOT` et `PERPETUAL` exposent `null` pour ces deux champs tant qu'une attribution exacte n'est pas disponible dans les faits durables.

Aucune répartition résiduelle, proportionnelle au notionnel, aux coûts ou à l'exposition n'est autorisée.

## ADR-368 — Décisions, intents, fills et trades sont des compteurs distincts

**ADOPTÉ — Batch 49.4 intégré via `2e552cb`.**

Un HOLD ou un REJECT reste une décision. Un intent sans fill n'est pas un trade. Plusieurs fills d'un intent restent distincts du nombre d'opérations économiques. Les cycles FAILED ne contribuent pas aux fills économiquement engagés.

## ADR-369 — L'identité d'observabilité est `(symbol, market_type)`

**ADOPTÉ — Batch 49.4 intégré via `2e552cb`.**

`BTC/USD SPOT` et `BTC/USD PERPETUAL` ne sont jamais fusionnés dans une même ligne de marché.

## ADR-370 — L'observabilité 49.4 ne peut pas modifier la stratégie

**ADOPTÉ — Batch 49.4 intégré via `2e552cb`.**

Les résultats 49.4 ne modifient aucun poids Radar/Analytics, aucune décision Agent, aucun paramètre Risk et aucun ordre Broker. Une adaptation future éventuelle devra faire l'objet d'une décision et d'un batch séparés.

---

## Changelog — 2026-10-05 — Batch 49.3 contexte Radar / Analytics causal — intégré

Base GitHub auditée au démarrage : `f0d4f94d2ed9b8f02eadb7ea021aa3fc817c973b` (`feat: feed radar shortlist into agent universe`).

Commit intégré : `d08cd31e6a795a8beb09530c2bc9a3f32f94fe35` (`feat: expose causal radar analytics context to agent`).

Décision active : `RadarAnalyticsStrategicContext` est un contrat dédié strict, borné et causal ; le snapshot doit correspondre exactement à celui de Discovery ; le score 47.5 reste descriptif ; les données dégradées restent explicitement dégradées ; `FrozenRadarContextDecisionProvider` ne crée aucun second appel Agent.

## ADR-361 — Le contexte 49.3 utilise un contrat dédié référencé par `CycleDecisionPlanInput`

**ADOPTÉ — Batch 49.3 intégré via `d08cd31`.**

## ADR-362 — Le contexte doit être figé sur le snapshot exact de Discovery

**ADOPTÉ — Batch 49.3 intégré via `d08cd31`.**

## ADR-363 — Le score 47.5 reste descriptif et inchangé

**ADOPTÉ — Batch 49.3 intégré via `d08cd31`.**

## ADR-364 — Les données dégradées restent des données dégradées

**ADOPTÉ — Batch 49.3 intégré via `d08cd31`.**

## ADR-365 — Un seul appel stratégique est conservé

**ADOPTÉ — Batch 49.3 intégré via `d08cd31`.**

---

## Changelog — Batch 49.2 Radar shortlist vers univers Agent — intégré

Commit intégré : `f0d4f94d2ed9b8f02eadb7ea021aa3fc817c973b` (`feat: feed radar shortlist into agent universe`).

Décisions actives :

- `MarketDiscoveryCoordinator` accepte `LEGACY_AGENT` ou `RADAR_SHORTLIST` ;
- les Campaigns dynamiques de production utilisent `RADAR_SHORTLIST` ;
- la frontière Discovery reste identité-only `{symbol, market_type}` ;
- chaque candidat est revalidé contre le catalogue public Kraken, le scope Campaign et la whitelist Risk éventuelle ;
- `BTC/USD SPOT` et `BTC/USD PERPETUAL` restent distincts ;
- nouvelles ouvertures fail-closed si Radar indisponible/stale/vide/sans candidat exécutable ;
- positions ouvertes toujours gérables en MANAGEMENT ;
- bootstrap non utilisé comme faux signal ;
- aucun chemin direct Radar -> Risk/Broker.

### ADR-357 — Radar derrière la frontière canonique Market Discovery

**ADOPTÉ — Batch 49.2 intégré via `f0d4f94`.**

### ADR-358 — La frontière d'univers 49.2 reste identité-only

**ADOPTÉ — Batch 49.2 intégré via `f0d4f94`.**

### ADR-359 — Panne Radar fail-closed pour les nouvelles ouvertures

**ADOPTÉ — Batch 49.2 intégré via `f0d4f94`.**

### ADR-360 — Revalidation de l'exécutabilité Kraken/Campaign

**ADOPTÉ — Batch 49.2 intégré via `f0d4f94`.**

---

## Changelog — Batch 49.1 activation officielle PERPETUAL PAPER — intégré

Commit intégré : `3194fce620f5e31672c6b52ef8986daddeea3a25` (`feat: activate perpetual paper trading`).

Décisions actives :

- PAPER officiel SPOT + PERPETUAL linéaire ;
- `FUTURE` daté non exécutable ;
- BUY/SELL expriment LONG/SHORT sur PERPETUAL, mais le LLM ne choisit pas le levier ;
- Risk contrôle quantité, levier, marge, exposition, liquidation et retournement ;
- `PaperBroker` et le ledger gèrent `DerivativePosition`, funding et P&L ;
- un ordre opposé surdimensionné ferme/réduit avant toute ouverture opposée ultérieure.

### ADR-353 — Univers PAPER SPOT + PERPETUAL linéaire

**ADOPTÉ — Batch 49.1 intégré via `3194fce`.**

### ADR-354 — Aucun retournement direct dans un seul `ExecutionIntent`

**ADOPTÉ — Batch 49.1 intégré via `3194fce`.**

### ADR-355 — Le levier reste entièrement déterministe

**ADOPTÉ — Batch 49.1 intégré via `3194fce`.**

### ADR-356 — Radar et exécution restent séparés

**ADOPTÉ — Batch 49.1 intégré via `3194fce`.**

---

## Décisions Analytics 47.5 / observabilité 48 toujours actives

- score 47.5 entier `0..4` ;
- quatre familles : `OPEN_INTEREST`, `FUNDING`, `LIQUIDATION_VOLUME`, `ORDER_FLOW` ;
- CVD + Aggressor = une seule composante order-flow ;
- disponibilité seule = 0 ;
- données absentes/partielles/insuffisantes/stale/technical error/N/A = 0 sans malus ;
- signes positifs/négatifs symétriques pour l'attention ;
- `interest_level` et `candidate_limit` inchangés ;
- aucune création de candidat par Analytics ;
- observabilité 48 calculée à la demande sur l'historique Radar borné ;
- `rank_change=0` distinct de l'absence de donnée ;
- aucune évaluation de rentabilité future ni calibration post-hoc.

Références : `docs/47_5_MULTI_ANALYTICS_RANKING.md`, `docs/48_OBSERVABILITE_RANKING_ANALYTICS.md` et historique Git pour les ADR antérieurs.
