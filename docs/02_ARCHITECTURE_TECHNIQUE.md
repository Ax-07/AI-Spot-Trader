# 02 — Architecture technique

## 1. Référence

Base GitHub auditée pour le Batch 19.2 :

```text
HEAD GitHub main : 01ca1e857947d969556481e5593c5712d137f5ad
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
                    +-- PaperSpotMarkToMarketMonitor
                    +-- PaperDerivativeMarkToMarketMonitor
                    +-- Kraken public research/execution sources
```

Le frontend n'est pas dans la chaîne d'exécution. Le backend possède la source de vérité trading et la valorisation live.

## 3. Comptabilité SPOT canonique — Batch 19.1

Le chemin comptable reste :

```text
MarketState
-> Risk
-> ExecutionIntent
-> PaperBroker
-> PaperExecutionCostModel
-> Fill
-> PaperPortfolioLedger
-> PortfolioState JSON durable
-> recovery / AgentInput / API / cockpit
```

`PaperExecutionCostModel` produit un prix de fill déjà dégradé par le spread et le slippage. Les coûts explicatifs `spread_cost` et `slippage_cost` restent enregistrés séparément mais ne sont pas réajoutés à la base de coût.

Pour un BUY SPOT :

```text
coût de revient restant += fill.notional + fill.fee
prix/coût moyen d'entrée = coût de revient restant / quantité
```

Pour un SELL partiel :

```text
base libérée = coût restant avant vente * quantité vendue / quantité avant vente
P&L réalisé du fill = (fill.notional - fill.fee) - base libérée
coût restant après vente = coût restant avant vente - base libérée
```

`AssetPosition.accounting_complete` distingue les positions possédant une base de coût fiable des snapshots historiques incomplets.

## 4. Mark-to-market SPOT canonique — Batch 19.2

Deux chemins alimentent le **même** ledger :

```text
cycle d'exécution SPOT
KrakenMarketDataSource.snapshot()
-> MarketState causal validé
-> PaperPortfolioLedger.mark_spot_market()

monitor indépendant du LLM
PaperSpotMarkToMarketMonitor
-> KrakenMarketDataSource.observation()
-> MarketObservation causal
-> PaperPortfolioLedger.mark_spot_observation()

PaperDerivativeMarkToMarketMonitor
-> KrakenDerivativesMarketDataSource.snapshot()
-> MarketState dérivé causal
-> PaperPortfolioLedger.mark_derivative_market()
```

La source retenue est le dernier prix ticker Kraken SPOT (`LAST_PRICE`). La date de l'observation est conservée. Aucun prix futur n'est accepté et un mark plus ancien ne remplace jamais un mark plus récent.

Pour une position complète :

```text
market_value   = quantity * mark_price
unrealized_pnl = market_value - remaining_cost_basis
```

Le mark ne simule pas une vente. Les frais/spread/slippage déjà supportés au BUY restent dans `remaining_cost_basis`; ils ne sont pas ajoutés une seconde fois.

Un mark périmé est masqué lors du `snapshot()` selon `paper_mark_to_market_stale_after_seconds` (30 s par défaut). Les champs deviennent indisponibles plutôt que de publier une valeur actuelle trompeuse.

## 5. Agrégats `PortfolioState`

Le ledger calcule les agrégats au moment du snapshot, avant l'API :

```text
cash_available
spot_remaining_cost_basis_total
spot_market_value_total
spot_realized_pnl_total
spot_unrealized_pnl_total
equity
exposure_value
exposure_fraction
valuation_complete
```

Définition d'equity lorsque toutes les composantes nécessaires sont fraîches :

```text
equity = cash settlement
       + valeur de marché SPOT
       + Σ(margin_used + unrealized_pnl + cumulative_funding) des dérivés
```

Le réalisé SPOT n'est pas rajouté à l'equity car il est déjà dans le cash. `exposure_value = valeur SPOT + Σ notional dérivé`. `PortfolioState.valuation_complete` qualifie la complétude de la valorisation de marché/equity, pas la connaissance de la base de coût de chaque position.

Pour une lignée historique antérieure à 19.2, `spot_realized_pnl_total` reste `None` si le snapshot ne permet pas de le connaître. Aucune reconstruction par replay n'est effectuée.

## 6. Persistence / recovery

Aucune migration SQL n'est requise : les snapshots `PortfolioState` sont déjà stockés sous forme JSON.

Compatibilité :

- snapshots 19.2 : comptabilité, marks et agrégats connus restaurés ;
- snapshots 19.1 : champs de valorisation absents acceptés par défaut ;
- anciens snapshots sans base de coût : `accounting_complete=false` ;
- mark restauré mais trop ancien : masqué au prochain snapshot ;
- aucun replay Agent/Risk/Broker ;
- aucune reconstruction rétrospective de base de coût ou de P&L.

## 7. Lifecycle et rafraîchissement

`AppRuntime` possède désormais des `background_services`. Le lifecycle est :

```text
initialize()
-> recovery paper_run
-> start monitor(s)

close()
-> stop TradingEngine
-> stop monitor(s)
-> close paper_run
-> close ressources réseau
-> close database
```

Les monitors SPOT et PERPETUAL sont donc indépendants du frontend et du cycle stratégique. Valeurs par défaut :

- cadence SPOT : 5 s ;
- cadence PERPETUAL : 15 s ;
- timeout par observation : 5 s ;
- staleness : 30 s.

Une erreur d'acquisition ne fabrique aucun prix et n'arrête pas le backend ; l'ancien mark cesse d'être exposé dès qu'il dépasse le seuil de fraîcheur.

## 8. API / Agent / Risk / frontend

`AgentInput` et `RiskEngine` consomment déjà `PortfolioState`; ils reçoivent donc naturellement les nouvelles valeurs sans calcul parallèle du P&L latent.

L'API portfolio sérialise le snapshot canonique. Le frontend affiche `mark_price`, `market_value`, `remaining_cost_basis`, `realized_pnl` et `unrealized_pnl` tels quels. Une donnée `None` apparaît comme `—`.

L'analytics PAPER historique conserve son rôle de replay causal des cycles persistés ; il n'est pas utilisé comme moteur de valorisation live.

## 9. Cadences futures

Les trois boucles restent séparées :

```text
A. monitoring / mark-to-market : rapide, déterministe, zéro LLM
B. cycle stratégique            : même Agent, BUY/SELL/HOLD
C. discovery/watchlist          : même Agent, cadence plus lente
```

## 10. Discovery, watchlist et Marchés

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

Pour les charts : Kraken/backend restent canoniques ; le cockpit consommera historique REST + mises à jour WebSocket normalisées côté backend et rendues via Lightweight Charts.
