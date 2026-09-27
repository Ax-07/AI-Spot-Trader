# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs, les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers Broker/Kraken, SPOT sans short/levier/marge, PERPETUAL PAPER derrière les contrôles dérivés déterministes, FUTURE daté interdit, audit durable des cycles, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Les Sessions PAPER canoniques autorisent `SPOT` et `PERPETUAL` linéaire. `FUTURE` daté reste interdit.

## Référence courante

```text
HEAD GitHub intégré : b4f1e50f22164c7d019d11d930485733c01c6711
Commit              : fix: restore paper perpetual session support
Batch 19.13         : intégré depuis 29316d7 ; durcissement LLM intégré dans aa404e4
Correctif PERPETUAL : intégré dans b4f1e50
Inspecteur LLM      : patch proposé au-dessus de b4f1e50, non intégré à GitHub
```

## Décisions historiques toujours actives

- ADR-173 à ADR-239 : immutabilité Strategy/Campaign, Control Plane, accounting, monitoring, discovery, explicabilité, candles/charts et overlays ;
- ADR-240 à ADR-247 : façade Session, lifecycle, immutabilité et modes de marchés ;
- ADR-248 à ADR-255 : Trading Style, coûts Agent et contexte stratégique multi-timeframes ;
- ADR-256 à ADR-258 : UX Session du style et compatibilité legacy ;
- ADR-259 à ADR-262 : gestion stratégique des positions, `position-management-v1`, plafond Risk par ordre et rotation du capital ;
- ADR-263 : classification robuste des limites fournisseur OpenAI et fail-closed ;
- ADR-264 : précision PAPER PERPETUAL et normalisation descendante du quantum ;
- ADR-265 à ADR-268 : multi-décisions / multi-marchés, Risk séquentiel, atomicité PAPER et audit 1:N ;
- ADR-269, ADR-270 et ADR-272 : Structured Outputs strict, contrat multi-marchés protégé et diagnostic sécurisé ;
- ADR-271 : garde-fou SPOT-only intégré par erreur dans `aa404e4`, supersédé ;
- ADR-273 : Sessions PAPER SPOT + PERPETUAL, FUTURE daté interdit ;
- ADR-274 : inspection en lecture seule du payload OpenAI réel à la frontière `OpenAIResponsesClient`.

## ADR-240 — Session est une façade UX, pas un nouvel agrégat persistant

**ADOPTÉ AU BATCH 19.8.** `Session` reste une projection sur Strategy, StrategyRevision, Campaign, paper_run et runtime actif. Aucune table `sessions` n'est créée.

## ADR-241 — La création Session est atomique côté backend

**ADOPTÉ AU BATCH 19.8.** Strategy + StrategyRevision 1 + Campaign sont créées dans une seule transaction.

## ADR-242 à ADR-247 — Versioning, archivage, lifecycle et marchés

**ADOPTÉS AU BATCH 19.8.** Les modifications créent de nouveaux faits immuables ; `Supprimer` archive ; les statuts sont dérivés ; `stop` ferme runtime/run ; `AUTOMATIC_AI` et `MANUAL` restent explicites.

## ADR-248 à ADR-255 — Style, coûts et multi-timeframes

**ADOPTÉS AUX BATCHES 19.9A/19.9B.** `SCALP`/`SWING`, `trading-style-map-v1`, `ExecutionCostContext` et `strategic-mtf-v1` enrichissent l'Agent sans modifier Risk. `history_as_of(...)` garantit la causalité des candles.

## ADR-256 à ADR-258 — UX du style

**ADOPTÉS AU BATCH 19.9C.** Le style est exposé sans couplage silencieux à l'agressivité, aux marchés ou à Risk.

## ADR-259 à ADR-262 — Gestion des positions et rotation du capital

**ADOPTÉS AU BATCH 19.10.** Les positions ouvertes restent des opportunités stratégiques ; `position-management-v1` reste factuel ; `risk_max_order_notional` reste un plafond par ordre ; aucune règle déterministe `après SELL -> BUY` n'est introduite.

## ADR-263 — Les limites fournisseur OpenAI sont classifiées avant retry

**ADOPTÉ AU BATCH 19.12.** Quota/crédit/usage/spend sont non retryables ; les limitations temporaires restent retryables avec `Retry-After` valide ou backoff borné. Toute erreur LLM reste fail-closed.

## ADR-264 — Précision PAPER PERPETUAL et quantum provider-derived

**ADOPTÉ ET INTÉGRÉ HISTORIQUEMENT AU HEAD `18596ac9d4f6554aa4817a9bdb374ab597c2399f`.** Les validations de précision dérivées restent canoniques.

## ADR-265 — Un cycle peut porter un plan stratégique ordonné multi-marchés

**ADOPTÉ ET INTÉGRÉ AU HEAD `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.** Un seul appel du même Agent stratégique produit un plan ordonné contenant plusieurs décisions sur des marchés distincts. `max_decisions_per_cycle` vaut `6` par défaut, hard limit `20`.

## ADR-266 — Risk et Broker suivent l'ordre du plan sur un portefeuille causal

**ADOPTÉ ET INTÉGRÉ AU HEAD `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.** Chaque décision est évaluée après application des éventuelles exécutions précédentes. `HOLD` et `REJECT` n'interrompent pas le plan.

## ADR-267 — Une défaillance technique rend le cycle PAPER atomique

**ADOPTÉ ET INTÉGRÉ AU HEAD `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.** Une erreur technique Risk ou Broker fait passer le cycle à `FAILED` et restaure le portefeuille au checkpoint initial.

## ADR-268 — L'audit devient 1:N et les analytics restent économiques

**ADOPTÉ ET INTÉGRÉ AU HEAD `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.** La migration `0007_multi_decision_cycles` conserve plusieurs décisions, évaluations Risk et intentions d'exécution dans leur ordre.

## ADR-269 — Le schéma Structured Outputs encode le contrat action/quantité

**ADOPTÉ ET INTÉGRÉ AU HEAD `aa404e46c1f05269ac2279507aa746b3af7a965d`.** `BUY`/`SELL` imposent une quantité strictement positive et `HOLD` impose `null`.

## ADR-270 — Le nouveau chemin reçoit un contrat protégé multi-marchés explicite

**ADOPTÉ ET INTÉGRÉ AU HEAD `aa404e46c1f05269ac2279507aa746b3af7a965d`.** `StrategyInstructionsClient` injecte `strategic-multi-market-plan-v1`. Le singleton historique reste disponible pour legacy/replay.

## ADR-271 — Garde-fou SPOT-only du runtime

**INTÉGRÉ PAR ERREUR DANS `aa404e4` — SUPERSEDÉ PAR ADR-273.** La restriction contredisait le support dérivés canonique.

## ADR-272 — Les erreurs de plan sont diagnostiquées sans sortie brute

**ADOPTÉ ET INTÉGRÉ AU HEAD `aa404e46c1f05269ac2279507aa746b3af7a965d`.** Les erreurs de contrat sont catégorisées sans persister la sortie LLM brute ; aucun retry sémantique n'est ajouté.

## ADR-273 — Les Sessions PAPER supportent SPOT et PERPETUAL ; FUTURE reste interdit

**ADOPTÉ ET INTÉGRÉ AU HEAD `b4f1e50f22164c7d019d11d930485733c01c6711`.** Le garde-fou SPOT-only est retiré. Les marchés `SPOT` et `PERPETUAL` linéaires restent soumis au pipeline Agent -> Risk -> Broker PAPER. `FUTURE` daté reste refusé.

## ADR-274 — L'inspection LLM se fait à la frontière canonique OpenAI

**PROPOSÉ DANS LE BATCH INSPECTEUR LLM — NON INTÉGRÉ.**

`OpenAIResponsesClient` capture en best-effort le dictionnaire exact utilisé comme body JSON de chaque appel Responses API réussi. La trace expose `instructions`, `input`, Structured Output, tools, `parallel_tool_calls`, `store`, output fournisseur et texte final lorsqu'il existe. Les headers HTTP, la clé OpenAI, les chaînes de connexion et secrets ne sont jamais ajoutés au record.

Les tool loops sont représentées par plusieurs records ordonnés, ce qui permet de voir le `function_call` reçu puis le `function_call_output` réellement renvoyé au modèle. La corrélation cycle/discovery est inférée des inputs canoniques ; le chat ajoute `session_id` via un `ContextVar` asynchrone sans modifier le prompt transmis.

La rétention est bornée à 200 records et 512 Kio par record, en mémoire du processus. Cette première version évite une migration DB supplémentaire : l'inspecteur est destiné au diagnostic immédiat des prompts et n'est pas une nouvelle source de vérité durable. Une exception de l'audit est absorbée et ne peut pas faire échouer le moteur.

## Anomalies de prompt constatées pendant l'audit

**CONFIRMÉES, NON CORRIGÉES DANS CE BATCH :**

- `OPERATOR_CHAT_SYSTEM_PROMPT` dit encore `Trading is SPOT only and PAPER only.` ;
- `_compose_strategy_context_sections()` produit `niveat=...` ;
- le prompt legacy `agent/prompt.py` dit que `FUTURE` daté « peut être découvrable », alors que l'invariant projet courant l'interdit à la discovery et à l'exécution.

Ces points doivent faire l'objet d'un correctif de prompt explicite après observation des payloads réels dans le cockpit.

## Changelog — 2026-09-27 — Inspecteur LLM proposé

- base GitHub vérifiée : `b4f1e50f22164c7d019d11d930485733c01c6711` ;
- instrumentation canonique : `OpenAIResponsesClient` ;
- endpoint lecture seule : `GET /api/v1/llm-audit` ;
- cockpit : Réglages -> Inspecteur LLM ;
- rétention bornée et fail-open de l'observabilité ;
- aucun changement de stratégie, Risk, Broker ou contrat d'ordre ;
- anomalies de prompt documentées, non corrigées.

## Changelog — 2026-09-27 — Correctif PERPETUAL intégré

- commit `b4f1e50f22164c7d019d11d930485733c01c6711` (`fix: restore paper perpetual session support`) ;
- retrait du garde-fou SPOT-only erroné ;
- SPOT + PERPETUAL linéaire PAPER restaurés ;
- FUTURE daté reste interdit.

## Changelog — 2026-09-27 — Durcissement multi-market LLM intégré

- commit `aa404e46c1f05269ac2279507aa746b3af7a965d` (`fix: harden multi-market LLM plan contract`) ;
- Structured Outputs strict ;
- contrat protégé `strategic-multi-market-plan-v1` ;
- diagnostic Agent sécurisé ;
- aucun retry LLM sémantique.

## Changelog — 2026-09-27 — Batch 19.13 intégré

- commit `29316d7521accfe46316cb2bc6dfcf7652ba04bf` ;
- plan ordonné multi-marchés, multi-`BUY` / `SELL` / `HOLD` ;
- Risk séquentiel et causal ;
- rollback PAPER atomique ;
- persistence 1:N et migration `0007_multi_decision_cycles` ;
- analytics basés sur fills/trades réels.
