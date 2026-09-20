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
|                         TradingCycleResult             |
|                                   |                   |
|                                   v                   |
|                         Audit persistence              |
+-----------------------------------+-------------------+
                                    |
                                    v
                               PostgreSQL
```

Le backend est un service autonome ; le frontend n'est jamais l'ordonnanceur du moteur. PostgreSQL est une dépendance de persistance et d'audit, pas un moteur de stratégie.

---

## 3. Découpage backend après intégration du Batch 09

```text
backend/
  alembic.ini
  alembic/
    env.py
    script.py.mako
    versions/
      0001_create_audit_journal.py
  src/ai_spot_trader/
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
    persistence/
      __init__.py
      audit.py
      db.py
      models.py
      repository.py
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
  tests/
    test_persistence.py
    ...
docker-compose.yml
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
- `trading` : orchestration du cycle et répétition séquentielle, sans stratégie ;
- `persistence` : conservation durable du résultat de cycle sans logique stratégique.

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

Les modèles SQLAlchemy ne remplacent pas ces contrats. Ils servent uniquement au mapping durable.

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

La persistance n'est appelée qu'après production du `TradingCycleResult`.

---

## 10. Primitive un-cycle

`TradingCycleRunner` reste la frontière d'orchestration canonique.

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

### Verrou de cycle

Un `asyncio.Lock` couvre tout `run_cycle()`. Un appel manuel et la boucle autonome partageant le même runner ne peuvent pas se chevaucher.

---

## 11. Chronologie technique

```text
market.as_of <= input.created_at
portfolio.as_of <= input.created_at
input.created_at <= decision.created_at
                   <= assessment.assessed_at
                   == intent.created_at
market.as_of <= fill.filled_at
fill.filled_at <= post_portfolio.as_of
```

L'Agent, Risk et Broker gardent leurs propres validations temporelles. La persistance conserve ces timestamps tels qu'ils ont été produits.

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

Le message brut de l'exception n'est pas copié dans le résultat mémoire ni dans le journal durable.

---

## 14. Timeouts

`TradingCycleTimeouts` impose trois durées explicitement injectées : Market, Agent et Broker. Elles doivent être numériques, finies et strictement positives.

Risk n'a pas de timeout artificiel car il est synchrone et déterministe.

Le Broker PAPER canonique ne contient pas de `await` entre le calcul du fill et la mutation ledger après acquisition de son verrou. Cette propriété n'est pas généralisée à un futur broker réseau.

---

## 15. TradingEngine

`TradingEngine` possède le runner et une cadence explicite `> 0`.

```text
while not stop:
    await runner.run_cycle()
    await cadence_or_stop()
```

La cadence commence après la fin du cycle. Il n'existe aucun calcul de retard ni lancement concurrent pour rattraper une échéance manquée.

`start()` crée une seule tâche et refuse un second démarrage actif. `stop()` pose l'event de stop, réveille la cadence immédiatement et attend la tâche.

---

## 16. Runtime FastAPI

`AppRuntime` possède optionnellement un objet satisfaisant le protocole `StoppableTradingEngine`.

`create_app(settings, trading_engine=...)` ne démarre jamais le moteur. Aucun appel réseau n'a lieu à l'import ni au lifespan par défaut.

Batch 10 ajoutera les routes de contrôle utiles.

---

## 17. Frontière de persistance Batch 09

Le port minimal est :

```python
class CycleAuditWriter(Protocol):
    async def record(self, result: TradingCycleResult) -> bool: ...
```

Le wrapper :

```text
AuditedTradingCycleRunner
    |
    +--> delegate.run_cycle()
    |
    +--> audit_writer.record(result)
    |
    +--> return result
```

La couche de persistance ne se branche pas directement dans Agent, Risk ou Broker. Elle ne duplique pas `TradingCycleRunner`.

Une panne du journal est propagée ; elle n'est jamais convertie en HOLD ou en faux succès durable.

---

## 18. SQLAlchemy async et lifecycle

`Database` encapsule :

- `AsyncEngine` ;
- `async_sessionmaker[AsyncSession]` ;
- création du schéma uniquement pour les tests isolés ;
- `close()` pour disposer les connexions.

Le driver de production est `asyncpg`.

`AI_SPOT_TRADER_DATABASE_URL` est chargé via `Settings.database_url: SecretStr | None`.

---

## 19. Modèle relationnel

### audit_cycles

Clé primaire : `cycle_id`.

Conserve notamment :

- statut technique ;
- empreinte `result_digest` ;
- erreur technique sanitizée ;
- IDs des snapshots ;
- timestamps des snapshots ;
- `AgentInput` JSON/JSONB ;
- portfolio post-cycle JSON/JSONB.

### audit_decisions

Une décision maximum par cycle, corrélée par `cycle_id`.

### audit_risk_assessments

Un assessment maximum par cycle, corrélé au cycle et à la décision.

### audit_execution_intents

Absent pour HOLD et REJECT. Corrélé au cycle, à la décision et au RiskAssessment.

### audit_fills

Zéro ou plusieurs fills rattachés à l'intent.

Les contraintes FK sont configurées avec `ON DELETE CASCADE` pour préserver un graphe cohérent.

---

## 20. Idempotence et atomicité

`SqlAlchemyCycleAuditRepository.record()` calcule une empreinte déterministe du `TradingCycleResult`.

Cas :

```text
cycle_id absent
    -> écrit le graphe
    -> True

cycle_id présent + même digest
    -> aucune nouvelle écriture
    -> False

cycle_id présent + digest différent
    -> CycleAuditConflictError
```

Une transaction unique couvre l'ensemble du graphe. Les tests injectent un échec après ajout des records et vérifient que le rollback laisse toutes les tables vides.

---

## 21. Alembic

La migration initiale est :

```text
0001_audit_journal
```

Le runtime Alembic exige explicitement `AI_SPOT_TRADER_DATABASE_URL`.

Le schéma de production ne doit pas être créé avec `Base.metadata.create_all()` ; cette méthode reste réservée aux tests isolés.

Validation réelle confirmée sur PostgreSQL 18 : `upgrade head` réussi et `alembic_version = 0001_audit_journal`.

---

## 22. PostgreSQL local avec Docker

`docker-compose.yml` fournit :

- image `postgres:18.6-bookworm` ;
- base `ai_spot_trader` ;
- utilisateur de développement `ai_spot_trader` ;
- port local 5432 ;
- volume persistant ;
- healthcheck `pg_isready`.

Pour PostgreSQL 18, le volume est monté sur `/var/lib/postgresql`.

Cette composition est destinée au développement local, pas au déploiement production.

---

## 23. Reprise, réconciliation et exactly-once

Le Batch 09 ne prétend pas résoudre l'atomicité entre deux systèmes distincts :

1. le `PaperPortfolioLedger` mémoire ;
2. PostgreSQL.

Le scénario suivant reste possible :

```text
Broker mutile le ledger PAPER
        |
process crash
        |
journal PostgreSQL non commité
```

Le journal durable améliore fortement l'audit et prépare la reprise, mais il ne peut pas inventer un état durable absent.

La future stratégie de recovery devra décider explicitement de la source de vérité du ledger, des checkpoints et de la réconciliation. Aucun replay automatique d'`ExecutionIntent` n'est autorisé entre-temps.

---

## 24. Tests et reproductibilité

Tests Batch 09 :

- SQLite async mémoire pour le repository ;
- aucune instance PostgreSQL externe nécessaire à la suite standard ;
- HOLD et REJECT sans intent/fill ;
- ALLOW/MODIFY avec graphe complet ;
- IDs/snapshots/status ;
- erreur technique ;
- idempotence ;
- rollback transactionnel ;
- wrapper audité ;
- lifecycle DB.

Validation locale : **209 tests**, Ruff OK, mypy OK sur 63 fichiers, `git diff --check` OK.

Validation PostgreSQL séparée : Docker healthy, migration réelle réussie, tables et révision Alembic vérifiées.

---

## 25. Qualité architecturale

Chaque batch doit préserver : séparation des responsabilités, contrats testables, dépendances fournisseur confinées, calculs financiers `Decimal`, no-look-ahead, testabilité offline, aucune stratégie déterministe cachée, mutations atomiques, persistance factuelle et remplacement Luna/Sol par configuration sans refonte métier.
