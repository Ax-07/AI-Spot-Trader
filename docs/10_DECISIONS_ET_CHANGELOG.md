# 10 — Décisions et changelog

> Ce document conserve les principes courants et les décisions récentes. L'historique détaillé
> antérieur reste dans Git.

## Principes historiques conservés

Un seul Agent stratégique, PAPER d'abord, Risk autorité finale, aucun LLM direct vers Broker,
SPOT sans short/levier, Derivatives avec protections déterministes, audit durable, no-look-ahead,
backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

Référence GitHub auditée au démarrage du Batch 18.5 :

```text
HEAD réel main = 5cc2e2897d9a1dccba325f8a543b208360c6120d
docs: record batch 18.3 behavioral validation

dernier commit code validé = 4042e0b0e6394de788009229e3dae5924cd732d7
fix: support nested Kraken derivative margin schedules
```

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

## Décision Batch 18.3 — intégrée

### ADR-147 — Normaliser récursivement les schedules de marge publics Kraken sans relâcher le fail-closed

**INTÉGRÉE au commit `4042e0b`.** `marginSchedules` peut être une map de feuilles directes ou une
structure imbriquée par région/profil contenant des listes de tiers. Le parser aplatit uniquement
les feuilles qui portent des clés de marge reconnues et continue de rejeter les noms, types ou
feuilles incohérents.

La politique de marge n'est pas rendue plus agressive : l'API publique ne permettant pas de
prouver le tier privé applicable, le runtime conserve les `initialMargin` et `maintenanceMargin`
publics les plus stricts observés. Aucun tier de compte n'est deviné.

## Décisions Batch 18.5 — patch proposé

### ADR-148 — Créer `paper-experiment-v3` sans réinterpréter v1/v2

**PROPOSÉE.** Les nouvelles expériences Luna/Sol multi-marchés utilisent
`paper-experiment-v3`. `paper-experiment-v1` et `paper-experiment-v2` restent lisibles, validables
et calculés avec leurs champs historiques. Aucun ancien manifeste n'est promu implicitement vers
v3. Le champ `agent_protocol` est omis de la sérialisation lorsqu'il est absent.

### ADR-149 — Versionner l'univers exécutable par `symbol + market_type`

**PROPOSÉE.** La v3 persiste le tuple canonique de `ExecutableMarket`. La projection symbolique
historique `universe` reste présente pour compatibilité et doit correspondre exactement aux
symboles du tuple typé. Une différence SPOT/PERPETUAL change l'identité du run et du groupe.

### ADR-150 — Versionner le chemin de sélection à deux phases

**PROPOSÉE.** La politique active porte l'identité `agent-market-selection-v1` : tools éventuels
pendant `select_market`, acquisition du `MarketState`, puis décision finale sans nouveaux tools.
Le provider vérifie cette identité avant l'appel LLM.

### ADR-151 — Dériver l'identité tools des définitions réellement exposées

**PROPOSÉE.** `ReadOnlyToolRegistry.openai_tools_digest` est calculé sur le JSON canonique des
définitions OpenAI effectives triées. Les limites runtime sont enregistrées séparément : max calls,
timeout, taille résultat et maximum de `list_markets.limit` lu depuis le schéma effectif. Aucun
simple numéro manuel n'est la seule source d'identité de la capacité tools.

### ADR-152 — Étendre `experiment_group_digest` aux nouveaux facteurs contrôlés

**PROPOSÉE.** En v3, le group digest exclut uniquement `llm_model` et `replicate_index`. Univers
typé, protocole de sélection, prompt, Risk, coûts, analytics, source, tools et bornes sont contrôlés.
Une dérive sur l'un d'eux interdit l'appartenance au même groupe Luna/Sol.

### ADR-153 — Refuser une incohérence v3 avant l'appel LLM

**PROPOSÉE.** Le runner vérifie l'univers typé avant le cycle. Le provider vérifie modèle, prompt,
protocole de sélection, présence/budget tools, digest des définitions et bornes avant l'appel LLM.
La décision finale v3 exige une `MarketSelection`.

### ADR-154 — Ne pas créer de migration PostgreSQL pour 18.5

**PROPOSÉE.** Le manifeste reste dans les payloads JSON déjà persistés ; aucune colonne nouvelle
n'est nécessaire.

### ADR-155 — Garder le PAPER normal hors campagne expérimentale

**PROPOSÉE.** `experiment_manifest=None` reste valide. La v3 est opt-in pour les campagnes qui ont
besoin d'une identité contrôlée complète.

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

## Changelog — 2026-09-23 — Batch 18.3 intégré

Validation comportementale réelle :

- cross-symbol SPOT confirmé avec sélection d'un symbole différent du bootstrap ;
- univers mixte SPOT/PERPETUAL confirmé avec projection historique `NULL/NULL` dans `paper_runs` ;
- research de `PERPETUAL:ETH/USD` et `SPOT:BTC/USD` confirmé dans un même cycle ;
- plusieurs cycles mixtes sélectionnant SPOT ont terminé `COMPLETED / HOLD` ;
- branche `PERPETUAL:ETH/USD` validée en singleton jusqu'au `MarketState`, à la décision `HOLD`
  puis à `Risk=ALLOW/HOLD_NO_EXECUTION` ;
- les snapshots de recherche n'ont pas été promus en snapshots d'exécution.

Défaut découvert pendant le smoke :

- Kraken renvoie actuellement des `marginSchedules` imbriqués par région/profil ;
- l'ancien parser interprétait un conteneur comme une ligne de marge et échouait sur
  `initialMargin is invalid` ;
- correctif intégré au commit `4042e0b0e6394de788009229e3dae5924cd732d7` ;
- après correctif, 296 instruments publics Derivatives ont été parsés lors du diagnostic réel.

Validation locale opérateur après correctif :

```text
27 tests Kraken Derivatives ciblés : passed
pytest backend : 449 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF avant commit
```

Observations non transformées en garanties :

- aucune sélection PERPETUAL spontanée depuis l'univers mixte n'a été observée ;
- aucun fill réel n'a été produit pendant les smokes ;
- un timeout SPOT au stage `MARKET` a été observé une fois puis non reproduit sur plusieurs cycles ;
- un `LLMTransportError` au stage `MARKET_SELECTION` a été observé isolément.

## Changelog — 2026-09-23 — Batch 18.5 proposé

Audit confirmé : v2 versionnait modèle, prompt, univers symbolique, Risk, coûts, analytics et
source, mais pas l'univers typé ni l'environnement réel de sélection/tools. Le provider vérifiait
modèle/prompt/agressivité sans contrôler ces nouveaux facteurs actifs.

Le patch ajoute v3, l'identité tools dérivée des définitions effectives, les bornes runtime, les
contrôles provider/runner et les tests de compatibilité historique, sans modifier le prompt
stratégique, Risk, Broker ni le schéma PostgreSQL.

## À décider après 18.5

- recovery durable du ledger multi-actifs ;
- robustesse/observabilité des erreurs réseau/LLM après mesure ;
- enrichissement research mesuré ;
- campagnes Luna/Sol multi-marchés sous protocole v3 ;
- éventuel multi-quote avec conversion explicite ;
- FUTURE daté seulement après implémentation réelle ;
- LIVE dans un batch séparé.
