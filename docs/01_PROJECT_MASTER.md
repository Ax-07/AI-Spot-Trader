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
- la persistance observe les faits métier, elle ne crée aucune stratégie ;
- le chat opérateur, lorsqu'il existe, reste conversationnel et ne devient pas un chemin d'exécution ni une mutation silencieuse de stratégie.

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

Le Batch 08 réalise le point 9. Le Batch 09 réalise le socle durable du point 10. Le Batch 10 réalise le socle REST du point 11 et est intégré sur `main` au commit fonctionnel `e6bcfd4dd345c934769b2f90fa7822232a80dd80`.

### V1 — cockpit et expérimentation instrumentée

V1 ajoute le cockpit Next.js/shadcn, historique, analytics P&L/drawdown/coûts/exposition, replay reproductible, expérimentations d'agressivité, comparaison Luna/Sol et une interface conversationnelle opérateur informative. Le LIVE n'est pas une condition de V1.

Le Batch 11 fournit le socle cockpit (`d3f41a3b9df6a69018508a4dc5c8a7286cbbced7`). Le Batch 12 fournit les analytics PAPER reproductibles (`3f39999736b6fc3800ecfd36ddee0253c734d25d`). Le Batch 13 fige le mapping d'agressivité et le protocole expérimental (`1747beb5efd1fe9763bc9b2d23f3a115575daaec`). Le Batch 14 ajoute la comparaison Luna/Sol contrôlée (`dc60033f60bf5d98a68e6131a9320e575d46cc8d`). Le Batch 15 ajoute le chat opérateur au commit fonctionnel `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6`.

Le Batch 15 est **intégré et validé localement** : chat opérateur avec le même modèle Agent configuré, sans modifier le pipeline autonome ni contaminer les expériences.

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

### Flux conversationnel Batch 15 intégré

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

Ce flux est **latéral**. Il ne rejoint jamais `DecisionCandidate -> Risk -> ExecutionIntent -> Broker`. Il ne possède aucun port de mutation de `RiskPolicy`, aucun appel Kraken privé et aucune méthode de création d'intent.

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

### Contrats expérimentaux Batch 13 / Batch 14

`AggressivenessContext` contient `mapping_version`, `level`, `posture` et `strategic_instruction`.

`ExperimentManifest` conserve `protocol_version`, digests SHA-256, contexte d'agressivité, `llm_model`, `prompt_version`, univers, snapshot Risk, coûts PAPER, version analytics, source/dataset, fenêtre et, en v2, identité de groupe/répétitions.

`paper-experiment-v1` reste le protocole agressivité. `paper-experiment-v2` ajoute :

```text
comparison_variable = LLM_MODEL
experiment_group_digest
replicate_index
replicate_count
```

Pour v2, `source_digest` est obligatoire.

### Contrats Chat Batch 15 intégré

Les contrats HTTP/chat sont séparés du domaine d'exécution :

- `SendChatMessageRequest` : `session_id?`, `message`, `context_cycle_id?` ;
- `ChatMessage` : UUID, timestamp UTC, rôle `OPERATOR|AGENT`, contenu ;
- `ChatExchangeResponse` : session, modèle, cycle historique éventuel, paire de messages ;
- `ChatHistoryResponse` : historique borné de la session ;
- `ChatContextSnapshot` : faits de lecture séparant explicitement `historical_cycle` et état courant.

Aucun de ces contrats ne contient ou ne retourne `ExecutionIntent`, une commande Broker ou une mutation `RiskPolicy`.

---

## 6. Market State

`MarketStateBuilder` est mono-symbole, déterministe et mémoire. Il garde un historique borné, impose un ordre temporel strict et construit les horizons descriptifs configurés. Pour un snapshot à `T`, seules les observations `observed_at <= T` sont utilisées. Le runner consomme `MarketDataSource.snapshot(symbol)` exactement une fois par cycle.

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

Ni l'agressivité ni le modèle LLM ne sont des paramètres de `RiskEngine.evaluate(...)`. Le Batch 15 n'ajoute aucun paramètre chat à Risk.

---

## 9. Agent IA

Le port canonique reste :

```text
LLMProvider.generate_decision(AgentInput) -> DecisionCandidate
```

Le modèle fournisseur ne produit que `action`, `symbol`, `proposed_quantity`, `rationale`. Le prompt stratégique courant reste `agent-strategy-v2`. Luna et Sol utilisent exactement `OpenAIDecisionProvider`; le modèle est un paramètre de configuration.

L'adapter OpenAI utilise la Responses API et un JSON Schema strict pour les décisions. Le Batch 15 étend le même client transport avec un appel texte **sans tools** destiné au chat ; cet appel ne traverse jamais `OpenAIDecisionProvider` et ne peut donc pas produire un artefact stratégique canonique.

Le prompt conversationnel `operator-chat-v1` impose la séparation conversation/exécution, l'absence de mutation silencieuse, l'utilisation exclusive des faits fournis et les règles no-look-ahead historiques.

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

Pour le chat, une explication d'un cycle historique reçoit le `CycleAuditDetail` durable correspondant et son `agent_input` exact. `current_market`, `current_portfolio` et `analytics_summary` sont des sections séparées. Le prompt interdit explicitement de les utiliser comme causes rétroactives de la décision passée. Quand un `context_cycle_id` explicite est demandé, la liste `recent_cycles` est retirée du contexte pour réduire encore le risque de mélange temporel.

---

## 11. Orchestration autonome

`TradingCycleRunner.run_cycle()` exécute exactement un cycle PAPER. `TradingEngine` répète le même runner séquentiellement ; aucun orchestrateur expérimental ni conversationnel parallèle n'est ajouté.

Market, Agent et Broker sont entourés de timeouts ; Risk reste synchrone et déterministe. Le verrou du runner couvre l'intégralité du cycle.

Le chat est servi par FastAPI de manière indépendante. Il ne stoppe ni ne redémarre le moteur, et le moteur ne dépend pas de la présence du frontend.

---

## 12. Runtime FastAPI et composition

Le runtime peut recevoir un `TradingEngine`, un lecteur de portefeuille, un `CycleAuditReader`, un `PaperAnalyticsReader` et éventuellement une DB possédée par l'application. `create_app(...)` ne démarre jamais le moteur.

Batch 15 intégré :

- `create_app(...)` accepte un `chat_service` injectable pour les tests ;
- si aucun service n'est injecté et qu'une clé OpenAI est configurée, le lifespan construit `OpenAIResponsesClient` + `OpenAIChatProvider` avec **le même `settings.llm_model`** ;
- `RuntimeChatContextSource` lit uniquement le runtime/audit/analytics déjà canoniques ;
- aucun I/O fournisseur n'est effectué au démarrage, seulement lors d'un message ;
- l'arrêt du runtime conserve son comportement existant sur le moteur et la DB.

---

## 13. Persistance durable

Le journal PostgreSQL/Alembic conserve le graphe immuable par cycle et l'`AgentInput` complet. Les champs expérimentaux sont persistés sans migration additionnelle.

**Décision Batch 15 acceptée :** les conversations restent process-locales et bornées pour la V1. Elles n'entrent pas dans les tables d'audit, le `result_digest`, `experiment_digest`, `experiment_group_digest` ou `PaperAnalyticsReport.source_digest`. Un redémarrage backend perd donc les sessions chat, comportement assumé pour préserver une séparation forte.

Un mécanisme durable d'instructions opérateur modifiant réellement la stratégie est explicitement hors périmètre ; il devra être versionné, audité et appliqué à partir d'un cycle identifié.

---

## 14. API de contrôle et d'observation

La façade REST versionnée `/api/v1` expose moteur, portefeuille, cycles, décisions, Risk, exécutions/fills, erreurs, dernier marché et analytics.

Batch 15 intégré ajoute :

```text
POST /api/v1/chat/messages
GET  /api/v1/chat/sessions/{session_id}
```

REST est suffisant pour la V1. Aucun SSE/WebSocket n'est ajouté. Les erreurs transport/fournisseur chat sont converties en réponses sanitizées distinctes des erreurs/cycles du moteur.

---

## 15. Frontend cockpit

Le cockpit reste strictement client des interfaces FastAPI, utilise un polling présentatif borné et n'est jamais propriétaire du moteur.

Batch 15 ajoute un `ChatPanel` et un hook `useChat`. La session est mémorisée côté navigateur uniquement par son UUID ; le contenu reste côté service backend mémoire. Le code Chat n'appelle aucune route lifecycle moteur. Fermer ou recharger le frontend n'appelle donc jamais `stop()` sur `TradingEngine`.

Le panneau rappelle explicitement qu'il est informatif et que ses messages ne créent aucun trade, ne modifient pas Risk et ne sont pas injectés dans les cycles autonomes.

---

## 16. Analytics PAPER

Les analytics observent le journal immuable. `build_paper_analytics_report` est déterministe, sans I/O/horloge courante. Equity, P&L brut/net, coûts, drawdown, exposition, trades et compteurs HOLD/REJECT/MODIFY/FAILED restent définis par `paper-analytics-v1`.

Le chat peut lire `PaperAnalyticsSummary` courant. Cette lecture est informative et ne modifie ni les faits sources ni le rapport.

---

## 17. Expérimentation agressivité

`aggressiveness-map-v1` est discret. `paper-experiment-v1` identifie niveau, modèle, prompt, univers, Risk, coûts, source et version analytics. `compare_aggressiveness_runs(...)` refuse une comparaison si un champ contrôlé hors agressivité diffère.

Aucun message chat n'est ajouté au manifeste, au mapping ou au prompt stratégique des cycles suivants.

---

## 18. Comparaison Luna / Sol

`paper-experiment-v2` fixe `comparison_variable = LLM_MODEL`. `experiment_group_digest` identifie les champs contrôlés communs ; `experiment_digest` identifie chaque run ; `replicate_index/count` imposent des répétitions appariées complètes. `source_digest` est obligatoire.

Le chat réutilise le modèle Agent configuré mais ne participe pas à ce protocole. Les conversations et réponses ne font pas partie des faits expérimentaux et ne doivent pas affecter les comparaisons Luna/Sol.

---

## 19. Chat opérateur — Batch 15 intégré

### Objectif

Permettre à l'opérateur de demander, pendant l'activité PAPER :

- pourquoi un BUY/SELL/HOLD a été proposé ;
- comment l'Agent interprète l'état courant ;
- comment il lit le portefeuille courant ;
- pourquoi Risk a `MODIFY` ou `REJECT` ;
- ce que montrent les derniers cycles et analytics.

### Frontières de sécurité

Le chat :

- ne crée jamais de `DecisionCandidate` destiné au moteur ;
- ne crée ni `RiskAssessment` ni `ExecutionIntent` ;
- n'importe ni Risk, ni Broker, ni Kraken, ni l'orchestrateur de trading ;
- n'appelle aucune API Kraken privée ;
- ne possède aucune méthode de mutation `RiskPolicy` ;
- ne transforme pas « BUY maintenant » en ordre ;
- ne transforme pas « agressivité 8 » en configuration active ;
- ne transforme pas « ignore Risk » en permission.

### Sessions et confidentialité

Par défaut : 20 messages maximum par session, 32 sessions process-locales, éviction des plus anciennes. Les formes de secrets courantes sont redigées avant stockage mémoire et avant envoi au provider. Cette redaction est une défense additionnelle, pas une invitation à transmettre des secrets.

### Historique vs présent

`historical_cycle.agent_input` représente ce que l'Agent stratégique avait effectivement comme entrée persistée pour le cycle. L'état courant est étiqueté séparément. Une rationale persistée peut être résumée comme justification enregistrée, mais le chat ne prétend pas accéder à une chaîne de pensée cachée.

---

## 20. Sécurité et séparation PAPER / LIVE

`ExecutionMode` ne contient que `PAPER`. Le LIVE reste non représentable et nécessitera une décision dédiée. Aucune clé Kraken privée n'est requise.

Le provider OpenAI stratégique ne dispose d'aucun outil d'exécution. Le provider conversationnel n'a également aucun outil ni port d'exécution. Les deux partagent uniquement la sélection `LLMModel`, pas une surface d'action.

Le bind API par défaut reste local. Toute exposition distante du cockpit/chat/lifecycle nécessitera une politique d'authentification explicite.

---

## 21. Stratégie de tests

Validation Batch 14 confirmée :

- `pytest backend` : **266 tests passés**, 2 warnings externes ;
- Ruff : **All checks passed** ;
- mypy : **81 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push : `dc60033f60bf5d98a68e6131a9320e575d46cc8d` ;
- working tree propre après push.

Tests Batch 15 intégrés :

- chat possible moteur RUNNING sans stop/restart ;
- même architecture pour Luna/Sol ;
- absence de chemin Risk/Broker/Kraken/`ExecutionIntent` ;
- historique chat absent de `AgentInput` ;
- BUY/Risk mutation conversationnels sans effet ;
- contexte historique exact, présent séparé, pas de look-ahead ;
- erreurs chat distinctes des cycles `FAILED` ;
- historique borné ;
- frontend Chat sans commande lifecycle.

Validation Batch 15 confirmée le 21 septembre 2026 :

- `pytest backend` : **277 tests passés**, 2 warnings externes ;
- Ruff : **All checks passed** ;
- mypy : **89 fichiers sans erreur** ;
- `pnpm lint` : **réussi** ;
- `pnpm typecheck` : **réussi** ;
- `pnpm build` : **réussi** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push fonctionnel : `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6`.

---

## 22. Questions ouvertes prioritaires

- capital PAPER et devise de référence produit ;
- univers initial de paires ;
- valeur produit de cadence ;
- valeurs produit des limites Risk ;
- valeurs de référence fee/spread/slippage ;
- limites avancées d'exposition/drawdown en tant que contraintes Risk ;
- dataset/replay canonique concret pour les expériences appariées ;
- politique de rétention du journal ;
- reconstruction du ledger et réconciliation après crash ;
- éventuelle persistance durable du chat si un besoin réel apparaît ;
- mécanisme explicite, audité et versionné d'instructions opérateur modifiant réellement la stratégie ;
- source d'événements et protocole d'un futur WebSocket cockpit ;
- conditions futures d'un éventuel LIVE.

Ces choix doivent être consignés dans `10_DECISIONS_ET_CHANGELOG.md` lorsqu'ils deviennent canoniques.
