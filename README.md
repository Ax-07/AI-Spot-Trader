# AI Spot Trader

AI Spot Trader est une application expérimentale de **trading crypto SPOT pilotée par un agent IA unique**.

Le projet étudie jusqu'où un agent IA peut prendre des décisions de trading autonomes à partir d'un état de marché et de portefeuille structurés, tout en restant encadré par un **Risk Engine déterministe** qui conserve l'autorité finale avant toute exécution.

> **Statut :** le Batch 09 — Persistance et journal d'audit est intégré sur `main`. Le Batch 10 — API FastAPI de contrôle et d'observation est actuellement un **patch proposé, non intégré** tant que la validation locale, le commit et le push n'ont pas été confirmés.

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
- communication : REST et WebSocket uniquement lorsqu'un besoin réel le justifie ;
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
                                       FastAPI read/query layer
```

## Agent IA

Le port canonique reste :

```python
LLMProvider.generate_decision(agent_input: AgentInput) -> DecisionCandidate
```

Le fournisseur ne produit que `action`, `symbol`, `proposed_quantity` et `rationale`. Les IDs et timestamps restent sous contrôle applicatif. GPT-5.6 Luna est le modèle initial ; Sol reste sélectionnable par configuration.

L'agressivité est un entier de 1 à 10. Son mapping produit exact n'est pas encore figé et n'est pas inventé par l'API.

## Trading PAPER canonique

`TradingCycleRunner.run_cycle()` exécute exactement un cycle et `TradingEngine` répète cette primitive séquentiellement. Un seul `MarketState` est partagé entre Agent, Risk et Broker pour le cycle, et un seul `PortfolioState` pré-cycle est partagé entre Agent et Risk.

- HOLD traverse Risk et produit un résultat complet sans intent.
- REJECT est une issue métier normale sans Broker.
- MODIFY utilise exactement la quantité autorisée par Risk.
- ALLOW transmet l'intent produit par Risk.
- Les erreurs Market/Portfolio/Agent/Risk/Broker restent des cycles `FAILED`, jamais des HOLD synthétiques.

## Persistance durable — Batch 09 intégré

Le package `ai_spot_trader.persistence` utilise SQLAlchemy async, PostgreSQL et Alembic. `AuditedTradingCycleRunner` persiste le `TradingCycleResult` après le runner canonique sans dupliquer l'orchestration.

Le schéma `0001_audit_journal` conserve :

- `audit_cycles` ;
- `audit_decisions` ;
- `audit_risk_assessments` ;
- `audit_execution_intents` ;
- `audit_fills`.

Le graphe est transactionnel et idempotent par `cycle_id`. La persistance ne garantit pas encore un exactly-once global entre la mutation du ledger PAPER mémoire et le commit PostgreSQL ; la reconstruction/réconciliation après crash reste différée.

## API FastAPI — Batch 10 proposé

Le Batch 10 ajoute une façade REST versionnée `/api/v1` sans seconde logique de trading.

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

Les listes utilisent `limit`, `offset`, un ordre déterministe `asc|desc` et des filtres simples. Les routes ne requêtent pas directement les modèles SQLAlchemy : `SqlAlchemyCycleAuditQueryService` fournit une frontière de lecture dédiée.

### Lifecycle

- `POST /api/v1/engine/start`
- `POST /api/v1/engine/stop`

Ces commandes appellent uniquement le `TradingEngine` canonique injecté dans le runtime. FastAPI ne démarre jamais automatiquement le moteur. Si aucun moteur n'est injecté, l'API l'indique explicitement au lieu d'inventer une configuration de capital, paire ou cadence.

### Portefeuille et marché

Le portefeuille courant vient du `PaperPortfolioLedger` injecté. Le dernier marché exposé par l'API d'audit est le dernier `MarketState` durable déjà utilisé par un cycle ; l'endpoint ne déclenche aucun refresh Kraken.

### Erreurs et DB

Les erreurs techniques sont exposées sous forme sanitizée (`stage`, `error_type`, `timed_out`) sans message brut potentiellement sensible.

Lorsque `AI_SPOT_TRADER_DATABASE_URL` est configurée et qu'aucun reader n'est injecté, FastAPI crée le `Database` et le query service pendant son lifespan, sans requête automatique et sans démarrer le trading. La connexion est disposée à l'arrêt. Une DB absente ou indisponible produit une erreur API générique sans fuite d'URL ou de secret.

Aucune nouvelle migration n'est nécessaire pour le Batch 10.

### WebSocket

Aucun WebSocket n'est ajouté dans ce batch. Il n'existe pas encore de bus d'événements canonique à diffuser ; ajouter un socket maintenant créerait une mécanique parallèle ou du polling déguisé. REST suffit au socle cockpit, et le temps réel sera décidé lorsque sa source d'événements sera explicitement cadrée.

## PostgreSQL local

Depuis la racine du repository :

```powershell
docker compose up -d
$env:AI_SPOT_TRADER_DATABASE_URL="postgresql+asyncpg://ai_spot_trader:local_dev_password@localhost:5432/ai_spot_trader"
backend\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

Le mot de passe versionné dans `docker-compose.yml` est uniquement une valeur locale de développement.

## Validation

Batch 09 intégré, validation Windows confirmée :

```text
pytest backend                  209 tests passés
ruff check backend              All checks passed
mypy backend\src backend\tests  63 fichiers sans erreur
git diff --check                aucune erreur
```

Pour le **patch Batch 10**, l'environnement ChatGPT a exécuté les tests FastAPI ciblés et la compilation Python. La suite complète, Ruff, mypy, `git diff --check`, le test SQL `aiosqlite` et la validation PostgreSQL doivent encore être rejoués localement avant intégration.

Commandes minimales :

```powershell
backend\.venv\Scripts\python.exe -m pytest backend
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m mypy backend\src backend\tests
git diff --check
```

Aucun appel OpenAI ou Kraken réel n'est requis pour les tests automatisés du Batch 10.

## Sécurité

- Aucun secret ou clé API réel ne doit être versionné, journalisé ou renvoyé par l'API.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- PAPER et LIVE restent explicitement séparés.
- Toute exécution doit continuer à passer par Risk.
- Le bind API par défaut reste local (`127.0.0.1`). Toute exposition distante des commandes lifecycle devra être protégée explicitement avant usage.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et développement. Il ne constitue pas un conseil financier et ne garantit aucun résultat de trading. La cible expérimentale de +4 %/jour reste une métrique de recherche, jamais une promesse.
