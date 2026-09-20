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
| Kraken -> normalized observations -> Market State  |
|                                      |             |
| Portfolio State ---------------------+--> Agent    |
|                                            |       |
|                                            v       |
|                                           Risk     |
|                                            |       |
|                                            v       |
|                                           Broker   |
|                                            |       |
|                                    Journal/Metrics |
+----------------------------------------------------+
```

Le backend est un processus/service autonome. Le frontend peut disparaître sans interrompre le moteur.

---

## 3. Découpage logique backend

### Confirmé après Batch 04

Le backend reste une application Python unique sous layout `src/` :

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
      market/
        errors.py
        state.py
      main.py
```

Responsabilités :

- `domain` : contrats canoniques indépendants de Kraken ;
- `integrations/kraken/rest.py` : découverte publique des paires Spot ;
- `integrations/kraken/symbols.py` : normalisation fournisseur vers symbole canonique ;
- `integrations/kraken/websocket.py` : connexion Spot WebSocket v2, abonnement `ticker`, parsing, heartbeat et retry ;
- `integrations/kraken/market_data.py` : conversion du ticker Kraken en `MarketObservation` fournisseur-agnostique et compatibilité avec le `MarketState` minimal du port existant ;
- `market/state.py` : historique mémoire borné, fenêtres temporelles, statistiques descriptives, fraîcheur et construction du `MarketState` enrichi ;
- `market/errors.py` : erreurs génériques de construction d'état de marché.

Les futurs domaines `portfolio`, `agent`, `risk`, `broker`, `trading`, `persistence`, `analytics` et `observability` ne sont créés que lorsqu'un batch le nécessite.

---

## 4. Contrats de domaine

### Confirmé au Batch 04

Les échanges critiques utilisent des contrats Pydantic explicites, stricts et `extra="forbid"` dans `ai_spot_trader.domain`.

Contrats marché :

- `MarketObservation` : `observed_at`, `symbol`, `last_price` ;
- `MarketState` : `market_state_id`, `as_of`, `symbol`, `last_price`, `context?` ;
- `MarketContext` : `last_observed_at`, `data_age_seconds`, `stale_after_seconds?`, `is_stale?`, `windows` ;
- `MarketWindowStats` : horizon, début de fenêtre, nombre d'observations, complétude et statistiques descriptives disponibles.

Les autres contrats canoniques restent `PortfolioState`, `AgentInput`, `DecisionCandidate`, `RiskAssessment`, `ExecutionIntent` et `Fill`.

Les structures REST/WebSocket Kraken restent confinées à `integrations/kraken`. La couche `market` ne dépend d'aucun type Kraken.

Les types monétaires/quantitatifs et les statistiques du Batch 04 utilisent `Decimal`. Les timestamps du domaine restent timezone-aware et normalisés UTC.

---

## 5. Interfaces externes

### 5.1 Kraken

**Confirmé :** Kraken est l'exchange initial.

Le port historique reste :

```text
MarketDataSource.snapshot(symbol) -> MarketState
```

Le Batch 04 ajoute le port fournisseur-agnostique :

```text
MarketObservationSource.observation(symbol) -> MarketObservation
```

`KrakenMarketDataSource` implémente les deux pour conserver la compatibilité du Batch 03 tout en permettant au futur moteur de consommer directement des observations normalisées avant agrégation.

```text
Kraken Spot public APIs
        |
        +-- REST AssetPairs -> KrakenPairRegistry
        |
        +-- WebSocket v2 ticker -> KrakenTicker
                                  |
                                  v
                           provider normalization
                                  |
                                  v
                           MarketObservation
                                  |
                                  v
                         MarketStateBuilder
                                  |
                                  v
                            MarketState
```

Règles :

- aucune structure Kraken n'entre dans `market` ou dans les calculs génériques ;
- aucune API Kraken privée ;
- aucune clé ;
- aucun ordre ;
- aucune tâche de fond persistante lancée automatiquement.

### 5.2 LLM

```text
LLMProvider.generate_decision(agent_input) -> DecisionCandidate
```

Le provider réel, le SDK, le prompt et la politique de retry restent hors Batch 04.

### 5.3 Broker

```text
Broker.execute(execution_intent) -> tuple[Fill, ...]
```

`ExecutionIntent` ne peut être qu'en `PAPER` dans l'état actuel.

---

## 6. Market State builder

### 6.1 Historique mémoire

`MarketStateBuilder` conserve un historique ordonné pour **un seul symbole canonique par instance**.

- limite par défaut : 10 000 observations ;
- limite surchargeable au constructeur ;
- purge déterministe des observations les plus anciennes ;
- aucun PostgreSQL, Redis ou cache externe ;
- aucun démarrage FastAPI nécessaire ;
- aucun lien avec le frontend.

Une observation dont le symbole change est rejetée. Les timestamps doivent être strictement croissants : doublon et insertion hors ordre sont des erreurs explicites.

### 6.2 Horizons

Deux horizons par défaut :

```text
5 minutes
30 minutes
```

Ils sont surchargeables et triés. Les doublons, durées nulles ou négatives sont rejetés.

Ces horizons sont des **fenêtres de calcul**. Ils ne fixent ni cadence de trading, ni cadence d'ingestion, ni fréquence de décision.

### 6.3 Statistiques

Pour chaque horizon :

- `observation_count` ;
- `min_price` ;
- `max_price` ;
- `price_range = max - min` ;
- `return_fraction = last / first - 1` à partir de deux observations ;
- `realized_volatility` à partir de trois observations, définie comme l'écart-type population des returns simples consécutifs.

Tout le calcul reste en `Decimal`. Aucun passage silencieux en `float` n'est utilisé.

Une statistique impossible à calculer reste `None`. Une fenêtre sans observation a un compteur à zéro et aucun prix factice.

### 6.4 Complétude

`is_complete` indique que l'historique retenu atteint ou précède le début de la fenêtre et qu'au moins une observation se situe dans cette fenêtre.

Cette propriété ne garantit pas l'absence de trous entre ticks : aucune cadence attendue n'est encore définie, donc le Batch 04 ne prétend pas détecter des gaps de marché sans référentiel de fréquence.

### 6.5 Fraîcheur

Le contexte expose :

- timestamp de la dernière observation utilisée ;
- âge de cette observation en secondes ;
- seuil `stale_after` si le builder en reçoit un ;
- résultat `is_stale` uniquement lorsque ce seuil a réellement été évalué.

Le seuil par défaut reste absent. Le Batch 04 ne définit donc aucune règle Risk globale de refus de trader.

### 6.6 No look-ahead

Pour `build(as_of=T)` :

```text
observations utilisées = observations avec observed_at <= T
```

Toute observation postérieure à `T` est exclue même si elle se trouve déjà dans l'historique. Cela permet d'utiliser le même code en temps réel et en replay.

---

## 7. Orchestration asynchrone

### Confirmé

`asyncio` reste le socle asynchrone. Les frontières externes I/O sont asynchrones.

Le `MarketStateBuilder` est volontairement déterministe et synchrone : il calcule sur des observations déjà normalisées et ne fait aucun I/O.

Le Batch 04 ne démarre aucune boucle persistante ni scheduler. L'orchestration entre ingestion, builder et cycle de trading reste au Batch 08.

---

## 8. API FastAPI

FastAPI fournit le plan de contrôle/observation du backend. `GET /health` reste inchangé.

Le Batch 04 n'ajoute pas de route marché et ne lance aucune tâche de marché dans le lifecycle FastAPI.

---

## 9. Persistance et transactions

PostgreSQL reste la cible future.

Le Batch 04 ne crée ni ORM, ni migration, ni table, ni pipeline de persistance. L'historique mémoire du builder est un mécanisme technique borné, pas la politique finale de stockage.

---

## 10. Configuration

La configuration existante reste inchangée au Batch 04.

Aucune nouvelle variable d'environnement n'est ajoutée pour les horizons, la taille de l'historique ou le stale du builder. Ces paramètres sont des valeurs de construction explicites et testables ; les defaults techniques sont versionnés dans le code.

Aucun capital PAPER, univers d'actifs, cadence de trading, sizing ou seuil Risk n'est ajouté.

---

## 11. Horloge, timestamps et reproductibilité

`Clock` / `SystemClock` restent le seam temporel canonique.

- observations et snapshots : UTC aware ;
- `build()` peut utiliser `Clock.now()` ou un `as_of` explicite ;
- tout `as_of` aware est normalisé UTC ;
- un timestamp naïf est rejeté ;
- le calcul d'âge utilise `Decimal` et les microsecondes sans conversion float.

---

## 12. Résilience

La résilience Kraken du Batch 03 reste inchangée : timeout, retries bornés, fermeture propre, heartbeat, stale technique optionnel.

La couche `market` ajoute des garde-fous déterministes :

- historique vide explicite ;
- données futures exclues ;
- données hors ordre rejetées ;
- doublons temporels rejetés ;
- symbole différent rejeté ;
- historique mémoire borné ;
- statistiques absentes plutôt que fabriquées.

---

## 13. Dépendances externes

Aucune dépendance runtime supplémentaire n'est introduite au Batch 04.

Les calculs utilisent uniquement la bibliothèque standard (`datetime`, `decimal`, collections/typing) et Pydantic déjà présent pour les contrats de domaine.

NumPy, Pandas, TA-Lib et bibliothèques d'analyse technique ne sont pas ajoutés.

---

## 14. Sécurité technique

Invariants préservés :

- pas de secrets versionnés ;
- pas de secrets dans prompts/logs ;
- aucune clé Kraken avec retrait ;
- LIVE séparé ;
- `ExecutionMode` reste PAPER uniquement ;
- aucun accès exchange depuis le LLM ;
- aucune sortie de statistique du Market State ne devient une commande de trading.

---

## 15. Déploiement

Toujours à décider : local, Docker Compose, VM, etc.

Le Batch 04 n'introduit ni microservice, ni worker séparé, ni infrastructure de cache.

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
- no look-ahead ;
- testabilité offline ;
- remplacement Luna/Sol par configuration sans refonte métier.
