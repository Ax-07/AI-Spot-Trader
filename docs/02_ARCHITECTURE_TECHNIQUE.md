# 02 — Architecture technique

## 1. Référence

Base GitHub auditée pour le cadrage des améliorations planifiées :

```text
HEAD GitHub main        : 9a312040eb671976b44e5f50077ca11a9d9213b3
Commit fonctionnel 18.13: 4cb0567cae6ff100c5ad9ad1df9e3f68b8f7ffd7
```

Le HEAD doit être revérifié au démarrage de chaque batch.

## 2. Architecture générale actuelle

```text
Next.js cockpit
  |
  +-- /backend rewrite -> FastAPI
        |
        +-- Control Plane persistence (PostgreSQL)
        |     +-- Strategy / StrategyRevision
        |     +-- Campaign
        |     +-- campaign_id -> paper_runs
        |
        +-- CampaignRuntimeManager
              |
              +-- runtime actif optionnel
                    +-- TradingEngine
                    +-- AuditedTradingCycleRunner
                    +-- TradingCycleRunner
                    +-- OpenAIDecisionProvider
                    +-- RiskEngine
                    +-- PaperBroker
                    +-- PaperPortfolioLedger
                    +-- Kraken public research/execution sources
```

Le frontend n'est pas dans la chaîne d'exécution. Le manager backend possède au plus un runtime actif et délègue aux composants canoniques existants.

## 3. Composants confirmés utiles aux prochaines évolutions

### Portefeuille / comptabilité

- `domain/models.py` : `PortfolioState`, `AssetPosition`, `DerivativePosition`, `DecisionCandidate`, inputs Agent ;
- `portfolio/ledger.py` : source de vérité PAPER en mémoire et logique d'application des fills ;
- `broker/paper.py` : coût d'exécution PAPER, fills, appels au ledger ;
- persistence/recovery : snapshots durables de `PortfolioState` et reprise fail-closed.

Le SPOT ne stocke actuellement que quantité détenue/disponible. Le PERPETUAL possède déjà une comptabilité détaillée et une primitive `mark_derivative_market()`.

### Marchés Kraken

- `integrations/kraken/market_data.py` : Spot, ticker WebSocket + historique OHLC REST pour construire `MarketState` ;
- `integrations/kraken/websocket.py` : client public ticker v2 avec `iter_tickers()` et `first_ticker()` ;
- `integrations/kraken/derivatives.py` : acquisition PERPETUAL et revalorisation déterministe du ledger via market sink ;
- `market/*` : normalisation et contexte de marché.

Le WebSocket Spot actuel sert principalement à obtenir un ticker pour le snapshot. Il n'existe pas encore de service backend durable de diffusion candles vers le cockpit.

### Trading / Agent / Risk

- `trading/engine.py` orchestre actuellement sélection, acquisition, décision, Risk et Broker dans le cycle ;
- `agent/provider.py` porte le même Agent pour `select_market()` puis `generate_decision()` ;
- `risk/engine.py` reste la frontière déterministe finale ;
- `paper_executable_markets` est snapshoté dans la Campaign et transmis comme univers exécutable statique.

### Cockpit

- `frontend/src/hooks/use-cockpit.ts` effectue aujourd'hui un polling HTTP global de 10 s lorsque l'onglet est visible ;
- `positions-panel.tsx` consomme le portefeuille/analytics backend ;
- `history-panel.tsx` regroupe les faits par cycle et expose les payloads techniques ;
- `cockpit-shell.tsx` porte la navigation principale ;
- aucun composant chart canonique n'existe actuellement.

## 4. Architecture cible des cadences

Les prochaines évolutions doivent éviter de confondre trois boucles :

```text
A. Market monitoring loop
   Kraken -> normalisation -> mark-to-market -> état portefeuille/risque technique
   fréquence rapide, zéro LLM

B. Strategic trading loop
   état canonique -> même Agent -> BUY/SELL/HOLD -> Risk -> Broker
   fréquence plus lente

C. Market discovery loop
   univers admissible -> même Agent -> watchlist stratégique versionnée
   fréquence beaucoup plus lente
```

Les valeurs exactes ne sont pas figées dans ce document. Elles devront être configurables lorsque pertinent et bornées par les limites Kraken, les besoins produit et le coût IA.

## 5. Architecture cible du portefeuille SPOT

Le modèle cible doit conserver dans le backend suffisamment d'information pour rendre déterministes et récupérables :

- quantité ;
- coût de revient restant ;
- prix moyen d'entrée ;
- P&L réalisé ;
- P&L latent calculé au mark courant ;
- frais/coûts associés.

Les buys successifs doivent produire une moyenne pondérée canonique. Une vente partielle doit libérer seulement la part de coût correspondante et réaliser le P&L de la quantité vendue. Une vente totale doit fermer la position sans perdre l'historique auditable des fills/P&L.

**À décider lors du batch comptable :** forme exacte du modèle (`AssetPosition` enrichi ou sous-structure dédiée), séparation coût brut/coûts d'exécution et politique d'arrondi/quantification.

## 6. Architecture cible du monitoring déterministe

Le monitoring ne constitue pas un second agent et ne prend aucune décision stratégique.

Il peut :

- maintenir les derniers prix/marks ;
- revaloriser SPOT et PERPETUAL ;
- calculer P&L latent, exposition, marge, maintenance et liquidation ;
- appliquer le funding PERPETUAL selon les données disponibles ;
- mettre à jour des snapshots/caches lisibles par l'Agent, Risk et l'API ;
- alimenter les métriques cockpit.

Il ne peut pas :

- choisir un marché à trader ;
- fermer une position de lui-même pour une raison stratégique ;
- remplacer la décision BUY/SELL/HOLD de l'Agent.

Les protections d'urgence déterministes éventuellement nécessaires à l'avenir devront faire l'objet d'une décision explicite distincte ; elles ne sont pas introduites par ce cadrage.

## 7. Mode gestion à exposition saturée

Une couche déterministe peut produire un état de capacité, par exemple conceptuellement :

```text
can_open_new_exposure: bool
reason: max_total_exposure | derivative_cap | cash/margin | ...
```

Cet état doit adapter **le périmètre présenté à l'Agent**, pas prendre la décision à sa place.

En mode gestion :

- univers stratégique = positions ouvertes ;
- outils orientés découverte de nouvelles ouvertures non nécessaires = évités ;
- actions restent BUY/SELL/HOLD selon les sémantiques du marché, avec contraintes permettant uniquement maintien/réduction/clôture ;
- Risk vérifie encore chaque proposition ;
- sortie automatique du mode dès que l'ouverture redevient techniquement possible.

Le contrat exact permettant d'empêcher une proposition augmentant l'exposition reste **à décider** entre contexte Agent explicite et validation déterministe renforcée, sans doublonner Risk.

## 8. Découverte dynamique / watchlist

Architecture cible :

```text
Kraken metadata
  -> filtre déterministe d'admissibilité
      -> univers admissible versionné
          -> même Agent IA de découverte
              -> watchlist stratégique versionnée
                  + positions ouvertes forcées
                      -> univers surveillé effectif
```

Le filtre backend peut éliminer un marché techniquement non supporté ; il ne doit pas classer les opportunités selon un score de trading.

Le mode manuel doit rester disponible pour les tests et expériences reproductibles.

## 9. Historique candles et diffusion cockpit

Architecture privilégiée :

```text
Kraken REST OHLC ------+
                       +-> CandleService normalisé -> cache/persistence -> API historique
Kraken WS OHLC --------+                               |
                                                       +-> WS cockpit
                                                               |
                                                       Lightweight Charts
```

Pour le Spot, Kraken REST OHLC renvoie au maximum les 720 entrées les plus récentes. Si le produit doit afficher davantage d'historique, le backend doit accumuler ses propres candles fermées de manière durable.

Le canal Kraken Spot WebSocket v2 `ohlc` permet les mises à jour OHLC par événement de trade. Le code actuel ne l'exploite pas encore comme service candles cockpit.

### Chargement frontend

- paire active : historique + abonnement temps réel prioritaires ;
- autres onglets : métadonnées légères, cache, lazy loading ;
- ne pas instancier/rendre tous les charts simultanément ;
- le frontend ne corrige ni ne réconcilie lui-même les séries canoniques.

## 10. API/WS cible

Les contrats précis sont **à décider**, mais le découpage probable est :

- endpoint lecture watchlist courante + version ;
- endpoint historique watchlist/audit ;
- endpoint état monitoring/positions enrichies ;
- endpoint candles initiales par marché/timeframe ;
- WebSocket cockpit pour ticks/candles/position marks ;
- endpoints d'audit/corrélation décisions ↔ positions/fills réutilisables par UI.

Un seul backend reste propriétaire de ces données.

## 11. Persistence et migrations

Les évolutions suivantes peuvent nécessiter des migrations :

- état comptable SPOT enrichi dans snapshots ou tables durables ;
- versions de watchlist et raisons de changement ;
- métriques d'appels/tokens économisés ;
- candles accumulées au-delà des limites natives Kraken.

Le schéma exact ne doit pas être figé avant l'audit du modèle de persistence au début de chaque batch.

## 12. Références externes Kraken vérifiées le 2026-09-24

- Spot REST OHLC : `https://docs.kraken.com/api-reference/market-data/get-ohlc-data`
  - jusqu'à 720 entrées récentes ; données plus anciennes non récupérables via cet endpoint ;
- Spot WebSocket v2 OHLC : `https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/ohlc`
  - abonnement multi-symboles ; updates OHLC générées sur événements de trade.
