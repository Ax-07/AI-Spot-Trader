# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading crypto **PAPER** pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est uniquement un cockpit de contrôle et de visualisation.

Base GitHub auditée pour le Batch 19.1 :

```text
HEAD GitHub main : dbdc8f83bb39c158ec7331ce2adba616d2922842
```

Le présent document décrit l'état attendu après application du patch 19.1 ; l'intégration GitHub reste une action explicite de l'opérateur.

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
- frontend non nécessaire au fonctionnement du moteur.

Principe central :

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

### SPOT

- aucun short ;
- aucun levier/margin ;
- `SELL` réduit uniquement une position détenue/disponible ;
- la comptabilité canonique est backend et n'est jamais reconstruite dans le frontend ;
- calculs monétaires et quantités restent en `Decimal` côté backend.

### PERPETUAL

- contrats linéaires uniquement ;
- LONG/SHORT ;
- marge `ISOLATED` ;
- levier déterministe/configuré, jamais choisi par le LLM ;
- Risk contrôle marge, exposition, liquidation, `reduce_only` et anti-reversal ;
- contrats inverses, CROSS et futures datés restent non exécutables tant qu'un périmètre dédié n'est pas décidé.

## 3. Pipeline canonique actuel

```text
PortfolioState
-> MarketSelectionInput
-> même Agent + tools read-only éventuels
-> MarketSelection
-> acquisition MarketState exécutable exact
-> AgentInput
-> même Agent -> BUY/SELL/HOLD
-> RiskEngine -> ALLOW/MODIFY/REJECT
-> ExecutionIntent éventuel
-> PaperBroker
-> Fill
-> PaperPortfolioLedger
-> audit + snapshot durable
```

Le même Agent porte la sélection stratégique de marché et la décision de trading. Aucun composant déterministe ni frontend ne choisit l'opportunité à sa place.

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

## 5. Portefeuille et comptabilité

### SPOT — Batch 19.1

`AssetPosition` porte désormais :

- `asset` ;
- `quantity` ;
- `available` ;
- `average_entry_price` ;
- `remaining_cost_basis` ;
- `realized_pnl` ;
- `accounting_complete`.

Règles canoniques :

- `average_entry_price` = **coût économique moyen par unité**, soit `remaining_cost_basis / quantity` ; il inclut donc le prix de fill dégradé par spread/slippage ainsi que les frais BUY ;
- `remaining_cost_basis` = somme des débits cash BUY réels (`notional + fee`) encore attachée à la quantité détenue ;
- une vente partielle libère la base de coût au prorata de la quantité vendue ;
- P&L réalisé d'une vente = crédit cash SELL net (`notional - fee`) − base de coût libérée ;
- les frais ne sont donc comptés qu'une fois et spread/slippage ne sont jamais ajoutés à nouveau au prix déjà dégradé du fill ;
- une vente totale supprime la position ouverte ; le fait durable du dernier P&L réalisé reste porté par le Fill/audit ;
- un ancien snapshot sans ces champs reste récupérable avec `accounting_complete=false` : aucune base de coût n'est inventée rétroactivement.

Le P&L latent SPOT reste séparé de cette comptabilité permanente et sera calculé à partir d'un mark courant dans le Batch 19.2.

### PERPETUAL

Les positions PERPETUAL possèdent déjà prix moyen d'entrée, mark price, notional, P&L réalisé/latent, marge, maintenance, funding et liquidation.

## 6. Mark-to-market et cadences

Le moteur doit distinguer au minimum trois cadences configurables :

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY/SELL/HOLD ;
3. **découverte / révision de watchlist IA** : beaucoup plus lente.

Le monitoring peut calculer prix, P&L latent, exposition, marge, liquidation et funding sans prendre de décision stratégique.

## 7. Mode gestion à exposition saturée

Lorsque le backend détermine qu'une **nouvelle exposition est impossible** :

- la phase stratégique doit se limiter aux positions ouvertes ;
- l'Agent peut proposer HOLD, réduction ou clôture ;
- le déterministe ne choisit pas à sa place quelle position conserver ou fermer ;
- Risk conserve son autorité finale ;
- le retour au mode normal est automatique dès qu'une capacité d'exposition redevient disponible ;
- les appels/tools qui ne peuvent conduire qu'à une nouvelle ouverture doivent être évités et leur économie mesurée.

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

Le Batch 19.1 étend le contenu JSON de `PortfolioState` sans migration SQL : les nouveaux snapshots restaurent exactement coût moyen, coût restant et P&L réalisé courant ; les anciens snapshots restent valides grâce aux valeurs par défaut et à `accounting_complete=false`.

## 11. Control Plane backend

`Strategy`, `StrategyRevision`, `Campaign` et `paper_run` conservent leurs rôles actuels. Une évolution de Campaign pourra être nécessaire pour les futures cadences et la watchlist automatique, sans impact requis pour 19.1.

## 12. Cockpit

Navigation cible planifiée :

```text
Accueil | Marchés | Positions | Historique | Réglages
```

Le frontend reste un client des contrats backend. Il ne :

- calcule pas de portefeuille alternatif ;
- ne reconstruit pas un coût moyen ou un P&L SPOT ;
- ne décide pas BUY/SELL/HOLD ;
- ne déduit pas une autorisation Risk ;
- ne devient pas la source de vérité candles/positions ;
- ne persiste aucun secret.

## 13. Documentation de planification

Le séquencement est dans `docs/09_ROADMAP_DEVELOPPEMENT.md` et le détail des améliorations dans `docs/11_AMELIORATIONS_PLANIFIEES.md`.
