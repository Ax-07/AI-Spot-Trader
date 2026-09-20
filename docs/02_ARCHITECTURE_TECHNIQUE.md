# 02 — Architecture technique

## 1. Objet

Ce document décrit l'architecture technique courante d'AI Spot Trader. Il complète `01_PROJECT_MASTER.md` sans remplacer les décisions produit.

---

## 2. Vue d'ensemble

```text
+--------------------------+
| Frontend cockpit         |
| Next.js / TS / shadcn    |
+------------+-------------+
             |
       REST / WebSocket
             |
+------------v-------------+
| FastAPI API              |
+------------+-------------+
             |
+------------v---------------------------------------+
| Backend trading                                   |
|                                                    |
| Kraken -> observations -> MarketState              |
| PortfolioState ---------> Agent -> DecisionCandidate|
|                                   |                |
|                                   v                |
|                              Risk Engine            |
|                                   |                |
|                         RiskAssessment/Intent       |
|                                   |                |
| MarketState -----------------> Paper Broker         |
|                                   |                |
|                          Fill + portfolio ledger    |
+----------------------------------------------------+
```

Le backend est un service autonome ; le frontend n'est jamais l'ordonnanceur du moteur.

---

## 3. Découpage backend après Batch 06

```text
backend/src/ai_spot_trader/
  api/
  broker/
    errors.py
    paper.py
    pricing.py
  core/
    clock.py
    config.py
    runtime.py
  domain/
    enums.py
    models.py
    ports.py
    symbols.py
  integrations/kraken/
  market/
    errors.py
    state.py
  portfolio/
    errors.py
    ledger.py
  risk/
    __init__.py
    engine.py
    errors.py
    policy.py
  main.py
```

Responsabilités :

- `domain` : contrats canoniques fournisseur-agnostiques et parsing du symbole canonique ;
- `integrations/kraken` : structures et I/O spécifiques Kraken uniquement ;
- `market` : historique et snapshots déterministes ;
- `portfolio` : état mutable PAPER mémoire ;
- `broker/pricing.py` : estimation PAPER pure et modèle de coûts partagé ;
- `broker/paper.py` : exécution PAPER et mutation du ledger ;
- `risk` : évaluation déterministe sans effets de bord.

---

## 4. Contrats de domaine

Les contrats sont Pydantic stricts, `extra="forbid"`, timestamps aware normalisés UTC et valeurs financières en `Decimal`.

### DecisionCandidate

BUY/SELL exigent une `proposed_quantity > 0`. HOLD interdit toute quantité. Cette quantité est la proposition stratégique amont.

### RiskAssessment

Le contrat expose statut, quantité demandée, quantité autorisée, limites réellement évaluées (`RiskLimit`) et raisons structurées. Invariants :

- `ALLOW` conserve la quantité demandée ;
- `MODIFY` réduit strictement la quantité ;
- `REJECT` n'autorise aucune quantité et possède au moins une raison ;
- HOLD peut être `ALLOW` sans quantité ni intent.

### ExecutionIntent

PAPER uniquement, BUY/SELL uniquement, quantité positive et corrélation au `RiskAssessment`.

---

## 5. Symboles canoniques

`domain.symbols.parse_canonical_symbol()` est désormais la primitive générique `BASE/QUOTE` partagée par Risk et Paper Broker. Elle ne connaît aucun alias Kraken.

Les alias et métadonnées fournisseur restent confinés à `integrations/kraken/symbols.py`.

---

## 6. Market State

`MarketStateBuilder` reste synchrone, mono-symbole, mémoire, historique borné et no-look-ahead. Il ne contient aucune stratégie.

Le `MarketContext` expose la dernière observation et son âge. Le stale technique éventuellement calculé au niveau Market State n'est pas automatiquement une décision Risk.

---

## 7. Portfolio ledger PAPER

`PaperPortfolioLedger` reçoit un `PortfolioState` initial injecté. `balances` et `positions` restent les deux rôles canoniques disjoints.

Les mutations sont copy-on-write ; un rejet ne laisse aucune modification partielle. Le ledger ne dépend ni de Kraken, ni FastAPI, ni Risk.

---

## 8. Pricing PAPER partagé

`broker/pricing.py` contient :

```text
PaperExecutionCostModel
PaperExecutionEstimate
estimate_paper_execution(...)
```

La fonction d'estimation est pure et utilisée par :

- le Risk Engine pour anticiper le débit quote complet d'un BUY ;
- le Paper Broker pour construire le fill réel.

Cela crée une seule mathématique canonique des coûts PAPER et évite deux modèles divergents.

Formules :

```text
spread_rate   = spread_bps / 10000
slippage_rate = slippage_bps / 10000
BUY price     = reference * (1 + spread_rate + slippage_rate)
SELL price    = reference * (1 - spread_rate - slippage_rate)
notional      = price * quantity
fee           = notional * fee_rate
```

BUY débite `notional + fee`; SELL crédite `notional - fee`.

---

## 9. Risk Engine

### 9.1 Construction

`RiskEngine` reçoit explicitement :

- `RiskPolicy` ;
- `PaperExecutionCostModel` ;
- `Clock` ;
- factories UUID pour assessment et execution.

Aucune dépendance à `Settings`, FastAPI, Kraken, LLM ou `PaperBroker`.

### 9.2 RiskPolicy

```text
RiskPolicy
- max_order_notional: Decimal | None
- allowed_pairs: frozenset[str] | None
- stale_after: timedelta | None
- allow_quantity_reduction: bool
```

Les valeurs sont injectées par l'appelant. `None` signifie que la limite correspondante n'est pas appliquée. Une whitelist vide est refusée pour éviter une sémantique ambiguë.

### 9.3 Pipeline d'évaluation

Pour BUY/SELL :

1. horloge Risk non antérieure à la décision ;
2. symbole canonique ;
3. symbole `DecisionCandidate == MarketState` ;
4. whitelist optionnelle ;
5. snapshots marché et portefeuille non futurs par rapport à la décision ;
6. stale métier optionnel ;
7. max notional optionnel ;
8. contrôle spécifique BUY ou SELL ;
9. construction du `RiskAssessment` ;
10. construction de l'`ExecutionIntent` uniquement si ALLOW/MODIFY.

Une violation métier normale retourne `REJECT`; les exceptions sont réservées aux états techniques invalides, par exemple une horloge d'évaluation impossible.

### 9.4 BUY

- l'actif base ne doit pas être un `balance` ;
- le quote balance doit exister ;
- le débit prévisible complet inclut prix adverse PAPER + frais ;
- si le cash manque, REJECT ou réduction si la policy l'autorise ;
- la quantité n'est jamais augmentée.

### 9.5 SELL

- le quote balance doit exister ;
- le base ne doit pas être un `balance` ;
- une position base doit exister ;
- la quantité ne peut pas dépasser `available` ;
- dépassement = REJECT ou réduction si explicitement autorisée ;
- quantité disponible nulle = REJECT.

### 9.6 HOLD

HOLD retourne un `RiskAssessment` auditable mais aucun `ExecutionIntent`.

---

## 10. Paper Broker

Le broker reste la dernière frontière d'intégrité. Il revalide PAPER, BUY/SELL, symbole, temporalité de pricing et les capacités du ledger.

Cette duplication est volontaire :

```text
Risk Engine  -> décision de sécurité explicable
Paper Broker -> intégrité finale de l'exécution
```

Le broker ne récupère jamais de prix réseau caché.

---

## 11. Chronologie

Relations canoniques du Batch 06 :

```text
MarketState.as_of <= DecisionCandidate.created_at
PortfolioState.as_of <= DecisionCandidate.created_at
DecisionCandidate.created_at <= RiskAssessment.assessed_at
RiskAssessment.assessed_at = ExecutionIntent.created_at
MarketState.as_of <= ExecutionIntent.created_at <= Fill.filled_at
```

Le Risk Engine utilise l'âge marché calculé à `assessed_at` lorsqu'un seuil métier `stale_after` est injecté. La frontière est stricte : âge égal au seuil = encore autorisable ; âge supérieur = stale.

---

## 12. Orchestration asynchrone

Les composants déterministes (`MarketStateBuilder`, ledger, Risk Engine, estimateur PAPER) sont synchrones. Les I/O externes restent asynchrones. `PaperBroker.execute()` reste asynchrone et sérialisé avec `asyncio.Lock`.

Le Batch 06 ne crée aucune boucle, tâche de fond ou scheduler. L'orchestration complète reste au Batch 08.

---

## 13. Configuration

`Settings` et `.env.example` ne reçoivent aucune limite Risk au Batch 06. Aucune valeur globale de max order, stale, whitelist, capital ou réserve cash n'est imposée.

Les valeurs produit seront décidées plus tard et pourront être injectées via une couche de configuration appropriée sans modifier la logique Risk.

---

## 14. Persistance, API et frontend

Aucune persistance, migration, route FastAPI ou modification frontend n'est introduite au Batch 06. PostgreSQL reste la cible future.

---

## 15. Dépendances externes

Aucune dépendance runtime supplémentaire. NumPy, Pandas, TA-Lib et SDK LLM/broker ne sont pas ajoutés.

---

## 16. Limites non calculables honnêtement au Batch 06

Sont volontairement laissés à des batches ultérieurs :

- max drawdown ;
- max daily loss ;
- P&L journalier ;
- VaR/corrélations/bêta ;
- exposition portefeuille avancée ;
- cooldown/turnover ;
- allocation optimale ;
- précision et minimums Kraken ;
- mapping agressivité 1–10.

---

## 17. Qualité architecturale

Chaque batch doit préserver : séparation des responsabilités, contrats testables, dépendances fournisseur confinées, calculs financiers `Decimal`, no-look-ahead, testabilité offline, aucune stratégie déterministe cachée, mutations atomiques et remplacement Luna/Sol par configuration sans refonte métier.
