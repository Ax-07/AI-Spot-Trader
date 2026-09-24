# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading crypto **PAPER** pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est uniquement un cockpit de contrôle et de visualisation.

Référence auditée pour le cadrage documentaire des améliorations planifiées :

```text
HEAD GitHub main audité : 9a312040eb671976b44e5f50077ca11a9d9213b3
Dernier commit fonctionnel : 4cb0567cae6ff100c5ad9ad1df9e3f68b8f7ffd7
Dernier commit documentaire : 9a312040eb671976b44e5f50077ca11a9d9213b3
```

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
- la comptabilité canonique doit rester backend et ne doit pas être reconstruite dans le frontend.

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
-> audit + ledger durable
```

Le même Agent porte la sélection stratégique de marché et la décision de trading. Aucun composant déterministe ni frontend ne choisit l'opportunité à sa place.

## 4. Univers exécutable actuel

`ExecutableMarket(symbol, market_type)` représente la frontière d'exécution. La Campaign snapshotte actuellement un `paper_executable_markets` statique, trié et limité aux types supportés. Tous les marchés d'une Campaign partagent l'actif de quote/règlement attendu par la configuration actuelle.

Les sources de recherche Kraken sont séparées des sources d'exécution. Un résultat de recherche ne devient jamais implicitement un `MarketState` exécutable.

### Évolution planifiée

Le cadrage prévoit de distinguer à terme :

```text
univers techniquement admissible     <- backend déterministe
watchlist stratégique actuelle       <- même Agent IA
univers surveillé                    <- watchlist IA + toutes positions ouvertes
marché d'une décision de trading     <- même Agent IA
```

Le backend pourra filtrer ce qui est structurellement exécutable, sans effectuer de ranking stratégique à la place de l'Agent.

## 5. Portefeuille et comptabilité

### Confirmé aujourd'hui

Le `PortfolioState` sépare :

- balances de règlement ;
- positions SPOT `asset / quantity / available` ;
- positions dérivées détaillées.

Les positions PERPETUAL possèdent déjà notamment : prix moyen d'entrée, mark price, notional, P&L réalisé/latent, marge, maintenance, funding et liquidation.

### Manquant aujourd'hui côté SPOT

Le contrat SPOT ne porte pas :

- coût/prix moyen d'entrée ;
- coût de revient restant ;
- P&L latent par position ;
- P&L réalisé cumulatif par position.

Cette extension doit être réalisée dans le modèle/ledger canonique backend avant toute exposition UI complète.

## 6. Mark-to-market et cadences

Le moteur doit distinguer conceptuellement au minimum trois cadences configurables :

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY/SELL/HOLD ;
3. **découverte / révision de watchlist IA** : beaucoup plus lente.

Le monitoring peut calculer prix, P&L latent, exposition, marge, liquidation et funding sans prendre de décision stratégique.

Le code PERPETUAL possède déjà des primitives de revalorisation déterministe ; le manque principal est une orchestration de monitoring indépendante du cycle IA, ainsi qu'un équivalent SPOT fondé sur une comptabilité enrichie.

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

Ces informations devront être réutilisables dans Accueil, Positions, Historique et les futurs markers de chart.

## 9. Données marchés et charts

La source de vérité reste Kraken via le backend.

Architecture cible :

```text
Kraken REST        -> historique initial
Kraken WebSocket   -> mises à jour temps réel
backend            -> normalisation + cache + persistence éventuelle
WebSocket cockpit  -> frontend
Lightweight Charts -> rendu
```

TradingView Lightweight Charts est privilégié pour le rendu. Un iframe TradingView externe ne doit pas devenir une dépendance de vérité du moteur.

Pour le Spot, l'API REST Kraken OHLC ne permet de récupérer que les 720 entrées les plus récentes ; une profondeur supérieure exige donc une accumulation durable côté backend si elle est réellement nécessaire.

## 10. Recovery PAPER

`paper-ledger-recovery-v1` reste le mécanisme canonique :

- nouveau `paper_run_id` par lifetime ;
- `resumed_from_paper_run_id` explicite ;
- snapshot initial/courant durable du ledger ;
- rollback mémoire sur cycle FAILED ou erreur d'audit ;
- aucun replay de MarketSelection, décision, Risk, Broker ou Fill ;
- validation fail-closed de l'état restauré.

Toute extension de comptabilité SPOT devra préserver ces propriétés et restaurer sans ambiguïté le coût moyen et les P&L nécessaires.

## 11. Control Plane backend

`Strategy`, `StrategyRevision`, `Campaign` et `paper_run` conservent leurs rôles actuels : configuration durable et immuable pour l'expérience, exécution/recovery explicite et runtime backend canonique.

Une évolution de Campaign sera probablement nécessaire pour les nouvelles cadences, le mode de watchlist (`manual`/`automatic`) et les paramètres associés. Le schéma/version de configuration exact reste **à décider** pendant les batches d'implémentation.

## 12. Cockpit

Navigation cible planifiée :

```text
Accueil | Marchés | Positions | Historique | Réglages
```

Le frontend reste un client des contrats backend. Il ne :

- calcule pas de portefeuille alternatif ;
- ne reconstruit pas un coût moyen SPOT ;
- ne décide pas BUY/SELL/HOLD ;
- ne déduit pas une autorisation Risk ;
- ne devient pas la source de vérité candles/positions ;
- ne persiste aucun secret.

## 13. Documentation de planification

La spécification détaillée et le séquencement des améliorations sont centralisés dans :

`docs/11_AMELIORATIONS_PLANIFIEES.md`

La roadmap d'exécution est résumée dans `docs/09_ROADMAP_DEVELOPPEMENT.md`.
