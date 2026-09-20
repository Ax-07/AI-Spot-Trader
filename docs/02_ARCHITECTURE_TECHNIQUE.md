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
| Kraken -> observations -> Market State             |
|                               |                    |
| Portfolio State --------------+--> Agent -> Risk   |
|                                      |             |
|                               ExecutionIntent      |
|                                      |             |
| Market State ------------------------+-> Broker    |
|                                      |             |
|                               Portfolio ledger     |
|                                      |             |
|                             Portfolio State/Fill   |
+----------------------------------------------------+
```

Le backend est un processus/service autonome. Le frontend peut disparaître sans interrompre le moteur.

---

## 3. Découpage logique backend

### Confirmé après Batch 05

Le backend reste une application Python unique sous layout `src/` :

```text
backend/
  src/
    ai_spot_trader/
      api/
      broker/
        errors.py
        paper.py
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
      portfolio/
        errors.py
        ledger.py
      main.py
```

Responsabilités :

- `domain` : contrats canoniques indépendants des fournisseurs ;
- `integrations/kraken/*` : données publiques Kraken et normalisation fournisseur ;
- `market/*` : historique déterministe, fenêtres, fraîcheur et construction du `MarketState` ;
- `portfolio/ledger.py` : état mémoire PAPER mutable et snapshots `PortfolioState` ;
- `portfolio/errors.py` : erreurs d'intégrité du ledger ;
- `broker/paper.py` : pricing PAPER déterministe et exécution immédiate complète ;
- `broker/errors.py` : erreurs PAPER explicites de pricing/configuration.

Les futurs domaines `agent`, `risk`, `trading`, `persistence`, `analytics` et `observability` ne sont créés que lorsqu'un batch le nécessite.

---

## 4. Contrats de domaine

### Confirmé au Batch 05

Les échanges critiques utilisent des contrats Pydantic explicites, stricts et `extra="forbid"` dans `ai_spot_trader.domain`.

Contrats marché :

- `MarketObservation` : `observed_at`, `symbol`, `last_price` ;
- `MarketState` : `market_state_id`, `as_of`, `symbol`, `last_price`, `context?` ;
- `MarketContext` : fraîcheur et fenêtres descriptives ;
- `MarketWindowStats` : statistiques de fenêtre disponibles.

Contrats portfolio/exécution :

- `AssetBalance` : `asset`, `available >= 0` ;
- `AssetPosition` : `asset`, `quantity >= 0`, `available >= 0`, avec `available <= quantity` ;
- `PortfolioState` : snapshot PAPER, actifs uniques et aucun actif partagé entre `balances` et `positions` ;
- `ExecutionIntent` : corrélation cycle/décision/risk, timestamp, PAPER, BUY/SELL, symbole, quantité positive ;
- `Fill` : corrélation exécution + `market_state_id`, `filled_at`, `pricing_as_of`, action, symbole, quantité, `reference_price`, `price`, `notional`, `fee`, `spread_cost`, `slippage_cost`.

Le `Fill` valide sa cohérence arithmétique : `notional = price * quantity` et les coûts de spread/slippage expliquent exactement l'écart adverse entre prix de référence et prix exécuté.

Toutes les quantités financières utilisent `Decimal`. Les timestamps du domaine restent timezone-aware et normalisés UTC.

---

## 5. Interfaces externes

### 5.1 Kraken

**Confirmé :** Kraken est l'exchange initial.

Le port historique reste :

```text
MarketDataSource.snapshot(symbol) -> MarketState
```

Le port d'observation normalisée reste :

```text
MarketObservationSource.observation(symbol) -> MarketObservation
```

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

Règles : aucune structure Kraken n'entre dans `market`, `portfolio` ou `broker`; aucune API privée, clé ou ordre n'est utilisé.

### 5.2 LLM

```text
LLMProvider.generate_decision(agent_input) -> DecisionCandidate
```

Le provider réel, le SDK, le prompt et la politique de retry restent hors Batch 05.

### 5.3 Broker

Le port évolue au Batch 05 afin de rendre le pricing explicite :

```text
Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]
```

`ExecutionIntent` reste uniquement `PAPER`. Le port ne contient aucun type Kraken et ne cache aucun lookup réseau.

---

## 6. Market State builder

### 6.1 Historique mémoire

`MarketStateBuilder` conserve un historique ordonné pour **un seul symbole canonique par instance**.

- limite par défaut : 10 000 observations ;
- limite surchargeable au constructeur ;
- purge déterministe des plus anciennes ;
- aucun PostgreSQL, Redis ou cache externe ;
- aucun démarrage FastAPI nécessaire.

Une observation dont le symbole change est rejetée. Les timestamps doivent être strictement croissants : doublon et insertion hors ordre sont des erreurs explicites.

### 6.2 Horizons

Deux horizons par défaut : 5 minutes et 30 minutes. Ils sont surchargeables et triés. Ils ne fixent ni cadence de trading, ni cadence d'ingestion, ni fréquence de décision.

### 6.3 Statistiques

Pour chaque horizon : `observation_count`, min, max, amplitude, return simple et volatilité réalisée lorsque calculables. Tout reste en `Decimal`; une statistique impossible reste `None`.

### 6.4 Fraîcheur et no look-ahead

Le contexte expose la dernière observation, son âge, un seuil technique optionnel et `is_stale` uniquement si ce seuil est évalué.

Pour `build(as_of=T)` :

```text
observations utilisées = observations avec observed_at <= T
```

Toute observation postérieure à `T` est exclue même si elle se trouve déjà dans l'historique.

---

## 7. Portfolio ledger PAPER

### 7.1 État initial explicite

`PaperPortfolioLedger` est construit avec un `PortfolioState` initial fourni par l'appelant. Il n'existe aucun capital ou quote asset implicite dans le composant.

```text
PaperPortfolioLedger(initial_state=PortfolioState(...))
```

Cela permet aux tests et futures expériences de choisir leurs actifs/capitaux sans figer une décision produit dans le code.

### 7.2 Sources canoniques

- `balances` : actifs de règlement disponibles ;
- `positions` : actifs détenus et vendables.

Ces rôles sont disjoints. L'invariant est validé dans le contrat `PortfolioState`, puis préservé par le ledger.

### 7.3 Mutations atomiques

Le ledger prépare chaque mutation sur copies de ses dictionnaires internes. L'état interne n'est remplacé qu'après toutes les validations :

```text
validate -> copy -> compute -> assign
```

Un rejet laisse donc balances et positions inchangées.

BUY : débit exact du quote asset, crédit de quantité base dans la position.

SELL : débit de la position base, crédit exact du quote asset. Une position tombant exactement à zéro est retirée du snapshot.

### 7.4 Snapshot

`snapshot()` produit un nouveau `PortfolioState` immutable, avec UUID injectables en test et actifs triés pour une représentation déterministe. L'horloge est injectable.

---

## 8. Paper Broker

### 8.1 Modèle de pricing

`PaperBroker` reçoit explicitement le `MarketState` associé à l'intention.

Validations avant mutation :

- mode PAPER ;
- action BUY/SELL ;
- symbole exact entre intent et Market State ;
- symbole canonique `BASE/QUOTE` ;
- `market_state.as_of <= intent.created_at` ;
- horloge d'exécution timezone-aware et non antérieure à l'intention.

Aucun appel Kraken n'est autorisé depuis `broker`.

### 8.2 Coûts injectés

```text
PaperExecutionCostModel
- fee_rate: Decimal
- spread_bps: Decimal
- slippage_bps: Decimal
```

Tous les paramètres sont finis et non négatifs. `fee_rate < 1`. La combinaison spread + slippage doit conserver un prix SELL strictement positif.

`spread_bps` représente un impact adverse **par côté**, pas un spread bid/ask total :

```text
spread_rate   = spread_bps / 10000
slippage_rate = slippage_bps / 10000

BUY  = reference * (1 + spread_rate + slippage_rate)
SELL = reference * (1 - spread_rate - slippage_rate)
```

Le calcul est strictement déterministe, sans randomisation ni arrondi silencieux.

### 8.3 Fill et mouvement de cash

```text
notional = execution_price * quantity
fee      = notional * fee_rate
```

BUY : `quote_debit = notional + fee`.

SELL : `quote_credit = notional - fee`.

Le `Fill` est construit et validé avant la mutation du ledger. Un échec de validation ou d'intégrité n'émet aucun fill retourné et ne modifie pas le portefeuille.

### 8.4 Concurrence locale

`PaperBroker.execute()` sérialise les exécutions d'une instance avec `asyncio.Lock`, afin que contrôle et mutation du ledger forment une opération cohérente dans le contexte asynchrone.

Le ledger lui-même reste synchrone et sans I/O.

---

## 9. Orchestration asynchrone

`asyncio` reste le socle asynchrone. Les frontières externes I/O sont asynchrones. `MarketStateBuilder` et `PaperPortfolioLedger` sont déterministes et synchrones.

Le Batch 05 ne démarre aucune boucle persistante ni scheduler. L'orchestration entre marché, agent, Risk et broker reste au Batch 08.

---

## 10. API FastAPI

FastAPI fournit le plan de contrôle/observation du backend. `GET /health` reste inchangé.

Le Batch 05 n'ajoute aucune route portfolio/trading et ne lance aucune tâche dans le lifecycle FastAPI.

---

## 11. Persistance et transactions

PostgreSQL reste la cible future.

Le Batch 05 ne crée ni ORM, ni migration, ni table. Le ledger mémoire est un composant PAPER technique, pas la politique finale de persistance/réconciliation.

---

## 12. Configuration

La configuration applicative `Settings` reste inchangée au Batch 05.

Aucune nouvelle variable d'environnement n'est ajoutée pour :

- capital initial ;
- devise de référence ;
- frais PAPER ;
- spread PAPER ;
- slippage PAPER.

L'état initial et les coûts sont injectés explicitement aux composants concernés. Les valeurs produit globales restent à décider.

---

## 13. Horloge, timestamps et reproductibilité

`Clock` / `SystemClock` restent le seam temporel canonique.

- observations, snapshots et fills : UTC aware ;
- snapshots portfolio : horloge ou `as_of` explicite ;
- pricing PAPER : `MarketState.as_of` doit précéder ou égaler `ExecutionIntent.created_at` ;
- fill : `pricing_as_of` conserve le timestamp du contexte de prix ;
- aucun lookup « prix actuel » n'est effectué par le broker.

Une même intention, un même portefeuille, un même Market State, un même modèle de coûts et des factories/horloges identiques produisent les mêmes valeurs numériques.

---

## 14. Résilience et erreurs

La résilience Kraken des batches précédents reste inchangée.

Le portfolio/broker ajoute des rejets explicites :

- quote balance inconnue ;
- fonds insuffisants ;
- position inexistante ;
- position disponible insuffisante ;
- rôle d'actif ambigu ;
- symbole canonique invalide ;
- symbole de pricing incompatible ;
- pricing futur ;
- horloge d'exécution invalide ;
- modèle de coûts invalide.

Les rejets ne sont pas convertis en `return ()` silencieux.

---

## 15. Dépendances externes

Aucune dépendance runtime supplémentaire n'est introduite au Batch 05.

Les calculs utilisent la bibliothèque standard (`asyncio`, `dataclasses`, `datetime`, `decimal`, `uuid`) et Pydantic déjà présent pour les contrats.

NumPy, Pandas, TA-Lib et SDK broker ne sont pas ajoutés.

---

## 16. Sécurité technique

Invariants préservés :

- pas de secrets versionnés ;
- pas de secrets dans prompts/logs ;
- aucune clé Kraken avec retrait ;
- LIVE séparé ;
- `ExecutionMode` reste PAPER uniquement ;
- aucun accès exchange depuis le LLM ;
- aucun accès Kraken depuis `portfolio` ou `broker` ;
- aucun signal stratégique produit par les composants déterministes ;
- aucune vente non couverte ;
- aucune balance ou position négative.

---

## 17. Déploiement

Toujours à décider : local, Docker Compose, VM, etc.

Le Batch 05 n'introduit ni microservice, ni worker séparé, ni infrastructure de cache.

---

## 18. Critères architecturaux de qualité

Chaque batch doit préserver :

- séparation des responsabilités ;
- contrats et interfaces testables ;
- dépendances externes encapsulées ;
- structures Kraken confinées à l'intégration ;
- pas de logique financière critique dans le frontend ;
- pas d'accès exchange depuis le LLM ;
- pas de stratégie déterministe cachée ;
- corrélation explicite des décisions/exécutions/pricing ;
- timestamps non ambigus ;
- no look-ahead ;
- testabilité offline ;
- mutations financières atomiques ;
- calculs financiers en `Decimal` ;
- remplacement Luna/Sol par configuration sans refonte métier.
