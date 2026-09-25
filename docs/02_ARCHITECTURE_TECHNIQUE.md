# 02 — Architecture technique

## 1. Référence

Base GitHub auditée pour le Batch 19.3 :

```text
HEAD GitHub main : 44670a249ba662b2afd50a0a9e2a0e63ea4ed76d
```

Le HEAD doit être revérifié au démarrage de chaque batch. Le Batch 19.3 décrit ci-dessous est un patch local tant qu'il n'a pas été validé/intégré explicitement par l'opérateur.

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
                    +-- CapacityEvaluator
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

## 6. CapacityEvaluator et mode MANAGEMENT — Batch 19.3

Le chemin multi-marchés devient :

```text
PortfolioState marqué + RiskPolicy partagé
        |
        v
CapacityEvaluator
   | NORMAL
   |   -> MarketSelectionInput complet
   |   -> même Agent + tools read-only éventuels
   |
   | MANAGEMENT
   |   -> positions ouvertes intersectées avec l'univers exécutable
   |   -> même Agent, sans tools de recherche d'ouverture
   v
MarketSelection -> MarketState exact -> AgentInput -> même Agent -> RiskEngine
```

`CapacityEvaluator` et `RiskEngine` reçoivent **la même instance `RiskPolicy`** dans `composition.py` et `campaign_composition.py`. Le premier ne possède donc pas une seconde configuration de limites.

Le pré-calcul ne prétend pas reproduire Risk. Il peut établir avant sélection :

- disponibilité du cash settlement ;
- présence d'une valorisation canonique complète ;
- notional dérivé total déjà utilisé par rapport à `max_total_derivative_exposure` ;
- saturation des positions existantes par rapport à `max_derivative_position_notional` ;
- marchés correspondant aux positions actuellement ouvertes.

Il ne possède pas encore le `MarketState` du marché sélectionné. Les contrôles suivants restent donc chez Risk : minimum de quantité, caractéristiques du contrat, levier maximum instrument, marge effective/frais, fraîcheur du marché et buffer de liquidation.

Le SPOT ne reçoit aucun plafond d'exposition global inventé : la politique actuelle ne possède pas un tel champ. Avant sélection, du cash settlement positif signifie donc qu'une ouverture SPOT est théoriquement possible ; l'ordre proposé reste ensuite borné/refusé par Risk.

Une valorisation incomplète produit `MANAGEMENT` avec raison explicite plutôt qu'une capacité fictive. Si aucune position ouverte exécutable n'existe dans ce cas, la sélection MANAGEMENT échoue explicitement au lieu de créer un HOLD synthétique déterministe.

### Barrière Risk

Le contexte `MANAGEMENT` est transmis à Risk. Après les contraintes communes, Risk rejette toute action qui augmenterait l'exposition avec `MANAGEMENT_EXPOSURE_INCREASE` :

- SPOT : `BUY` augmente, `SELL` réduit ;
- PERPETUAL : action de même sens ou ouverture sans position augmente ; action opposée à la position existante réduit et conserve la logique `reduce_only`/anti-reversal existante.

HOLD passe toujours sans intention d'exécution. Le mode n'autorise jamais Broker directement.

### Économie IA et audit

`OpenAIDecisionProvider` conserve ses surfaces normales. Pour MANAGEMENT, deux surfaces dédiées du **même objet Agent** :

- désactivent la boucle de tools pendant la sélection ;
- remplacent uniquement l'univers transporté par les positions ouvertes ;
- ajoutent un `capacity_context` indiquant mode, raison et `new_opening_research_skipped=true` ;
- gardent la décision finale stratégique sur le `MarketState` exact.

Aucune estimation de tokens n'est inventée : aucune donnée `input_tokens`/`output_tokens` canonique n'existe aujourd'hui dans l'infrastructure.

## 7. Persistence / recovery

Aucune migration SQL n'est requise. Les snapshots `PortfolioState` sont déjà stockés sous forme JSON et le `market_selection_input_payload` du cycle peut porter le `capacity_context`.

Le digest du résultat audité inclut l'évaluation de capacité. Le mode n'est pas un état durable mutable : après recovery, il est recalculé depuis le nouveau `PortfolioState` à chaque cycle. Il n'existe donc aucun replay ni snapshot de « mode courant » à restaurer.

Compatibilité 19.1/19.2 conservée : aucun replay Agent/Risk/Broker, aucune reconstruction rétrospective de base de coût/P&L et staleness réévaluée au snapshot.

## 8. Lifecycle et rafraîchissement

`AppRuntime` possède des `background_services`. Le lifecycle reste :

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

Les monitors SPOT et PERPETUAL sont indépendants du frontend et du cycle stratégique.

## 9. API / Agent / Risk / frontend

L'API portfolio continue de sérialiser le snapshot canonique. Le frontend affiche les valeurs du backend sans recalcul financier.

Le Batch 19.3 n'ajoute aucune dépendance frontend et ne modifie pas le cockpit : mode et raison sont déjà auditables dans les payloads de cycle. Une exposition UI dédiée pourra être ajoutée ultérieurement si elle apporte une valeur opérateur mesurée, sans déplacer le calcul de capacité dans TypeScript.

## 10. Cadences futures

Les trois boucles restent séparées :

```text
A. monitoring / mark-to-market : rapide, déterministe, zéro LLM
B. cycle stratégique            : même Agent, BUY/SELL/HOLD
C. discovery/watchlist          : même Agent, cadence plus lente
```

## 11. Discovery, watchlist et Marchés

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
