# 11 — Améliorations planifiées

> Référence de reprise des chantiers 19.x. Ce document distingue ce qui est **intégré**, ce qui est **implémenté dans le patch 19.4**, ce qui reste **planifié** et ce qui reste **à décider**.

## 1. Référence

```text
Repository              : Ax-07/AI-Spot-Trader
Branche                 : main
HEAD GitHub main audité : bfef06d78dc34089541272c2944518499d4a1530
Date Batch 19.4         : 2026-09-25
```

Les Batches 19.1, 19.2 et 19.3 sont intégrés. Le patch 19.4 n'est pas déclaré intégré à GitHub avant validation/commit explicites de l'opérateur.

## 2. Invariants transverses

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement ;
- SPOT + PERPETUAL linéaire ;
- aucune sortie LLM ne déclenche directement Broker/Kraken ;
- Risk Engine déterministe = autorité finale ;
- IA = choix stratégique ;
- calculs, comptabilité, monitoring, capacité, filtrage technique et statistiques = déterministes ;
- frontend jamais source de vérité trading ;
- aucun secret dans prompts/logs/docs/Git ;
- frais, spread, slippage et funding pris en compte sans double comptage ;
- HOLD auditable ;
- aucun look-ahead ni sélection rétrospective.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## 3. Cadences cibles

| Cadence | But | LLM |
| --- | --- | --- |
| Monitoring / mark-to-market | prix, marks, P&L, exposition, marge, liquidation, funding | non |
| Cycle stratégique | BUY / SELL / HOLD, avec restriction MANAGEMENT si nécessaire | oui, Agent unique |
| Discovery / watchlist | réévaluer les marchés intéressants | oui, même Agent |

Le monitoring utilise par défaut une cadence de 5 s en SPOT et 15 s en PERPETUAL, avec 5 s de timeout et 30 s de staleness. Le Batch 19.4 ajoute une cadence de discovery indépendante de 15 min par défaut, évaluée uniquement pendant les cycles `NORMAL`.

# 4. Comptabilité SPOT par position — INTÉGRÉE 19.1

Confirmé : coût économique moyen pondéré, coût restant frais BUY inclus, ventes partielles au prorata, P&L réalisé net, pas de double comptage spread/slippage/frais, recovery JSON et compatibilité `accounting_complete=false`.

# 5. Monitoring / mark-to-market — INTÉGRÉ 19.2

Confirmé :

- source de mark SPOT : dernier ticker Kraken causal (`LAST_PRICE`) ;
- `mark_price`, `mark_observed_at`, `mark_source`, `market_value`, `unrealized_pnl`, `valuation_complete` ;
- P&L latent calculé uniquement côté backend avec `market_value - remaining_cost_basis` ;
- mark absent ou périmé => valeurs indisponibles ;
- position legacy avec coût inconnu => valeur de marché possible, P&L latent interdit ;
- agrégats portfolio : cash, coût restant, valeur SPOT, P&L réalisé/latent, equity, exposition ;
- monitor backend indépendant de l'Agent et du frontend ;
- snapshot/recovery compatible sans migration SQL ;
- Agent et Risk reçoivent le `PortfolioState` enrichi sans calcul financier parallèle ;
- cockpit Positions branché sur les champs backend.

# 6. Mode gestion lorsque l'exposition est saturée — INTÉGRÉ 19.3

Objectif : lorsque le backend sait qu'une nouvelle augmentation d'exposition est impossible ou qu'il ne peut pas établir une capacité sûre, éviter la recherche IA d'ouverture et concentrer le même Agent sur l'existant.

Architecture :

```text
Portfolio mark-to-market + RiskPolicy partagé
-> CapacityEvaluator déterministe
   -> NORMAL
   -> MANAGEMENT
```

Confirmé :

- une seule instance `RiskPolicy` alimente CapacityEvaluator et RiskEngine ;
- `NORMAL` conserve le chemin de sélection actuel ;
- `MANAGEMENT` limite la sélection transportée aux positions ouvertes ;
- tools read-only de recherche d'ouverture désactivés dans cette phase ;
- même `OpenAIDecisionProvider` pour sélection MANAGEMENT et décision finale ;
- HOLD, réduction partielle et clôture restent des décisions stratégiques ;
- Risk reçoit le mode et refuse toute hausse d'exposition avec `MANAGEMENT_EXPOSURE_INCREASE` ;
- réduction PERPETUAL conserve `reduce_only`/anti-reversal ;
- retour à NORMAL automatique au cycle suivant dès qu'une capacité certaine réapparaît ;
- portefeuille mixte SPOT/PERPETUAL pris en compte ;
- `valuation_complete=false` => MANAGEMENT explicite, sans capacité inventée ;
- mode, raison, capacité SPOT/PERP et `new_opening_research_skipped` audités ;
- aucun nouvel état durable de mode et aucune migration SQL.

# 7. Discovery automatique et watchlist — PATCH 19.4 IMPLÉMENTÉ

Objectif : supprimer l'obligation de maintenir manuellement toute la liste des paires à surveiller sans créer de scanner algorithmique qui décide des trades.

Architecture :

```text
Kraken MarketResearchService
-> catalogue factuel mis en cache
-> filtre déterministe d'admissibilité
-> sous-ensemble candidat borné
-> même Agent IA -> watchlist multi-marchés
-> univers effectif = watchlist + positions ouvertes
-> cycle canonique BUY/SELL/HOLD -> Risk -> Broker PAPER
```

## 7.1 Univers disponible

Le catalogue canonique reste `MarketResearchService` avec `KrakenMarketResearchBackend`. Il n'existe pas de second client/scanner stratégique.

Filtres déterministes autorisés dans 19.4 :

- `SPOT` / `PERPETUAL` configurés ;
- même quote que `paper_settlement_asset` ;
- statut Kraken exploitable ;
- PERPETUAL linéaire uniquement ;
- éventuelle `risk_allowed_pairs` non nulle ;
- snapshot disponible et causal ;
- fraîcheur maximale ;
- historique/candles suffisant selon la policy.

Ces filtres n'attribuent aucun score de qualité de trade.

## 7.2 Univers candidat

Valeurs par défaut :

- cache catalogue : 900 s ;
- refresh watchlist : 900 s ;
- timeout global d'un refresh : 45 s ;
- probe : 24 marchés max ;
- candidats Agent : 12 max ;
- watchlist : 6 max ;
- âge snapshot : 120 s max ;
- au moins 2 observations d'historique par défaut.

Le probe tourne déterministement dans le catalogue compatible afin qu'un catalogue plus large puisse être couvert au fil des refreshs sans classer les opportunités.

## 7.3 Watchlist stratégique

`OpenAIWatchlistSelector` est un adaptateur sur **la même instance `OpenAIDecisionProvider`**. Il réutilise :

- le même modèle Luna/Sol ;
- le même `StrategyInstructionsClient` ;
- la même horloge ;
- la même stratégie opérateur.

La sortie est structurée et contient plusieurs `symbol + market_type + rationale`. Le backend refuse toute sélection hors candidats, dupliquée ou supérieure à la limite.

La sélection d'une watchlist ne produit aucun `ExecutionIntent`.

## 7.4 NORMAL / MANAGEMENT

Le runner dynamique évalue `CapacityEvaluator` **avant** tout refresh de discovery.

```text
NORMAL
  -> refresh si dû
  -> watchlist Agent
  -> cycle canonique

MANAGEMENT
  -> aucun refresh destiné à ouvrir de nouveaux marchés
  -> positions ouvertes uniquement pour la sélection de gestion
  -> même Agent -> HOLD/réduction/clôture
  -> Risk reste autoritaire
```

L'économie d'IA est donc structurelle : la cadence de discovery ne contourne jamais 19.3.

## 7.5 Positions hors watchlist

Invariant implémenté :

```text
univers effectif = watchlist IA actuelle + toutes les positions ouvertes
```

Une position SPOT/PERPETUAL reste gérable même si son marché est retiré au refresh suivant.

## 7.6 Fallback et indisponibilités

- Kraken/LLM de discovery indisponible + watchlist précédente : maintien de la dernière watchlist valide ;
- aucune watchlist précédente : utilisation du bootstrap `paper_executable_markets` ;
- l'échec est audité avec son type ;
- un échec sans watchlist est temporisé par la cadence de refresh, il n'est pas retenté à chaque cycle ;
- une panne du LLM final ou de la source d'exécution reste un échec technique du cycle : le fallback de discovery ne fabrique ni décision ni prix.

## 7.7 Persistence et recovery

Décision 19.4 : **pas de table mutable dédiée de watchlist**.

La watchlist est un cache process-local. Chaque cycle enregistre dans `market_selection_input.market_discovery` les faits nécessaires à l'audit : statut, tailles catalogue/candidats, faits candidats, watchlist précédente/effective, ajouts/maintiens/retraits, rationale, erreur et prochain refresh.

Après restart :

- `NORMAL` reconstruit la watchlist ;
- `MANAGEMENT` gère d'abord les positions durables sans refresh d'ouverture ;
- `DynamicCampaignPaperRunLifecycle` étend le lifecycle canonique uniquement pour ajouter les marchés des positions restaurées à l'univers du nouveau run avant validation.

Aucun ordre historique n'est rejoué et aucune décision IA historique n'est réutilisée comme nouvelle décision.

## 7.8 Control Plane / UX

- `MarketDiscoveryPolicy` est optionnel : absence = Campaign statique historique ;
- `paper_executable_markets` reste obligatoire comme bootstrap immuable ;
- `risk_allowed_pairs=null` est accepté uniquement avec discovery ;
- une whitelist non nulle continue à restreindre Risk et la discovery ;
- le configurateur simple active la discovery et demande seulement une paire de départ/secours ;
- le mode Control Plane avancé peut toujours créer des Campaigns statiques reproductibles.

# 8. Explicabilité des décisions IA — PLANIFIÉ 19.5

Le `rationale` existe déjà. Le chantier porte sur son exposition produit :

- Accueil : dernière décision + « Pourquoi l'IA ? » ;
- Positions : décisions/trades corrélés ;
- Historique : lecture synthétique avant JSON ;
- watchlist : distinguer « pourquoi surveiller ce marché » de « pourquoi BUY/SELL/HOLD » ;
- chart : rationale associé aux markers ;
- Risk toujours affiché séparément.

# 9. Nouvel espace Marchés — PLANIFIÉ 19.6B

Navigation cible :

```text
Accueil | Marchés | Positions | Historique | Réglages
```

La vue Marchés affichera en onglets les marchés surveillés. Le frontend n'a aucune autorité sur la watchlist ou le moteur.

# 10. Charts chandeliers — PLANIFIÉ 19.6B

Renderer privilégié : **TradingView Lightweight Charts** avec données Kraken normalisées par le backend.

À afficher lorsque disponible : OHLC, prix courant, volume, prix moyen, mark/liquidation PERPETUAL et événements BUY/SELL/réduction/clôture.

# 11. Historique candles + WebSocket — PLANIFIÉ 19.6A

Pipeline cible :

```text
Kraken REST -> historique initial
Kraken WebSocket -> updates temps réel
backend -> normalisation/cache/persistence éventuelle
WebSocket cockpit -> frontend
```

Le backend doit gérer déduplication, candle courante mutable, reconnect/backfill et limitations de profondeur sans inventer de données.

# 12. Ordre global

| Ordre | Batch | Résultat principal | Statut |
| ---: | --- | --- | --- |
| 1 | 19.1 — Comptabilité SPOT | coût moyen, coût restant, P&L réalisé, recovery | intégré |
| 2 | 19.2 — Monitoring | P&L latent et état vivant sans LLM | intégré |
| 3 | 19.3 — Mode gestion | évite recherche IA inutile quand ouverture indisponible | intégré |
| 4 | 19.4 — Discovery/watchlist | univers dynamique audité, même Agent | patch implémenté |
| 5 | 19.5 — Explicabilité | rationale visible vs Risk | planifié |
| 6 | 19.6A — Candles/streaming | données chart canoniques | planifié |
| 7 | 19.6B — Marchés/charts | rendu, onglets, markers | planifié |

## 13. Validation attendue

### 19.4 — patch courant

- catalogue Kraken valide ;
- exclusion marchés incompatibles ;
- univers candidat déterministe ;
- aucun look-ahead ;
- sélection IA uniquement dans les candidats ;
- watchlist multi-marchés ;
- ajout / maintien / retrait ;
- réponse LLM invalide ou hors univers ;
- indisponibilité Kraken / LLM ;
- recovery des positions dynamiques ;
- NORMAL / MANAGEMENT ;
- aucun refresh d'ouverture inutile en MANAGEMENT ;
- positions hors nouvelle watchlist toujours gérables ;
- SPOT / PERPETUAL / portefeuille mixte ;
- audit complet ;
- aucune dépendance frontend du moteur ;
- compatibilité Campaign statique.

### 19.5

- API/audit ;
- lint/typecheck/build frontend ;
- rationale watchlist, décision et Risk clairement séparés.

### 19.6A

- parsing OHLC, déduplication, reconnect/backfill ;
- persistence/cache ;
- WebSocket cockpit ;
- staleness/lifecycle.

### 19.6B

- lint/typecheck/build ;
- light/dark ;
- changement onglet/timeframe ;
- cleanup subscriptions ;
- markers cohérents avec les fills.
