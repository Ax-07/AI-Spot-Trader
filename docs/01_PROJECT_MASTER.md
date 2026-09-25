# 01 — Project Master

## 1. Mission et référence

AI Spot Trader est une application expérimentale de trading **PAPER** pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est uniquement un cockpit de contrôle et de visualisation.

Référence intégrée auditée avant le Batch 19.4 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : bfef06d78dc34089541272c2944518499d4a1530
Commit     : feat: add deterministic capacity management mode
```

Le Batch 19.3 est intégré. Le Batch 19.4 décrit ici le patch proposé dans cette livraison ; son intégration GitHub reste une action explicite de l'opérateur.

## 2. Invariants fonctionnels

- un seul Agent IA stratégique ;
- Kraken comme source initiale ;
- PAPER uniquement ; LIVE reste séparé et ultérieur ;
- SPOT + PERPETUAL linéaire selon les capacités intégrées ;
- actions finales `BUY`, `SELL`, `HOLD` ;
- GPT-5.6 Luna pour les premiers tests, Sol sélectionnable par configuration ;
- Risk Engine déterministe = autorité finale ;
- aucune sortie LLM ni aucun tool ne déclenche directement Broker/Kraken ;
- aucun short/levier/margin en SPOT ;
- levier, marge, `reduce_only`, anti-reversal et liquidation PERPETUAL restent déterministes ;
- coûts PAPER, spread, slippage et funding restent appliqués ;
- toutes les décisions et sélections importantes restent auditables ;
- aucun look-ahead ;
- aucun secret dans prompts, logs, navigateur ou Git ;
- frontend non nécessaire au fonctionnement du moteur ;
- calculs financiers canoniques en `Decimal` côté backend.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## 3. Pipeline canonique avec Batch 19.4

```text
Kraken catalogue public
-> filtre déterministe d'admissibilité
-> snapshots factuels bornés
-> univers candidat
-> même Agent IA -> watchlist stratégique multi-marchés
-> univers effectif = watchlist + positions ouvertes

PortfolioState marqué + RiskPolicy
-> CapacityEvaluator
   -> NORMAL
      -> univers effectif dynamique
      -> même Agent -> MarketSelection
   -> MANAGEMENT
      -> découverte d'ouverture non relancée
      -> marchés des positions ouvertes uniquement
      -> même Agent -> MarketSelection de gestion
-> MarketState exécutable exact
-> même Agent -> BUY / SELL / HOLD
-> RiskEngine -> ALLOW / MODIFY / REJECT
-> PaperBroker éventuel
-> ledger + audit durable
```

La découverte ne constitue ni un second Agent ni une stratégie algorithmique parallèle. Le déterministe établit uniquement ce qui est techniquement admissible et suffisamment documenté par les données disponibles. Il ne produit aucun score d'opportunité.

## 4. Univers de marchés

Quatre niveaux sont distingués :

1. **univers disponible** : marchés Kraken publics découverts par le catalogue canonique ;
2. **univers candidat** : sous-ensemble factuellement admissible, borné et causal ;
3. **watchlist stratégique** : marchés retenus par le même Agent IA ;
4. **univers effectif de trading** : watchlist + toutes les positions ouvertes.

`paper_executable_markets` reste dans `CampaignConfiguration` comme bootstrap/fallback immuable. Il n'est pas réécrit par la découverte et continue de servir au mode manuel/reproductible lorsque `market_discovery` est absent.

La découverte filtre notamment : type autorisé, quote/settlement, état de marché, PERPETUAL linéaire, disponibilité/fraîcheur des snapshots et historique minimal. Ces critères ne disent jamais qu'un marché est un « bon trade ».

## 5. Configuration de découverte

`market_discovery` est optionnel. Son absence conserve exactement le comportement statique historique et son champ est exclu du payload canonique lorsqu'il vaut `None`, afin de préserver les digests des Campaigns existantes.

Valeurs par défaut du Batch 19.4 :

```text
catalog_refresh_seconds      = 900
watchlist_refresh_seconds    = 900
refresh_timeout_seconds      = 45
candidate_probe_limit        = 24
candidate_limit              = 12
watchlist_limit              = 6
max_snapshot_age_seconds     = 120
min_window_observations      = 2
require_complete_window      = false
```

`risk_allowed_pairs` reste une whitelist Risk déterministe lorsqu'elle est renseignée. Pour une Campaign dynamique uniquement, elle peut être `null`, auquel cas la découverte Kraken + contraintes structurelles délimitent les symboles et Risk conserve toutes ses autres protections. Une Campaign statique continue d'exiger une whitelist explicite.

## 6. Cache, cadence et indisponibilités

Le catalogue et la watchlist sont des caches process-local : aucune nouvelle table SQL n'est introduite en 19.4.

- catalogue Kraken : rafraîchi au plus toutes les 15 minutes par défaut ;
- watchlist IA : renouvelée au plus toutes les 15 minutes par défaut ;
- un refresh complet est borné par timeout ;
- panne Kraken, timeout ou sortie LLM invalide : conservation de la dernière watchlist valide ;
- sans watchlist précédente : retour au bootstrap configuré ;
- le fallback est audité et les retries sont temporisés.

## 7. NORMAL / MANAGEMENT

Le Batch 19.3 reste autoritaire pour la capacité :

- `NORMAL` autorise le renouvellement de watchlist lorsqu'il est dû ;
- `MANAGEMENT` ne relance pas la découverte destinée à de nouvelles ouvertures ;
- les positions ouvertes restent toujours gérables, même si leur marché n'appartient plus à la watchlist ;
- Risk refuse toujours toute augmentation d'exposition en MANAGEMENT.

## 8. Audit et recovery

Chaque cycle dynamique transporte un `market_discovery` auditable dans le `MarketSelectionInput` : statut du refresh, tailles catalogue/candidats, faits candidats, watchlist précédente/effective, ajouts, maintiens, retraits, rationales et éventuel type d'erreur.

La watchlist n'est pas restaurée comme état durable autonome. Après restart :

- en NORMAL, elle est reconstruite au premier refresh utile ;
- en MANAGEMENT, la découverte est évitée et les positions récupérées sont immédiatement gérables ;
- le lifecycle de recovery étend l'univers du run avec les marchés réellement détenus avant d'appliquer les validations canoniques existantes.

Aucun replay Agent/Risk/Broker/Fill n'est introduit.

## 9. Portefeuille, comptabilité et valorisation

Les Batches 19.1 et 19.2 restent canoniques : coût moyen pondéré SPOT, base de coût restante, P&L réalisé, marks causaux, P&L latent, equity et exposition sont calculés côté backend. Les monitors SPOT/PERPETUAL restent indépendants du LLM et peuvent désormais valoriser les marchés dynamiques correspondant aux positions détenues.

## 10. Cadences distinctes

1. monitoring / mark-to-market : rapide, déterministe, sans LLM ;
2. cycle stratégique : BUY / SELL / HOLD par l'Agent ;
3. découverte / watchlist : même Agent, cadence nettement plus lente.

## 11. Cockpit

Le configurateur simple active la découverte dynamique par défaut : l'opérateur choisit un type de marché et une ou plusieurs paires de **départ/secours**, pas la watchlist complète. Le mode avancé reste utilisable pour construire une Campaign statique reproductible.

Le frontend ne calcule ni Risk, ni P&L, ni classement de marché et ne devient pas une dépendance du moteur.

## 12. Suites planifiées

- Batch 19.5 : explicabilité dédiée Agent/Risk ;
- Batch 19.6A : candles, cache et streaming backend ;
- Batch 19.6B : vue Marchés, onglets et charts ;
- LIVE : séparé et ultérieur.
