# 11 — Améliorations planifiées

> Référence de reprise des chantiers 19.x. Ce document distingue ce qui est **implémenté dans le Batch 19.1**, ce qui reste **planifié** et ce qui reste **à décider**.

## 1. Référence

```text
Repository              : Ax-07/AI-Spot-Trader
Branche                 : main
HEAD GitHub main audité : dbdc8f83bb39c158ec7331ce2adba616d2922842
Date Batch 19.1         : 2026-09-24
```

Le patch 19.1 n'est pas déclaré intégré à GitHub avant validation/commit explicites de l'opérateur.

## 2. Invariants transverses

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement ;
- SPOT + PERPETUAL linéaire ;
- aucune sortie LLM ne déclenche directement Broker/Kraken ;
- Risk Engine déterministe = autorité finale ;
- IA = choix stratégique ;
- calculs, comptabilité, monitoring et statistiques = déterministes ;
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
| Cycle stratégique | BUY / SELL / HOLD | oui, Agent unique |
| Discovery / watchlist | réévaluer les marchés intéressants | oui, même Agent |

Les valeurs exactes restent configurables et ne sont pas figées ici.

# 4. Comptabilité SPOT par position — INTÉGRÉE DANS LE PATCH 19.1

## Confirmé dans 19.1

- `AssetPosition` expose `asset`, `quantity`, `available`, `average_entry_price`, `remaining_cost_basis`, `realized_pnl`, `accounting_complete` ;
- BUY successifs : coût économique moyen pondéré, calculé comme coût restant / quantité ;
- coût restant : débits cash BUY réels, frais inclus ;
- vente partielle : base libérée au prorata, P&L réalisé net, coût moyen unitaire du solde conservé ;
- vente totale : position supprimée, dernier P&L réalisé conservé dans le Fill/audit ;
- spread/slippage déjà inclus au prix de fill, donc jamais rajoutés à la base de coût ;
- frais SELL déjà retranchés du crédit cash utilisé pour le P&L ;
- persistence/recovery via JSON `PortfolioState`, sans migration SQL ;
- anciens snapshots compatibles avec `accounting_complete=false` ;
- API et types frontend enrichis ;
- cockpit Positions affiche les valeurs backend et ne recalcule rien ;
- `AgentInput` transporte naturellement le `PortfolioState` enrichi.

## Encore planifié

- P&L latent SPOT ;
- mark/prix courant canonique daté ;
- rafraîchissement indépendant du cycle IA ;
- éventuelle projection historique complète d'une position après fermeture/réouverture.

## À décider

- prix de valorisation SPOT du Batch 19.2 (`last`, autre mark canonique ou approche conservatrice) ;
- éventuel modèle durable séparé pour l'historique de position au-delà des fills/audits déjà persistés ;
- politique d'arrondi/quantification spécifique exchange si un besoin réel apparaît au-delà de `Decimal`.

# 5. Monitoring / mark-to-market — PLANIFIÉ 19.2

Objectif : faire évoluer l'état des positions sans appel LLM.

À construire :

- acquisition prix/marks Kraken adaptée au monitoring ;
- revalorisation de toutes les positions ouvertes ;
- P&L latent SPOT et PERPETUAL ;
- exposition, marge, maintenance, liquidation, funding ;
- snapshots datés cohérents ;
- cadence configurable ;
- staleness/erreurs explicites ;
- atomicité entre fills et revalorisation.

À décider : cadence, référence de valorisation SPOT, persistence des marks et comportement en trou de données.

# 6. Mode gestion lorsque l'exposition est saturée — PLANIFIÉ 19.3

Objectif : lorsque le backend sait qu'aucune nouvelle exposition ne peut être autorisée, éviter la recherche IA inutile d'ouverture et concentrer le même Agent sur l'existant.

Cible :

```text
Portfolio mark-to-market + limites Risk
-> CapacityEvaluator déterministe
   -> NORMAL
   -> MANAGEMENT
```

En MANAGEMENT : univers stratégique = positions ouvertes ; HOLD/réduction/clôture restent possibles ; aucune augmentation d'exposition ne doit contourner Risk.

À décider : nom des états, granularité de la capacité et métriques exactes de tokens économisés.

# 7. Explicabilité des décisions IA — PLANIFIÉ 19.5

Le `rationale` existe déjà. Le chantier porte sur son exposition produit :

- Accueil : dernière décision + « Pourquoi l'IA ? » ;
- Positions : décisions/trades corrélés ;
- Historique : lecture synthétique avant JSON ;
- chart : rationale associé aux markers ;
- Risk toujours affiché séparément.

# 8. Discovery automatique et watchlist — PLANIFIÉ 19.4

Deux étapes distinctes :

1. backend déterministe → univers techniquement admissible ;
2. même Agent stratégique → watchlist.

Invariant :

```text
univers surveillé = watchlist IA actuelle + toutes les positions ouvertes
```

Le mode manuel reste nécessaire pour les tests reproductibles.

À décider : taille de watchlist, persistence/versionnement, lien avec Campaign/paper_run et recovery.

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
| 1 | 19.1 — Comptabilité SPOT | coût moyen, coût restant, P&L réalisé, recovery | patch implémenté |
| 2 | 19.2 — Monitoring | P&L latent et état vivant sans LLM | planifié |
| 3 | 19.3 — Mode gestion | évite recherche IA inutile à exposition saturée | planifié |
| 4 | 19.4 — Discovery/watchlist | univers dynamique versionné | planifié |
| 5 | 19.5 — Explicabilité | rationale visible vs Risk | planifié |
| 6 | 19.6A — Candles/streaming | données chart canoniques | planifié |
| 7 | 19.6B — Marchés/charts | rendu, onglets, markers | planifié |

## 13. Validation attendue des prochains batches

### 19.2

- monitor sans Agent ;
- multi-position SPOT/PERP ;
- funding/liquidation ;
- concurrence/restart/staleness.

### 19.3

- aucune recherche d'ouverture lorsque capacité saturée ;
- réduction/clôture/HOLD ;
- retour au mode normal ;
- métriques IA.

### 19.4

- eligibility sans ranking ;
- watchlist Agent bornée ;
- versionnement/recovery ;
- invariant watchlist + positions ouvertes ;
- mode manuel reproductible.

### 19.5

- API/audit ;
- lint/typecheck/build frontend ;
- rationale et Risk clairement séparés.

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
