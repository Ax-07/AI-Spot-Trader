# 10 — Décisions et changelog

> Ce document conserve les principes courants et les décisions récentes. L'historique détaillé
> antérieur reste dans Git.

## Principes historiques conservés

Un seul Agent stratégique, PAPER d'abord, Risk autorité finale, aucun LLM direct vers Broker,
SPOT sans short/levier, Derivatives avec protections déterministes, audit durable, no-look-ahead,
backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

Commit d'intégration code du Batch 18.7 :

```text
0886216324106d941c3df0e30f074e24dbe1d33a
feat: add bounded network retry resilience
```

Base auditée au démarrage du Batch 18.6 :

```text
70457125c5a238fe9b798463081c8769d8879d5e
docs: record batch 18.5 integration
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

## Décisions Batch 18.5 — intégrées

### ADR-148 — Créer `paper-experiment-v3` sans réinterpréter v1/v2

**INTÉGRÉE.** Les nouvelles expériences Luna/Sol multi-marchés utilisent
`paper-experiment-v3`. `paper-experiment-v1` et `paper-experiment-v2` restent lisibles, validables
et calculés avec leurs champs historiques. Aucun ancien manifeste n'est promu implicitement vers
v3. Le champ `agent_protocol` est omis de la sérialisation lorsqu'il est absent.

### ADR-149 — Versionner l'univers exécutable par `symbol + market_type`

**INTÉGRÉE.** La v3 persiste le tuple canonique de `ExecutableMarket`. La projection symbolique
historique `universe` reste présente pour compatibilité et doit correspondre exactement aux
symboles du tuple typé. Une différence SPOT/PERPETUAL change l'identité du run et du groupe.

### ADR-150 — Versionner le chemin de sélection à deux phases

**INTÉGRÉE.** La politique active porte l'identité `agent-market-selection-v1` : tools éventuels
pendant `select_market`, acquisition du `MarketState`, puis décision finale sans nouveaux tools.
Le provider vérifie cette identité avant l'appel LLM.

### ADR-151 — Dériver l'identité tools des définitions réellement exposées

**INTÉGRÉE.** `ReadOnlyToolRegistry.openai_tools_digest` est calculé sur le JSON canonique des
définitions OpenAI effectives triées. Les limites runtime sont enregistrées séparément : max calls,
timeout, taille résultat et maximum de `list_markets.limit` lu depuis le schéma effectif. Aucun
simple numéro manuel n'est la seule source d'identité de la capacité tools.

### ADR-152 — Étendre `experiment_group_digest` aux nouveaux facteurs contrôlés

**INTÉGRÉE.** En v3, le group digest exclut uniquement `llm_model` et `replicate_index`. Univers
typé, protocole de sélection, prompt, Risk, coûts, analytics, source, tools et bornes sont contrôlés.
Une dérive sur l'un d'eux interdit l'appartenance au même groupe Luna/Sol.

### ADR-153 — Refuser une incohérence v3 avant l'appel LLM

**INTÉGRÉE.** Le runner vérifie l'univers typé avant le cycle. Le provider vérifie modèle, prompt,
protocole de sélection, présence/budget tools, digest des définitions et bornes avant l'appel LLM.
La décision finale v3 exige une `MarketSelection`.

### ADR-154 — Ne pas créer de migration PostgreSQL pour 18.5

**INTÉGRÉE.** Le manifeste reste dans les payloads JSON déjà persistés ; aucune colonne nouvelle
n'est nécessaire.

### ADR-155 — Garder le PAPER normal hors campagne expérimentale

**INTÉGRÉE.** `experiment_manifest=None` reste valide. La v3 est opt-in pour les campagnes qui ont
besoin d'une identité contrôlée complète.

## Décisions Batch 18.6 — intégrées

### ADR-156 — Conserver un nouveau `paper_run_id` par lifetime backend et relier les reprises

**INTÉGRÉE.** Le recovery ne réouvre pas une row historique. Le nouveau run porte
`resumed_from_paper_run_id` vers le run parent. Cela préserve l'isolation analytique historique et
rend la continuité runtime explicite.

Si le parent était resté ouvert après crash, son `ended_at` est renseigné lors du handoff. Une
contrainte unique sur `resumed_from_paper_run_id` interdit deux successeurs directs du même run.

### ADR-157 — Persister l'état initial et courant du ledger dans `paper_runs`

**INTÉGRÉE.** La migration `0005_paper_run_recovery` ajoute :

- `resumed_from_paper_run_id` ;
- `recovery_version` ;
- `initial_portfolio_payload` ;
- `current_portfolio_payload`.

Les nouveaux runs utilisent `paper-ledger-recovery-v1`. Le snapshot courant contient le
`PortfolioState` canonique complet : balances, inventaire SPOT et positions PERPETUAL avec marge,
P&L, funding et timestamps correspondants.

### ADR-158 — Faire avancer le snapshot courant dans la même transaction que le cycle

**INTÉGRÉE.** `SqlAlchemyCycleAuditRepository` met à jour `current_portfolio_payload` uniquement
pour un cycle `COMPLETED`, dans la transaction qui persiste le graphe audit.

Pour un cycle exécuté, la source est `portfolio_state_after`. Pour un cycle sans exécution, la
source est `AgentInput.portfolio_state`, qui inclut les éventuels mark/funding causaux acquis avant
la décision.

### ADR-159 — Un cycle `FAILED` n'est pas un commit de ledger

**INTÉGRÉE.** `AuditedTradingCycleRunner` capture un checkpoint du ledger avant le cycle. Un
résultat `FAILED` restaure ce checkpoint avant d'écrire le failure durable.

Cela évite qu'un mark/funding ou une mutation partielle non représentée par un état durable devienne
silencieusement la nouvelle source de vérité.

### ADR-160 — Rollback mémoire si l'audit durable échoue ou n'insère rien

**INTÉGRÉE.** Si l'écriture PostgreSQL échoue après une mutation PAPER, le checkpoint est restauré
et le runner reste fail-closed. Si `record()` retourne `False` pour un replay exact idempotent, le
checkpoint est également restauré afin de ne pas doubler l'exposition mémoire.

### ADR-161 — Reprendre depuis le snapshot, jamais depuis un replay de décisions/fills

**INTÉGRÉE.** Au restart, le runtime restaure le `PaperPortfolioLedger` depuis
`current_portfolio_payload`. Il ne relance ni `MarketSelection`, ni LLM, ni Risk, ni Broker et ne
réapplique aucun `Fill`.

Cette règle empêche toute régénération historique, look-ahead ou double traitement.

### ADR-162 — Migrer les runs legacy uniquement lorsqu'ils sont non ambigus

**INTÉGRÉE.** Pour un run antérieur à `paper-ledger-recovery-v1`, le dernier cycle `COMPLETED`
peut fournir un snapshot terminal durable. En revanche, un run legacy terminant par un cycle
`FAILED`, un payload invalide ou un état manquant provoque un refus fail-closed.

Aucune reconstruction approximative n'est autorisée.

### ADR-163 — Refuser une reprise incompatible avec l'univers courant

**INTÉGRÉE.** Le recovery exige le même `execution_universe`. Les balances de règlement, actifs
SPOT détenus et symboles PERPETUAL sont validés contre la configuration. Une incohérence bloque le
démarrage au lieu de créer un ledger partiellement plausible.

### ADR-164 — Faire suivre à l'analytics la lignée de recovery explicite

**INTÉGRÉE.** `paper_analytics_for_run()` remonte `resumed_from_paper_run_id` et rejoue les cycles
des runs parents avant ceux du run demandé. Les faits ne changent pas de propriétaire et aucun
cycle n'est copié ; la lecture devient seulement chain-aware. Cela conserve P&L, frais, funding,
drawdown et compteurs cumulés après restart tout en gardant un `paper_run_id` distinct par session.

## Décisions Batch 18.7 — intégrées

### ADR-165 — Réessayer uniquement les opérations prouvées répétables

**INTÉGRÉE.** Les retries automatiques sont confinés aux lectures REST publiques Kraken et à un
appel transport Responses API avant création d'un artefact stratégique durable. Aucun retry n'est
ajouté autour de Risk, Broker, persistance, recovery ou d'un snapshot PERPETUAL complet.

Pour Kraken Derivatives, la frontière de retry reste sous `KrakenDerivativesMarketDataSource` :
`fetch_instruments`, `fetch_ticker` et `fetch_mark_history` peuvent être répétés, mais
`mark_derivative_market()` et l'accrual funding ne le sont jamais.

### ADR-166 — Classer explicitement transitoire et permanent

**INTÉGRÉE.** Timeout/transport, HTTP 408, HTTP 429 et HTTP 5xx sont transitoires sur les frontières
réessayables. Les autres 4xx sont permanents. Un JSON invalide, un payload Kraken invalide ou un
contrat provider LLM invalide reste fail-closed et n'est pas rejoué.

Les erreurs finales sont typées sans recopier le corps de réponse : timeout, réseau, rate-limit,
serveur 5xx ou HTTP permanent. Cette granularité est visible dans `failure_error_type` sans
migration de schéma.

### ADR-167 — Borner les budgets et conserver un backoff déterministe

**INTÉGRÉE.** Les lectures REST publiques Kraken ont au maximum 3 tentatives, avec backoff
exponentiel borné à partir de 250 ms. Un appel Responses API a au maximum 2 tentatives, avec un
premier délai de 500 ms. Aucune boucle infinie n'est possible.

Aucun jitter n'est ajouté dans 18.7 : le runtime visé reste mono-Agent et séquentiel, et les tests
restent déterministes. Un jitter ne sera envisagé que si une contention concurrente réelle est
mesurée.

### ADR-168 — Les deadlines de stage restent l'autorité temporelle supérieure

**INTÉGRÉE.** `TradingCycleTimeouts.market_seconds` et `agent_seconds` restent des plafonds absolus.
La couche de retry n'étend jamais ces deadlines. Un timeout de stage peut donc interrompre le budget
restant, ce qui préserve le fail-closed et évite qu'une politique transport rallonge silencieusement
un cycle.

### ADR-169 — Observer sans exposer les causes sensibles

**INTÉGRÉE.** Chaque retry journalise seulement l'opération, le numéro de tentative, le type
d'erreur, le statut HTTP éventuel et le délai. Le message provider, le corps de réponse, les prompts,
les clés et autres secrets ne sont pas journalisés par cette couche.

Aucun nouveau backend métrique n'est introduit. Le couple logs + stage/type d'échec durable est la
surface d'observabilité de 18.7 ; Prometheus/OpenTelemetry reste une décision séparée.

## Changelog — 2026-09-22 — Batch 18.2 intégré

Audit de départ :

- GitHub `main = e158ea71d9f7cdf010d98d41be1968440c640a53` ;
- Batch 18.1 confirmé intégré malgré des documents encore marqués « patch proposé » ;
- verrou historique confirmé dans provider + runner autour du `MarketState` initial ;
- modèle `paper_runs.market_type/symbol` confirmé insuffisant pour un run multi-marché honnête ;
- séparation research/execution du Batch 18.1 confirmée et conservée.

Implémentation intégrée : contrats de sélection et univers typé, deux phases du même Agent, routeur
d'exécution causal, configuration multi-marché, migration/persistance/API, analytics multi-actifs
causal et tests de fail-closed/compatibilité.

Validation locale confirmée avant intégration :

```text
pytest backend : 447 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
Alembic 0003_agent_tool_traces -> 0004_multi_market_selection sur PostgreSQL : OK
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

## Changelog — 2026-09-23 — Batch 18.3 intégré

Validation comportementale réelle : cross-symbol SPOT, univers mixte SPOT/PERPETUAL, research des
deux familles, plusieurs cycles SPOT `COMPLETED / HOLD` et branche PERPETUAL singleton jusqu'à
Risk. Le défaut de `marginSchedules` imbriqués a été corrigé au commit
`4042e0b0e6394de788009229e3dae5924cd732d7`.

Validation locale opérateur :

```text
27 tests Kraken Derivatives ciblés : passed
pytest backend : 449 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF avant commit
```

## Changelog — 2026-09-23 — Batch 18.5 intégré

Audit confirmé : v2 versionnait modèle, prompt, univers symbolique, Risk, coûts, analytics et
source, mais pas l'univers typé ni l'environnement réel de sélection/tools. Le Batch 18.5 ajoute
v3, l'identité tools dérivée des définitions effectives, les bornes runtime et les contrôles
provider/runner sans modifier le prompt stratégique, Risk, Broker ni le schéma PostgreSQL.

Validation locale opérateur avant intégration :

```text
pytest ciblé experiments/provider/tools/market-selection : 136 passed
pytest backend : 460 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Intégration confirmée sur `main` au commit
`84548d23efda0b0a8e2c1350bacc830c1de34140`.

## Changelog — 2026-09-23 — Batch 18.6 intégré

Audit de départ : GitHub `main = 70457125c5a238fe9b798463081c8769d8879d5e`, commit documentaire
18.5 ; dernier commit code `84548d23...`.

Constats de départ :

- confirmé : cycle/audit/fills et snapshots étaient persistés ;
- confirmé : le ledger et le Broker partageaient un état process-local canonique ;
- confirmé : un restart recréait capital initial + nouveau run ;
- confirmé : l'idempotence du graphe de cycle existait par `cycle_id + digest` ;
- manquant : snapshot courant durable du ledger et handoff de restart ;
- manquant : rollback mémoire si mutation PAPER puis panne d'audit ;
- décision retenue : nouveau run lié plutôt que réouverture du même run.

Implémentation intégrée : migration `0005_paper_run_recovery`, snapshots initial/courant du ledger,
handoff `resumed_from_paper_run_id`, restore SPOT/PERPETUAL, rollback mémoire à la frontière
d'audit, reprise legacy fail-closed et analytics chain-aware.

Validation locale opérateur :

```text
Alembic 0004_multi_market_selection -> 0005_paper_run_recovery sur PostgreSQL : OK
pytest ciblé recovery/persistence/trading/broker : 75 passed
pytest backend : 468 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Intégration confirmée sur `main` au commit
`9642ec394357fe1e1807b538a2353bdc6d062f46`
(`feat: add durable PAPER ledger recovery`). Le working tree opérateur était propre après push.

## Changelog — 2026-09-23 — Batch 18.7 intégré

Audit de départ : GitHub `main = c5ddd2c6c1df74c2166a758cfb1cdf02d665d8d2`, commit documentaire
`docs: record batch 18.6 integration`; dernier commit code intégré `9642ec394357...`.

Constats : REST public Kraken et Responses API n'avaient pas de retry, le WebSocket SPOT avait déjà
un reconnect borné, le runner produisait déjà `FAILED` sans faux HOLD et le rollback 18.6 protégeait
le ledger. Le batch intègre donc uniquement des retries sous les frontières répétables, une
classification d'erreurs plus fine et des logs sanitaires, sans migration ni changement de
stratégie.

Validation locale opérateur confirmée après application du correctif statique :

```text
pytest réseau/LLM ciblé : 27 passed
pytest trading/market-selection/recovery ciblé : 55 passed
pytest backend : 487 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 81 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Les validations ChatGPT antérieures incluent en complément un harness transport déterministe de
8 tests, compilation Python, contrôle whitespace et scan de motifs de secrets. Aucune migration
PostgreSQL n'est introduite. Intégration confirmée sur `main` au commit
`0886216324106d941c3df0e30f074e24dbe1d33a`
(`feat: add bounded network retry resilience`) ; le working tree opérateur était propre après push.

## À décider après 18.7

- mesure réelle des taux de retry, 429, 5xx, timeout et erreurs réseau ;
- ajout éventuel de jitter si une contention concurrente réelle apparaît ;
- exposition éventuelle des budgets de retry dans `Settings` si un besoin opératoire est mesuré ;
- backend métrique dédié (Prometheus/OpenTelemetry ou autre) seulement si justifié ;
- enrichissement research mesuré et campagnes Luna/Sol multi-marchés restent séparés ;
- multi-quote/FX, FUTURE daté et LIVE restent hors de ce batch.
