# AI Spot Trader

AI Spot Trader est une application expérimentale de **trading crypto SPOT pilotée par un agent IA unique**.

Le projet étudie jusqu'où un agent IA peut prendre des décisions de trading autonomes à partir d'un état de marché et de portefeuille structurés, tout en restant encadré par un **Risk Engine déterministe** qui conserve l'autorité finale avant toute exécution.

> **Statut :** le **Batch 14 — Comparaison contrôlée GPT-5.6 Luna / GPT-5.6 Sol est intégré** sur GitHub `main` au commit fonctionnel `dc60033f60bf5d98a68e6131a9320e575d46cc8d` (`feat: add controlled Luna Sol experiments`), après validation locale complète, push confirmé et working tree propre. Le Batch 13 reste référencé par `1747beb5efd1fe9763bc9b2d23f3a115575daaec`.

## Principes

- Exchange initial : **Kraken**.
- Trading **SPOT uniquement**.
- Aucun short, levier, margin, future ou perpetual.
- Actions stratégiques : `BUY`, `SELL`, `HOLD`.
- Impossible de vendre un actif non détenu.
- Un seul agent IA conserve la décision stratégique.
- Le Risk Engine déterministe autorise, réduit ou refuse une proposition.
- Seul Risk peut produire un `ExecutionIntent`.
- Aucune sortie LLM ne déclenche directement un Broker ou un ordre Kraken.
- Les premières versions restent exclusivement en **PAPER**.
- Frais, spread et slippage restent explicitement mesurables.
- Toutes les décisions, y compris HOLD et REJECT, sont auditables.
- Les erreurs techniques restent distinctes des décisions métier.
- Aucun secret dans prompts, logs, réponses API ou fichiers versionnés.
- Aucun look-ahead ni réécriture post-hoc.

Principe central : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Architecture

Le backend constitue l'application de trading. Le frontend est uniquement un cockpit de contrôle et de visualisation : fermer ou redémarrer le frontend ne doit jamais arrêter le moteur.

Stack :

- backend : Python, `asyncio`, FastAPI, Pydantic ;
- persistance : PostgreSQL, SQLAlchemy 2 async, `asyncpg`, Alembic ;
- frontend : Next.js, TypeScript, shadcn/ui, Tailwind CSS ;
- communication : REST tant qu'aucun besoin réel et bus d'événements canonique ne justifient un WebSocket ;
- Kraken et le fournisseur LLM restent derrière des interfaces dédiées.

```text
Kraken public data
        |
        v
   MarketState --------+
                       |
 PortfolioState -------+--> AgentInput --> Agent Luna/Sol
                                          BUY / SELL / HOLD
                                                  |
                                                  v
                                             Risk Engine
                                      ALLOW / MODIFY / REJECT
                                                  |
                            HOLD/REJECT -----------+--- tradable
                            aucun Broker                 |
                                                      v
                                             ExecutionIntent
                                               créé par Risk
                                                      |
                                                      v
                                               Paper Broker
                                                      |
                                             Fill(s) + ledger
                                                      |
                                                      v
                                            TradingCycleResult
                                                      |
                                                      v
                                     AuditedTradingCycleRunner
                                                      |
                                                      v
                                      PostgreSQL audit journal
                                                      |
                                                      v
                              durable read/query + analytics reducer
                                                      |
                                                      v
                                       FastAPI REST / analytics
                                                      |
                                                      v
                                          Next.js cockpit
```

## Agent IA

Le port canonique reste :

```python
LLMProvider.generate_decision(agent_input: AgentInput) -> DecisionCandidate
```

Le fournisseur ne produit que `action`, `symbol`, `proposed_quantity` et `rationale`. Les IDs et timestamps restent sous contrôle applicatif. GPT-5.6 Luna est le modèle initial ; Sol reste sélectionnable par configuration.

### Agressivité — Batch 13 intégré

Le Batch 13 fixe une interprétation **discrète et versionnée** des niveaux `1..10` sous `aggressiveness-map-v1`. Chaque niveau fournit un `AggressivenessContext` explicite (posture + instruction stratégique) transmis dans `AgentInput`.

L'agressivité peut influencer uniquement la **volonté stratégique d'agir** et la **quantité proposée par l'Agent**. Elle ne modifie jamais `RiskPolicy`, les balances, les positions détenues, la solvabilité BUY, les contraintes temporelles, les coûts PAPER ou l'autorité finale de Risk.

Le prompt Agent devient `agent-strategy-v2` afin de rendre cette frontière explicite. Une expérience contrôlée peut attacher à chaque `AgentInput` un `ExperimentManifest` `paper-experiment-v1` contenant notamment : niveau/mapping, modèle, prompt, univers, snapshot `RiskPolicy`, coûts PAPER, version analytics et identité des faits/dataset. Le digest SHA-256 du manifeste identifie la configuration expérimentale sans prétendre rendre le LLM déterministe.

Les comparaisons d'agressivité réutilisent directement les rapports `paper-analytics-v1` du Batch 12 : aucune métrique n'est recalculée avec une formule parallèle et aucun classement automatique n'est produit.

### Comparaison Luna / Sol — Batch 14 intégré

Le Batch 14 conserve `paper-experiment-v1` pour l'axe agressivité et introduit `paper-experiment-v2` pour une expérience dont **le modèle LLM est l'unique variable contrôlée**.

`paper-experiment-v2` ajoute une identité de groupe et une identité de répétition : `comparison_variable = LLM_MODEL`, `experiment_group_digest`, `replicate_index` et `replicate_count`. Pour une comparaison Luna/Sol, `source_digest` devient obligatoire afin d'identifier un dataset/snapshot figé. Le digest de groupe inclut agressivité, prompt, univers, `RiskPolicy`, coûts PAPER, source/dataset, fenêtre, version analytics et nombre de répétitions, mais exclut volontairement le modèle et l'index de répétition. Le digest complet du manifeste reste l'identité durable de chaque run.

`compare_model_runs(...)` exige un protocole apparié complet : toutes les répétitions déclarées doivent être présentes pour **Luna et Sol**. Il réutilise directement `PaperAnalyticsReport` (`paper-analytics-v1`) et expose factuellement P&L brut/net, coûts, drawdown, exposition, trades BUY/SELL, HOLD, REJECT, MODIFY, FAILED, points cumulés et séries quotidiennes. Il ne produit ni score composite, ni classement, ni « meilleur modèle » automatique.

Le support de plusieurs répétitions sert à conserver la dispersion observable du LLM sans prétendre à un déterminisme fournisseur. Aucune sélection post-hoc de répétitions n'est autorisée par le comparateur apparié.

## Trading PAPER canonique

`TradingCycleRunner.run_cycle()` exécute exactement un cycle et `TradingEngine` répète cette primitive séquentiellement. Un seul `MarketState` est partagé entre Agent, Risk et Broker pour le cycle, et un seul `PortfolioState` pré-cycle est partagé entre Agent et Risk.

- HOLD traverse Risk et produit un résultat complet sans intent.
- REJECT est une issue métier normale sans Broker.
- MODIFY utilise exactement la quantité autorisée par Risk.
- ALLOW transmet l'intent produit par Risk.
- Les erreurs Market/Portfolio/Agent/Risk/Broker restent des cycles `FAILED`, jamais des HOLD synthétiques.
- Le changement Luna/Sol ne modifie aucun chemin d'exécution : l'Agent continue de produire un `DecisionCandidate`, jamais un `ExecutionIntent`.

## Persistance durable — Batch 09 intégré

Le package `ai_spot_trader.persistence` utilise SQLAlchemy async, PostgreSQL et Alembic. `AuditedTradingCycleRunner` persiste le `TradingCycleResult` après le runner canonique sans dupliquer l'orchestration.

Le schéma `0001_audit_journal` conserve :

- `audit_cycles` ;
- `audit_decisions` ;
- `audit_risk_assessments` ;
- `audit_execution_intents` ;
- `audit_fills`.

Le graphe est transactionnel et idempotent par `cycle_id`. La persistance ne garantit pas encore un exactly-once global entre la mutation du ledger PAPER mémoire et le commit PostgreSQL ; la reconstruction/réconciliation après crash reste différée.

Les Batches 13/14 n'ajoutent pas de table ni de migration : `AgentInput` est déjà persisté intégralement en JSON/JSONB, donc le mapping, le manifeste, l'identité de groupe et les répétitions deviennent des faits durables et participent au `result_digest` du cycle.

## API FastAPI — Batch 10 intégré

Le Batch 10 expose une façade REST versionnée `/api/v1` sans seconde logique de trading.

### Observation

- `GET /health`
- `GET /api/v1/engine`
- `GET /api/v1/portfolio`
- `GET /api/v1/cycles`
- `GET /api/v1/cycles/latest`
- `GET /api/v1/cycles/{cycle_id}`
- `GET /api/v1/decisions`
- `GET /api/v1/risk-assessments`
- `GET /api/v1/executions`
- `GET /api/v1/errors/latest`
- `GET /api/v1/market/latest`
- `GET /api/v1/analytics`

Le Batch 14 n'ajoute aucun endpoint : le protocole expérimental reste une responsabilité backend/domaine, et le cockpit demeure une surface d'observation.

## Frontend cockpit — Batch 11 intégré

Le cockpit affiche l'état backend/moteur, portefeuille, marché durable, cycles, décisions, Risk, exécutions/fills, erreurs sanitizées et analytics PAPER. Il ne contient aucune logique Agent/Risk/Broker et n'est pas modifié au Batch 14.

## Analytics PAPER — Batch 12 intégré

Le reducer analytics reste **pur, déterministe et en lecture seule** au-dessus du journal durable. Les coûts sont lus dans les fills persistés, chaque point est valorisé au `MarketState` durable du même cycle et la reproductibilité des métriques repose sur `paper-analytics-v1` + digest des `result_digest`.

Les Batches 13/14 réutilisent ces rapports tels quels pour comparer factuellement l'axe expérimental autorisé : P&L brut/net, coûts, drawdown, exposition, trades, HOLD, REJECT, MODIFY, FAILED et séries quotidiennes/cumulées.

## Validation

### Batch 13 intégré

```text
Python                                  : 3.13.14
pytest backend                          : 249 tests passés, 2 warnings externes
ruff check backend                      : All checks passed
mypy backend/src backend/tests          : 81 fichiers sans erreur
git diff --check                        : aucune erreur, warnings LF -> CRLF uniquement
commit/push                             : 1747beb5efd1fe9763bc9b2d23f3a115575daaec
working tree après push                 : propre
```

### Batch 14 intégré

```text
pytest backend                          : 266 tests passés, 2 warnings externes
ruff check backend                      : All checks passed
mypy backend/src backend/tests          : 81 fichiers sans erreur
git diff --check                        : aucune erreur, warnings LF -> CRLF uniquement
commit/push                             : dc60033f60bf5d98a68e6131a9320e575d46cc8d
working tree après push                 : propre
```

La préparation ChatGPT avait également exécuté **34 tests ciblés** et `py_compile` sur les fichiers Python modifiés. Aucun test frontend additionnel n'était requis puisque le frontend n'a pas été modifié.

## Sécurité

- Aucun secret ou clé API réel ne doit être versionné, journalisé ou renvoyé par l'API.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- PAPER et LIVE restent explicitement séparés.
- Toute exécution doit continuer à passer par Risk.
- Le bind API par défaut reste local (`127.0.0.1`). Toute exposition distante des commandes lifecycle devra être protégée explicitement avant usage.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et développement. Il ne constitue pas un conseil financier et ne garantit aucun résultat de trading. La cible expérimentale de +4 %/jour reste une métrique de recherche, jamais une promesse.
