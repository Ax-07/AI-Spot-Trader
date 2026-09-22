# 10 — Décisions et changelog

> Les décisions détaillées antérieures au Batch 18 restent dans l'historique Git. Ce document conserve les principes courants et les décisions nouvelles du Batch 18.1.

## Principes historiques conservés

Un seul Agent stratégique, PAPER d'abord, Risk autorité finale, aucun LLM direct vers Broker, SPOT sans short/levier, Derivatives avec protections déterministes, audit durable, no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

Référence intégrée avant Batch 18.1 : `ca5077af00293ccca9794132ee0dd53a5b339911` ; tag `baseline-batch17` identique et non modifié.

## Décisions Batch 18.1 — patch proposé non intégré

### ADR-127 — Les tools sont des capacités factuelles read-only, jamais des agents ou signaux

**PROPOSÉE.** Le registry initial contient uniquement `list_markets` et `get_market_snapshot`. Aucun scanner, ranking, score d'opportunité, top-N stratégique, second Agent, Broker tool ou `buy/sell` tool n'est introduit.

### ADR-128 — La recherche cross-symbol n'élargit pas encore le symbole exécutable

**PROPOSÉE.** L'Agent peut examiner d'autres marchés, mais `DecisionCandidate.symbol` doit toujours être égal à `AgentInput.market_state.symbol`. Le `MarketState` envoyé à Risk/Broker reste celui du `paper_symbol`. Le choix multi-symbole exécutable est explicitement reporté au Batch 18.2.

### ADR-129 — La tool loop Responses reste stateless côté OpenAI et bornée côté application

**PROPOSÉE.** `store=false` est conservé. L'application rejoue explicitement les output items du tour précédent avec les `function_call_output`. Les functions utilisent des schémas stricts, `parallel_tool_calls=false`, un nombre max d'appels, un timeout par tool et une taille max de résultat.

Ces limites sont techniques et non stratégiques.

### ADR-130 — Les sources de recherche sont isolées des sources de trading

**PROPOSÉE.** Les recherches SPOT et Derivatives réutilisent les mêmes classes/adapters canoniques mais dans des instances dédiées. Le source Derivatives de recherche n'a pas de `market_sink`, donc une recherche ne peut ni marquer le ledger ni accumuler du funding.

Le catalogue Derivatives s'appuie sur les instruments publics normalisés complets. Le snapshot 18.1 reste SPOT/PERPETUAL ; un snapshot FUTURE générique n'est pas prétendu tant que le mapping exécutable privilégie volontairement le perpetual lors de collisions canoniques.

### ADR-131 — Les traces de tools sont des faits causaux durables au niveau du cycle

**PROPOSÉE.** Chaque appel terminé produit un `AgentToolTrace` normalisé et digesté. Les traces d'une décision sont attachées au `DecisionCandidate`, mais elles sont aussi portées par `TradingCycleResult` afin de survivre à un échec Agent survenu après une recherche et avant une décision valide.

La migration `0003_agent_tool_traces` ajoute `audit_cycles.agent_tool_traces_payload`. Les lignes historiques restent compatibles via `NULL`/liste vide à la lecture.

### ADR-132 — Le digest du cycle inclut les recherches causales

**PROPOSÉE.** `_result_digest()` incorpore `agent_tool_traces`. Une variation de résultats, d'arguments, d'ordre ou de statut de tools modifie donc l'identité durable du cycle, y compris pour un cycle `FAILED` sans `DecisionRecord`.

### ADR-133 — Les erreurs fournisseur sont observables mais sanitizées ; les violations de contrat échouent fermées

**PROPOSÉE.** Réseau, payload Kraken, symbole indisponible, timeout ou résultat trop volumineux deviennent des résultats de tool bornés avec seulement un type d'erreur. Les messages bruts ne sont pas transmis.

Un nom de tool inconnu, des arguments malformed ou un budget global dépassé arrêtent le stade Agent ; ils ne sont jamais masqués en HOLD.

### ADR-134 — Risk reste l'unique frontière vers l'exécution

**PROPOSÉE.** Le registry read-only ne dépend ni de `RiskEngine`, ni de `PaperBroker`, ni de `ExecutionIntent`. Le LLM ne choisit toujours ni levier ni `reduce_only`. Seul Risk peut construire un intent.

### ADR-135 — Conserver `agent-strategy-v4` implique de versionner séparément la politique de tools pour les futures expériences

**PROPOSÉE.** Le Batch 18.1 conserve explicitement l'identifiant de prompt demandé `agent-strategy-v4`, tout en ajoutant des instructions de recherche. Avant toute comparaison expérimentale sérieuse pré/post tools, le manifeste devra identifier distinctement la politique/capacité de tools afin de ne pas attribuer à tort deux environnements différents au seul même `prompt_version`.

## Changelog — 2026-09-22 — Batch 18.1 proposé

Audit de départ :

- GitHub `main = ca5077af00293ccca9794132ee0dd53a5b339911` ;
- `baseline-batch17` vérifié identique ;
- `docs/00_ETAT_ACTUEL.md` contenait encore textuellement le HEAD fonctionnel Batch 17 `25efe211...`, corrigé dans le patch documentaire ;
- architecture existante confirmée : un seul runner, validations de symbole en place, transport OpenAI partagé, journal de cycle/décision durable et `MarketStateBuilder` réutilisable.

Implémentation proposée : service de recherche provider-agnostic, adapter Kraken read-only, registry strict, tool loop bornée, traces causales, migration/reader API et composition de sources isolées.

Validation exécutée dans l'environnement de livraison :

```text
47 tests ciblés/non-régression passés
compileall code + test + migration : OK
```

Non exécuté dans cet environnement : suite complète `pytest backend`, Ruff, mypy, Alembic PostgreSQL réel et commandes Git. Ces validations restent obligatoires localement avant intégration.

## À décider après 18.1

- architecture exacte du Batch 18.2 pour choisir le symbole exécutable avant le snapshot final ;
- version formelle de la politique de tools dans `ExperimentManifest` ;
- éventuel support de snapshots FUTURE distincts ;
- utilité empirique de données supplémentaires ;
- recovery durable du ledger ;
- LIVE dans un batch séparé.
