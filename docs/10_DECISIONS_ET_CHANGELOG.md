# 10 — Décisions et changelog

> Ce document conserve les principes courants et les décisions récentes. L'historique détaillé
> antérieur reste dans Git.

## Principes historiques conservés

Un seul Agent stratégique, PAPER d'abord, Risk autorité finale, aucun LLM direct vers Broker,
SPOT sans short/levier, Derivatives avec protections déterministes, audit durable, no-look-ahead,
backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

Référence intégrée actuelle :
`e19255df2ff0f2d432034808abeacca88832d403`
(`feat: add causal executable market selection`).

## Statut du Batch 18.1

Les ADR-127 à ADR-135 du Batch 18.1 ont été **INTÉGRÉES** au commit `e158ea7` et restent actives :

- tools factuels read-only uniquement ;
- recherche cross-symbol sans exécution cross-symbol dans 18.1 ;
- boucle Responses stateless/bornée ;
- sources research isolées ;
- traces causales durables ;
- digest incluant les recherches ;
- erreurs sanitizées et fail-closed ;
- Risk unique frontière d'exécution ;
- dette explicite de versionnement de la politique de tools.

La limitation cross-symbol d'ADR-128 est précisément celle que le Batch 18.2 fait évoluer par un
nouveau pipeline causal, sans réutiliser le mauvais `MarketState`.

## Décisions Batch 18.2 — intégrées

### ADR-136 — Séparer sélection de marché et décision finale avec le même Agent

**INTÉGRÉE.** Un cycle multi-marché possède deux appels stratégiques au même
`OpenAIDecisionProvider` : sélection, puis décision finale après acquisition du marché choisi.
Aucun second Agent n'est introduit.

### ADR-137 — L'univers exécutable est typé par `symbol + market_type`

**INTÉGRÉE.** `risk_allowed_pairs` reste une whitelist Risk de symboles, mais ne peut pas à lui
seul représenter SPOT vs PERPETUAL. `ExecutableMarket` et
`AI_SPOT_TRADER_PAPER_EXECUTABLE_MARKETS` fournissent cette frontière explicite.

Seuls SPOT et PERPETUAL sont autorisés. FUTURE daté reste non exécutable.

### ADR-138 — La sélection est un artefact durable explicite

**INTÉGRÉE.** `MarketSelection` contient identité, timestamp, symbole, type, rationale, traces et
digest. La sélection ne doit pas être reconstruite à partir d'un texte libre de rationale.

Une panne après sélection conserve cet artefact.

### ADR-139 — Aucun snapshot de recherche ne devient un snapshot d'exécution

**INTÉGRÉE.** Le marché sélectionné est reacquis via `RoutedExecutableMarketDataSource` et les
sources execution dédiées. Le routeur valide le couple typé et le contrat Derivatives mais ne
classe ni ne choisit jamais les marchés.

### ADR-140 — La phase finale ne relance pas les tools dans le chemin 18.2

**INTÉGRÉE.** Les recherches de sélection sont attachées à `MarketSelection` puis transmises dans
`AgentInput`. Après acquisition du `MarketState` exécutable, la décision finale est structurée mais
sans nouvelle recherche. Cela maintient une frontière causale lisible : recherches -> sélection ->
snapshot exécutable -> décision.

Le chemin historique 18.1 sans `MarketSelection` garde sa boucle de tools optionnelle.

### ADR-141 — Recapturer le portefeuille après acquisition du marché sélectionné

**INTÉGRÉE.** La phase de sélection reçoit le portefeuille complet avant recherche. Le runner
recapture ensuite le portefeuille après le snapshot d'exécution. C'est nécessaire car un snapshot
PERPETUAL d'exécution peut marquer une position existante et accumuler du funding.

Les sources research restent sans `market_sink`.

### ADR-142 — `paper_runs` persiste l'univers au lieu d'inventer `MULTI`

**INTÉGRÉE.** La migration `0004_multi_market_selection` ajoute
`execution_universe_payload JSONB NOT NULL` et rend `market_type`/`symbol` nullables.

Un singleton conserve la projection historique. Un vrai multi-marché met les deux colonnes à
`NULL`. Le downgrade est refusé tant qu'un run multi-marché existe.

### ADR-143 — Le journal de cycle persiste l'entrée et le résultat de sélection

**INTÉGRÉE.** `audit_cycles` reçoit `market_selection_input_payload` et
`market_selection_payload`, tous deux nullable pour compatibilité historique. Le digest global les
inclut.

Le résumé API expose le marché typé sélectionné même si la décision finale n'existe pas encore.

### ADR-144 — Analytics multi-marchés utilise seulement des marks SPOT causaux durables

**INTÉGRÉE.** `paper-analytics-v3` conserve le dernier prix SPOT déjà rencontré dans le journal
pour chaque actif détenu. Aucun prix actuel externe ou futur n'est recherché lors du replay.

Si un actif n'a pas de mark causal, le calcul échoue explicitement.

### ADR-145 — Une quote de règlement commune est requise dans Batch 18.2

**INTÉGRÉE.** Tous les marchés de `PAPER_EXECUTABLE_MARKETS` doivent avoir la même quote que
`paper_settlement_asset`. Le batch n'introduit aucune conversion FX implicite ou non auditée.

### ADR-146 — Conserver un chemin mono-marché compatible pendant la transition

**INTÉGRÉE.** `TradingCycleRunner` accepte encore le couple historique `market_data + symbol`, et
`OpenAIDecisionProvider.generate_decision()` conserve le comportement 18.1 en l'absence de
`MarketSelection`. La composition PAPER canonique utilise néanmoins le nouveau chemin.

## Changelog — 2026-09-22 — Batch 18.2 intégré

Audit de départ :

- GitHub `main = e158ea71d9f7cdf010d98d41be1968440c640a53` ;
- Batch 18.1 confirmé intégré malgré des documents encore marqués « patch proposé » ;
- verrou historique confirmé dans provider + runner autour du `MarketState` initial ;
- modèle `paper_runs.market_type/symbol` confirmé insuffisant pour un run multi-marché honnête ;
- séparation research/execution du Batch 18.1 confirmée et conservée.

Implémentation intégrée :

- contrats de sélection et univers typé ;
- deux phases du même Agent ;
- routeur d'exécution causal ;
- configuration multi-marché ;
- migration/persistance/API ;
- analytics multi-actifs causal ;
- tests de fail-closed et compatibilité.

Validation locale confirmée avant intégration :

```text
pytest backend : 447 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
Alembic 0003_agent_tool_traces -> 0004_multi_market_selection sur PostgreSQL : OK
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Les deux warnings de dépendances Starlette/AnyIO sont non bloquants et ne constituent pas un
échec du batch.

Le smoke PAPER multi-marchés / cross-symbol n'est pas confirmé comme exécuté dans les validations
fournies.

## À décider après 18.2

- intégrer la politique de sélection/tools dans le protocole expérimental versionné ;
- recovery durable du ledger multi-actifs ;
- éventuel multi-quote avec conversion explicite ;
- FUTURE daté et contrats supplémentaires seulement après implémentation réelle ;
- LIVE dans un batch séparé.
