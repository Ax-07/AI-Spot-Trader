# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading crypto **PAPER** pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est uniquement un cockpit de contrôle et de visualisation.

Base GitHub auditée pour le Batch 19.2 :

```text
HEAD GitHub main : 01ca1e857947d969556481e5593c5712d137f5ad
```

Le présent document décrit l'état attendu après application du patch 19.2 ; l'intégration GitHub reste une action explicite de l'opérateur.

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
PortfolioState marqué
-> MarketSelectionInput
-> même Agent + tools read-only éventuels
-> MarketSelection
-> acquisition MarketState exécutable exact
-> mark causal du ledger
-> AgentInput
-> même Agent -> BUY/SELL/HOLD
-> RiskEngine -> ALLOW/MODIFY/REJECT
-> ExecutionIntent éventuel
-> PaperBroker
-> Fill + mise à jour comptable
-> valorisation séparée par la source de marché / le monitor
-> PaperPortfolioLedger
-> audit + snapshot durable
```

En parallèle, les monitors SPOT et PERPETUAL peuvent rafraîchir les marks sans appel LLM. Le même Agent porte la sélection stratégique de marché et la décision de trading. Aucun composant déterministe ni frontend ne choisit l'opportunité à sa place.

## 4. Univers exécutable actuel

`ExecutableMarket(symbol, market_type)` représente la frontière d'exécution. La Campaign snapshotte actuellement un `paper_executable_markets` statique, trié et limité aux types supportés. Tous les marchés d'une Campaign partagent l'actif de quote/règlement attendu par la configuration actuelle.

Les sources de recherche Kraken sont séparées des sources d'exécution. Un résultat de recherche ne devient jamais implicitement un `MarketState` exécutable.

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
- `spot_realized_pnl_total` : P&L SPOT réalisé cumulé quand la lignée 19.2 permet de le connaître ;
- `spot_unrealized_pnl_total` : somme des P&L latents SPOT si tous sont calculables ;
- `equity` : cash + valeur SPOT + equity isolée des positions dérivées (`margin_used + unrealized_pnl + cumulative_funding`) lorsque la valorisation globale est complète ;
- `exposure_value` : valeur SPOT + notional dérivé ;
- `exposure_fraction = exposure_value / equity` lorsque `equity > 0`.

`PortfolioState.valuation_complete` signifie que la **valorisation de marché/equity** dispose de toutes ses composantes fraîches ; il ne remplace pas `AssetPosition.accounting_complete`. Une position legacy peut donc contribuer à l'equity via sa valeur de marché tout en conservant un P&L latent inconnu.

Le P&L réalisé SPOT n'est **pas** ajouté à l'equity : il est déjà reflété dans le cash. Un snapshot 19.1/legacy qui ne permet pas de connaître le réalisé global conserve `spot_realized_pnl_total=None`.

### PERPETUAL

Les positions PERPETUAL conservent prix moyen d'entrée, mark price, notional, P&L réalisé/latent, marge, maintenance, funding et liquidation. Leur implémentation comptable existante n'est pas dupliquée par 19.2.

## 6. Mark-to-market et cadences

Trois cadences restent distinctes :

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY/SELL/HOLD ;
3. **découverte / révision de watchlist IA** : beaucoup plus lente.

Les monitors 19.2 fonctionnent dans le backend actif indépendamment du frontend et du cycle IA. Valeurs par défaut : cadence SPOT 5 s, cadence PERPETUAL 15 s, timeout acquisition 5 s, staleness 30 s. Ces paramètres techniques sont configurables par environnement.

## 7. Mode gestion à exposition saturée

Lorsque le backend détermine qu'une **nouvelle exposition est impossible** :

- la phase stratégique doit se limiter aux positions ouvertes ;
- l'Agent peut proposer HOLD, réduction ou clôture ;
- le déterministe ne choisit pas à sa place quelle position conserver ou fermer ;
- Risk conserve son autorité finale ;
- le retour au mode normal est automatique dès qu'une capacité d'exposition redevient disponible ;
- les appels/tools qui ne peuvent conduire qu'à une nouvelle ouverture doivent être évités et leur économie mesurée.

Ce périmètre reste celui du Batch 19.3.

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

Le Batch 19.2 étend encore le JSON `PortfolioState` sans migration SQL : les marks frais et agrégats connus sont restaurés tels quels. La règle de staleness est réévaluée au moment du nouveau snapshot ; aucune ancienne observation n'est transformée en prix courant.

## 11. Control Plane backend

`Strategy`, `StrategyRevision`, `Campaign` et `paper_run` conservent leurs rôles. Les paramètres de mark-to-market 19.2 sont des paramètres techniques de processus ; ils ne modifient pas silencieusement la stratégie ou les limites Risk de la Campaign.

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

## 13. Documentation de planification

Le séquencement est dans `docs/09_ROADMAP_DEVELOPPEMENT.md` et le détail des améliorations dans `docs/11_AMELIORATIONS_PLANIFIEES.md`.
