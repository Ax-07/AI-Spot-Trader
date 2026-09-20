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

### Proposé

Le code devra favoriser des modules aux responsabilités nettes plutôt qu'un service monolithique :

```text
backend/
  app/
    api/
    core/
    market/
    portfolio/
    agent/
    risk/
    broker/
    trading/
    persistence/
    analytics/
    observability/
    integrations/
      kraken/
      llm/
```

Cette arborescence est **proposée**, pas encore canonique. Le batch bootstrap peut l'ajuster si une structure plus simple est préférable.

### Responsabilités

- `market` : normalisation et construction du `MarketState`.
- `portfolio` : modèle canonique du portefeuille.
- `agent` : contrat d'entrée/sortie et décision stratégique.
- `risk` : règles déterministes, autorité finale.
- `broker` : exécution PAPER puis abstraction d'exécution.
- `trading` : orchestration de la boucle.
- `persistence` : repositories, transactions, migrations.
- `analytics` : P&L et mesures.
- `observability` : logs, métriques, traces/corrélation.
- `integrations/kraken` : détails Kraken.
- `integrations/llm` : fournisseur Luna/Sol.

---

## 4. Contrats de domaine

### Confirmé

Les échanges entre composants critiques doivent utiliser des types explicites et validés. Pydantic est le choix confirmé pour les modèles/validation exposés entre couches.

### Proposé

Contrats principaux :

- `MarketState`
- `PortfolioState`
- `AgentInput`
- `DecisionCandidate`
- `RiskAssessment`
- `ExecutionIntent`
- `OrderRequest`
- `Fill`
- `TradeCycleRecord`
- `PerformanceSnapshot`

Chaque contrat devrait comporter :

- version de schéma si nécessaire ;
- timestamp ;
- identifiant stable/corrélable ;
- types stricts ;
- validation aux frontières.

Les noms exacts peuvent évoluer au bootstrap.

---

## 5. Interfaces externes

### 5.1 Kraken

**Confirmé :** Kraken est l'exchange initial et doit être isolé derrière une interface.

**Proposé :** séparer au moins :

- source publique de données de marché ;
- métadonnées de produits/paires ;
- future exécution privée LIVE.

Le PAPER ne doit pas dépendre d'une clé Kraken privée.

### 5.2 LLM

**Confirmé :** abstraction dédiée permettant Luna puis Sol par configuration.

**Proposé :**

```text
LLMProvider
  generate_decision(agent_input, model_config) -> raw_response

TradingAgent
  decide(agent_input) -> DecisionCandidate
```

Ainsi, la logique d'agent ne dépend pas directement d'un SDK fournisseur.

---

## 6. Orchestration asynchrone

### Confirmé

`asyncio` est le socle asynchrone.

### Proposé

Le backend pourra séparer des tâches longues :

- réception de marché ;
- construction/rafraîchissement d'état ;
- trading loop ;
- publication d'événements cockpit ;
- persistance non bloquante.

L'orchestration doit garder une sémantique claire d'arrêt, reprise et annulation. L'usage exact de tâches, queues ou bus interne sera décidé lors des batches concernés.

**À décider :** bus d'événements interne, files `asyncio.Queue`, ou appels directs structurés.

---

## 7. API FastAPI

### Confirmé

FastAPI fournit le plan de contrôle/observation du backend.

### Proposé

Premiers domaines d'API :

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

Les routes ne sont pas encore figées.

WebSocket pourra diffuser :

- état moteur ;
- prix/market snapshots utiles ;
- décisions ;
- fills PAPER ;
- P&L.

Les commandes doivent toujours être appliquées par le backend ; le frontend ne modifie jamais directement l'état de trading.

---

## 8. Persistance et transactions

### Confirmé

PostgreSQL est la cible.

### Proposé

La persistance devra permettre :

- audit immuable ou append-oriented des événements de décision/exécution ;
- lecture efficace des états récents ;
- reconstruction ou vérification des métriques ;
- migrations versionnées.

**À décider :**

- SQLAlchemy ou autre couche d'accès ;
- Alembic ou autre outil de migration ;
- event sourcing complet ou modèle relationnel plus simple ;
- politique de snapshots.

Aucun event sourcing complet n'est décidé à ce stade.

---

## 9. Frontend

### Confirmé

- Next.js ;
- TypeScript ;
- shadcn/ui ;
- Tailwind CSS ;
- cockpit uniquement.

### Proposé

Pages/espaces :

- Overview ;
- Market ;
- Portfolio ;
- Decisions ;
- Trades ;
- Performance ;
- Settings / Experiments ;
- System / Logs.

L'ergonomie exacte sera définie après stabilisation de l'API.

---

## 10. Configuration

### Confirmé

Le modèle LLM doit être sélectionnable par configuration et PAPER/LIVE doit être séparé explicitement.

### Proposé

Configuration typée pour :

- environnement ;
- mode d'exécution ;
- modèle LLM ;
- agressivité ;
- univers d'actifs ;
- cadence ;
- limites de risque ;
- paramètres PAPER ;
- connexion PostgreSQL ;
- niveaux de log.

Priorité : rendre les expériences reproductibles et éviter les constantes cachées.

**À décider :** format de configuration, précédence variables d'environnement/fichier/DB, réglages modifiables à chaud.

---

## 11. Horloge, timestamps et reproductibilité

### Proposé fortement

Introduire une abstraction d'horloge pour permettre :

- tests déterministes ;
- replay ;
- simulation sans look-ahead ;
- timestamps cohérents.

Stocker les timestamps en UTC. L'affichage local peut être géré par le frontend.

**À décider :** frontière de journée pour les métriques quotidiennes.

---

## 12. Résilience

### Principes proposés

- ne pas trader sur données périmées ;
- timeout explicite des appels externes ;
- retries bornés ;
- backoff ;
- circuit/état dégradé observable ;
- échec LLM => pas d'ordre ;
- échec persistance critique => comportement sûr à définir ;
- arrêt gracieux des tâches `asyncio`.

**À décider :** politiques exactes de retry et comportement fail-safe par composant.

---

## 13. Sécurité technique

### Confirmé

- pas de secrets versionnés ;
- pas de secrets dans les prompts/logs ;
- aucune clé Kraken avec retrait ;
- LIVE séparé.

### Proposé

- configuration sensible uniquement côté backend ;
- frontend ne reçoit jamais de clés d'exchange/LLM ;
- redaction centralisée ;
- API de contrôle protégée avant toute exposition réseau non locale ;
- permissions minimales ;
- audit des changements de configuration sensibles.

L'authentification du cockpit n'est pas encore décidée.

---

## 14. Déploiement

### À décider

Le mode de déploiement initial n'est pas encore figé : local, Docker Compose, VM, etc.

Contraintes confirmées quel que soit le choix :

- backend indépendant du frontend ;
- redémarrage frontend sans impact trading ;
- PostgreSQL durable ;
- secrets hors repository ;
- logs récupérables ;
- mode PAPER explicite.

Kubernetes, microservices et orchestration complexe sont hors périmètre tant qu'un besoin n'est pas démontré.

---

## 15. Critères architecturaux de qualité

Chaque batch devrait préserver :

- séparation des responsabilités ;
- interfaces testables ;
- dépendances externes encapsulées ;
- pas de logique financière critique dans le frontend ;
- pas d'accès exchange depuis le LLM ;
- pas de stratégie déterministe cachée dans les indicateurs ;
- observabilité des décisions ;
- testabilité offline ;
- possibilité de remplacer Luna par Sol sans refonte métier.
