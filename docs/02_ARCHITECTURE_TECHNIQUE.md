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

Le backend reste une application Python unique sous layout `src/`.

### Introduit par le Batch 03

Le patch Batch 03 ajoute une intégration Kraken dédiée sans créer de microservice ni dupliquer les contrats de domaine :

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
      integrations/
        kraken/
          errors.py
          market_data.py
          models.py
          rest.py
          symbols.py
          websocket.py
      main.py
```

Responsabilités :

- `domain` : contrats canoniques indépendants de Kraken ;
- `integrations/kraken/rest.py` : découverte publique des paires Spot ;
- `integrations/kraken/symbols.py` : normalisation fournisseur vers symbole canonique ;
- `integrations/kraken/websocket.py` : connexion Spot WebSocket v2, abonnement `ticker`, parsing, heartbeat et retry ;
- `integrations/kraken/market_data.py` : implémentation du port `MarketDataSource` et conversion finale en `MarketState` ;
- `market` : futur Batch 04, pour construction/enrichissement du contexte marché, pas pour parler directement à Kraken.

Les futurs domaines `portfolio`, `agent`, `risk`, `broker`, `trading`, `persistence`, `analytics` et `observability` ne sont créés que lorsqu'un batch le nécessite.

---

## 4. Contrats de domaine

### Confirmé au Batch 02 et préservé au Batch 03

Les échanges critiques utilisent des contrats Pydantic explicites, stricts et `extra="forbid"` dans `ai_spot_trader.domain`.

Contrats initiaux canoniques :

- `MarketState` : `market_state_id`, `as_of`, `symbol`, `last_price` ;
- `PortfolioState` : `portfolio_state_id`, `as_of`, mode PAPER, balances et positions minimales ;
- `AgentInput` : `cycle_id`, `created_at`, `market_state`, `portfolio_state`, `aggressiveness` ;
- `DecisionCandidate` : `decision_id`, `cycle_id`, `created_at`, `action`, `symbol`, `rationale` optionnelle ;
- `RiskAssessment` : `risk_assessment_id`, `cycle_id`, `decision_id`, `assessed_at`, `status`, `reasons` ;
- `ExecutionIntent` : corrélation cycle/décision/risk, timestamp, mode PAPER, action BUY/SELL, symbole et quantité positive ;
- `Fill` : `fill_id`, `execution_id`, timestamp, action BUY/SELL, symbole, quantité et prix positifs.

Le Batch 03 ne modifie pas `MarketState`. Les structures REST/WebSocket Kraken restent confinées à `integrations/kraken` et sont normalisées avant exposition au domaine.

Les types monétaires/quantitatifs utilisent `Decimal`. Les timestamps du domaine restent timezone-aware et normalisés UTC.

---

## 5. Interfaces externes

### 5.1 Kraken

**Confirmé :** Kraken est l'exchange initial et reste isolé derrière le port :

```text
MarketDataSource.snapshot(symbol) -> MarketState
```

### Adapter public retenu au Batch 03

```text
Kraken Spot public APIs
        |
        +-- REST /0/public/AssetPairs?assetVersion=1
        |      |
        |      v
        |  KrakenPairRegistry
        |  alias Kraken -> symbole canonique
        |
        +-- WebSocket v2 / ticker
               |
               v
          KrakenTicker
               |
               v
       KrakenMarketDataSource
               |
               v
          MarketState minimal
```

Règles :

- REST est utilisé uniquement pour la découverte/normalisation des paires Spot ;
- `assetVersion=1` fournit les noms d'affichage slash-separated comme représentation canonique côté intégration ;
- les alias `altname` et `wsname` sont enregistrés à partir des métadonnées Kraken, ce qui évite les conversions dispersées codées en dur ;
- WebSocket Spot v2 `ticker` fournit le dernier prix et le timestamp nécessaires au `MarketState` minimal ;
- `heartbeat` et les messages système non pertinents ne produisent pas de donnée de domaine ;
- l'abonnement public ne contient ni token, ni clé, ni secret ;
- `snapshot()` consomme le premier ticker utile puis ferme la connexion WebSocket ; aucune tâche de fond persistante n'est démarrée au Batch 03 ;
- en cas de rupture réseau, la connexion est réessayée un nombre borné et configurable de fois, avec délai configurable ;
- les payloads Kraken invalides lèvent des erreurs d'intégration dédiées plutôt que de traverser le domaine.

Le Batch 03 n'utilise aucune API privée Kraken et ne contient aucune logique d'ordre ou de trading.

### 5.2 LLM

**Confirmé :** Luna puis Sol sont isolés derrière une interface dédiée.

```text
LLMProvider.generate_decision(agent_input) -> DecisionCandidate
```

Le provider réel, le SDK, le prompt et la politique de retry restent hors Batch 03.

### 5.3 Broker

```text
Broker.execute(execution_intent) -> tuple[Fill, ...]
```

`ExecutionIntent` ne peut être qu'en `PAPER` dans l'état actuel, ce qui interdit un chemin LIVE implicite.

---

## 6. Orchestration asynchrone

### Confirmé

`asyncio` est le socle asynchrone. Les ports externes susceptibles d'effectuer de l'I/O sont asynchrones.

Au Batch 03, l'adapter Kraken suit un lifecycle borné par appel : ouverture WebSocket, abonnement, réception asynchrone, éventuel retry, puis fermeture dans un `finally`. Cela évite toute tâche orpheline et ne lance aucune boucle de trading.

Le futur moteur pourra séparer réception de marché, construction/rafraîchissement d'état, trading loop, publication cockpit et persistance. L'usage exact de tâches, queues ou bus interne reste à décider lors des batches concernés.

---

## 7. API FastAPI

### Confirmé

FastAPI fournit le plan de contrôle/observation du backend. Le bootstrap `GET /health` du Batch 01 reste inchangé et couvert par les tests.

Le Batch 03 n'ajoute pas de route de marché et ne démarre pas automatiquement l'adapter Kraken dans le lifecycle FastAPI.

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

Le frontend n'est pas modifié par le Batch 03.

---

## 10. Configuration

### Confirmé au Batch 02

La configuration comprend environnement applicatif, host/port API, log level, mode PAPER, modèle LLM et agressivité optionnelle 1–10.

### Ajout Batch 03

Configuration publique Kraken uniquement :

- `kraken_rest_url` : `https://api.kraken.com` ;
- `kraken_ws_url` : `wss://ws.kraken.com/v2` ;
- timeout REST ;
- timeout de réception WebSocket ;
- nombre maximal de reconnexions ;
- délai entre reconnexions ;
- `kraken_stale_after_seconds` optionnel.

Le seuil stale reste `None` par défaut : l'intégration sait tester/rejeter une donnée périmée lorsqu'un seuil est fourni, mais le Batch 03 ne transforme pas un choix technique local en règle métier globale.

Aucune clé API Kraken, aucun secret, aucun mode LIVE, aucun capital PAPER, aucun univers d'actifs, aucune cadence de trading et aucune limite Risk ne sont ajoutés.

---

## 11. Horloge, timestamps et reproductibilité

### Confirmé

`Clock` / `SystemClock` fournissent le seam temporel. Les timestamps de ticker Kraken RFC3339 sont normalisés en UTC avant construction du `MarketState`.

La stale detection technique compare le timestamp fournisseur à `Clock.now()`. Le seuil est injecté/configuré ; il n'est pas fixé par le domaine au Batch 03.

**À décider :** frontière de journée pour les métriques quotidiennes et seuils métier de fraîcheur pour le futur Market State/Risk Engine.

---

## 12. Résilience

### Confirmé pour l'intégration Kraken du Batch 03

- timeout explicite REST et WebSocket ;
- reconnexion WebSocket bornée ;
- délai de retry configurable ;
- réabonnement après reconnexion ;
- heartbeat Kraken accepté sans créer de faux snapshot ;
- payload mal formé rejeté ;
- fermeture WebSocket dans tous les chemins ;
- aucune boucle infinie de retry ;
- stale detection disponible avec horloge injectable.

Un circuit breaker, des connexions redondantes et une politique opérationnelle avancée restent hors périmètre.

---

## 13. Dépendances externes

### Batch 03

- `httpx` devient une dépendance runtime directe pour le REST public Kraken ;
- `websockets` est ajouté comme dépendance runtime asynchrone directe pour Spot WebSocket v2.

Aucun SDK Kraken lourd n'est ajouté. Les tests réseau ne sont pas requis pour la suite par défaut ; les tests d'intégration sont offline via fixtures, `httpx.MockTransport` et faux WebSocket.

---

## 14. Sécurité technique

### Confirmé

- pas de secrets versionnés ;
- pas de secrets dans les prompts/logs ;
- aucune clé Kraken avec retrait ;
- LIVE séparé ;
- `ExecutionMode` ne contient actuellement que `PAPER` ;
- le Batch 03 ne définit aucun champ de clé/secret Kraken et n'utilise aucune API privée.

La configuration sensible future reste côté backend et le frontend ne reçoit jamais de clés d'exchange ou de fournisseur LLM.

---

## 15. Déploiement

### À décider

Le mode de déploiement initial n'est pas encore figé : local, Docker Compose, VM, etc.

Contraintes confirmées : backend indépendant du frontend, PostgreSQL durable à terme, secrets hors repository, logs récupérables et mode PAPER explicite.

Kubernetes, microservices et orchestration complexe sont hors périmètre tant qu'un besoin n'est pas démontré.

---

## 16. Critères architecturaux de qualité

Chaque batch doit préserver :

- séparation des responsabilités ;
- contrats et interfaces testables ;
- dépendances externes encapsulées ;
- structures Kraken confinées à l'intégration ;
- pas de logique financière critique dans le frontend ;
- pas d'accès exchange depuis le LLM ;
- pas de stratégie déterministe cachée dans les indicateurs ;
- corrélation explicite des décisions ;
- timestamps non ambigus ;
- testabilité offline ;
- remplacement Luna/Sol par configuration sans refonte métier.
