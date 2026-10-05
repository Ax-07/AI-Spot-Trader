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

## Référence courante

```text
Base GitHub auditée 49.3     : f0d4f94d2ed9b8f02eadb7ea021aa3fc817c973b
Batch 49.1 intégré           : 3194fce — feat: activate perpetual paper trading
Batch 49.2 intégré           : f0d4f94 — feat: feed radar shortlist into agent universe
Batch 49.3                   : PATCH PROPOSÉ — NON INTÉGRÉ À LA LIVRAISON
```

## Changelog — 2026-10-05 — Batch 49.3 contexte Radar / Analytics causal — patch proposé

Base GitHub auditée au démarrage : `f0d4f94d2ed9b8f02eadb7ea021aa3fc817c973b` (`feat: feed radar shortlist into agent universe`).

### Audit confirmé

- `CycleDecisionPlanInput` est la frontière causale du plan multi-marchés ;
- `StrategicMultiTimeframeContext` est un contrat spécialisé candles et ne doit pas être surchargé de faits Radar ;
- `OpenAIMultiMarketDecisionProvider` sérialise déjà l'entrée complète du plan de façon déterministe et n'effectue qu'un appel stratégique ;
- `DynamicMarketTradingCycleRunner` reçoit l'univers Radar 49.2 puis délègue au runner multi-marchés canonique ;
- `MarketAttentionSnapshotV6Analytics` contient activité, microstructure, Market Structure, Analytics Futures et ranking 47.5 ;
- le ranking 47.5 reste exactement quatre familles `0/1` : OI, Funding, Liquidations et Order Flow ;
- CVD + Aggressor Differential restent une seule famille `ORDER_FLOW` ;
- les statuts Analytics existants distinguent déjà disponibilité, partial, stale, historique insuffisant, erreur technique et N/A ;
- Risk et Broker ne dépendent pas du Radar et restent en aval du plan Agent.

### Patch 49.3

- ajout de `RadarAnalyticsStrategicContext`, contrat strict, immuable, borné et trié ;
- séparation explicite entre identité d'univers 49.2 et contexte analytique 49.3 ;
- projection compacte de l'activité/tendance/liquidité, microstructure SPOT et Market Structure ;
- projection PERPETUAL du ranking 47.5, Open Interest, Funding, Liquidation Volume, CVD et Aggressor Differential ;
- statuts dégradés conservés sans valeurs artificielles ;
- SPOT expose les Analytics Futures comme `NOT_APPLICABLE` ;
- diagnostics techniques internes, ranks avant/après, `rank_change`, historiques bruts et métadonnées d'observabilité inutiles exclus du prompt ;
- contrôle de causalité imbriqué : aucun timestamp ne peut dépasser le snapshot Radar ;
- contrôle de frontière : le snapshot relu doit porter exactement le `radar_observed_at` utilisé par Discovery ;
- contrôle de plan : le contexte ne peut pas postdater `CycleDecisionPlanInput.created_at` ni contenir un marché hors `market_states` ;
- `FrozenRadarContextDecisionProvider` attache le contexte puis délègue une seule fois au même Agent ;
- contrat de prompt explicite : score 0..4 descriptif, jamais signal BUY/SELL/probabilité/conviction ;
- aucune modification du Risk Engine ou du `PaperBroker` ;
- aucune migration, aucun LIVE et aucune API Kraken Futures privée.

## ADR-361 — Le contexte 49.3 utilise un contrat dédié référencé par `CycleDecisionPlanInput`

**ADOPTÉ DANS LE PATCH 49.3 — NON INTÉGRÉ À LA LIVRAISON.**

Options comparées :

1. ajouter les faits directement comme champs dispersés dans `CycleDecisionPlanInput` : rejeté, séparation insuffisante ;
2. étendre `StrategicMultiTimeframeContext` : rejeté, mélange Radar/Analytics avec le contrat candles ;
3. **ajouter un `RadarAnalyticsStrategicContext` dédié : retenu**.

Motifs : contrat borné/testable, identité séparée des faits analytiques, pas de duplication du pipeline candles, sérialisation déterministe et évolution indépendante.

## ADR-362 — Le contexte doit être figé sur le snapshot exact de Discovery

**ADOPTÉ DANS LE PATCH 49.3 — NON INTÉGRÉ À LA LIVRAISON.**

Le runner accepte la projection seulement si :

```text
radar.latest.observed_at == discovery.audit.radar_observed_at
```

Tous les timestamps imbriqués doivent être `<=` à cette frontière et la frontière doit être `<=` au plan. Une divergence de snapshot ou une donnée future échoue fermée pour les nouvelles ouvertures.

Le provider Agent ne consulte donc jamais un service Radar mutable pendant l'appel LLM ; il reçoit un objet figé.

## ADR-363 — Le score 47.5 reste descriptif et inchangé

**ADOPTÉ DANS LE PATCH 49.3 — NON INTÉGRÉ À LA LIVRAISON.**

Le score reste :

```text
OPEN_INTEREST      0/1
FUNDING            0/1
LIQUIDATION_VOLUME 0/1
ORDER_FLOW         0/1
TOTAL              0..4
```

CVD et Aggressor concordants valent toujours au plus `+1` ensemble ; un conflit garde sa sémantique existante. Le Batch 49.3 ne recalibre ni poids ni seuils.

Dans le prompt, ce score est explicitement décrit comme **indice d'attention**, jamais comme probabilité de hausse/baisse, conviction ou instruction d'action.

## ADR-364 — Les données dégradées restent des données dégradées

**ADOPTÉ DANS LE PATCH 49.3 — NON INTÉGRÉ À LA LIVRAISON.**

Le contexte distingue :

```text
AVAILABLE
PARTIAL
STALE
INSUFFICIENT_HISTORY
TECHNICAL_ERROR
NOT_APPLICABLE
UNAVAILABLE
```

Aucun statut dégradé n'est converti en valeur artificielle positive/négative. Une panne technique ne devient jamais une information de marché. Les Analytics Futures SPOT sont `NOT_APPLICABLE`.

## ADR-365 — Un seul appel stratégique est conservé

**ADOPTÉ DANS LE PATCH 49.3 — NON INTÉGRÉ À LA LIVRAISON.**

`FrozenRadarContextDecisionProvider` est un décorateur d'entrée, pas un second Agent. Il enrichit `CycleDecisionPlanInput`, revalide le contrat puis appelle une seule fois `delegate.generate_decision_plan(...)`.

Les outils read-only actuels ne sont pas supprimés : ils couvrent des recherches ponctuelles distinctes du snapshot Radar figé.

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

Aucun second système de discovery ni seconde shortlist concurrente n'est créé.

### ADR-358 — La frontière d'univers 49.2 reste identité-only

**ADOPTÉ — Batch 49.2 intégré via `f0d4f94`.**

```text
{ symbol, market_type }
```

Le Batch 49.3 ajoute un contexte séparé ; il ne transforme pas l'audit Discovery en dump Radar.

### ADR-359 — Panne Radar fail-closed pour les nouvelles ouvertures

**ADOPTÉ — Batch 49.2 intégré via `f0d4f94`.**

```text
Radar utilisable + candidats exécutables -> plan normal
Radar inutilisable + positions ouvertes  -> MANAGEMENT uniquement
Radar inutilisable + aucune position      -> cycle FAILED avant Agent/Risk/Broker
```

### ADR-360 — Revalidation de l'exécutabilité Kraken/Campaign

**ADOPTÉ — Batch 49.2 intégré via `f0d4f94`.**

Type autorisé, quote de règlement, statut tradable, PERPETUAL linéaire, présence catalogue et whitelist éventuelle restent nécessaires.

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
