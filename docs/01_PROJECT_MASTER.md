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
- Luna et Sol utilisent le même provider canonique ;
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
- la persistance observe les faits métier, elle ne crée aucune stratégie ;
- le contexte marché est descriptif et déterministe, jamais un moteur BUY/SELL/HOLD parallèle ;
- la cadence du moteur ne doit pas modifier artificiellement l'échantillonnage statistique du contexte marché ;
- le chat opérateur reste conversationnel et ne devient pas un chemin d'exécution ni une mutation silencieuse de stratégie.

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

Le runtime PAPER exécutable est intégré sur `main` au commit `4b9701f07854a943cf47a14287aadfdf4aa48232`. Le Batch 15.2 est intégré au commit fonctionnel `97d529647179c6769a6bdc528b9d9f5e7c85c119`, puis son état documentaire a été finalisé par `bb1aa047157deb1b62d27de952fa53ec14992f09`. Le Batch 15.3 est intégré sur `main` au commit fonctionnel `d0f6d46b9adb37117051a7a497a8d55075c41d32` (`fix: decouple market context from engine cadence`).

### V1 — cockpit et expérimentation instrumentée

V1 ajoute le cockpit Next.js/shadcn, historique, analytics P&L/drawdown/coûts/exposition, replay reproductible, expérimentations d'agressivité, comparaison Luna/Sol et une interface conversationnelle opérateur informative. Le LIVE n'est pas une condition de V1.

Batches déjà intégrés : cockpit (11), analytics (12), agressivité (13), comparaison Luna/Sol (14), chat opérateur (15), composition PAPER exécutable (15.1), contexte marché multi-horizon (15.2) et indépendance du contexte descriptif vis-à-vis de la cadence moteur (15.3).

---

## 4. Architecture et flux de confiance

**Confirmé :** backend Python + `asyncio` + FastAPI + Pydantic ; persistance PostgreSQL + SQLAlchemy async + Alembic ; frontend Next.js + TypeScript + shadcn/ui + Tailwind ; REST/WebSocket selon le besoin.

```text
Kraken public AssetPairs / OHLC / ticker
              |
              v
       MarketStateBuilder
       |             |
       |             ` ticker courant -> prix/fraîcheur du snapshot
       ` OHLC 1 min clôturées -> fenêtres descriptives 5/30 min
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

### Flux conversationnel Batch 15

```text
Cockpit Chat
    |
    v
POST /api/v1/chat/messages
    |
    v
OperatorChatService ---------> Runtime / audit / analytics en lecture seule
    |
    v
OpenAIChatProvider ----------> même LLMModel Luna ou Sol
```

Ce flux est **latéral**. Il ne rejoint jamais `DecisionCandidate -> Risk -> ExecutionIntent -> Broker`.

---

## 5. Contrats de domaine canoniques

Les frontières critiques utilisent des modèles Pydantic stricts avec champs supplémentaires interdits, UUID explicites et timestamps timezone-aware normalisés UTC.

### Marché et portefeuille

- `MarketObservation` : fait marché fournisseur-agnostique minimal ;
- `MarketState` : snapshot déterministe, symbole canonique, dernier prix et contexte ;
- `MarketContext` : fraîcheur descriptive et fenêtres multi-horizon ;
- `MarketWindowStats` : statistiques descriptives d'une fenêtre ;
- `PortfolioState` : snapshot PAPER avec `balances` et `positions` disjoints ;
- `AssetBalance` : actif de règlement disponible ;
- `AssetPosition` : quantité détenue et quantité disponible à la vente.

`MarketState.context` reste optionnel dans le contrat de domaine pour compatibilité et tests, mais le runtime Kraken PAPER canonique le renseigne lorsqu'un snapshot est construit avec succès.

Le Batch 15.3 n'ajoute aucun nouveau modèle de domaine : il fait évoluer la construction canonique afin de distinguer l'observation courante du snapshot et les observations retenues pour les fenêtres statistiques.

### Agent, Risk et exécution

`AgentInput` contient :

```text
cycle_id
created_at
market_state
portfolio_state
aggressiveness = 1..10
aggressiveness_context?
experiment_manifest?
```

`DecisionCandidate` contient :

```text
decision_id
cycle_id
created_at
action = BUY | SELL | HOLD
symbol
proposed_quantity?
rationale?
```

Le sizing initial est **stratégique**. BUY/SELL exigent une quantité positive ; HOLD n'en porte aucune.

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

`MODIFY` réduit strictement la quantité demandée. `REJECT` n'autorise aucune quantité. HOLD produit un assessment auditable sans intent. `ExecutionIntent` reste uniquement PAPER, BUY/SELL, et n'existe que si le Risk Engine autorise une quantité strictement positive. Seul Risk le construit.

### Contrats expérimentaux

`AggressivenessContext` contient `mapping_version`, `level`, `posture` et `strategic_instruction`.

`ExperimentManifest` conserve l'identité du protocole, digests SHA-256, contexte d'agressivité, modèle, prompt, univers, snapshot Risk, coûts PAPER, version analytics, source/dataset et métadonnées de comparaison lorsque nécessaires.

`paper-experiment-v1` reste le protocole agressivité. `paper-experiment-v2` fixe la comparaison modèle avec `comparison_variable = LLM_MODEL`, `experiment_group_digest`, `replicate_index` et `replicate_count` ; `source_digest` y est obligatoire.

### Contrats Chat

Les contrats HTTP/chat restent séparés du domaine d'exécution. Aucun ne contient ou ne retourne `ExecutionIntent`, une commande Broker ou une mutation `RiskPolicy`.

---

## 6. Market State

`MarketStateBuilder` est **la voie canonique provider-agnostique** de construction du snapshot marché enrichi. Il est mono-symbole, déterministe et mémoire. Il garde un historique borné, impose un ordre temporel strict et construit les horizons descriptifs configurés.

Les horizons canoniques existants restent :

```text
5 minutes
30 minutes
```

Les statistiques exposées restent descriptives : compte, complétude, extrêmes, amplitude, rendement de fenêtre et volatilité réalisée lorsque le nombre d'observations le permet. Elles ne constituent aucun signal de trading déterministe.

### Séparation entre observation statistique et observation courante — Batch 15.3

Les observations ajoutées par `MarketStateBuilder.add_observation(...)` forment la **série statistique retenue**. Elles seules servent aux calculs des fenêtres. `MarketStateBuilder.build(...)` accepte désormais une `current_observation` optionnelle : cette observation est utilisée pour le prix courant du snapshot et sa fraîcheur, mais n'est pas insérée dans l'historique statistique.

`build(...)` accepte également un `statistics_as_of` optionnel. Cette ancre doit être inférieure ou égale à `MarketState.as_of` et fixe le temps causal auquel les fenêtres statistiques sont évaluées. Lorsque ce paramètre n'est pas fourni, le comportement générique historique reste inchangé : les fenêtres sont ancrées sur `as_of`.

Cette séparation garantit qu'une fréquence plus élevée d'appels à `build(...)` ne crée pas de nouveaux points statistiques par elle-même.

### Runtime Kraken PAPER — Batches 15.2 / 15.3

`KrakenMarketDataSource.snapshot(symbol)` :

1. normalise la paire via le registry public Kraken ;
2. lit un ticker WebSocket courant ;
3. vérifie l'ordre temporel des tickers courants successifs ;
4. demande un bootstrap OHLC public 1 minute couvrant au moins le plus grand horizon, avec marge technique ;
5. exclut systématiquement la dernière entrée OHLC, que Kraken documente comme la fenêtre courante non clôturée ;
6. transforme chaque clôture historique en `MarketObservation` horodatée à `started_at + interval` ;
7. n'ajoute que les clôtures strictement antérieures au ticker courant ;
8. conserve les clôtures OHLC comme seule série statistique persistée dans le builder ;
9. choisit la dernière clôture OHLC retenue comme `statistics_as_of` causal ;
10. transmet le ticker courant à `build(...)` comme `current_observation` non persistée ;
11. construit le `MarketState` final avec `as_of=snapshot_at`.

La granularité **1 minute** est un choix technique d'échantillonnage descriptif suffisamment fin pour les horizons existants 5/30 min ; elle n'ajoute aucun horizon stratégique et ne produit aucun signal directionnel.

Conséquences :

- `MarketState.last_price` reste toujours le prix ticker courant ;
- `MarketContext.last_observed_at`, `data_age_seconds` et `is_stale` restent basés sur l'observation courante ;
- `observation_count`, min/max/range, rendement et volatilité sont calculés uniquement sur la série OHLC fixe ;
- sans nouvelle clôture OHLC, plusieurs snapshots successifs conservent les mêmes fenêtres statistiques même si `MarketState.as_of`, le ticker ou la cadence moteur changent ;
- quand une nouvelle clôture OHLC devient causalement disponible, elle est ajoutée une seule fois et les fenêtres avancent naturellement ;
- une fenêtre vide ou partielle reste explicitement représentée comme telle ;
- une erreur Kraken ou une impossibilité de construire le snapshot reste une erreur Market explicite.

La fraîcheur technique est vérifiée sur le ticker puis réévaluée après la récupération historique afin qu'un appel REST lent ne puisse pas faire passer silencieusement une observation devenue stale.

Le runner consomme `MarketDataSource.snapshot(symbol)` exactement une fois par cycle.

---

## 7. Portfolio State et Paper Broker

`balances` est la source canonique des actifs de règlement ; `positions` est la source canonique des actifs détenus/vendables. `PaperPortfolioLedger` reçoit un état initial explicitement injecté. Aucun capital PAPER, devise de référence ou univers produit n'est imposé globalement.

`PaperBroker` reçoit explicitement `ExecutionIntent` et `MarketState` :

```text
Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]
```

Il ne consulte jamais Kraken. Le calcul des coûts est factorisé dans `estimate_paper_execution` et partagé par Risk et le Paper Broker.

---

## 8. Risk Engine

Le package canonique est `ai_spot_trader.risk`. Le moteur est synchrone, déterministe, sans FastAPI, Kraken, LLM ou I/O réseau. Il ne mute ni `MarketState` ni `PortfolioState` et n'exécute jamais lui-même un ordre.

`RiskPolicy` reste explicitement injectée : `max_order_notional`, `allowed_pairs`, `stale_after`, `allow_quantity_reduction` sont optionnels/explicites. Les contrôles actuels couvrent symbole, chronologie, whitelist, fraîcheur, max notional, balance quote, solvabilité BUY avec coûts PAPER et position SELL disponible.

Ni l'agressivité, ni les statistiques marché, ni le modèle LLM ne deviennent des règles déterministes de décision stratégique dans Risk. Le contexte permet seulement les contrôles techniques déjà définis et fournit des faits à l'Agent.

Le Batch 15.3 ne modifie ni `RiskEngine`, ni `RiskPolicy`, ni les limites de risque.

---

## 9. Agent IA

Le port canonique reste :

```text
LLMProvider.generate_decision(AgentInput) -> DecisionCandidate
```

Le modèle fournisseur ne produit que `action`, `symbol`, `proposed_quantity`, `rationale`. Le prompt stratégique courant reste `agent-strategy-v2`. Luna et Sol utilisent exactement `OpenAIDecisionProvider`; le modèle est un paramètre de configuration.

Le contexte multi-horizon est transmis comme partie du `MarketState` canonique de l'`AgentInput`. L'Agent peut l'interpréter stratégiquement, mais aucun calcul de contexte ne lui impose BUY, SELL ou HOLD.

Le Batch 15.3 ne change ni le prompt Agent, ni l'agressivité, ni la logique stratégique Luna/Sol.

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

Le même `MarketState` imbriqué dans `AgentInput` est réutilisé pour Risk puis, si autorisé, pour le Broker. La persistance enregistre les timestamps produits ; elle ne les recalcule pas.

Pour les OHLC Kraken, le timestamp fournisseur de la bougie correspond à son début. Le runtime attribue donc la clôture historique à `started_at + interval` et ignore l'entrée courante non clôturée. Une clôture à ou après le ticker courant n'est pas injectée.

Pour le Batch 15.3 :

```text
statistics_as_of <= MarketState.as_of
chaque observation statistique utilisée <= statistics_as_of
ticker courant utilisé <= MarketState.as_of
clôture OHLC retenue < ticker courant
```

Le ticker courant ne devient jamais une observation statistique. Ces règles empêchent à la fois le look-ahead et la contamination des fenêtres par la cadence moteur.

Pour le chat, une explication d'un cycle historique reçoit le `CycleAuditDetail` durable correspondant et son `agent_input` exact. L'état courant est séparé et ne peut pas devenir une cause rétroactive.

---

## 11. Orchestration autonome

`TradingCycleRunner.run_cycle()` exécute exactement un cycle PAPER. `TradingEngine` répète le même runner séquentiellement ; aucun orchestrateur expérimental, conversationnel ou marché parallèle n'est ajouté.

Market, Agent et Broker sont entourés de timeouts ; Risk reste synchrone et déterministe. Le verrou du runner couvre l'intégralité du cycle. L'appel REST OHLC et l'appel WebSocket ticker font tous deux partie du stage Market et restent donc sous le timeout Market global du cycle, en plus de leurs bornes fournisseur propres.

La cadence `TradingEngine` détermine uniquement **quand** un nouveau cycle est demandé. Elle ne définit plus l'échantillonnage des statistiques du `MarketContext`.

Le chat est servi par FastAPI de manière indépendante. Il ne stoppe ni ne redémarre le moteur, et le moteur ne dépend pas de la présence du frontend.

---

## 12. Runtime FastAPI et composition

Le commit `4b9701f07854a943cf47a14287aadfdf4aa48232` intègre le composition root PAPER canonique :

- configuration du run explicitement requise et fail-closed ;
- Kraken public uniquement ;
- même `PaperExecutionCostModel` entre Risk et Paper Broker ;
- même `PaperPortfolioLedger` entre moteur/API/Chat ;
- même PostgreSQL pour writer et surfaces de lecture ;
- même `LLMModel` pour Agent stratégique et Chat ;
- `main:app` compose au lifespan mais ne démarre jamais automatiquement le moteur ;
- `POST /api/v1/engine/run-cycle` exécute exactement un cycle canonique et refuse pendant la boucle autonome ;
- audit préflight + latch fail-closed après panne d'audit ;
- fermeture ordonnée moteur, ressources Kraken, DB.

Les Batches 15.2 et 15.3 ne modifient pas cette composition : `build_kraken_market_data_source(...)` conserve la même frontière `MarketDataSource`; seule la construction interne du snapshot est enrichie/corrigée via le builder canonique.

---

## 13. Persistance durable

Le journal PostgreSQL/Alembic conserve le graphe immuable par cycle et l'`AgentInput` complet. Les champs expérimentaux et le `MarketContext` imbriqué sont persistés via les contrats existants sans migration additionnelle.

Les conversations restent process-locales et bornées pour la V1 ; elles ne participent ni au journal de trading, ni aux digests expérimentaux, ni aux analytics.

Les Batches 15.2/15.3 n'ajoutent aucune migration : ils modifient uniquement la construction des valeurs déjà sérialisées dans le `MarketState`.

La limite exactly-once globale entre mutation du ledger mémoire et commit PostgreSQL reste explicitement non résolue.

---

## 14. API de contrôle et d'observation

La façade REST versionnée `/api/v1` expose moteur, portefeuille, cycles, décisions, Risk, exécutions/fills, erreurs, dernier marché, analytics et chat opérateur.

Commandes moteur canoniques :

```text
POST /api/v1/engine/run-cycle
POST /api/v1/engine/start
POST /api/v1/engine/stop
```

Aucune route ne reçoit directement une action stratégique ou un `ExecutionIntent`. Le Batch 15.3 n'ajoute aucune route.

---

## 15. Frontend cockpit

Le cockpit reste strictement client des interfaces FastAPI, utilise un polling présentatif borné et n'est jamais propriétaire du moteur. Aucun changement frontend n'est nécessaire pour le Batch 15.3.

La cadence de polling frontend n'est pas la cadence moteur et aucune des deux ne définit l'échantillonnage OHLC statistique.

---

## 16. Analytics PAPER

Les analytics observent le journal immuable. `build_paper_analytics_report` est déterministe, sans I/O/horloge courante. Equity, P&L brut/net, coûts, drawdown, exposition, trades et compteurs HOLD/REJECT/MODIFY/FAILED restent définis par `paper-analytics-v1`.

Le Batch 15.3 n'introduit aucun nouvel indicateur de performance ni scoring du contexte marché.

---

## 17. Expérimentation agressivité

`aggressiveness-map-v1` est discret. `paper-experiment-v1` identifie niveau, modèle, prompt, univers, Risk, coûts, source et version analytics. `compare_aggressiveness_runs(...)` refuse une comparaison si un champ contrôlé hors agressivité diffère.

Aucun message chat ni calcul de contexte marché ne modifie le mapping d'agressivité ou `RiskPolicy`.

L'indépendance statistique vis-à-vis de la cadence moteur du Batch 15.3 améliore la comparabilité expérimentale : changer `trading_cadence_seconds` ne rajoute plus artificiellement des observations dans les fenêtres descriptives.

---

## 18. Comparaison Luna / Sol

`paper-experiment-v2` fixe `comparison_variable = LLM_MODEL`. `experiment_group_digest` identifie les champs contrôlés communs ; `experiment_digest` identifie chaque run ; `replicate_index/count` imposent des répétitions appariées complètes. `source_digest` est obligatoire.

Le chat réutilise le modèle Agent configuré mais ne participe pas à ce protocole.

---

## 19. Chat opérateur — Batch 15 intégré

Le chat permet à l'opérateur de demander des explications sur décisions, marché, portefeuille, Risk, cycles et analytics. Il reste sans outils d'exécution, sans mutation implicite et sans persistance PostgreSQL en V1.

Pour un cycle historique, `historical_cycle.agent_input` représente ce que l'Agent stratégique avait effectivement comme entrée persistée. L'état courant reste séparé. Le chat ne prétend pas accéder à une chaîne de pensée cachée.

---

## 20. Sécurité et séparation PAPER / LIVE

`ExecutionMode` ne contient que `PAPER`. Le LIVE reste non représentable et nécessitera une décision dédiée. Aucune clé Kraken privée n'est requise par le runtime actuel ni par les Batches 15.2/15.3.

Le provider OpenAI stratégique ne dispose d'aucun outil d'exécution. Le provider conversationnel n'a également aucun outil ni port d'exécution.

Le bind API par défaut reste local. Toute exposition distante du cockpit/chat/lifecycle nécessitera une politique d'authentification explicite.

---

## 21. Stratégie de tests

Le socle déjà intégré dispose de tests pour contrats domaine, Market State, Kraken public, portfolio/broker, Risk, Agent, boucle, persistance, API, analytics, expériences, chat et composition PAPER.

Le Batch 15.2 avait ajouté les tests de parsing/normalisation OHLC, exclusion de bougie non clôturée, construction multi-horizon, fraîcheur et propagation jusqu'à l'`AgentInput`.

Le Batch 15.3 ajoute des tests déterministes pour :

- séparation entre série statistique retenue et observation courante ;
- ticker courant comme `MarketState.last_price` ;
- fraîcheur basée sur le ticker courant ;
- absence de modification artificielle des fenêtres lors de snapshots répétés sans nouvelle bougie OHLC ;
- comparaison de simulations de cadence 10 s et 120 s avec statistiques descriptives finales identiques pour la même série sous-jacente ;
- ancrage des fenêtres sur la dernière observation statistique causale ;
- absence de look-ahead ;
- fenêtres vides/partielles honnêtes ;
- ordre temporel strict des observations statistiques et des tickers courants ;
- comportement après plusieurs snapshots successifs.

Validation exécutée par ChatGPT dans l'environnement de génération :

```text
pytest tests/test_market_state.py tests/test_kraken_market_data.py : 38 passés
compileall fichiers Python modifiés                           : réussi
```

Validation complète exécutée localement par l'utilisateur le 21 septembre 2026 : `pytest` **315 passés** avec 2 warnings externes, `ruff check .` **All checks passed**, `mypy .` **94 fichiers sans erreur**, et `git diff --check` sans erreur avec uniquement des warnings LF -> CRLF sous Windows.

---

## 22. Questions ouvertes prioritaires

- limites avancées d'exposition/drawdown en tant que contraintes Risk ;
- dataset/replay canonique concret pour les expériences appariées ;
- politique de rétention du journal ;
- reconstruction du ledger et réconciliation après crash ;
- éventuelle persistance durable du chat si un besoin réel apparaît ;
- mécanisme explicite, audité et versionné d'instructions opérateur modifiant réellement la stratégie ;
- source d'événements et protocole d'un futur WebSocket cockpit ;
- conditions futures d'un éventuel LIVE.

Les valeurs concrètes du premier essai PAPER restent des paramètres explicites de run. Les horizons descriptifs 5/30 minutes et la granularité technique OHLC 1 minute sont des mécanismes descriptifs ; ils ne constituent aucune stratégie algorithmique déterministe. Le Batch 15.3 fixe explicitement que l'échantillonnage statistique dépend de la série marché et non de la cadence du moteur.
