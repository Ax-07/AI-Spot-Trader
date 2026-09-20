# 02 — Architecture technique

## 1. Objet

Ce document complète le Project Master avec une vue technique. Il ne remplace pas les décisions de `01_PROJECT_MASTER.md`.

### Statuts

- **Confirmé** : décision actée.
- **Proposé** : architecture recommandée à valider par l'implémentation.
- **À décider** : choix non figé.
- **Hors périmètre** : non prévu à court terme.

---

## 2. Vue d'ensemble

### Confirmé

```text
+--------------------------+
|      Frontend cockpit    |
| Next.js / TS / shadcn    |
+------------+-------------+
             |
       REST / WebSocket
             |
+------------v-------------+
|        FastAPI API       |
| contrôle / lecture état  |
+------------+-------------+
             |
+------------v---------------------------------------+
|                 Backend trading                    |
|                                                    |
|  Market Data -> Market State                       |
|                     |                              |
|  Portfolio State ---+--> Agent -> Risk -> Broker   |
|                                      |             |
|                                      v             |
|                               Journal / Metrics    |
|                                      |             |
|                                  PostgreSQL        |
+----------------------------------------------------+
```

Le backend est un processus/service autonome. Le frontend peut disparaître sans interrompre le moteur.

---

## 3. Découpage logique backend

### Confirmé après Batch 01 / Batch 02

Le backend reste une application Python unique sous layout `src/`. Le Batch 02 introduit uniquement les packages nécessaires aux contrats et à l'infrastructure minimale :

```text
backend/
  src/
    ai_spot_trader/
      api/
      core/
        clock.py
        config.py
        runtime.py
      domain/
        enums.py
        models.py
        ports.py
      main.py
```

Les futurs domaines `market`, `portfolio`, `agent`, `risk`, `broker`, `trading`, `persistence`, `analytics`, `observability` et `integrations` ne seront créés que lorsqu'un batch en a réellement besoin. Aucun microservice n'est introduit.

Responsabilités futures :

- `market` : normalisation et construction du `MarketState` ;
- `portfolio` : modèle canonique du portefeuille ;
- `agent` : orchestration de la décision stratégique ;
- `risk` : règles déterministes, autorité finale ;
- `broker` : exécution PAPER puis abstraction d'exécution ;
- `trading` : orchestration de la boucle ;
- `persistence` : repositories, transactions, migrations ;
- `analytics` : P&L et mesures ;
- `observability` : logs, métriques, corrélation ;
- `integrations/kraken` : détails Kraken ;
- `integrations/llm` : fournisseur Luna/Sol.

---

## 4. Contrats de domaine

### Confirmé au Batch 02

Les échanges critiques utilisent des contrats Pydantic explicites, stricts et `extra="forbid"` dans `ai_spot_trader.domain`.

Contrats initiaux canoniques :

- `MarketState` : `market_state_id`, `as_of`, `symbol`, `last_price` ;
- `PortfolioState` : `portfolio_state_id`, `as_of`, mode PAPER, balances et positions minimales ;
- `AgentInput` : `cycle_id`, `created_at`, `market_state`, `portfolio_state`, `aggressiveness` ;
- `DecisionCandidate` : `decision_id`, `cycle_id`, `created_at`, `action`, `symbol`, `rationale` optionnelle ;
- `RiskAssessment` : `risk_assessment_id`, `cycle_id`, `decision_id`, `assessed_at`, `status`, `reasons` ;
- `ExecutionIntent` : corrélation cycle/décision/risk, timestamp, mode PAPER, action BUY/SELL, symbole et quantité positive ;
- `Fill` : `fill_id`, `execution_id`, timestamp, action BUY/SELL, symbole, quantité et prix positifs.

Types structurants :

- `TradingAction = BUY | SELL | HOLD` ;
- `ExecutionMode = PAPER` uniquement ;
- `RiskDecision = ALLOW | MODIFY | REJECT` ;
- `LLMModel = gpt-5.6-luna | gpt-5.6-sol`.

Le contrat stratégique ne fige pas encore le sizing. La quantité exacte existe uniquement sur l'intention d'exécution déjà autorisée/modifiée. Le mapping de sizing et d'agressivité reste à décider.

Les types monétaires/quantitatifs utilisent `Decimal`. Les quantités impossibles négatives sont rejetées et `HOLD` ne peut produire ni `ExecutionIntent` ni `Fill`.

---

## 5. Interfaces externes

### 5.1 Kraken

**Confirmé :** Kraken est l'exchange initial et doit être isolé derrière une interface.

Le Batch 02 confirme le port minimal :

```text
MarketDataSource.snapshot(symbol) -> MarketState
```

Aucune implémentation Kraken n'est fournie. Le PAPER ne dépend d'aucune clé privée.

### 5.2 LLM

**Confirmé :** Luna puis Sol sont isolés derrière une interface dédiée.

Port initial :

```text
LLMProvider.generate_decision(agent_input) -> DecisionCandidate
```

Le provider réel, le SDK, le prompt et la politique de retry restent hors Batch 02.

### 5.3 Broker

Port initial :

```text
Broker.execute(execution_intent) -> tuple[Fill, ...]
```

`ExecutionIntent` ne peut être qu'en `PAPER` dans l'état actuel, ce qui interdit un chemin LIVE implicite.

---

## 6. Orchestration asynchrone

### Confirmé

`asyncio` est le socle asynchrone. Les ports externes susceptibles d'effectuer de l'I/O sont asynchrones.

Le backend pourra séparer des tâches longues : réception de marché, construction/rafraîchissement d'état, trading loop, publication cockpit et persistance. L'usage exact de tâches, queues ou bus interne reste à décider lors des batches concernés.

---

## 7. API FastAPI

### Confirmé

FastAPI fournit le plan de contrôle/observation du backend. Le bootstrap `GET /health` du Batch 01 reste inchangé et couvert par les tests.

### Proposé

Premiers domaines d'API futurs :

```text
GET  /health
GET  /status
GET  /market
GET  /portfolio
GET  /decisions
GET  /performance

POST /engine/start
POST /engine/stop
PATCH /settings/...
```

Les routes ne sont pas encore figées. Le frontend ne modifie jamais directement l'état de trading.

---

## 8. Persistance et transactions

### Confirmé

PostgreSQL est la cible.

### Proposé

La persistance devra permettre l'audit des décisions/exécutions, la lecture d'états récents, la reconstruction des métriques et des migrations versionnées.

**À décider :** ORM, migrations, event sourcing éventuel, snapshots et politique de rétention.

---

## 9. Frontend

### Confirmé

- Next.js ;
- TypeScript ;
- shadcn/ui ;
- Tailwind CSS ;
- cockpit uniquement ;
- `pnpm` comme gestionnaire de paquets canonique.

Le frontend n'est pas modifié par le Batch 02.

---

## 10. Configuration

### Confirmé au Batch 02

La configuration backend via `pydantic-settings` comprend maintenant :

- environnement applicatif ;
- host/port API et log level ;
- `execution_mode`, dont la seule valeur acceptée est `PAPER` ;
- `llm_model`, Luna par défaut et Sol sélectionnable ;
- `aggressiveness`, entier optionnel validé de 1 à 10 ; aucune valeur par défaut métier n’est décidée.

`backend/.env.example` documente ces valeurs sans secret.

Ne sont pas encore configurés : univers d'actifs, cadence, limites chiffrées de risque, capital PAPER, connexion PostgreSQL, modèle de fill/slippage ou paramètres LIVE.

---

## 11. Horloge, timestamps et reproductibilité

### Confirmé au Batch 02

Une abstraction minimale `Clock` est introduite avec `SystemClock` comme implémentation de production. Elle fournit un point d'injection concret pour les futurs tests déterministes et replays sans look-ahead sans installer d'infrastructure de simulation supplémentaire.

Les timestamps techniques des contrats sont obligatoirement timezone-aware et normalisés en UTC.

**À décider :** la frontière de journée utilisée pour les métriques quotidiennes. Le choix UTC pour le stockage technique ne tranche pas cette question statistique.

---

## 12. Résilience

### Principes proposés

- ne pas trader sur données périmées ;
- timeout explicite des appels externes ;
- retries bornés ;
- backoff ;
- état dégradé observable ;
- échec LLM => pas d'ordre ;
- arrêt gracieux des tâches `asyncio`.

Les politiques exactes seront décidées dans les batches d'intégration.

---

## 13. Sécurité technique

### Confirmé

- pas de secrets versionnés ;
- pas de secrets dans les prompts/logs ;
- aucune clé Kraken avec retrait ;
- LIVE séparé ;
- `ExecutionMode` ne contient actuellement que `PAPER`.

La configuration sensible reste côté backend et le frontend ne reçoit jamais de clés d'exchange ou de fournisseur LLM.

---

## 14. Déploiement

### À décider

Le mode de déploiement initial n'est pas encore figé : local, Docker Compose, VM, etc.

Contraintes confirmées : backend indépendant du frontend, PostgreSQL durable à terme, secrets hors repository, logs récupérables et mode PAPER explicite.

Kubernetes, microservices et orchestration complexe sont hors périmètre tant qu'un besoin n'est pas démontré.

---

## 15. Critères architecturaux de qualité

Chaque batch doit préserver :

- séparation des responsabilités ;
- contrats et interfaces testables ;
- dépendances externes encapsulées ;
- pas de logique financière critique dans le frontend ;
- pas d'accès exchange depuis le LLM ;
- pas de stratégie déterministe cachée dans les indicateurs ;
- corrélation explicite des décisions ;
- timestamps non ambigus ;
- testabilité offline ;
- remplacement Luna/Sol par configuration sans refonte métier.
