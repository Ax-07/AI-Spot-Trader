# 03 — Agent, trading et Risk

## 1. Principe d'autorité

**L'Agent propose. Le Risk Engine autorise, modifie ou refuse.**

L'Agent est stratégique. Risk, Broker, comptabilité, monitoring, capacité et contraintes structurelles restent déterministes.

## 2. Agent unique aujourd'hui

```text
NORMAL
MarketSelectionInput -> select_market() -> MarketSelection
AgentInput           -> generate_decision() -> DecisionCandidate

MANAGEMENT
MarketSelectionInput -> select_management_market() -> MarketSelection
AgentInput           -> generate_management_decision() -> DecisionCandidate
```

Ces quatre surfaces appartiennent au même `OpenAIDecisionProvider`, au même modèle et au même rôle stratégique. MANAGEMENT n'introduit pas un second Agent.

## 3. Trois rythmes, toujours un seul Agent

1. monitoring/mark-to-market déterministe — **sans LLM** ;
2. décision stratégique de trading — **même Agent IA** ;
3. découverte/révision de watchlist — **même Agent IA**, cadence plus lente.

Cette séparation ne crée pas un second agent.

## 4. Contrat Agent protégé

Le contrat applicatif impose notamment :

- PAPER uniquement ;
- sorties structurées BUY/SELL/HOLD ;
- décision limitée au contexte exécutable fourni ;
- SPOT sans short/levier/marge ;
- sémantique LONG/SHORT PERPETUAL ;
- levier et `reduce_only` déterministes ;
- aucune invention de faits absents ;
- aucun LLM -> Broker/Kraken ;
- aucun tool -> Broker/Risk ;
- Risk final.

En MANAGEMENT, le transport ajoute un `capacity_context` déterministe et n'expose à la sélection que les positions ouvertes. Il indique explicitement que les tools de recherche d'ouverture sont désactivés et qu'une augmentation d'exposition sera refusée par Risk.

## 5. Rationale et explicabilité

Le `DecisionCandidate.rationale` reste une explication stratégique explicite et persistée, jamais une instruction d'exécution. L'UI doit le distinguer des raisons déterministes `ALLOW / MODIFY / REJECT` produites par Risk.

## 6. SPOT

`BUY` acquiert la base. `SELL` réduit un actif détenu. Risk vérifie notamment symbole/type, whitelist, chronologie/fraîcheur, cash quote, position disponible, max notional et coûts PAPER.

Aucun short, leverage ou margin SPOT.

### Comptabilité Batch 19.1

Le `PortfolioState` transmis à l'Agent contient la comptabilité backend : quantité, disponible, `average_entry_price`, `remaining_cost_basis`, `realized_pnl`, `accounting_complete`.

### Valorisation Batch 19.2

Le même `PortfolioState` peut désormais contenir :

- `mark_price`, `mark_observed_at`, `mark_source` ;
- `market_value` ;
- `unrealized_pnl` ;
- `valuation_complete` ;
- les agrégats cash/coût/valeur/P&L/equity/exposition du portefeuille.

Ces valeurs sont calculées exclusivement par le backend déterministe. L'Agent et Risk ne doivent pas recalculer un autre P&L latent.

`accounting_complete=false` signifie qu'une position historique ne dispose pas d'une base de coût suffisamment fiable. Même avec un mark, son P&L latent reste indisponible. Un mark absent/périmé rend également la valorisation indisponible.

## 7. PERPETUAL

`BUY` exprime/augmente LONG ou réduit SHORT. `SELL` exprime/augmente SHORT ou réduit LONG.

Risk garde le contrôle du contrat, taille, levier, marge, notional, exposition, buffer liquidation, `reduce_only`, anti-reversal et marge `ISOLATED`. Le LLM ne choisit jamais le levier effectif.

La comptabilité/valorisation dérivée existante reste canonique ; le Batch 19.3 ne crée pas une seconde implémentation parallèle.

## 8. Monitoring déterministe

`PaperSpotMarkToMarketMonitor` et `PaperDerivativeMarkToMarketMonitor` alimentent le ledger canonique sans référence stratégique à l'Agent. Ils ne peuvent pas produire d'ordre.

Le monitor reste actif avec le runtime backend même si le TradingEngine est `STOPPED`. Fermer le frontend n'arrête donc pas la valorisation du runtime actif.

## 9. Mode gestion lorsque la capacité de nouvelle exposition n'est pas certaine

Le Batch 19.3 implémente :

```text
PortfolioState valorisé + RiskPolicy partagé
-> CapacityEvaluator
   -> NORMAL
   -> MANAGEMENT
```

### NORMAL

- univers exécutable normal ;
- `select_market()` et tools read-only comme avant ;
- même Agent final ;
- BUY/SELL/HOLD restent soumis à Risk.

### MANAGEMENT

- aucune recherche/tool de découverte destinée à de nouvelles ouvertures ;
- univers de sélection du même Agent = marchés correspondant aux positions ouvertes ;
- HOLD, réduction partielle et clôture restent stratégiques ;
- le déterministe ne classe ni ne choisit la position à fermer ;
- Risk reçoit explicitement le mode et refuse toute hausse d'exposition par `MANAGEMENT_EXPOSURE_INCREASE` ;
- une réduction PERPETUAL conserve la logique `reduce_only` et anti-reversal existante ;
- le mode est recalculé à chaque cycle et disparaît automatiquement dès qu'une capacité redevient disponible.

### Ce que CapacityEvaluator sait avant sélection

Il réutilise la même `RiskPolicy` et peut constater le cash settlement, la complétude de valorisation, le plafond d'exposition dérivée totale et le plafond de notional par position déjà ouverte.

Il **ne** recalcule pas les contraintes dépendant du marché exact : quantité minimum, contract metadata, levier maximum instrument, marge/frais précis, fraîcheur ou liquidation. Ces contrôles restent exclusivement dans Risk après acquisition de `MarketState`.

Il n'existe pas de plafond global d'exposition SPOT dans la politique actuelle ; 19.3 n'en invente pas un. Pour SPOT, une capacité théorique pré-sélection existe tant que du cash settlement positif existe, puis Risk décide l'exécutabilité de l'ordre proposé.

### Valorisation incertaine

`valuation_complete=false` produit un mode MANAGEMENT explicite plutôt qu'une capacité inventée. Si aucune position ouverte exécutable n'existe, le cycle échoue de manière technique/visible à la sélection au lieu de générer artificiellement un HOLD.

### Économie IA

Le fait `new_opening_research_skipped=true` est audité. Les `AgentToolTrace` restent vides pour une sélection MANAGEMENT. L'infrastructure actuelle ne persiste pas de compteurs de tokens ; aucun chiffre estimé n'est fabriqué.

## 10. Découverte périodique des marchés

Le backend fournit un univers techniquement admissible ; le même Agent produit la sélection stratégique/watchlist. Le déterministe ne doit pas calculer un score d'opportunité qui remplace le choix stratégique de l'Agent.

## 11. Watchlist et positions ouvertes

Invariant cible :

```text
univers surveillé = watchlist IA actuelle + toutes les positions ouvertes
```

## 12. Recovery

Le recovery restaure un `PortfolioState` durable et ne réexécute jamais sélection, Agent, Risk, Broker ou Fill.

Pour 19.3, aucun état `NORMAL/MANAGEMENT` n'est restauré : `CapacityEvaluator` le recalcule au prochain cycle depuis le snapshot courant. Le mode et sa raison restent des faits audités du cycle qui les a produits.

## 13. Interdits maintenus

- aucun LIVE ;
- aucun second Agent ;
- aucun scanner/ranking déterministe choisissant le trade ;
- aucun ordre direct LLM/tool ;
- aucune modification post-hoc d'une décision ;
- aucun look-ahead ;
- aucune obligation de trader ;
- aucun calcul stratégique ou financier canonique déporté dans le frontend.

Le séquencement détaillé est documenté dans `docs/11_AMELIORATIONS_PLANIFIEES.md`.
