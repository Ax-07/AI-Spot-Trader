# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs, les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers Broker/Kraken, SPOT sans short/levier, PERPETUAL selon les capacités intégrées, audit durable, no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence courante

```text
HEAD GitHub vérifié au démarrage 19.8 : 130429eca6c7c8385c1caf4b2eb2870bef61ec3e
Référence fonctionnelle Batch 19.7      : 8b969b434916d89f6b6aa127c3bac9c27e990966
Batch 19.8                              : patch proposé localement, non intégré
```

## Décisions historiques toujours actives

- ADR-173 à ADR-181 : StrategyRevision immuable, contrat Agent protégé, digests, Campaign snapshot, identité expérimentale, distinction Campaign/paper_run, runtime backend et recovery ;
- ADR-182 à ADR-190 : frontend client du Control Plane, API/validators backend, preview canonique, activation/reprise distinctes et typing frontière ;
- ADR-191 à ADR-204 : cockpit opérateur, aide progressive, règles métier backend et dark mode ;
- ADR-205 à ADR-226 : comptabilité, monitoring, `NORMAL`/`MANAGEMENT`, discovery/watchlist, whitelist et recovery ;
- ADR-227 à ADR-230 : explicabilité ;
- ADR-231 à ADR-238 : candles/streaming, vue Marchés, univers sans ranking frontend, markers de fills et Lightweight Charts comme rendu uniquement ;
- ADR-239 : overlays de position strictement issus du portefeuille backend.

## ADR-240 — Session est une façade UX, pas un nouvel agrégat persistant

**PROPOSÉ AU BATCH 19.8.**

`Session` devient le concept utilisateur principal mais son identité technique reste la `Strategy`. Aucune table `sessions` n'est créée. La projection repose sur Strategy, StrategyRevision, Campaign, paper_run et le runtime actif.

Raison : préserver l'audit et les composants canoniques tout en masquant leur complexité dans le parcours normal.

## ADR-241 — La création Session est atomique côté backend

**PROPOSÉ AU BATCH 19.8.**

La création Strategy + StrategyRevision 1 + Campaign est réalisée dans une seule transaction persistence. Le navigateur n'orchestre plus plusieurs écritures pouvant laisser une Strategy orpheline si la création Campaign échoue.

`Créer et démarrer` enchaîne ensuite activation fraîche et démarrage du moteur dans le backend.

## ADR-242 — Modifier une Session produit de nouveaux faits immuables

**PROPOSÉ AU BATCH 19.8.**

- rename seul : mise à jour du nom de Strategy ;
- prompt modifié : nouvelle StrategyRevision ;
- configuration modifiée : nouvelle Campaign ;
- les Campaigns et revisions historiques ne sont jamais écrasées.

Une Session RUNNING ne peut pas être modifiée silencieusement. Elle doit d'abord être arrêtée.

## ADR-243 — Supprimer une Session signifie archiver

**PROPOSÉ AU BATCH 19.8.**

L'action UX `Supprimer` utilise `Strategy.archived_at`. Campaigns, paper_runs, cycles, décisions, Risk assessments, executions/fills et données P&L restent persistés. La restauration d'une Session archivée est hors scope v1.

## ADR-244 — Les statuts Session sont dérivés

**PROPOSÉ AU BATCH 19.8.**

Aucune colonne de statut parallèle n'est ajoutée. Le statut dépend de l'archivage Strategy, de la Campaign courante, des runs existants et du runtime actif : `DRAFT`, `READY`, `RUNNING`, `STOPPED`, `RESUMABLE`, `ARCHIVED`.

## ADR-245 — Arrêter une Session ferme le runtime et le paper_run

**PROPOSÉ AU BATCH 19.8.**

Le simple `engine.stop` historique laisse la Campaign chargée. L'action Session `stop` doit être une fin explicite de Session : arrêter la boucle si nécessaire, fermer le runtime, persister `ended_at` sur le `paper_run` puis libérer la Campaign active.

Le contrôle technique `engine.stop` reste disponible dans le mode avancé pour les diagnostics historiques.

## ADR-246 — Deux modes de marchés explicites

**PROPOSÉ AU BATCH 19.8.**

- `AUTOMATIC_AI` : `market_discovery` présent ; le bootstrap/fallback ne constitue pas une obligation de trader ; la watchlist reste choisie par le même Agent IA parmi les candidats déterministes ;
- `MANUAL` : `market_discovery = null`, `paper_executable_markets` et `risk_allowed_pairs` sont alignés sur l'univers explicite.

Aucun second moteur de sélection ni ranking TypeScript n'est introduit.

## ADR-247 — Les defaults Market Discovery restent canoniques et visibles

**PROPOSÉ AU BATCH 19.8.**

La configuration avancée expose les valeurs effectives : 900 s catalogue, 900 s watchlist, timeout 45 s, probe 24, candidats 12, watchlist 6, snapshot 120 s, 2 observations minimales, fenêtre complète non requise. Le backend conserve la validation autoritaire.

## Changelog — 2026-09-25 — Batch 19.8 proposé

- façade backend Session sans migration SQL ;
- endpoints CRUD + start/stop/resume/run-cycle ;
- création atomique ;
- update versionné et immutable-history ;
- duplication indépendante et archivage logique ;
- arrêt de Session avec fermeture du run ;
- navigation Sessions et page de gestion ;
- configurateur simple/avancé réutilisé pour create/edit ;
- modes Automatique IA / Manuel ;
- typing frontend de `market_discovery` et whitelist Risk aligné sur le backend ;
- tests ciblés ajoutés pour configuration Session et persistence/lifecycle ;
- documentation refondue autour du vocabulaire Session.
