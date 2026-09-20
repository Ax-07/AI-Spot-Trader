# 02 — Architecture technique

## 1. Objet

Ce document décrit l'architecture technique courante d'AI Spot Trader. Il complète `01_PROJECT_MASTER.md` sans remplacer les décisions produit.

---

## 2. Vue d'ensemble

```text
+--------------------------+
| Frontend cockpit         |
| Next.js / TS / shadcn    |
+------------+-------------+
             |
       REST / WebSocket
             |
+------------v-------------+
| FastAPI API              |
+------------+-------------+
             |
+------------v------------------------------------------+
| Backend trading                                      |
|                                                       |
| Market source -> MarketState                          |
| PortfolioState ---> Agent -> DecisionCandidate        |
|                                   |                   |
|                                   v                   |
|                              Risk Engine               |
|                                   |                   |
|                         RiskAssessment/Intent          |
|                                   |                   |
| same MarketState ------------> Paper Broker            |
|                                   |                   |
|                          Fill + portfolio ledger       |
|                                   |                   |
|                         TradingCycleResult mémoire     |
+-------------------------------------------------------+
```

Le backend est un service autonome ; le frontend n'est jamais l'ordonnanceur du moteur.

---

## 3. Découpage backend après application du patch Batch 08

```text
backend/src/ai_spot_trader/
  agent/
    errors.py
    openai_client.py
    prompt.py
    provider.py
  api/
  broker/
    errors.py
    paper.py
    pricing.py
  core/
    clock.py
    config.py
    runtime.py
  domain/
    enums.py
    models.py
    ports.py
    symbols.py
  integrations/kraken/
  market/
    errors.py
    state.py
  portfolio/
    errors.py
    ledger.py
  risk/
    engine.py
    errors.py
    policy.py
  trading/
    __init__.py
    engine.py
  main.py
```

Responsabilités :

- `domain` : contrats canoniques fournisseur-agnostiques ;
- `integrations/kraken` : I/O et structures spécifiques Kraken public ;
- `market` : historique et snapshots déterministes ;
- `portfolio` : état mutable PAPER mémoire ;
- `broker/pricing.py` : estimation PAPER pure partagée ;
- `broker/paper.py` : exécution PAPER et mutation du ledger ;
- `risk` : évaluation déterministe sans effets de bord ;
- `agent` : transformation d'un `AgentInput` en `DecisionCandidate`, sans exécution ;
- `trading` : orchestration du cycle et répétition séquentielle, sans stratégie.

---

## 4. Contrats de domaine

Les contrats canoniques sont Pydantic stricts, `extra="forbid"`, timestamps aware normalisés UTC et valeurs financières en `Decimal`.

### DecisionCandidate

BUY/SELL exigent `proposed_quantity > 0`. HOLD interdit toute quantité. Cette quantité est la proposition stratégique amont.

### RiskAssessment

- `ALLOW` conserve la quantité demandée ;
- `MODIFY` réduit strictement la quantité ;
- `REJECT` n'autorise aucune quantité et possède au moins une raison ;
- HOLD peut être `ALLOW` sans quantité ni intent.

### ExecutionIntent

PAPER uniquement, BUY/SELL uniquement, quantité positive et corrélation au `RiskAssessment`. L'orchestrateur n'en construit jamais.

---

## 5. Frontière Agent / fournisseur LLM

Le port reste :

```python
async def generate_decision(self, agent_input: AgentInput) -> DecisionCandidate: ...
```

`OpenAIDecisionProvider` dépend de son client structuré, `LLMModel`, `Clock`, factory UUID et contrats domaine. Il ne dépend pas de Risk, Broker, Kraken, FastAPI, PostgreSQL ou du package `trading`.

Le fournisseur LLM n'émet pas `decision_id`, `cycle_id` ni `created_at`. Ces métadonnées sont enveloppées côté application.

---

## 6. Contrat structuré fournisseur

Le JSON Schema envoyé à OpenAI impose :

```text
object
  action: BUY | SELL | HOLD
  symbol: string non vide
  proposed_quantity: number | null
  rationale: string | null
required: les 4 champs
additionalProperties: false
```

La sortie est reparsée avec `Decimal`, puis validée par un modèle Pydantic interne strict. Aucune réparation silencieuse n'est admise.

---

## 7. Adapter OpenAI Responses API

`OpenAIResponsesClient` est un adapter HTTP minimal autour de `/v1/responses`, `gpt-5.6-luna | gpt-5.6-sol`, Structured Outputs stricts et `store=false`.

Les erreurs réseau/HTTP sont distinguées des erreurs d'enveloppe. Aucun retry automatique n'est implémenté.

---

## 8. Prompt versionné

`agent/prompt.py` expose `AGENT_PROMPT_VERSION = agent-luna-v1` et le prompt système. Aucun secret, aucune clé, aucune instruction d'ordre Kraken et aucun tool-calling n'y figurent.

---

## 9. Market State, Portfolio, Risk et Broker

Les composants canoniques des Batches 04 à 06 sont réutilisés directement :

- `MarketDataSource.snapshot(symbol)` fournit le snapshot marché du cycle ;
- `PaperPortfolioLedger.snapshot()` fournit le snapshot portefeuille pré-cycle ;
- `RiskEngine.evaluate()` est synchrone et produit `RiskResult` ;
- `PaperBroker.execute(intent, market_state)` réalise l'unique mutation PAPER d'exécution.

Le Batch 08 ne duplique aucun de ces composants.

---

## 10. Primitive un-cycle

`TradingCycleRunner` est la frontière d'orchestration canonique du Batch 08.

```text
run_cycle()
  |
  +--> MarketDataSource.snapshot(symbol)        [timeout]
  +--> PaperPortfolioLedger.snapshot()
  +--> AgentInput
  +--> LLMProvider.generate_decision()          [timeout]
  +--> RiskEngine.evaluate()                    [synchrone]
  +--> Broker.execute(intent, same_market)      [timeout, si intent]
  +--> PaperPortfolioLedger.snapshot(post-fill)
  +--> TradingCycleResult
```

Le runner reçoit explicitement `symbol`, `aggressiveness`, `TradingCycleTimeouts`, `Clock` et une factory `cycle_id`.

### Snapshot policy

Il n'existe qu'un appel Market par cycle. Le `MarketState` placé dans `AgentInput` est exactement celui passé à Risk puis au Broker. Le `PortfolioState` pré-cycle placé dans `AgentInput` est exactement celui passé à Risk.

Le runner réutilise les objets validés contenus dans `AgentInput` afin de rendre cette identité explicite et testable.

### Verrou de cycle

Un `asyncio.Lock` couvre tout `run_cycle()`. Un appel manuel et la boucle autonome partageant le même runner ne peuvent pas se chevaucher. Aucun autre cycle ne peut muter le ledger entre snapshot, Risk et Broker via cette orchestration.

---

## 11. Chronologie technique

Le runner utilise uniquement `Clock` pour ses timestamps testables.

```text
market.as_of <= input.created_at
portfolio.as_of <= input.created_at
input.created_at <= decision.created_at
                   <= assessment.assessed_at
                   == intent.created_at
market.as_of <= fill.filled_at
fill.filled_at <= post_portfolio.as_of
```

L'Agent, Risk et Broker gardent leurs propres validations temporelles. Cette redondance protège chaque frontière sans créer de stratégie.

---

## 12. Validation des artefacts aval

Le runner vérifie les invariants applicatifs avant de poursuivre :

- `DecisionCandidate.cycle_id` et symbole cohérents ;
- `RiskAssessment` corrélé au cycle/décision ;
- HOLD = ALLOW sans intent ;
- REJECT = aucun intent ;
- intent corrélé à l'assessment et créé au même timestamp ;
- Risk ne change pas action/symbole ;
- quantité de l'intent = quantité autorisée ;
- fills corrélés à l'intent et au même `MarketState` ;
- référence de prix = `MarketState.last_price` ;
- somme des quantités des fills = quantité autorisée.

Une violation est une erreur technique de cycle et ne provoque aucune réparation stratégique.

---

## 13. TradingCycleResult et erreurs

`TradingCycleResult` est une dataclass interne immuable. Son statut technique vaut `COMPLETED` ou `FAILED`.

`COMPLETED` inclut aussi les issues métier HOLD et REJECT. `FAILED` conserve les artefacts déjà obtenus et une `TradingCycleFailure` composée de :

```text
stage
error_type
timed_out
```

Le message brut de l'exception n'est pas copié dans ce résultat mémoire, ce qui évite de faire transiter accidentellement un détail distant sensible. Batch 09 décidera du format de journal durable.

Étapes distinguées : Market, Portfolio, Input, Agent, Risk, Broker, Post-Portfolio.

---

## 14. Timeouts

`TradingCycleTimeouts` impose trois durées explicitement injectées : Market, Agent et Broker. Elles doivent être numériques, finies et strictement positives.

`asyncio.timeout` borne les attentes I/O de l'orchestrateur. Les adapters peuvent garder leurs propres timeouts plus bas niveau ; l'enveloppe de cycle reste une borne explicite supplémentaire.

Risk n'a pas de timeout artificiel car il est synchrone et déterministe.

### Broker PAPER et annulation

`PaperBroker.execute()` prend son propre verrou puis appelle un chemin synchrone sans `await` jusqu'à la fin de la mutation. Une expiration asyncio ne peut donc pas interrompre la mutation à mi-chemin une fois ce chemin démarré.

Cette propriété n'est pas généralisée à un futur broker réseau. Si un futur appel externe laisse une exécution incertaine, la boucle ne devra jamais rejouer automatiquement le même intent sans persistance/réconciliation.

---

## 15. TradingEngine

`TradingEngine` possède le runner et une cadence explicite `> 0`.

```text
while not stop:
    await runner.run_cycle()
    await cadence_or_stop()
```

La cadence commence après la fin du cycle. Il n'existe aucun calcul de retard ni lancement concurrent pour rattraper une échéance manquée.

`start()` crée une seule tâche nommée et refuse un second démarrage actif. `stop()` pose l'event de stop, réveille la cadence immédiatement et attend la tâche. Il ne laisse pas de tâche orpheline.

Les échecs techniques représentés par `TradingCycleResult` sont des retours normaux du runner. Une exception inattendue du runner est isolée par la boucle ; son type est mémorisé, puis la cadence normale est attendue avant un nouveau cycle afin d'éviter une boucle serrée.

---

## 16. Runtime FastAPI

`AppRuntime` possède désormais optionnellement un objet satisfaisant le protocole `StoppableTradingEngine`. Son `close()` :

1. pose `shutdown_requested` ;
2. appelle et attend `trading_engine.stop()` si un moteur a été injecté ;
3. rend la main à FastAPI.

`create_app(settings, trading_engine=...)` ne démarre jamais le moteur. Aucun appel réseau n'a lieu à l'import ni au lifespan par défaut.

Batch 10 ajoutera les routes de contrôle si retenues. Le frontend reste sans autorité de lifecycle directe sur le moteur.

---

## 17. Configuration produit

Le Batch 08 n'ajoute aucune cadence, paire, capital, RiskPolicy ou coût PAPER par défaut à `Settings`.

Les timeouts de cycle et la cadence sont des paramètres explicites de composition. Les timeouts OpenAI/Kraken existants restent des paramètres d'adapters et ne deviennent pas silencieusement la policy de cycle.

---

## 18. Persistance, API et frontend

Aucune persistance, migration, route FastAPI de trading, WebSocket cockpit ou modification frontend n'est introduite au Batch 08.

La frontière Batch 09 est nette : `TradingCycleResult` fournit les données en mémoire nécessaires pour concevoir ensuite le journal durable, mais aucune reprise après crash ou réconciliation n'est prétendue ici.

---

## 19. Tests et reproductibilité

Les tests Batch 08 injectent :

- `FakeMarketData` ;
- `FakeAgent` ;
- Risk canonique instrumenté ;
- Broker PAPER canonique ou fake d'erreur/blocage ;
- `Clock` fixe ;
- factories UUID fixes ;
- timeouts/cadences très courts uniquement dans les tests.

Ils ne dépendent ni d'Internet, ni d'un compte OpenAI, ni de Kraken. La suite ciblée valide les chemins métier, les timeouts, la chronologie, l'identité des snapshots, l'absence de chevauchement, start/stop et le shutdown runtime.

---

## 20. Qualité architecturale

Chaque batch doit préserver : séparation des responsabilités, contrats testables, dépendances fournisseur confinées, calculs financiers `Decimal`, no-look-ahead, testabilité offline, aucune stratégie déterministe cachée, mutations atomiques et remplacement Luna/Sol par configuration sans refonte métier.
