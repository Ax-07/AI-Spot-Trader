# 02 — Architecture technique

## 1. Référence

Base GitHub auditée pour le Batch 19.1 :

```text
HEAD GitHub main : dbdc8f83bb39c158ec7331ce2adba616d2922842
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

Le frontend n'est pas dans la chaîne d'exécution. Le backend possède la source de vérité trading.

## 3. Comptabilité SPOT canonique — Batch 19.1

Le chemin comptable est :

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

Le coût moyen unitaire de la quantité restante ne change pas sous la méthode du coût moyen pondéré. Une clôture totale supprime l'`AssetPosition`; le Fill durable conserve le P&L réalisé de la clôture.

`AssetPosition.accounting_complete` distingue les positions créées avec la nouvelle comptabilité des snapshots historiques qui ne permettent pas de reconstruire honnêtement une base de coût.

## 4. Persistence / recovery

Aucune migration SQL n'est requise pour 19.1 : les snapshots `PortfolioState` sont déjà stockés sous forme JSON. Les nouveaux champs sont persistés dans ce JSON et restaurés par le chemin existant `paper-ledger-recovery-v1`.

Compatibilité :

- nouveaux snapshots : comptabilité complète restaurée exactement ;
- anciens snapshots : nouveaux champs absents acceptés par défaut, `accounting_complete=false` ;
- aucun replay Agent/Risk/Broker ;
- aucune reconstruction rétrospective de base de coût.

## 5. API / Agent / frontend

Le contrat portefeuille API expose les nouveaux champs SPOT. `AgentInput` transporte déjà le `PortfolioState`, donc l'Agent reçoit naturellement l'état enrichi sans calcul LLM supplémentaire.

Le frontend affiche les champs backend tels quels et laisse le P&L latent SPOT à `—` tant qu'aucun mark-to-market canonique n'est disponible.

## 6. Architecture cible des cadences

Les évolutions suivantes doivent rester séparées :

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

## 7. Monitoring déterministe — Batch 19.2

Le P&L latent SPOT n'est pas stocké comme un coût permanent dans 19.1. Il sera calculé à partir d'une valorisation datée (`as_of`) fournie par le backend.

Le monitor pourra maintenir prix/marks, revaloriser SPOT/PERPETUAL, calculer exposition/marge/liquidation/funding et publier des snapshots cohérents, sans choisir de BUY/SELL/HOLD.

## 8. Discovery, watchlist et Marchés

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

## 9. Persistence future

Les futurs batches peuvent nécessiter de nouvelles tables pour watchlists, marks ou candles. Ces décisions restent hors périmètre 19.1 et doivent être prises après audit du batch concerné.
