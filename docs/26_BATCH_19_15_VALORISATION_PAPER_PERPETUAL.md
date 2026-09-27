# Batch 19.15 — Valorisation PAPER PERPETUAL avant capacité d'ouverture

## Référence auditée

- repository : `Ax-07/AI-Spot-Trader`
- branche intégrée auditée : `main`
- HEAD GitHub au début du batch : `b4f1e50f22164c7d019d11d930485733c01c6711`
- commit local annoncé par l'opérateur : `7846d89` (`feat: add read-only LLM request inspector`), non présent sur GitHub au moment de l'audit

Le correctif ne modifie ni le prompt stratégique, ni les règles Risk, ni les contrats BUY/SELL/HOLD.

## Diagnostic

### Confirmé

Le `PortfolioState` PAPER est produit par `PaperPortfolioLedger.snapshot()`.

Pour un portefeuille avec règlement USD :

- `cash_available` vient de la balance de l'actif de règlement ;
- la valeur SPOT provient des positions SPOT marquées ;
- une position PERPETUAL contribue à l'equity par :
  `margin_used + unrealized_pnl + cumulative_funding` ;
- une position PERPETUAL contribue à l'exposition par son `notional` marqué ;
- `exposure_fraction = exposure_value / equity` lorsque l'equity est strictement positive.

La valorisation globale est complète uniquement lorsque :

1. le cash de règlement est connu ;
2. toutes les positions SPOT sont valorisées ;
3. chaque position dérivée possède un `mark_observed_at` présent, non futur et non périmé selon `paper_mark_to_market_stale_after_seconds`.

Ainsi, une position PERPETUAL peut contenir `mark_price`, `notional`, `unrealized_pnl` et `margin_used` tout en rendant le portefeuille incomplet si son timestamp de mark est absent ou périmé.

`CapacityEvaluator` conserve le comportement fail-closed : `valuation_complete=false` produit `VALUATION_INCOMPLETE`, passe le cycle en `MANAGEMENT` et interdit toute augmentation d'exposition.

### Cause racine confirmée

À la reprise d'une session PAPER, le portefeuille durable est restauré avant le démarrage des moniteurs de mark-to-market. Avant ce batch, `PaperSpotMarkToMarketMonitor.start()` et `PaperDerivativeMarkToMarketMonitor.start()` lançaient `refresh_once()` dans une tâche de fond et rendaient la main après un simple yield de boucle événementielle.

Une acquisition réseau réelle peut rester en attente après ce yield. Le moteur pouvait donc démarrer son premier cycle avec les anciens `mark_observed_at` ou avec `mark_observed_at=None`. La capacité était alors évaluée comme `VALUATION_INCOMPLETE` avant que le premier rafraîchissement technique ne soit terminé.

Ce comportement est particulièrement visible après récupération d'anciennes positions PERPETUAL dont les données financières sont présentes mais dont le timestamp de mark n'est pas suffisamment frais.

### Obsolète

Il n'est pas nécessaire de modifier la formule d'equity ou d'exposition pour ajouter le support PERPETUAL : ces formules existent déjà dans le ledger et dans les invariants de `PortfolioState`.

Il n'est pas nécessaire non plus de contourner `VALUATION_INCOMPLETE` dans le prompt LLM ou dans le Risk Engine.

### Manquant avant ce batch

- garantie que le premier rafraîchissement mark-to-market est terminé avant que le runtime soit considéré initialisé ;
- couverture dédiée LONG/SHORT/multi-PERPETUAL de la valorisation du portefeuille ;
- test démontrant qu'un `mark_observed_at` absent garde la valorisation fail-closed même si le prix et le P&L sont présents ;
- test de capacité démontrant qu'un portefeuille PERPETUAL complet repasse en `NORMAL` avec headroom Risk ;
- test de course au démarrage du moniteur.

### À décider ultérieurement

Aucune décision architecturale supplémentaire n'est requise pour ce correctif.

Une optimisation éventuelle du rafraîchissement de plusieurs positions en parallèle doit rester un batch séparé : elle modifierait les caractéristiques I/O et de concurrence du provider Kraken et n'est pas nécessaire pour corriger la course d'initialisation.

## Correctif

Les deux moniteurs PAPER exécutent désormais un `refresh_once()` initial **avant** de rendre la main à `AppRuntime.initialize()`.

Ensuite seulement, la boucle périodique est lancée. Cette boucle attend la cadence configurée avant le prochain passage, ce qui évite un double rafraîchissement immédiat.

Les erreurs techniques de refresh restent non fatales pour le moniteur, comme auparavant : elles sont mémorisées dans `last_error_type`. Surtout, elles ne fabriquent aucune valorisation. Si le mark indispensable ne peut pas être obtenu, le ledger reste incomplet et Capacity/Risk restent fail-closed.

## Invariants conservés

- PAPER uniquement pour l'exécution actuelle ;
- SPOT + PERPETUAL linéaire ;
- FUTURE daté non exécutable ;
- l'IA conserve la décision stratégique ;
- le Risk Engine déterministe reste l'autorité finale ;
- aucune sortie LLM ne déclenche directement un ordre ;
- aucun assouplissement de Risk ;
- aucun changement du prompt LLM ;
- aucune invention de mark, d'equity ou d'exposition lorsque la donnée indispensable manque.

## Tests ajoutés

`backend/tests/test_perpetual_portfolio_valuation.py` couvre :

1. portefeuille cash-only ;
2. valorisation SPOT ;
3. PERPETUAL LONG ;
4. PERPETUAL SHORT ;
5. plusieurs positions PERPETUAL ;
6. agrégation cohérente equity/exposition/fraction ;
7. timestamp de mark absent ;
8. mark périmé ;
9. portefeuille complet avec capacité PERPETUAL `NORMAL` ;
10. portefeuille incomplet maintenu en `MANAGEMENT / VALUATION_INCOMPLETE` ;
11. démarrage PERPETUAL bloqué jusqu'à la fin du premier refresh ;
12. échec du premier refresh conservant le fail-closed ;
13. même garantie d'initialisation pour le moniteur SPOT.

## Note documentaire locale

`7846d89` n'étant pas présent sur GitHub, ses versions locales de `docs/00_ETAT_ACTUEL.md` et `docs/10_DECISIONS_ET_CHANGELOG.md` ne sont pas accessibles depuis l'état intégré. Ce ZIP ne remplace donc volontairement pas ces deux fichiers par leurs versions plus anciennes de `b4f1e50` afin de ne pas écraser la documentation de l'Inspecteur LLM.

Après application locale et validation, ces deux index canoniques doivent être réconciliés avec l'état local courant en mentionnant ce batch et son résultat de tests.
