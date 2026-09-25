# 11 — Améliorations planifiées

> Référence de reprise des chantiers 19.x. Ce document distingue ce qui est **intégré**, ce qui est **implémenté dans le patch 19.3**, ce qui reste **planifié** et ce qui reste **à décider**.

## 1. Référence

```text
Repository              : Ax-07/AI-Spot-Trader
Branche                 : main
HEAD GitHub main audité : 44670a249ba662b2afd50a0a9e2a0e63ea4ed76d
Date Batch 19.3         : 2026-09-25
```

Les Batches 19.1 et 19.2 sont intégrés. Le patch 19.3 n'est pas déclaré intégré à GitHub avant validation/commit explicites de l'opérateur.

## 2. Invariants transverses

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement ;
- SPOT + PERPETUAL linéaire ;
- aucune sortie LLM ne déclenche directement Broker/Kraken ;
- Risk Engine déterministe = autorité finale ;
- IA = choix stratégique ;
- calculs, comptabilité, monitoring, capacité et statistiques = déterministes ;
- frontend jamais source de vérité trading ;
- aucun secret dans prompts/logs/docs/Git ;
- frais, spread, slippage et funding pris en compte sans double comptage ;
- HOLD auditable ;
- aucun look-ahead ni sélection rétrospective.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## 3. Cadences cibles

| Cadence | But | LLM |
| --- | --- | --- |
| Monitoring / mark-to-market | prix, marks, P&L, exposition, marge, liquidation, funding | non |
| Cycle stratégique | BUY / SELL / HOLD, avec restriction MANAGEMENT si nécessaire | oui, Agent unique |
| Discovery / watchlist | réévaluer les marchés intéressants | oui, même Agent |

Le monitoring utilise par défaut une cadence de 5 s en SPOT et 15 s en PERPETUAL, avec 5 s de timeout et 30 s de staleness. Les cadences restent configurables séparément.

# 4. Comptabilité SPOT par position — INTÉGRÉE 19.1

Confirmé : coût économique moyen pondéré, coût restant frais BUY inclus, ventes partielles au prorata, P&L réalisé net, pas de double comptage spread/slippage/frais, recovery JSON et compatibilité `accounting_complete=false`.

# 5. Monitoring / mark-to-market — INTÉGRÉ 19.2

Confirmé :

- source de mark SPOT : dernier ticker Kraken causal (`LAST_PRICE`) ;
- `mark_price`, `mark_observed_at`, `mark_source`, `market_value`, `unrealized_pnl`, `valuation_complete` ;
- P&L latent calculé uniquement côté backend avec `market_value - remaining_cost_basis` ;
- mark absent ou périmé => valeurs indisponibles ;
- position legacy avec coût inconnu => valeur de marché possible, P&L latent interdit ;
- agrégats portfolio : cash, coût restant, valeur SPOT, P&L réalisé/latent, equity, exposition ;
- monitor backend indépendant de l'Agent et du frontend ;
- snapshot/recovery compatible sans migration SQL ;
- Agent et Risk reçoivent le `PortfolioState` enrichi sans calcul financier parallèle ;
- cockpit Positions branché sur les champs backend.

# 6. Mode gestion lorsque l'exposition est saturée — PATCH 19.3 IMPLÉMENTÉ

Objectif : lorsque le backend sait qu'une nouvelle augmentation d'exposition est impossible ou qu'il ne peut pas établir une capacité sûre, éviter la recherche IA d'ouverture et concentrer le même Agent sur l'existant.

Architecture :

```text
Portfolio mark-to-market + RiskPolicy partagé
-> CapacityEvaluator déterministe
   -> NORMAL
   -> MANAGEMENT
```

## Confirmé dans le patch

- une seule instance `RiskPolicy` alimente CapacityEvaluator et RiskEngine ;
- `NORMAL` conserve le chemin de sélection actuel ;
- `MANAGEMENT` limite la sélection transportée aux positions ouvertes ;
- tools read-only de recherche d'ouverture désactivés dans cette phase ;
- même `OpenAIDecisionProvider` pour sélection MANAGEMENT et décision finale ;
- HOLD, réduction partielle et clôture restent des décisions stratégiques ;
- Risk reçoit le mode et refuse toute hausse d'exposition avec `MANAGEMENT_EXPOSURE_INCREASE` ;
- réduction PERPETUAL conserve `reduce_only`/anti-reversal ;
- retour à NORMAL automatique au cycle suivant dès qu'une capacité certaine réapparaît ;
- portefeuille mixte SPOT/PERPETUAL pris en compte ;
- `valuation_complete=false` => MANAGEMENT explicite, sans capacité inventée ;
- mode, raison, capacité SPOT/PERP et `new_opening_research_skipped` audités ;
- aucun nouvel état durable et aucune migration SQL ;
- aucune modification frontend.

## Limite volontaire du pré-calcul

CapacityEvaluator ne possède pas le `MarketState` du marché futur. Il ne décide donc pas :

- quantité minimum exacte ;
- contrat/instrument effectif ;
- levier maximum instrument ;
- marge/frais exacts ;
- fraîcheur du snapshot d'exécution ;
- liquidation/buffer.

Ces contrôles restent chez Risk. Le pré-calcul ne doit pas devenir un second Risk Engine.

## SPOT

La politique actuelle ne contient aucun plafond global d'exposition SPOT. Le Batch 19.3 n'invente donc pas un seuil basé sur `exposure_fraction`. Du cash settlement positif implique seulement une capacité **théorique** d'ouverture SPOT avant MarketState ; Risk reste responsable de l'ordre réel.

## PERPETUAL

Avant MarketState, CapacityEvaluator peut utiliser les limites canoniques déjà connues :

- `max_total_derivative_exposure` ;
- `max_derivative_position_notional` pour les positions déjà ouvertes ;
- disponibilité du cash settlement.

Les autres contraintes restent Risk.

## Économie IA observable

- sélection MANAGEMENT sans tools ;
- `AgentToolTrace` vide pour la phase de gestion ;
- `new_opening_research_skipped=true` audité.

L'infrastructure ne persiste actuellement aucun compteur `input_tokens`/`output_tokens`. Aucun chiffre estimé de tokens économisés n'est ajouté.

# 7. Explicabilité des décisions IA — PLANIFIÉ 19.5

Le `rationale` existe déjà. Le chantier porte sur son exposition produit :

- Accueil : dernière décision + « Pourquoi l'IA ? » ;
- Positions : décisions/trades corrélés ;
- Historique : lecture synthétique avant JSON ;
- chart : rationale associé aux markers ;
- Risk toujours affiché séparément.

# 8. Discovery automatique et watchlist — PLANIFIÉ 19.4

Deux étapes distinctes :

1. backend déterministe → univers techniquement admissible ;
2. même Agent stratégique → watchlist.

Invariant :

```text
univers surveillé = watchlist IA actuelle + toutes les positions ouvertes
```

Le mode manuel reste nécessaire pour les tests reproductibles.

À décider : taille de watchlist, persistence/versionnement, lien avec Campaign/paper_run et recovery.

# 9. Nouvel espace Marchés — PLANIFIÉ 19.6B

Navigation cible :

```text
Accueil | Marchés | Positions | Historique | Réglages
```

La vue Marchés affichera en onglets les marchés surveillés. Le frontend n'a aucune autorité sur la watchlist ou le moteur.

# 10. Charts chandeliers — PLANIFIÉ 19.6B

Renderer privilégié : **TradingView Lightweight Charts** avec données Kraken normalisées par le backend.

À afficher lorsque disponible : OHLC, prix courant, volume, prix moyen, mark/liquidation PERPETUAL et événements BUY/SELL/réduction/clôture.

# 11. Historique candles + WebSocket — PLANIFIÉ 19.6A

Pipeline cible :

```text
Kraken REST -> historique initial
Kraken WebSocket -> updates temps réel
backend -> normalisation/cache/persistence éventuelle
WebSocket cockpit -> frontend
```

Le backend doit gérer déduplication, candle courante mutable, reconnect/backfill et limitations de profondeur sans inventer de données.

# 12. Ordre global

| Ordre | Batch | Résultat principal | Statut |
| ---: | --- | --- | --- |
| 1 | 19.1 — Comptabilité SPOT | coût moyen, coût restant, P&L réalisé, recovery | intégré |
| 2 | 19.2 — Monitoring | P&L latent et état vivant sans LLM | intégré |
| 3 | 19.3 — Mode gestion | évite recherche IA inutile quand ouverture indisponible | patch implémenté |
| 4 | 19.4 — Discovery/watchlist | univers dynamique versionné | planifié |
| 5 | 19.5 — Explicabilité | rationale visible vs Risk | planifié |
| 6 | 19.6A — Candles/streaming | données chart canoniques | planifié |
| 7 | 19.6B — Marchés/charts | rendu, onglets, markers | planifié |

## 13. Validation attendue des prochains batches

### 19.3 — patch courant

- capacité disponible -> NORMAL ;
- saturation -> MANAGEMENT ;
- aucune recherche d'ouverture en MANAGEMENT ;
- positions ouvertes transmises au même Agent ;
- HOLD/réduction/clôture SPOT/PERPETUAL ;
- aucune augmentation ne contourne Risk ;
- retour à NORMAL ;
- portefeuille mixte ;
- valorisation incomplète ;
- audit du mode et de sa raison ;
- recovery sans état de mode durable ;
- aucune régression de la sélection normale ;
- aucun look-ahead ;
- aucune dépendance frontend.

### 19.4

- eligibility sans ranking ;
- watchlist Agent bornée ;
- versionnement/recovery ;
- invariant watchlist + positions ouvertes ;
- mode manuel reproductible.

### 19.5

- API/audit ;
- lint/typecheck/build frontend ;
- rationale et Risk clairement séparés.

### 19.6A

- parsing OHLC, déduplication, reconnect/backfill ;
- persistence/cache ;
- WebSocket cockpit ;
- staleness/lifecycle.

### 19.6B

- lint/typecheck/build ;
- light/dark ;
- changement onglet/timeframe ;
- cleanup subscriptions ;
- markers cohérents avec les fills.
