# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs
> et les décisions récentes nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Risk, SPOT sans short/levier, PERPETUAL avec protections déterministes, audit durable,
no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence GitHub auditée pour le Batch 18.11

```text
HEAD GitHub : e2807621352219e355810bcd212844ea646c83da
Message     : docs: sync batch 18.10 integrated state
Code 18.10  : b445b70b02d2c4af4b24a86ccfbdeff6f18a75e9
Batch 18.11 : patch local livré, non intégré
```

Le commit `e280762` synchronise uniquement la documentation après l'intégration de 18.10.

## Décisions Batch 18.9A toujours actives

ADR-173 à ADR-181 restent applicables : StrategyRevision immuable, contrat Agent protégé séparé,
digest prompt déterministe, Campaign snapshot non sensible, `paper-experiment-v4`, distinction
Campaign/paper_run, ownership runtime backend, preview canonique et lineage recovery exposé.

## Décisions Batch 18.9B toujours actives

ADR-182 à ADR-188 restent applicables : frontend client du Control Plane, client API unique,
validators métier backend, révisions lues via les contrats existants, preview non recomposé côté
frontend, aucun draft Control Plane persistant dans le navigateur, activation fraîche et reprise
explicitement distinctes.

## Décisions Batch 18.9C

### ADR-189 — Adapter les enums JSON à la frontière Control Plane sans relâcher le domaine strict

**INTÉGRÉ.** Une Campaign créée depuis le navigateur transporte `market_type` comme chaîne JSON.
`ExecutableMarket` reste strict dans le domaine ; le Control Plane adapte uniquement les valeurs
canoniques `SPOT` et `PERPETUAL` vers `MarketType` avant la validation du modèle imbriqué.

Une valeur inconnue n'est pas normalisée silencieusement et reste rejetée par la validation.
Le frontend, le Risk Engine, le TradingEngine et le Broker ne sont pas modifiés par ce correctif.

### ADR-190 — Corriger les frontières API mypy sans changer le runtime

**INTÉGRÉ.** La validation mypy globale avait exposé quatre incompatibilités de typing entre valeurs
`str` lues depuis les vues de persistence et schémas de réponse `Literal[...]`.

La correction reste limitée aux frontières API :

- casts explicites pour `market_type` dans `paper_runs` ;
- cast explicite du `market_type` dans les résumés d'audit ;
- annotation explicite du type du modèle dynamique dans le prompt preview.

Aucune validation métier, décision Agent, règle Risk ou exécution Broker n'est modifiée.

## Décisions Batch 18.10 — intégrées

### ADR-191 — Faire de la Vue d'ensemble la surface opérateur principale

**INTÉGRÉ.** La page racine n'empile plus directement Dashboard, Control Plane, Chat et Analytics.
Elle instancie une `CockpitShell` qui applique une divulgation progressive :

- la landing ne montre que les états et actions nécessaires au pilotage immédiat ;
- les détails de configuration, d'audit, de performance et de chat restent accessibles dans des vues
  distinctes ;
- PAPER, Campaign active et état moteur restent visibles en permanence dans le header.

Cette décision est purement UX et ne modifie aucun contrat backend.

### ADR-192 — Réutiliser les panneaux canoniques plutôt que dupliquer leurs fonctions

**INTÉGRÉ.** `ControlPlanePanel`, `CockpitDashboard`, `AnalyticsPanel` et `ChatPanel` sont conservés
comme vues secondaires. La nouvelle Vue d'ensemble consomme les hooks/API existants pour afficher
une synthèse ; elle ne recrée ni validation Campaign, ni logique Risk, ni calcul de trading, ni
exécution Broker.

Les commandes `run-cycle`, Start et Stop restent les commandes canoniques du backend. Fermer ou
recharger le frontend ne déclenche aucun Stop implicite.

## Décisions Batch 18.11 — patch local

### ADR-193 — Structurer l'aide en trois niveaux sans créer une seconde application

**PROPOSÉ / LIVRÉ DANS LE PATCH.** L'aide opérateur suit la même architecture Option A :

1. démarrage rapide directement dans la Vue d'ensemble ;
2. aide contextuelle courte uniquement aux endroits ambigus ;
3. vue **Guide** dédiée dans la navigation principale pour l'explication complète.

La vue Guide reste un composant du `CockpitShell`. Elle ne recrée aucun flux de navigation ou
runtime parallèle.

### ADR-194 — Réutiliser les explications existantes et garder les règles métier au backend

**PROPOSÉ / LIVRÉ DANS LE PATCH.** Le Control Plane contient déjà des explications utiles sur
Strategy/StrategyRevision, validation backend, Risk, activation/reprise et PERPETUAL `ISOLATED`.
Le Batch 18.11 les conserve au lieu d'ajouter des tooltips répétitifs.

Les nouveaux blocs d'aide utilisent des cartes existantes et des `<details>` natifs. Ils décrivent
le comportement sans implémenter de validation métier, de logique Risk, de calcul de portefeuille ou
de commande Broker.

### ADR-195 — Versionner un guide opérateur distinct du Project Master

**PROPOSÉ / LIVRÉ DANS LE PATCH.** `docs/01_PROJECT_MASTER.md` reste la spécification principale et
technique. `docs/11_GUIDE_OPERATEUR.md` devient la référence pédagogique destinée à l'opérateur.

Le guide rappelle explicitement :

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Il documente PAPER, SPOT/PERPETUAL, Campaigns, recovery, lecture des décisions et performances, sans
ouvrir le périmètre LIVE.

## Changelog — 2026-09-24 — Batch 18.9C intégré et validé

Le commit `5fc7704e7ca43ded4c2565b21871b81fe2161b0a` est intégré sur `main`.

Validation comportementale réelle effectuée depuis le cockpit avant intégration :

- Strategy créée, renommée, archivée ; révisions immuables, comparaison et preview confirmées ;
- refus 409 confirmé lors d'une tentative de révision sur Strategy archivée ;
- correctif de création Campaign intégré pour l'adaptation JSON de `market_type` ;
- Campaign SPOT créée et activée avec Luna ;
- sélection multi-marchés réelle BTC/ETH/SOL par le même Agent ;
- BUY SPOT naturel sur SOL/USD : quantité proposée par l'Agent réduite par Risk pour respecter le
  max order notional, puis fill PAPER avec frais, spread et slippage ;
- HOLD naturels observés et journalisés sans exécution ;
- `run-cycle` isolé confirmé : un cycle et moteur restant `STOPPED` ;
- Start/Stop confirmés sur la boucle autonome backend ;
- après restart backend : aucune Campaign ni moteur repris automatiquement ;
- `run-cycle` sans runtime confirmé en 503 fail-closed ;
- reprise explicite confirmée avec nouveau `paper_run_id`, lineage correct et restauration du ledger ;
- Campaign PERPETUAL BTC/ETH/SOL créée avec levier 2, marge `ISOLATED`, caps de position et
  d'exposition ;
- cycle PERPETUAL réel : sélection SOL/USD, BUY naturel, Risk `MODIFY`, fill PAPER, marge isolée et
  position LONG persistée ;
- 422 confirmé pour un levier PAPER supérieur au plafond Risk ;
- `gpt-5.6-sol` sélectionnable et persisté par configuration avec digests distincts ;
- aucun SELL naturel observé et aucun SELL forcé.

Validation locale opérateur exécutée avant le push du commit intégré :

```text
pytest backend : 506 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed
mypy backend/src : Success: no issues found in 89 source files
git diff --check : OK hors avertissements LF -> CRLF
working tree propre avant push
```

## Changelog — 2026-09-24 — Batch 18.10 UX/UI intégré et validé

Le commit `b445b70b02d2c4af4b24a86ccfbdeff6f18a75e9` est intégré sur `main` avec la refonte UX/UI du
cockpit PAPER.

Contenu intégré :

- nouvelle `CockpitShell` opérateur ;
- navigation latérale simple à cinq vues ;
- landing **Vue d'ensemble** selon l'Option A ;
- header permanent avec PAPER, Campaign/Strategy active, modèle, types de marchés et état moteur ;
- commandes moteur visibles et explicites ;
- KPI PAPER, Marché & activité, Actions rapides, dernières décisions IA + Risk et alertes ;
- anciens panneaux réutilisés comme vues détaillées ;
- typographie globale remplacée par une stack système plus lisible ;
- aucun changement backend.

Validation opérateur réelle avant intégration :

```text
validation visuelle opérateur : OK
pnpm lint : OK, 0 erreur, 0 warning
pnpm typecheck : OK
pnpm build : OK
git diff --check : OK hors avertissements LF -> CRLF
working tree propre après push
```

## Changelog — 2026-09-24 — Batch 18.11 guide opérateur livré à validation

Audit du cockpit 18.10 : l'architecture Option A est lisible, mais les concepts Control Plane et la
séquence du premier test restent difficiles à découvrir sans connaître l'architecture interne.

Patch livré :

- nouvelle vue **Guide** dans la navigation principale ;
- démarrage rapide PAPER en trois phases dans la Vue d'ensemble ;
- guide complet couvrant Strategy, StrategyRevision, Campaign, Agent, Risk, SPOT, PERPETUAL,
  activation, `run-cycle`, Start/Stop, recovery, décisions, positions, performance et erreurs ;
- aide contextuelle progressive sur `run-cycle`/Start, HOLD/Risk et états moteur ;
- nouveau document `docs/11_GUIDE_OPERATEUR.md` ;
- aucun changement backend.

Validation exécutée dans l'environnement de livraison :

```text
TypeScript transpile/syntax check des fichiers frontend 18.11 : OK
TypeScript ciblé avec stubs locaux des dépendances : OK
harness structure/invariants + ancres Guide : OK
heuristique secrets sur les fichiers livrés : OK
git diff --cached --check sur les fichiers livrés : OK
```

Les validations `pnpm lint`, `pnpm typecheck` et `pnpm build` restent à exécuter localement avec les
dépendances du repository avant intégration.
