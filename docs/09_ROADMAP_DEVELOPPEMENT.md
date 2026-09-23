# 09 — Roadmap de développement

## Règle de lecture

Un batch est **intégré** uniquement après validation locale, commit et push confirmés sur GitHub
`main`. Un ZIP livré par ChatGPT reste un patch proposé tant que ces étapes ne sont pas réalisées.

## Historique intégré synthétique

- Batches 00–15.3 : socle SPOT PAPER, Agent, Risk, Broker, PostgreSQL, API/cockpit, analytics et expériences.
- Batch 16 : Kraken Derivatives PAPER, LONG/SHORT, marge ISOLATED, levier déterministe, funding, P&L et anti-reversal.
- Batch 16.2 : isolation durable par `paper_run_id`.
- Batch 16.3 : smokes LONG/SHORT contrôlés.
- Batch 16.5 : contexte PERPETUAL causal via `MarketStateBuilder` et bougies mark publiques.
- Batch 16.6 : validation comportementale Luna sans forcer BUY/SELL.
- Prompt `agent-strategy-v4` : localisation française.
- Batch 17 : durcissement fail-closed de la frontière Kraken Derivatives publique.
- Batch 18.1 : tools Agent read-only bornés, boucle Responses function calling, traces causales et migration `0003_agent_tool_traces`.
- Batch 18.2 : sélection causale du marché exécutable par le même Agent, univers PAPER typé, routeur SPOT/PERPETUAL, persistance/API multi-marchés, migration `0004_multi_market_selection` et analytics causal v3.
- Batch 18.3 : validation comportementale PAPER multi-marchés/cross-symbol et correction du parsing des `marginSchedules` Kraken Derivatives imbriqués.
- Batch 18.5 : protocole expérimental `paper-experiment-v3` pour versionner univers typé, sélection et capacité tools sans modifier la stratégie.
- Batch 18.6 : recovery/restart durable du ledger PAPER multi-actifs, migration `0005_paper_run_recovery`, handoff de runs et rollback mémoire fail-closed.
- Batch 18.7 : retries réseau bornés sur lectures Kraken publiques et Responses API
  pré-décision, classification d’erreurs et observabilité sanitizée sans retry des mutations.

HEAD GitHub vérifié après intégration du Batch 18.7 :

```text
0886216324106d941c3df0e30f074e24dbe1d33a
feat: add bounded network retry resilience
```

Dernier commit code intégré :

```text
0886216324106d941c3df0e30f074e24dbe1d33a
feat: add bounded network retry resilience
```

## Batch 18.2 — intégré

Le même Agent stratégique exécute deux phases causales :

```text
MarketSelectionInput
-> recherche/sélection par l'Agent
-> MarketSelection
-> acquisition du MarketState exécutable exact
-> AgentInput final
-> BUY/SELL/HOLD
-> Risk
-> Broker éventuel
```

Le périmètre intégré conserve les invariants suivants : aucun second Agent, aucun
scanner/ranking/opportunity score, séparation stricte research/execution, SPOT sans short/levier,
PERPETUAL linéaire uniquement lorsque supporté, Risk autorité finale et aucune exécution directe
par le LLM ou un tool.

Validation locale confirmée avant intégration 18.2 :

```text
pytest backend : 447 passed, 2 warnings
ruff check backend : OK
mypy backend/src : OK, 79 source files
Alembic 0003_agent_tool_traces -> 0004_multi_market_selection sur PostgreSQL : OK
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

## Batch 18.3 — intégré

### Objectif

Valider réellement le pipeline PAPER multi-marchés/cross-symbol de 18.2 avec le provider réel et
les sources Kraken publiques, sans forcer BUY/SELL ni transformer un résultat HOLD en échec.

### Résultats confirmés

- sélection cross-symbol SPOT réelle ;
- `paper_runs.execution_universe_payload` multi-marché réel avec projection historique
  `market_type/symbol = NULL` ;
- univers mixte `SPOT:BTC/USD + PERPETUAL:ETH/USD` chargé et recherché ;
- plusieurs cycles mixtes SPOT terminés `COMPLETED / HOLD` ;
- branche singleton `PERPETUAL:ETH/USD` validée de la sélection jusqu'au `MarketState`, à la
  décision `HOLD` et à `Risk=ALLOW/HOLD_NO_EXECUTION` ;
- catalogue public Derivatives parsé après correction : 296 instruments lors du smoke ;
- séparation research/execution observée : les snapshots de research restent des traces et le
  marché sélectionné est reacquis par la source d'exécution dédiée.

### Défaut découvert et intégré

Le payload public Kraken expose désormais notamment :

```text
marginSchedules
  -> région
    -> retail | professional
      -> [tiers de marge]
```

Le parser historique supposait une map directe `nom -> ligne de marge` et échouait avec
`KrakenPayloadError: initialMargin is invalid`. Le commit `4042e0b` aplatit les feuilles reconnues,
les valide toutes fail-closed et conserve la sémantique conservatrice existante : taux publics les
plus stricts retenus faute de tier privé prouvable.

### Validation locale confirmée

```text
pytest backend/tests/test_kraken_derivatives.py backend/tests/test_kraken_derivatives_context.py : 27 passed
pytest backend : 449 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF avant commit
```

Les deux warnings Starlette/AnyIO restent non bloquants.

### Limites honnêtes du smoke

- aucune sélection PERPETUAL spontanée n'a été observée depuis l'univers mixte ;
- aucun fill réel n'a été produit, les décisions observées ayant été `HOLD` ;
- un timeout SPOT au stage `MARKET` a été observé une fois puis non reproduit sur plusieurs cycles
  suivants ;
- un `LLMTransportError` au stage `MARKET_SELECTION` a été observé isolément.

Ces limites ne remettent pas en cause les branches validées, mais elles restent des axes de
robustesse/expérimentation à mesurer au lieu d'être déclarées résolues.

## Batch 18.5 — intégré

### Objectif

Versionner scientifiquement l'environnement Agent/tools/sélection déjà utilisé par le pipeline
multi-marché, sans modifier la stratégie de trading.

### Décisions intégrées

- nouvelle identité `paper-experiment-v3` pour les **nouveaux** manifestes multi-marchés ;
- conservation stricte de `paper-experiment-v1` et `paper-experiment-v2` comme identités
  historiques ;
- univers contrôlé v3 = tuple déterministe de `ExecutableMarket(symbol, market_type)` ;
- protocole de sélection causal explicitement identifié ;
- tools exposés pendant la sélection et interdits pendant la décision finale canonique ;
- identité tools = digest des définitions OpenAI effectives, pas simple version manuelle ;
- bornes contrôlées = max calls, timeout, taille résultat et maximum `list_markets.limit` ;
- tous ces facteurs entrent dans le `experiment_group_digest` v3 ; `llm_model` et
  `replicate_index` restent les seules exclusions volontaires pour les comparaisons modèle ;
- contrôles provider/runner avant appel Agent lorsqu'un manifeste v3 est fourni ;
- aucune migration PostgreSQL, le JSON persistant existant restant suffisant ;
- `experiment_manifest=None` reste valide pour le PAPER normal.

### Validation et intégration

```text
pytest ciblé experiments/provider/tools/market-selection : 136 passed
pytest backend : 460 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
commit : 84548d23efda0b0a8e2c1350bacc830c1de34140
```

Le commit a été poussé sur `origin/main` et le working tree opérateur était propre après push.

## Batch 18.6 — intégré

### Objectif

Rendre le recovery/restart du ledger PAPER multi-actifs déterministe et durable sans rejouer une
décision Agent, un `ExecutionIntent` ou un `Fill` historique.

### Audit confirmé

Avant 18.6 :

- `AppRuntime.initialize()` créait systématiquement un run durable neuf ;
- `build_paper_runtime()` créait systématiquement un `PaperPortfolioLedger` depuis le capital
  initial configuré ;
- les cycles, décisions, risk assessments, intents, fills et snapshots de portefeuille étaient
  durables ;
- le ledger courant restait process-local ;
- le Broker pouvait muter le ledger avant que `AuditedTradingCycleRunner` ne committe le graphe ;
- aucun recovery canonique n'était câblé au restart.

### Design intégré

- conserver un nouveau `paper_run_id` par lifetime backend ;
- relier le nouveau run avec `resumed_from_paper_run_id` ;
- persister `initial_portfolio_payload` et `current_portfolio_payload` ;
- identité de recovery : `paper-ledger-recovery-v1` ;
- migration `0005_paper_run_recovery` ;
- mise à jour de `current_portfolio_payload` dans la même transaction que le cycle `COMPLETED` ;
- checkpoint mémoire avant chaque cycle audité ;
- rollback du ledger pour les cycles `FAILED`, les erreurs de persistance et les replays
  idempotents ;
- restart depuis `current_portfolio_payload` sans replay historique ;
- analytics du run courant rejouée sur la lignée `resumed_from_paper_run_id` pour conserver les
  métriques cumulées à travers les restarts ;
- validation de l'univers, des balances, de l'inventaire SPOT et des positions PERPETUAL ;
- migration legacy uniquement lorsque l'état terminal est non ambigu ; sinon fail-closed.

### État restauré

- cash disponible ;
- inventaire SPOT ;
- positions PERPETUAL LONG/SHORT ;
- quantité, entry price, mark, notional ;
- realized/unrealized P&L ;
- levier, marge et maintenance ;
- cumulative funding et `funding_updated_at` ;
- liquidation price portée par le dernier snapshot durable.

Les coûts/frais déjà réalisés restent reflétés dans le cash et auditables dans les fills historiques.

### Validation locale et intégration

```text
Alembic 0004_multi_market_selection -> 0005_paper_run_recovery sur PostgreSQL : OK
pytest ciblé recovery/persistence/trading/broker : 75 passed
pytest backend : 468 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
commit : 9642ec394357fe1e1807b538a2353bdc6d062f46
```

Le commit a été poussé sur `origin/main` et le working tree opérateur était propre après push.

## Batch 18.7 — intégré

### Objectif

Durcir les pannes transitoires observées sur Kraken public et Responses API sans modifier la
stratégie, sans masquer les erreurs et sans introduire de double exécution.

### Audit retenu

- le WebSocket SPOT possède déjà un reconnect borné ;
- les clients REST publics SPOT/Derivatives n'avaient aucun retry ;
- le client Responses API n'avait aucun retry ;
- les erreurs HTTP/transport étaient agrégées en types trop génériques pour diagnostiquer 429,
  5xx, timeout et connectivité depuis l'audit ;
- le runner transforme déjà toute panne technique en cycle `FAILED`, jamais en `HOLD` ;
- `AuditedTradingCycleRunner` 18.6 restaure déjà le checkpoint ledger pour tout cycle `FAILED` ;
- le Broker est state-mutating et ne doit recevoir aucun retry générique.

### Implémentation intégrée

- `core/retry.py` : budget borné + backoff exponentiel + logs sanitaires ;
- REST Kraken public : 3 tentatives max uniquement sur timeout/transport, 408, 429 et 5xx ;
- Responses API : 2 tentatives max sur les mêmes classes transitoires avant décision durable ;
- 4xx permanent, JSON/payload invalide et contrat provider invalide : échec immédiat ;
- wrappers REST placés avant toute mutation de `MarketState`/ledger, jamais autour du snapshot
  PERPETUAL complet ;
- types d'erreur dédiés pour timeout, réseau, rate-limit, 5xx et HTTP permanent ;
- aucun retry Risk, Broker, audit DB ou recovery ;
- aucun jitter dans ce batch, afin de conserver des tests déterministes sur le runtime mono-Agent.

### Compatibilité visée

Aucun bump de `agent-strategy-v4`, `paper-experiment-v1/v2/v3` ou
`paper-ledger-recovery-v1`. Aucune migration PostgreSQL.

### Validation locale et intégration

```text
pytest backend/tests/test_network_resilience.py backend/tests/test_openai_client.py : 27 passed
pytest backend/tests/test_trading_engine.py backend/tests/test_market_selection_runner.py backend/tests/test_paper_recovery.py : 55 passed
pytest backend : 487 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 81 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Aucune migration PostgreSQL n'est ajoutée par ce batch. Intégration confirmée sur `main` au commit
`0886216324106d941c3df0e30f074e24dbe1d33a`
(`feat: add bounded network retry resilience`). Le working tree opérateur était propre après push.

## Prochains candidats après 18.7

Aucune priorité architecturale nouvelle n'est décidée ici. Candidats :

- mesurer le taux réel de retries, 429, 5xx et timeouts sur plusieurs cycles PAPER avant tout
  ajustement de budget ou ajout de jitter ;
- enrichissement mesuré des données de recherche : order book, trades, funding historique, news ;
- campagnes Luna/Sol sur univers multi-marché sous `paper-experiment-v3` ;
- valorisation multi-quote avec FX explicite seulement si le besoin est mesuré ;
- FUTURE daté seulement si le domaine correspondant est réellement implémenté ;
- LIVE toujours dans un batch séparé.
