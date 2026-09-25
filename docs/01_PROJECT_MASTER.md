# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading crypto **PAPER** pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est uniquement un cockpit de contrôle et de visualisation.

Base GitHub auditée pour le Batch 19.3 :

```text
HEAD GitHub main : 44670a249ba662b2afd50a0a9e2a0e63ea4ed76d
```

Les Batches 19.1 et 19.2 sont intégrés. Le présent document décrit l'état attendu après application du patch local 19.3 ; l'intégration GitHub reste une action explicite de l'opérateur.

## 2. Invariants fonctionnels

### Globaux

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement à ce stade ; LIVE reste séparé et ultérieur ;
- actions finales `BUY`, `SELL`, `HOLD` ;
- GPT-5.6 Luna pour les premiers tests, Sol sélectionnable par configuration ;
- Risk Engine déterministe avec autorité finale ;
- seul Risk peut produire l'intention d'exécution autorisée ;
- aucune sortie LLM ni aucun tool ne déclenche directement Broker/Kraken ;
- coûts PAPER, spread, slippage et funding lorsque pertinent sont pris en compte ;
- toutes les décisions, `HOLD` inclus, restent auditables ;
- aucun secret dans prompts, logs, navigateur ou Git ;
- aucun look-ahead ni sélection rétrospective ;
- frontend non nécessaire au fonctionnement du moteur ;
- calculs financiers canoniques en `Decimal` côté backend.

Principe central :

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

### SPOT

- aucun short ;
- aucun levier/margin ;
- `SELL` réduit uniquement une position détenue/disponible ;
- comptabilité et mark-to-market canoniques côté backend ;
- aucune donnée manquante n'est remplacée par une estimation rétroactive.

### PERPETUAL

- contrats linéaires uniquement ;
- LONG/SHORT ;
- marge `ISOLATED` ;
- levier déterministe/configuré, jamais choisi par le LLM ;
- Risk contrôle marge, exposition, liquidation, `reduce_only` et anti-reversal ;
- contrats inverses, CROSS et futures datés restent non exécutables tant qu'un périmètre dédié n'est pas décidé.

## 3. Pipeline canonique actuel

```text
PortfolioState marqué + RiskPolicy
-> CapacityEvaluator déterministe
   -> NORMAL
      -> MarketSelectionInput (univers exécutable normal)
      -> même Agent + tools read-only éventuels
   -> MANAGEMENT
      -> MarketSelectionInput audité
      -> même Agent, candidats = positions ouvertes uniquement
      -> tools de recherche d'ouverture désactivés
-> MarketSelection
-> acquisition MarketState exécutable exact
-> mark causal du ledger
-> AgentInput + contexte de capacité si MANAGEMENT
-> même Agent -> BUY/SELL/HOLD
-> RiskEngine -> ALLOW/MODIFY/REJECT
   -> en MANAGEMENT, veto sur toute augmentation d'exposition
-> ExecutionIntent éventuel
-> PaperBroker
-> Fill + mise à jour comptable
-> valorisation séparée par la source de marché / le monitor
-> PaperPortfolioLedger
-> audit + snapshot durable
```

En parallèle, les monitors SPOT et PERPETUAL rafraîchissent les marks sans appel LLM. `CapacityEvaluator` ne choisit jamais une opportunité : il détermine uniquement le périmètre stratégique autorisé avant sélection. Le même Agent conserve la sélection entre positions ouvertes et la décision finale.

## 4. Univers exécutable actuel

`ExecutableMarket(symbol, market_type)` représente la frontière d'exécution. La Campaign snapshotte actuellement un `paper_executable_markets` statique, trié et limité aux types supportés. Tous les marchés d'une Campaign partagent l'actif de quote/règlement attendu par la configuration actuelle.

Les sources de recherche Kraken sont séparées des sources d'exécution. Un résultat de recherche ne devient jamais implicitement un `MarketState` exécutable.

En mode `MANAGEMENT`, l'univers de sélection transmis au transport LLM est l'intersection entre l'univers exécutable de Campaign et les positions réellement ouvertes. Les positions SPOT sont mappées vers `BASE/settlement_asset`; les positions PERPETUAL conservent leur symbole exact. Le `MarketSelectionInput` canonique garde l'univers de Campaign pour préserver les contrats/audits existants ; le contexte transport explicite la restriction de gestion.

### Évolution planifiée

```text
univers techniquement admissible     <- backend déterministe
watchlist stratégique actuelle       <- même Agent IA
univers surveillé                    <- watchlist IA + toutes positions ouvertes
marché d'une décision de trading     <- même Agent IA
```

Le backend pourra filtrer ce qui est structurellement exécutable, sans effectuer de ranking stratégique à la place de l'Agent.

## 5. Portefeuille, comptabilité et valorisation

### SPOT — comptabilité 19.1

`AssetPosition` conserve : `asset`, `quantity`, `available`, `average_entry_price`, `remaining_cost_basis`, `realized_pnl`, `accounting_complete`.

Règles canoniques :

- `average_entry_price = remaining_cost_basis / quantity` ;
- `remaining_cost_basis` correspond aux débits cash BUY réels encore attachés à la quantité ouverte, frais inclus ;
- une vente partielle libère la base de coût au prorata ;
- P&L réalisé d'un SELL = crédit cash net − base de coût libérée ;
- spread/slippage sont déjà incorporés au prix de fill et ne sont jamais rajoutés une seconde fois ;
- `accounting_complete=false` interdit toute reconstruction artificielle d'un coût historique inconnu.

### SPOT — mark-to-market 19.2

Pour une position ouverte :

- `mark_price` = dernier prix ticker Kraken SPOT causal retenu ;
- `mark_observed_at` = timestamp de l'observation ;
- `mark_source = LAST_PRICE` ;
- `market_value = quantity * mark_price` ;
- `unrealized_pnl = market_value - remaining_cost_basis` lorsque `accounting_complete=true` ;
- `valuation_complete` indique qu'une position dispose à la fois d'une comptabilité complète et d'un mark utilisable.

Le mark n'inclut pas un coût de sortie hypothétique. Les coûts BUY déjà supportés figurent dans le coût restant ; aucun frais, spread ou slippage n'est donc recompté au mark-to-market.

Un mark absent/périmé rend `mark_price`, `market_value` et `unrealized_pnl` indisponibles dans le snapshot. Une position legacy peut avoir `market_value` grâce à un mark, mais son `unrealized_pnl` reste `None` faute de base de coût fiable.

### Agrégats portefeuille

`PortfolioState` peut exposer :

- `cash_available` : solde disponible de l'actif de règlement ;
- `spot_remaining_cost_basis_total` : somme des coûts restants des positions SPOT si tous sont connus ;
- `spot_market_value_total` : somme des valeurs de marché SPOT si tous les marks nécessaires sont disponibles ;
- `spot_realized_pnl_total` : P&L SPOT réalisé cumulé quand la lignée permet de le connaître ;
- `spot_unrealized_pnl_total` : somme des P&L latents SPOT si tous sont calculables ;
- `equity` : cash + valeur SPOT + equity isolée des positions dérivées (`margin_used + unrealized_pnl + cumulative_funding`) lorsque la valorisation globale est complète ;
- `exposure_value` : valeur SPOT + notional dérivé ;
- `exposure_fraction = exposure_value / equity` lorsque `equity > 0`.

`PortfolioState.valuation_complete` signifie que la **valorisation de marché/equity** dispose de toutes ses composantes fraîches ; il ne remplace pas `AssetPosition.accounting_complete`.

### PERPETUAL

Les positions PERPETUAL conservent prix moyen d'entrée, mark price, notional, P&L réalisé/latent, marge, maintenance, funding et liquidation. Leur implémentation comptable existante n'est pas dupliquée par 19.3.

## 6. Mark-to-market et cadences

Trois cadences restent distinctes :

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY/SELL/HOLD ;
3. **découverte / révision de watchlist IA** : beaucoup plus lente.

Les monitors fonctionnent dans le backend actif indépendamment du frontend et du cycle IA. Valeurs par défaut : cadence SPOT 5 s, cadence PERPETUAL 15 s, timeout acquisition 5 s, staleness 30 s.

## 7. Mode gestion à capacité d'ouverture indisponible

Le Batch 19.3 introduit `CapacityEvaluator`, déterministe et alimenté par la **même instance `RiskPolicy`** que `RiskEngine`.

Il distingue :

- exposition actuellement utilisée ;
- capacité théorique à augmenter encore l'exposition avant acquisition d'un marché ;
- possibilité de réduire/clôturer une position existante.

Le calcul pré-sélection utilise uniquement les faits déjà canoniques. Il peut constater notamment : cash de règlement nul, plafond total PERPETUAL atteint, tous les marchés PERPETUAL déjà au plafond par position, ou valorisation globale incomplète. Il **ne duplique pas** les contraintes qui nécessitent un `MarketState` exact : minimum d'ordre, caractéristiques de contrat, levier instrument, marge exacte et buffer de liquidation restent chez Risk.

Règles :

- si une capacité théorique certaine existe sur au moins un marché applicable : `NORMAL` ;
- si aucune capacité certaine n'existe, ou si la valorisation nécessaire est incomplète : `MANAGEMENT` ;
- SPOT ne reçoit aucun plafond global inventé : en l'état intégré, sa capacité d'ouverture pré-sélection dépend du cash disponible, tandis que les limites d'ordre restent Risk ;
- en `MANAGEMENT`, les tools de découverte d'ouverture sont désactivés et l'Agent choisit seulement parmi les positions ouvertes ;
- HOLD et réductions restent possibles ; Risk refuse toute augmentation d'exposition via `MANAGEMENT_EXPOSURE_INCREASE` ;
- le mode est recalculé à chaque cycle et revient automatiquement à `NORMAL` après libération de capacité ;
- aucune estimation de tokens n'est produite faute de métrique d'usage canonique existante.

## 8. Explicabilité

Le champ `rationale` est une explication stratégique enregistrée par l'Agent ; il ne constitue jamais une instruction d'exécution.

Le produit doit distinguer explicitement :

- **Pourquoi l'IA ?** → `rationale` stratégique ;
- **Risk Engine** → `ALLOW / MODIFY / REJECT` et raisons déterministes.

## 9. Données marchés et charts

La source de vérité reste Kraken via le backend.

```text
Kraken REST        -> historique initial
Kraken WebSocket   -> mises à jour temps réel
backend            -> normalisation + cache + persistence éventuelle
WebSocket cockpit  -> frontend
Lightweight Charts -> rendu
```

TradingView Lightweight Charts est privilégié pour le rendu. Un iframe TradingView externe ne devient pas une source de vérité du moteur.

## 10. Recovery PAPER

`paper-ledger-recovery-v1` reste le mécanisme canonique :

- nouveau `paper_run_id` par lifetime ;
- `resumed_from_paper_run_id` explicite ;
- snapshot initial/courant durable du ledger ;
- rollback mémoire sur cycle FAILED ou erreur d'audit ;
- aucun replay de MarketSelection, décision, Risk, Broker ou Fill ;
- validation fail-closed de l'état restauré.

Le mode 19.3 ne nécessite aucun nouvel état durable ni migration SQL. Le snapshot restauré est valorisé selon les règles courantes puis `CapacityEvaluator` recalcule le mode au cycle suivant. Le mode et sa raison sont des faits de cycle audités, pas un état métier persistant à restaurer.

## 11. Control Plane backend

`Strategy`, `StrategyRevision`, `Campaign` et `paper_run` conservent leurs rôles. Le Batch 19.3 n'ajoute aucun paramètre opérateur : `CapacityEvaluator` réutilise les limites Risk de la Campaign et ne crée pas une seconde configuration divergente.

## 12. Cockpit

Navigation cible planifiée :

```text
Accueil | Marchés | Positions | Historique | Réglages
```

Le frontend reste un client des contrats backend. Il ne :

- calcule pas de portefeuille alternatif ;
- ne reconstruit pas un coût moyen, un mark, une valeur ou un P&L SPOT ;
- ne décide pas BUY/SELL/HOLD ;
- ne déduit pas une autorisation Risk ;
- ne devient pas la source de vérité candles/positions ;
- ne persiste aucun secret.

Le Batch 19.3 ne requiert aucune modification frontend.

## 13. Documentation de planification

Le séquencement est dans `docs/09_ROADMAP_DEVELOPPEMENT.md` et le détail des améliorations dans `docs/11_AMELIORATIONS_PLANIFIEES.md`.
