# 01 — Project Master

## 1. Rôle de ce document

Ce document est la spécification fonctionnelle et architecturale principale d'**AI Spot Trader**. Les détails spécialisés sont complétés par `02_ARCHITECTURE_TECHNIQUE.md`, `03_AGENT_TRADING_RISK.md`, `09_ROADMAP_DEVELOPPEMENT.md` et `10_DECISIONS_ET_CHANGELOG.md`.

Statuts utilisés : **Confirmé**, **Proposé**, **À décider** et **Hors périmètre pour l'instant**.

---

## 2. Vision et invariants

**Confirmé.** AI Spot Trader est une application expérimentale de trading crypto **SPOT** pilotée par **un agent IA unique**. L'agent conserve la décision stratégique ; les composants déterministes construisent le contexte, imposent les contraintes de risque, exécutent en PAPER, persistent les faits et mesurent les résultats.

Invariants principaux :

- Kraken est l'exchange initial ;
- SPOT uniquement : aucun short, levier, margin, future ou perpetual ;
- actions stratégiques `BUY`, `SELL`, `HOLD` ;
- aucune vente d'un actif non détenu ;
- GPT-5.6 Luna pour les premiers essais, Sol sélectionnable par configuration ;
- Luna et Sol utilisent le **même provider canonique** ;
- Risk Engine déterministe avec autorité finale ;
- aucune sortie LLM ne déclenche directement une exécution ;
- premières versions exclusivement en PAPER ;
- frais, spread et slippage pris en compte ;
- toutes les décisions, y compris `HOLD`, sont journalisables durablement ;
- les erreurs techniques restent distinctes des décisions métier ;
- aucun secret dans Git, prompts ou logs ;
- aucun look-ahead ;
- frontend indépendant du moteur backend ;
- un seul cycle de trading à la fois ;
- la persistance observe les faits métier, elle ne crée aucune stratégie.

La cible expérimentale de **+4 %/jour** reste une métrique de recherche très agressive, jamais une garantie, une hypothèse de rendement attendu ou une obligation de forcer des trades.

---

## 3. Périmètre V0 / V1

### V0 — socle expérimental

V0 est atteinte lorsque le backend peut, sans frontend obligatoire :

1. recevoir des données publiques Kraken ;
2. construire un `MarketState` cohérent ;
3. maintenir un `PortfolioState` PAPER ;
4. obtenir une décision structurée de l'agent Luna ;
5. soumettre toute proposition au Risk Engine, y compris HOLD ;
6. produire `ALLOW`, `MODIFY` ou `REJECT` ;
7. simuler l'exécution autorisée via le Paper Broker ;
8. mettre à jour le portefeuille ;
9. répéter le cycle de manière autonome et séquentielle ;
10. journaliser durablement les cycles ;
11. exposer suffisamment d'état via FastAPI.

Le Batch 08 réalise le point 9. Le Batch 09 réalise le socle durable du point 10. Le Batch 10 réalise le socle REST du point 11 et est **intégré sur `main`** au commit fonctionnel `e6bcfd4dd345c934769b2f90fa7822232a80dd80`.

### V1 — cockpit et expérimentation instrumentée

V1 ajoute le cockpit Next.js/shadcn, historique, analytics P&L/drawdown/coûts/exposition, replay reproductible, expérimentations d'agressivité et comparaison Luna/Sol. Le LIVE n'est pas une condition de V1.

Le Batch 11 fournit le socle cockpit et est **intégré sur `main`** au commit `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7`. Le Batch 12 fournit les analytics PAPER reproductibles et est **intégré** au commit fonctionnel `3f39999736b6fc3800ecfd36ddee0253c734d25d`.

Le Batch 13 est **intégré sur `main`** au commit `1747beb5efd1fe9763bc9b2d23f3a115575daaec` : il fige le mapping d'agressivité et le protocole expérimental, sans modifier l'autorité Risk ni les analytics Batch 12. Le HEAD documentaire GitHub resynchronisé avant Batch 14 est `655b66b639c4e9c1803cef3920c9a96e7dd16055`.

Le Batch 14 est **intégré sur `main`** au commit `dc60033f60bf5d98a68e6131a9320e575d46cc8d` : il ajoute une comparaison Luna/Sol contrôlée et appariée sans modifier Agent/Risk/Broker, API ou frontend.

---

## 4. Architecture et flux de confiance

**Confirmé :** backend Python + `asyncio` + FastAPI + Pydantic ; persistance PostgreSQL + SQLAlchemy async + Alembic ; frontend Next.js + TypeScript + shadcn/ui + Tailwind ; REST/WebSocket selon le besoin.

```text
MarketDataSource
      |
      v
MarketState -----+
                 |
PortfolioState --+--> AgentInput --> Agent IA --> DecisionCandidate
                         |                   |
                         |                   v
                         |              Risk Engine
                         |           /       |       \
                         |       REJECT    MODIFY    ALLOW
                         |           \       |       /
                         |                   v
                         |             RiskAssessment
                         |                   |
                         |      ExecutionIntent si tradable
                         |                   |
                         |        même MarketState du cycle
                         |                   |
                         |                   v
                         |             Paper Broker
                         |                   |
                         |        Fill(s) + PortfolioState
                         |                   |
                         +-------------------v
                                   TradingCycleResult
                                           |
                                           v
                               durable audit persistence
                                           |
                        +------------------+------------------+
                        |                                     |
                        v                                     v
                 audit query service                 analytics reducer
                        |                                     |
                        +------------------+------------------+
                                           |
                                           v
                                     FastAPI REST
                                           |
                                           v
                                    Next.js cockpit
```

Principe absolu : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Le package Agent ne possède aucun chemin direct vers Risk, Broker, Kraken, FastAPI ou une base de données. Le mapping d'agressivité canonique est un contrat de domaine. Le package `experiments` peut construire un manifeste à partir des configurations Risk/coûts injectées et comparer des rapports analytics, mais n'exécute aucun ordre et ne remplace pas le runner.

---

## 5. Contrats de domaine canoniques

Les frontières critiques utilisent des modèles Pydantic stricts avec champs supplémentaires interdits, UUID explicites et timestamps timezone-aware normalisés UTC.

### Marché et portefeuille

- `MarketObservation` : fait marché fournisseur-agnostique minimal ;
- `MarketState` : snapshot déterministe, symbole canonique, dernier prix et contexte optionnel ;
- `MarketContext` : fraîcheur descriptive et fenêtres multi-horizon ;
- `PortfolioState` : snapshot PAPER avec `balances` et `positions` disjoints ;
- `AssetBalance` : actif de règlement disponible ;
- `AssetPosition` : quantité détenue et quantité disponible à la vente.

### Agent, Risk et exécution

`AgentInput` contient :

```text
cycle_id
created_at
market_state
portfolio_state
aggressiveness = 1..10
aggressiveness_context?   # mapping versionné Batch 13
experiment_manifest?      # protocole expérimental versionné
```

Les deux champs expérimentaux restent optionnels pour rester compatibles avec les faits Batch 12 déjà persistés. Tout nouveau cycle expérimental construit le `AggressivenessContext` explicite.

`DecisionCandidate` contient :

```text
decision_id
cycle_id
created_at
action = BUY | SELL | HOLD
symbol
proposed_quantity?   # obligatoire pour BUY/SELL, interdite pour HOLD
rationale?
```

Le sizing initial est **stratégique** : le Risk Engine ne choisit pas arbitrairement une taille de départ.

`RiskAssessment` contient :

```text
risk_assessment_id
cycle_id
decision_id
assessed_at
status = ALLOW | MODIFY | REJECT
requested_quantity?
authorized_quantity?
evaluated_limits[]
reasons[]
```

`MODIFY` réduit strictement la quantité demandée. `REJECT` n'autorise aucune quantité. HOLD produit un assessment auditable sans intent.

`ExecutionIntent` reste uniquement PAPER, BUY/SELL, et n'existe que si le Risk Engine autorise une quantité strictement positive. Seul le Risk Engine le construit.

`Fill` reste le fait d'exécution PAPER auditable avec contexte de pricing, prix de référence, prix exécuté, notional, frais, spread et slippage.

### Contrats expérimentaux Batch 13 / Batch 14

`AggressivenessContext` contient `mapping_version`, `level`, `posture` et `strategic_instruction`.

`ExperimentManifest` conserve les champs communs :

- `protocol_version` ;
- `experiment_digest` SHA-256 ;
- contexte d'agressivité complet ;
- `llm_model` ;
- `prompt_version` ;
- univers trié de symboles ;
- snapshot déterministe de `RiskPolicy` ;
- snapshot des coûts PAPER ;
- `analytics_version` ;
- `source_id`, `source_digest` ;
- fenêtre temporelle optionnelle.

`paper-experiment-v1` reste compatible avec le Batch 13 et n'utilise pas les champs Batch 14. `paper-experiment-v2` ajoute :

```text
comparison_variable = LLM_MODEL
experiment_group_digest
replicate_index
replicate_count
```

Pour v2, `source_digest` est obligatoire. `experiment_group_digest` identifie les champs contrôlés communs en excluant uniquement `llm_model` et `replicate_index`. `experiment_digest` identifie chaque run complet.

La couche SQLAlchemy n'introduit pas de seconde représentation métier : ses records conservent les objets canoniques sous forme JSON/JSONB et leurs clés de corrélation.

---

## 6. Market State

### Confirmé au Batch 04

`MarketStateBuilder` est mono-symbole, déterministe et mémoire. Il garde un historique borné, impose un ordre temporel strict et construit les horizons descriptifs configurés.

Pour un snapshot à `T`, seules les observations `observed_at <= T` sont utilisées. Le seuil technique de stale du Market State reste distinct de la politique métier Risk.

Le runner consomme `MarketDataSource.snapshot(symbol)` exactement une fois par cycle. Aucun refresh caché n'est permis ensuite pour cette décision.

---

## 7. Portfolio State et Paper Broker

### Confirmé au Batch 05

`balances` est la source canonique des actifs de règlement ; `positions` est la source canonique des actifs détenus/vendables. Les rôles sont uniques et non chevauchants.

`PaperPortfolioLedger` reçoit un état initial explicitement injecté. Aucun capital PAPER, devise de référence ou univers produit n'est imposé globalement. Les mutations sont copy-on-write et atomiques.

`PaperBroker` reçoit explicitement `ExecutionIntent` et `MarketState` :

```text
Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]
```

Il ne consulte jamais Kraken. Le calcul des coûts est factorisé dans `estimate_paper_execution` et partagé par Risk et le Paper Broker. `PaperExecutionCostModel` reste injecté : `fee_rate`, `spread_bps`, `slippage_bps`.

Les Batches 13/14 ne modifient pas cette mathématique. Les valeurs injectées sont seulement enregistrées dans le manifeste expérimental afin de détecter une comparaison non contrôlée.

---

## 8. Risk Engine — intégré au Batch 06

Le package canonique est `ai_spot_trader.risk`. Le moteur est synchrone, déterministe, sans FastAPI, Kraken, LLM ou I/O réseau. Il ne mute ni `MarketState` ni `PortfolioState` et n'exécute jamais lui-même un ordre.

`RiskPolicy` reste explicitement injectée. Elle peut porter :

- `max_order_notional` optionnel ;
- `allowed_pairs` optionnel ;
- `stale_after` métier optionnel ;
- `allow_quantity_reduction` explicite.

Contrôles actuels : symbole, chronologie, whitelist optionnelle, fraîcheur métier optionnelle, max notional, balance quote, solvabilité BUY avec coûts PAPER, position SELL disponible et rôles d'actifs.

`MODIFY` ne change jamais BUY↔SELL ou le symbole et n'augmente jamais la taille stratégique.

HOLD traverse Risk et produit `ALLOW + HOLD_NO_EXECUTION`, sans `ExecutionIntent`.

Ni l'agressivité ni le modèle LLM ne sont des paramètres de `RiskEngine.evaluate(...)`. À décision et snapshots identiques, Luna et Sol passent par exactement les mêmes contrôles déterministes.

---

## 9. Agent IA — Batch 07 intégré, prompt Batch 13 intégré

Le port canonique reste :

```text
LLMProvider.generate_decision(AgentInput) -> DecisionCandidate
```

Le modèle fournisseur ne produit que `action`, `symbol`, `proposed_quantity`, `rationale`. `decision_id`, `cycle_id` et `created_at` restent sous contrôle de l'application.

L'Agent est limité au symbole de `agent_input.market_state.symbol`. Une sortie divergente est rejetée avant création d'un `DecisionCandidate` utilisable.

L'adapter OpenAI utilise la Responses API et un JSON Schema strict. La réponse est parsée et revalidée localement sans réparation stratégique silencieuse.

Le prompt courant reste `agent-strategy-v2`. Luna et Sol utilisent exactement `OpenAIDecisionProvider`; le modèle est un paramètre de configuration, pas une implémentation Agent parallèle.

Lorsqu'un `ExperimentManifest` est présent, le provider valide avant l'appel LLM :

- son digest ;
- le modèle LLM actif ;
- la version de prompt active ;
- le mapping d'agressivité canonique.

Aucun retry automatique n'est introduit.

---

## 10. Chronologie et no look-ahead

Un cycle valide respecte :

```text
MarketState.as_of <= AgentInput.created_at
PortfolioState.as_of <= AgentInput.created_at
AgentInput.created_at <= DecisionCandidate.created_at
DecisionCandidate.created_at <= RiskAssessment.assessed_at
RiskAssessment.assessed_at = ExecutionIntent.created_at   # si intent
MarketState.as_of <= Fill.filled_at                       # si fill
```

Le runner crée `AgentInput.created_at` après acquisition des deux snapshots. Les composants Agent et Risk conservent également leurs propres contrôles temporels.

Le même `MarketState` imbriqué dans `AgentInput` est réutilisé pour Risk puis, si autorisé, pour le Broker. Le même `PortfolioState` pré-cycle est réutilisé pour Agent et Risk.

La persistance enregistre les timestamps produits ; elle ne les recalcule pas et ne réécrit pas les décisions a posteriori.

Le manifeste ne permet aucun look-ahead : sa fenêtre/source décrit les faits autorisés pour l'expérience, mais ne modifie pas les snapshots réellement fournis au cycle. Pour une comparaison Luna/Sol strictement appariée, `paper-experiment-v2` exige une identité `source_digest` figée.

---

## 11. Orchestration autonome — Batch 08 intégré

### Primitive un-cycle

`TradingCycleRunner.run_cycle()` exécute exactement un cycle PAPER pour un symbole explicite. Il dépend des ports/composants canoniques existants et injecte :

- `MarketDataSource` ;
- `PaperPortfolioLedger` ;
- `LLMProvider` ;
- `RiskEngine` ;
- `Broker` ;
- symbole ;
- agressivité ;
- manifeste expérimental optionnel ;
- `Clock` ;
- factory `cycle_id` ;
- timeouts Market/Agent/Broker.

Le constructeur valide le niveau via `aggressiveness-map-v1`. Si un manifeste est fourni, il valide son digest, son niveau et l'appartenance du symbole à l'univers.

Un verrou `asyncio.Lock` interne couvre l'intégralité du cycle.

### Résultat de cycle

`TradingCycleResult` reste une dataclass immuable interne d'orchestration. HOLD et REJECT restent des cycles `COMPLETED`. Les pannes techniques restent `FAILED`.

### Timeouts et boucle

Market, Agent et Broker sont entourés d'`asyncio.timeout`. Risk reste synchrone et déterministe, sans timeout artificiel.

`TradingEngine` répète le même runner séquentiellement ; aucun orchestrateur expérimental parallèle n'est ajouté.

---

## 12. Runtime FastAPI et composition

Le runtime peut recevoir un `TradingEngine`, un lecteur de portefeuille, un `CycleAuditReader`, un `PaperAnalyticsReader` et éventuellement une DB possédée par l'application.

`create_app(...)` ne démarre jamais le moteur. Les commandes `start`/`stop` passent uniquement par le moteur injecté.

Batch 14 n'ajoute aucune configuration expérimentale à l'API. La composition d'un runner expérimental reste explicite côté backend afin de ne pas inventer silencieusement capital, univers, cadence, RiskPolicy ou coûts.

---

## 13. Persistance durable — Batch 09 intégré

Le journal repose sur PostgreSQL, SQLAlchemy async, `asyncpg` et Alembic. La migration initiale reste `0001_audit_journal`.

`CycleAuditWriter.record(TradingCycleResult)` persiste un graphe immuable par `cycle_id`, avec idempotence par digest et transaction unique.

Le cycle enregistre notamment `AgentInput` complet en JSON/JSONB. Par conséquent, les champs Batch 13/14 du manifeste sont persistés sans nouvelle colonne ni migration et participent au `result_digest`.

`experiment_digest` identifie durablement un run. `experiment_group_digest` relie les runs Luna/Sol et leurs répétitions appartenant au même groupe contrôlé.

HOLD, REJECT, MODIFY, ALLOW et FAILED conservent leur sémantique durable existante.

La limite exactly-once entre mutation du ledger mémoire et commit PostgreSQL reste inchangée.

---

## 14. API de contrôle et d'observation — Batch 10 intégré

La façade REST versionnée `/api/v1` expose moteur, portefeuille, cycles, décisions, Risk, exécutions/fills, erreurs, dernier marché et analytics.

Batch 14 n'ajoute aucun endpoint. Les payloads durables détaillés continuent d'être exposés comme faits enregistrés sans être réinterprétés stratégiquement.

---

## 15. Frontend cockpit — Batch 11 intégré

Le cockpit reste strictement client des interfaces FastAPI. Il affiche les vues intégrées et le panneau analytics Batch 12, utilise un polling présentatif borné et n'est jamais propriétaire du moteur.

Aucune modification frontend n'est proposée au Batch 14. Il n'existe donc aucun configurateur navigateur capable de muter modèle, agressivité, RiskPolicy, coûts ou manifeste d'un moteur en cours.

---

## 16. Analytics PAPER — Batch 12 intégré

### Source et frontière de calcul

Les analytics observent le journal immuable. Le reducer `ai_spot_trader.analytics.paper` travaille sur une séquence de faits `PaperAnalyticsCycleFact` issue des records durables.

### Définitions intégrées

- equity : valeur du portefeuille durable au `MarketState.last_price` du même cycle ;
- P&L net : equity marquée moins l'equity initiale durable ;
- coûts : `fee`, `spread_cost`, `slippage_cost` lus dans les fills ;
- P&L brut : P&L net + coûts cumulés ;
- drawdown : écart depuis le pic historique d'equity nette ;
- exposition : valeur position / equity positive ;
- trade : `execution_id` ayant produit au moins un fill ;
- jour : date UTC.

HOLD/REJECT/MODIFY/FAILED restent comptés explicitement.

### Reproductibilité Batch 12

La réponse porte `calculation_version = paper-analytics-v1` et un `source_digest` calculé sur `(cycle_id, result_digest)` ordonné.

Les comparateurs Batches 13/14 **réutilisent** ces rapports ; ils n'implémentent aucune formule analytics alternative.

---

## 17. Expérimentation agressivité — Batch 13 intégré

### Mapping

`aggressiveness-map-v1` est un mapping discret des dix niveaux vers une posture et une instruction stratégique. Il ne contient aucun seuil Risk ou indicateur de trading déterministe.

### Manifeste

`build_experiment_manifest(...)` reçoit explicitement niveau, modèle, prompt, univers, `RiskPolicy`, coûts PAPER, source/dataset, fenêtre et version analytics. Il construit `paper-experiment-v1` et son digest déterministe.

### Comparabilité

`compare_aggressiveness_runs(...)` refuse des runs qui diffèrent sur un champ contrôlé autre que l'agressivité. La comparaison expose les métriques existantes sans ranking ni optimisation rétrospective.

---

## 18. Comparaison Luna / Sol — Batch 14 intégré

### Axe expérimental versionné

Le manifeste Batch 13 contient déjà `llm_model`, mais son identité de comparaison exclut uniquement l'agressivité. Le réutiliser tel quel pour Luna/Sol casserait la sémantique de la comparaison d'agressivité.

Le Batch 14 introduit donc `paper-experiment-v2` avec `comparison_variable = LLM_MODEL`. `paper-experiment-v1` reste inchangé pour Batch 13 et ses anciens payloads restent lisibles.

### Identités et répétitions

`build_model_experiment_manifest(...)` construit chaque run avec :

- `experiment_digest` : identité complète du run ;
- `experiment_group_digest` : identité des champs contrôlés communs ;
- `replicate_index` : répétition courante ;
- `replicate_count` : nombre de répétitions déclaré pour chaque modèle.

Le digest de groupe exclut uniquement `llm_model` et `replicate_index`. Une variation d'agressivité, prompt, univers, `RiskPolicy`, coûts PAPER, source/dataset, fenêtre, version analytics ou `replicate_count` produit donc un groupe différent et invalide une comparaison directe.

### Dataset figé et no look-ahead

`source_digest` est obligatoire en v2. Une comparaison Luna/Sol strictement appariée suppose un dataset/snapshot de faits sources figé et identique. Le batch **n'ajoute pas** de moteur de replay historique : il formalise l'identité requise pour qu'un replay futur ou un dataset fourni soit auditable.

### Non-déterminisme et anti cherry-picking

Plusieurs répétitions sont supportées sans seed fournisseur fictif. `compare_model_runs(...)` exige toutes les répétitions `1..N` pour Luna **et** Sol. Cette contrainte empêche de présenter un groupe incomplet après suppression post-hoc d'une répétition défavorable.

Le comparateur renvoie les runs bruts et les métriques Batch 12 existantes, y compris les points cumulés et le daily. Il ne calcule aucun score composite, ne classe pas les modèles et ne conclut pas automatiquement qu'un modèle est « meilleur ».

---

## 19. Sécurité et séparation PAPER / LIVE

`ExecutionMode` ne contient que `PAPER`. Le LIVE reste non représentable et nécessitera une décision dédiée. Aucune clé Kraken privée n'est requise.

Le provider OpenAI ne dispose d'aucun outil d'exécution et ne connaît ni Broker ni Kraken. L'orchestrateur n'interprète jamais `rationale` comme commande.

Le manifeste ne contient aucun secret ; il ne stocke que des identités/configurations non sensibles.

---

## 20. Stratégie de tests

Les tests restent déterministes et offline autant que possible.

Validation Batch 13 confirmée :

- Python local : **3.13.14** ;
- `pytest backend` : **249 tests passés**, 2 warnings externes ;
- Ruff : **All checks passed** ;
- mypy : **81 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push : `1747beb5efd1fe9763bc9b2d23f3a115575daaec` ;
- working tree propre après push.

Validation Batch 14 confirmée :

- `pytest backend` : **266 tests passés**, 2 warnings externes ;
- Ruff : **All checks passed** ;
- mypy : **81 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push : `dc60033f60bf5d98a68e6131a9320e575d46cc8d` ;
- working tree propre après push ;
- préparation ChatGPT : **34 tests ciblés** et `py_compile` réussis.

Aucun test frontend additionnel n'était requis puisque le frontend n'a pas été modifié.

---

## 21. Questions ouvertes prioritaires

- capital PAPER et devise de référence produit ;
- univers initial de paires ;
- valeur produit de cadence ;
- valeurs produit des limites Risk ;
- valeurs de référence fee/spread/slippage ;
- limites avancées d'exposition/drawdown en tant que contraintes Risk ;
- dataset/replay canonique concret pour exécuter les expériences appariées ;
- éventuelles statistiques descriptives de dispersion à ajouter plus tard sans score composite ;
- politique de rétention du journal ;
- reconstruction du ledger et réconciliation après crash ;
- source d'événements et protocole d'un futur WebSocket cockpit ;
- conditions futures d'un éventuel LIVE.

Ces choix doivent être consignés dans `10_DECISIONS_ET_CHANGELOG.md` lorsqu'ils deviennent canoniques.
