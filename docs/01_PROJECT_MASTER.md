# 01 — Project Master

## 1. Rôle de ce document

Ce document est la spécification fonctionnelle et architecturale principale d'**AI Spot Trader**. Les détails spécialisés sont complétés par `02_ARCHITECTURE_TECHNIQUE.md`, `03_AGENT_TRADING_RISK.md`, `09_ROADMAP_DEVELOPPEMENT.md` et `10_DECISIONS_ET_CHANGELOG.md`.

Statuts utilisés : **Confirmé**, **Proposé**, **À décider** et **Hors périmètre pour l'instant**.

---

## 2. Vision et invariants

**Confirmé.** AI Spot Trader est une application expérimentale de trading crypto **SPOT** pilotée par **un agent IA unique**. L'agent conserve la décision stratégique ; les composants déterministes construisent le contexte, imposent les contraintes de risque, exécutent en PAPER et mesurent les résultats.

Invariants principaux :

- Kraken est l'exchange initial ;
- SPOT uniquement : aucun short, levier, margin, future ou perpetual ;
- actions stratégiques `BUY`, `SELL`, `HOLD` ;
- aucune vente d'un actif non détenu ;
- GPT-5.6 Luna pour les premiers essais, Sol sélectionnable par configuration ;
- Risk Engine déterministe avec autorité finale ;
- aucune sortie LLM ne déclenche directement une exécution ;
- premières versions exclusivement en PAPER ;
- frais, spread et slippage pris en compte ;
- toutes les décisions, y compris `HOLD`, doivent pouvoir être journalisées ;
- aucun secret dans Git, prompts ou logs ;
- aucun look-ahead ;
- frontend indépendant du moteur backend ;
- un seul cycle de trading à la fois.

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

Le Batch 08 réalise le point 9. Le Batch 09 apportera le journal durable du point 10.

### V1 — cockpit et expérimentation instrumentée

V1 ajoute le cockpit Next.js/shadcn, historique, analytics P&L/drawdown/coûts/exposition, replay reproductible, expérimentations d'agressivité et comparaison Luna/Sol. Le LIVE n'est pas une condition de V1.

---

## 4. Architecture et flux de confiance

**Confirmé :** backend Python + `asyncio` + FastAPI + Pydantic ; frontend Next.js + TypeScript + shadcn/ui + Tailwind ; PostgreSQL cible ; REST/WebSocket selon le besoin.

```text
MarketDataSource
      |
      v
MarketState -----+
                 |
PortfolioState --+--> AgentInput --> Agent IA --> DecisionCandidate
                                             |
                                             v
                                        Risk Engine
                                     /       |       \
                                 REJECT    MODIFY    ALLOW
                                     \       |       /
                                             v
                                       RiskAssessment
                                             |
                              ExecutionIntent si tradable
                                             |
                              même MarketState du cycle
                                             |
                                             v
                                       Paper Broker
                                             |
                                  Fill(s) + PortfolioState
```

Principe absolu : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Le package Agent ne possède aucun chemin direct vers Risk, Broker, Kraken, FastAPI ou une base de données. Le package d'orchestration relie explicitement les composants canoniques sans réimplémenter leur métier.

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

`AgentInput` contient `cycle_id`, `created_at`, les deux snapshots et `aggressiveness`.

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

---

## 6. Market State

### Confirmé au Batch 04

`MarketStateBuilder` est mono-symbole, déterministe et mémoire. Il garde un historique borné, impose un ordre temporel strict et construit les horizons descriptifs configurés.

Pour un snapshot à `T`, seules les observations `observed_at <= T` sont utilisées. Le seuil technique de stale du Market State reste distinct de la politique métier Risk.

Le Batch 08 consomme le port `MarketDataSource.snapshot(symbol)` exactement une fois par cycle. Aucun refresh caché n'est permis ensuite pour cette décision.

---

## 7. Portfolio State et Paper Broker

### Confirmé au Batch 05

`balances` est la source canonique des actifs de règlement ; `positions` est la source canonique des actifs détenus/vendables. Les rôles sont uniques et non chevauchants.

`PaperPortfolioLedger` reçoit un état initial explicitement injecté. Aucun capital PAPER, devise de référence ou univers produit n'est imposé globalement. Les mutations sont copy-on-write et atomiques.

`PaperBroker` reçoit explicitement `ExecutionIntent` et `MarketState` :

```text
Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]
```

Il ne consulte jamais Kraken. Une fois son verrou acquis, le chemin de calcul/mutation PAPER est synchrone et atomique du point de vue asyncio : le fill est construit puis la mutation ledger est appliquée sans `await` intermédiaire.

Le calcul des coûts est factorisé dans `estimate_paper_execution` et partagé par Risk et le Paper Broker. `PaperExecutionCostModel` reste injecté : `fee_rate`, `spread_bps`, `slippage_bps`.

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

---

## 9. Agent IA — intégré au Batch 07

Le port canonique reste :

```text
LLMProvider.generate_decision(AgentInput) -> DecisionCandidate
```

Le modèle fournisseur ne produit que `action`, `symbol`, `proposed_quantity`, `rationale`. `decision_id`, `cycle_id` et `created_at` restent sous contrôle de l'application.

L'Agent est limité au symbole de `agent_input.market_state.symbol`. Une sortie divergente est rejetée avant création d'un `DecisionCandidate` utilisable.

L'adapter OpenAI utilise la Responses API et un JSON Schema strict. La réponse est parsée et revalidée localement sans réparation stratégique silencieuse. Le prompt versionné est `agent-luna-v1`.

Aucun retry automatique n'est implémenté : transport, enveloppe fournisseur, sortie structurée invalide et violation du contrat Agent restent des erreurs explicites.

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
- `Clock` ;
- factory `cycle_id` ;
- timeouts Market/Agent/Broker.

Un verrou `asyncio.Lock` interne couvre l'intégralité du cycle. Les appels manuels et la boucle autonome partageant le même runner ne peuvent donc pas modifier le ledger entre le snapshot pré-cycle, Risk et l'exécution.

### Résultat de cycle

`TradingCycleResult` est une dataclass immuable interne d'orchestration. Elle conserve les artefacts canoniques réellement atteints : `AgentInput`, `DecisionCandidate`, `RiskAssessment`, `ExecutionIntent`, fills et snapshot portfolio post-exécution.

Elle ne remplace aucun modèle métier et ne fournit pas de persistance durable. Elle prépare Batch 09 à conserver HOLD, REJECT, MODIFY, ALLOW et erreurs techniques.

### Erreurs

Une erreur avant décision n'appelle pas l'Agent si les entrées ne sont pas disponibles. Une erreur Agent n'appelle ni Risk ni Broker. Une exception technique Risk n'appelle pas le Broker. REJECT n'est pas une exception. Une erreur Broker n'est jamais transformée en réussite.

Les échecs techniques sont représentés par `FAILED` avec une étape et un type d'erreur sanitizé. Aucune erreur LLM n'est transformée en HOLD.

### Timeouts

Market, Agent et Broker sont entourés d'`asyncio.timeout`. Les trois durées sont obligatoirement injectées, finies et strictement positives. Aucun timeout artificiel n'est appliqué au Risk Engine synchrone.

Le Paper Broker canonique ne contient pas de `await` entre le calcul du fill et la mutation ledger après acquisition de son verrou. Une incertitude d'exécution d'un futur broker externe ne devra jamais déclencher une réexécution automatique du même intent sans mécanisme de réconciliation.

### Boucle

`TradingEngine` répète le même runner séquentiellement :

```text
cycle terminé -> attente cadence -> cycle suivant
```

La cadence est injectée et `> 0`. Elle est mesurée après la fin du cycle ; aucun cycle de rattrapage n'est lancé si un cycle dure plus longtemps que la cadence.

`start()` refuse une seconde loop. `stop()` pose un signal coopératif, réveille immédiatement l'attente de cadence et attend le cycle borné déjà en cours. Une erreur de cycle ne provoque pas de boucle serrée : la cadence normale reste appliquée avant le cycle suivant.

---

## 12. Runtime FastAPI et composition

`AppRuntime` peut recevoir un moteur implémentant uniquement `stop()` comme dépendance de lifecycle. `close()` pose le signal global de shutdown puis attend le moteur configuré.

`create_app(..., trading_engine=...)` permet cette composition sans lancer le moteur. L'import du module, le healthcheck et les tests d'application ne provoquent aucun appel OpenAI/Kraken et aucune boucle réelle.

Le Batch 08 ne fabrique pas de composition production complète, car capital PAPER, symbole, cadence, RiskPolicy et coûts PAPER restent des décisions produit ouvertes.

---

## 13. Persistance et analytics

PostgreSQL reste la cible du Batch 09. Le Batch 08 ne prétend pas fournir de journal durable ni de reprise après crash.

P&L brut/net, drawdown, frais, slippage, exposition, nombre de trades et performance quotidienne/cumulée restent des objectifs Analytics ultérieurs.

---

## 14. Sécurité et séparation PAPER / LIVE

`ExecutionMode` ne contient que `PAPER`. Le LIVE reste non représentable et nécessitera une décision dédiée. Aucune clé Kraken privée n'est requise.

Le provider OpenAI ne dispose d'aucun outil d'exécution et ne connaît ni Broker ni Kraken. L'orchestrateur n'interprète jamais `rationale` comme commande.

---

## 15. Stratégie de tests

Les tests Batch 08 sont offline et déterministes. Ils utilisent des fakes des ports canoniques, horloges/UUID contrôlés et cadences/timeouts courts.

Cas couverts par la suite ciblée : HOLD via Risk, BUY/SELL ALLOW, MODIFY, REJECT, identité des snapshots, corrélation `cycle_id`, erreurs Market/Agent/Risk/Broker, timeouts, absence de refresh caché, sérialisation manuelle/autonome, start double interdit, stop pendant cadence, absence de boucle serrée, mutation portfolio BUY/SELL et shutdown runtime.

Aucun test réussi ne doit être déclaré s'il n'a pas réellement été exécuté.

---

## 16. Questions ouvertes prioritaires

- capital PAPER et devise de référence produit ;
- univers initial de paires ;
- valeur produit de cadence ;
- valeurs produit des limites Risk ;
- mapping agressivité 1–10 ;
- valeurs de référence fee/spread/slippage ;
- exposition portefeuille avancée ;
- frontière de journée et données P&L ;
- ORM, migrations, rétention et reprise après panne ;
- conditions futures d'un éventuel LIVE.

Ces choix doivent être consignés dans `10_DECISIONS_ET_CHANGELOG.md` lorsqu'ils deviennent canoniques.
