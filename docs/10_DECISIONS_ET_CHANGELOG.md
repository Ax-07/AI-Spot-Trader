# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs,
> les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Kraken, SPOT sans short/levier, PERPETUAL linéaire avec protections déterministes, audit
durable, no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE
séparé.

## Référence intégrée du Batch 19.4

```text
HEAD GitHub main observé           : e7e4c8248406516eada576b3907e77dc8b72a0e4
Référence fonctionnelle Batch 19.4 : de65c6677ce01f9c75da5545fe81553a021f588d
Commit fonctionnel                 : feat: add dynamic audited market discovery
```

Les Batches 19.1, 19.2, 19.3 et 19.4 sont intégrés. Le Batch 19.5 ci-dessous a passé la validation automatisée locale ; son intégration GitHub reste en attente du commit/push et de la clôture opérateur.

Validation opérateur communiquée pour 19.4 : `tests/test_market_discovery.py` = 12 tests passés ; suite backend complète = 578 tests passés avec 2 warnings de dépréciation ; frontend = `pnpm lint`, `pnpm typecheck` et `pnpm build` passés.

## Décisions historiques toujours actives

- ADR-173 à ADR-181 : StrategyRevision immuable, contrat Agent protégé, digests, Campaign snapshot, identité expérimentale, distinction Campaign/paper_run, runtime backend et recovery ;
- ADR-182 à ADR-188 : frontend client du Control Plane, API unique, validators backend, preview canonique, activation et reprise distinctes ;
- ADR-189/190 : adaptation JSON `market_type` à la frontière API et typing sans changement runtime ;
- ADR-191/192 : Vue d'ensemble comme surface principale et réutilisation des panneaux canoniques ;
- ADR-193 à ADR-195 : aide progressive, règles métier au backend et guide opérateur ;
- ADR-196 à ADR-204 : simplification opérateur, navigation orientée tâches, profils Risk UX, `next-themes`, tokens sémantiques et modernisation du cockpit ;
- ADR-205 : comptabilité SPOT canonique backend ;
- ADR-206 / ADR-215 / ADR-216 / ADR-217 : monitoring et valorisation ;
- ADR-207 / ADR-218 / ADR-219 / ADR-220 : `NORMAL` / `MANAGEMENT`, `CapacityEvaluator` et économie IA ;
- ADR-221 à ADR-226 : discovery/watchlist dynamique, audit, univers effectif, whitelist et recovery.

## ADR-210 — Exposer le `rationale` sans le confondre avec Risk

**BATCH 19.5 VALIDÉ AUTOMATIQUEMENT EN LOCAL — INTÉGRATION GITHUB EN ATTENTE.**

Le cockpit expose séparément :

- rationale de sélection de watchlist quand une vraie sélection `REFRESHED` existe ;
- rationale de sélection du marché du cycle ;
- rationale de la décision BUY / SELL / HOLD ;
- statut et raisons déterministes Risk ;
- exécution PAPER réelle éventuelle.

`CACHE_REUSED`, `FALLBACK` et `SKIPPED_MANAGEMENT` ne sont jamais présentés comme une nouvelle sélection IA.

## ADR-227 — L'explicabilité est une projection de lecture, pas une nouvelle source de vérité

**BATCH 19.5 VALIDÉ AUTOMATIQUEMENT EN LOCAL — INTÉGRATION GITHUB EN ATTENTE.**

Aucune table SQL, aucun ledger et aucune mutation des payloads persistés ne sont ajoutés. La projection est construite à la frontière API à partir des détails de cycle existants.

Elle peut présenter les faits, mais ne doit jamais :

- recalculer la décision Agent ;
- reconstituer approximativement la logique Risk ;
- recalculer le P&L ;
- inventer une rationale absente ;
- transformer un cache ou une corrélation par symbole en causalité métier.

## ADR-228 — L'Historique se base sur les détails corrélés de cycle

**BATCH 19.5 VALIDÉ AUTOMATIQUEMENT EN LOCAL — INTÉGRATION GITHUB EN ATTENTE.**

La liste `/cycles` sert d'index. Pour chaque cycle visible, le cockpit lit `/cycles/{cycle_id}` afin d'obtenir le graphe corrélé persistant. Il ne joint plus les pages indépendantes `/decisions`, `/risk-assessments` et `/executions` pour fabriquer un parcours.

Les JSON canoniques restent disponibles dans les détails techniques.

## ADR-229 — Positions : corrélation par marché uniquement en l'absence de provenance directe

**BATCH 19.5 VALIDÉ AUTOMATIQUEMENT EN LOCAL — INTÉGRATION GITHUB EN ATTENTE.**

Les modèles de position ne portent pas de `decision_id`, `execution_id` ou `fill_id` d'origine. Le cockpit affiche donc seulement une **activité auditée récente liée au même symbole + type de marché**.

Cette activité n'est jamais intitulée ou décrite comme « décision à l'origine de cette position ».

## ADR-230 — HOLD, REJECT et FAILED conservent des sémantiques distinctes

**BATCH 19.5 VALIDÉ AUTOMATIQUEMENT EN LOCAL — INTÉGRATION GITHUB EN ATTENTE.**

- HOLD + ALLOW : décision métier normale sans exécution attendue ;
- REJECT : décision Risk déterministe, aucun `ExecutionIntent` ;
- FAILED : échec technique à son stage propre ;
- si un intent existe déjà avant un échec Broker, cet artefact reste visible ;
- MODIFY expose séparément quantité demandée/proposée et quantité autorisée.

## ADR-211 à ADR-214 — Charts, données et cadences

**PLANIFIÉS 19.6.** Kraken/backend restent la source canonique des charts ; Lightweight Charts est le renderer privilégié ; historique REST + temps réel WebSocket + accumulation backend éventuelle ; monitoring, stratégie et discovery restent trois cadences distinctes ; les charts sont chargés à la demande.

## Changelog — 2026-09-24 — Batch 19.1

- comptabilité SPOT canonique au coût moyen pondéré ;
- coût restant all-in, ventes partielles et P&L réalisé ;
- compatibilité historique via `accounting_complete=false` ;
- API/types/cockpit enrichis.

## Changelog — 2026-09-24 — Batch 19.2

- mark SPOT causal `LAST_PRICE` et P&L latent backend ;
- agrégats portefeuille et equity/exposition backend ;
- monitor SPOT/PERPETUAL sans LLM ;
- séparation exécution/valorisation ;
- compatibilité snapshot/recovery sans migration SQL.

## Changelog — 2026-09-25 — Batch 19.3

- `CapacityEvaluator` déterministe avec `NORMAL` / `MANAGEMENT` ;
- même `RiskPolicy` partagée entre CapacityEvaluator et RiskEngine ;
- sélection MANAGEMENT limitée aux positions ouvertes ;
- tools de recherche d'ouverture désactivés en MANAGEMENT ;
- Risk bloque explicitement toute augmentation d'exposition en MANAGEMENT ;
- mode/reason/search-skip audités sans état durable ;
- intégré sur GitHub au commit `bfef06d78dc34089541272c2944518499d4a1530`.

## Changelog — 2026-09-25 — Batch 19.4

- `MarketDiscoveryPolicy`, cache catalogue et coordinateur de discovery ;
- présélection factuelle Kraken sans ranking algorithmique ;
- watchlist multi-marchés sélectionnée par le même Agent ;
- fallback dernière watchlist/bootstrap, timeout 45 s et cadence de retry bornée ;
- interaction explicite avec NORMAL/MANAGEMENT ;
- positions ouvertes réinjectées dans l'univers effectif ;
- routeur/mark-to-market/recovery adaptés aux marchés dynamiques ;
- audit détaillé sans migration SQL ;
- configurateur simple orienté « paire de départ/secours » ;
- validation finale opérateur : 12 tests discovery, 578 tests backend avec 2 warnings, frontend lint/typecheck/build ;
- intégré sur GitHub au commit `de65c6677ce01f9c75da5545fe81553a021f588d`.

## Changelog — 2026-09-25 — Batch 19.5 (validation locale réussie, intégration en attente)

- resynchronisation sur le HEAD GitHub `e7e4c8248406516eada576b3907e77dc8b72a0e4` ;
- projection API d'explicabilité construite depuis les payloads canoniques persistés ;
- séparation discovery/contexte, sélection marché, Agent, Risk et PAPER ;
- traitement explicite de HOLD, MODIFY, REJECT, FAILED et legacy partiel ;
- faits de fills PAPER exposés dans la projection ;
- Accueil enrichi avec rationale IA, raisons Risk et résultat d'exécution ;
- Historique basé sur les détails corrélés par cycle ;
- Positions enrichies d'une activité récente liée au marché sans causalité inventée ;
- validation opérateur ciblée `pytest tests/test_cycle_explainability.py` : **8 tests passés** ;
- suite backend complète `pytest` : **586 tests passés**, 2 warnings de dépréciation ;
- frontend : `pnpm lint`, `pnpm typecheck` et `pnpm build` **passés** ;
- `git diff --check` sans erreur de whitespace, avec seulement des avertissements LF -> CRLF ;
- revue visuelle light/dark + responsive encore à distinguer de la validation automatisée avant clôture définitive.
