# 03 — Agent IA, trading et Risk Engine

## 1. Objet

Ce document fixe la frontière entre :

1. les calculs déterministes de contexte ;
2. la décision stratégique de l'agent IA ;
3. les règles déterministes de sécurité et d'exécution.

Cette frontière est centrale pour éviter de transformer AI Spot Trader en bot algorithmique traditionnel.

---

## 2. Principe de décision

### Confirmé

L'agent IA est l'unique décideur stratégique. Il choisit parmi :

- `BUY`
- `SELL`
- `HOLD`

Les systèmes déterministes peuvent calculer et présenter prix, spread, volume, bougies, statistiques, indicateurs, volatilité, exposition, P&L, contraintes et fraîcheur des données. Ils ne doivent pas décider silencieusement qu'un signal technique implique un `BUY` ou `SELL`.

Le Risk Engine reste déterministe et possède l'autorité finale d'autoriser, modifier ou refuser une intention.

---

## 3. Chaîne de décision

### Confirmé

```text
MarketState + PortfolioState + config
                  |
                  v
              Agent IA
                  |
                  v
         DecisionCandidate
                  |
        validation Pydantic
                  |
                  v
            Risk Engine
         /       |        \
     REJECT    MODIFY      ALLOW
         \       |        /
          v      v       v
          ExecutionIntent
                  |
          MarketState pricing
                  |
                  v
            Paper Broker
                  |
             Fill + ledger
```

Aucune sortie LLM ne déclenche directement un ordre Kraken.

Au Batch 05, Market State, Portfolio State et Paper Broker sont implémentés. L'agent réel et le Risk Engine fonctionnel restent respectivement aux Batch 07 et 06.

---

## 4. AgentInput

### Confirmé au Batch 02

Le contrat initial est structuré et strict :

```text
AgentInput
- cycle_id
- created_at
- market_state
- portfolio_state
- aggressiveness (1..10)
```

Les snapshots imbriqués sont eux-mêmes des modèles Pydantic stricts. Les timestamps techniques sont timezone-aware et normalisés en UTC.

Les champs `risk_context`, `experiment_context`, `allowed_actions` ou métadonnées de politique ne sont pas encore figés. Le Risk Engine devra toujours revalider une décision tradable, même si le contexte présenté à l'agent indique déjà les contraintes.

---

## 5. DecisionCandidate

### Confirmé au Batch 02

L'action appartient à `BUY | SELL | HOLD`.

```text
DecisionCandidate
- decision_id
- cycle_id
- created_at
- action
- symbol
- rationale?
```

Le sizing stratégique n'est pas tranché dans `DecisionCandidate`. `confidence`, horizon et métadonnées restent également ouverts.

La `rationale` est une donnée d'audit optionnelle ; elle n'est jamais interprétée comme une commande d'exécution.

---

## 6. Validation de sortie LLM

### Confirmé par principe de sécurité

- structure attendue ;
- validation Pydantic stricte ;
- enum d'action ;
- aucune action inconnue ;
- aucune exécution si parsing/validation échoue ;
- aucune donnée textuelle du LLM ne devient directement une commande Kraken.

Le parsing d'une réponse fournisseur réelle, les retries et le prompt restent hors Batch 05.

---

## 7. Risk Engine

### Mission confirmée

Le Risk Engine impose les règles de sécurité et d'intégrité. Il a autorité finale.

Il ne doit pas inventer un signal de marché, convertir un `HOLD` en `BUY`, choisir un actif alternatif ou devenir la stratégie principale.

Il peut refuser, réduire une taille, normaliser une intention, empêcher une vente non couverte, bloquer des données trop anciennes et imposer des limites absolues.

### Sortie initiale confirmée

```text
RiskAssessment
- risk_assessment_id
- cycle_id
- decision_id
- assessed_at
- status: ALLOW | MODIFY | REJECT
- reasons[]
```

Le détail d'une intention modifiée et les limites appliquées seront enrichis avec le Risk Engine réel si nécessaire.

### Règles candidates — toujours à décider/chiffrer

- balance disponible suffisante ;
- position disponible suffisante ;
- max order notional ;
- max exposure par actif ;
- max total exposure ;
- min cash reserve ;
- max drawdown ;
- max daily loss ;
- cooldown/frequency ;
- market data freshness ;
- spread maximal éventuel ;
- pair whitelist ;
- précision/minimum Kraken.

Le fait que le Paper Broker refuse un cash insuffisant ou une vente non couverte est une dernière frontière d'intégrité, pas une implémentation parallèle du Risk Engine.

---

## 8. ExecutionIntent

### Confirmé

L'intention d'exécution est distincte de la décision stratégique. Elle représente une requête déjà autorisée ou modifiée par le Risk Engine :

```text
ExecutionIntent
- execution_id
- cycle_id
- decision_id
- risk_assessment_id
- created_at
- mode = PAPER
- action = BUY | SELL
- symbol
- quantity > 0
```

`HOLD` ne produit jamais d'`ExecutionIntent`. Le mode `LIVE` n'existe pas dans l'enum actuel.

La quantité exacte fixe uniquement ce dont le broker a besoin à sa frontière d'exécution ; elle ne tranche pas le mécanisme amont de sizing stratégique.

---

## 9. PAPER Broker et Fill

### Confirmé au Batch 05

Le Paper Broker est l'unique cible d'exécution des premières versions.

Le port canonique reçoit explicitement l'intention et le contexte de pricing :

```text
Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]
```

Cela interdit un prix réseau caché et rend le replay/no-look-ahead auditables.

Le modèle initial est **fill immédiat complet ou rejet explicite**. Il n'existe pas de partial fill, carnet simulé, ordre limit/pending, matching engine ou aléatoire.

Le `Fill` devient :

```text
Fill
- fill_id
- execution_id
- market_state_id
- filled_at
- pricing_as_of
- action = BUY | SELL
- symbol
- quantity > 0
- reference_price > 0
- price > 0
- notional > 0
- fee >= 0
- spread_cost >= 0
- slippage_cost >= 0
```

Le contrat valide sa propre cohérence arithmétique et le caractère adverse du prix exécuté par rapport au prix de référence.

Le Paper Broker ne dépend d'aucun module Kraken et n'appelle aucun provider de marché.

---

## 10. Frais, spread et slippage

### Confirmé au Batch 05

Les trois sont pris en compte dans l'exécution PAPER et deviennent visibles dans le `Fill`.

Le modèle est injecté et ne prétend pas être le barème Kraken réel :

```text
PaperExecutionCostModel
- fee_rate
- spread_bps
- slippage_bps
```

Sémantique retenue :

- `fee_rate` est un taux décimal sur le notional exécuté ;
- `spread_bps` est l'impact adverse appliqué **à chaque côté** ; ce n'est pas un spread bid/ask total ;
- `slippage_bps` est un impact adverse additionnel par côté ;
- aucun composant n'est aléatoire.

Avec `P` comme prix de référence :

```text
BUY  = P * (1 + spread_bps/10000 + slippage_bps/10000)
SELL = P * (1 - spread_bps/10000 - slippage_bps/10000)
```

Les frais BUY sont débités en plus du notional. Les frais SELL sont déduits du produit. Tous les calculs utilisent `Decimal`, sans quantification fournisseur silencieuse.

Les valeurs produit par défaut des coûts restent **À DÉCIDER**. Les tests utilisent des valeurs explicites uniquement pour vérifier les mathématiques.

---

## 11. Portfolio PAPER et invariants SPOT

### Confirmé au Batch 05

Le `PortfolioState` distingue :

- `balances` : actifs de règlement disponibles ;
- `positions` : actifs détenus et disponibles à la vente.

Les deux collections sont disjointes par actif. Les snapshots sont fournis par `PaperPortfolioLedger`, initialisé explicitement par un état fourni à sa construction.

BUY : le broker doit disposer du quote asset nécessaire à `notional + fee`, puis débite le quote et crédite la position base.

SELL : la position base doit exister et disposer de la quantité demandée, puis le broker débite la base et crédite le quote de `notional - fee`.

Aucune balance ni position négative n'est permise. Un rejet laisse le portefeuille inchangé.

Aucune base de coût n'est introduite au Batch 05 ; les analytics/P&L complètes restent au Batch 12.

---

## 12. Agressivité

### Confirmé

Valeur entière de 1 à 10, validée dans la configuration et dans `AgentInput`.

Le mapping exact reste à décider. L'agressivité ne peut jamais autoriser short/margin/levier, permettre de vendre plus que détenu, bypasser le Risk Engine ou contourner une limite absolue.

---

## 13. Objectif quotidien +4 %

### Confirmé

Cible expérimentale : +4 % par jour.

Le système ne doit pas générer un trade uniquement parce que la journée est sous +4 %, augmenter automatiquement l'agressivité pour « rattraper » une perte sans expérience dédiée, masquer les jours négatifs, supprimer une mauvaise période ou utiliser le résultat futur pour modifier une décision passée.

L'objectif est une métrique, pas une obligation d'exécution.

---

## 14. Identifiants, timestamps et audit

### Confirmé

Les contrats utilisent des UUID explicites pour corréler les objets importants : snapshot de marché, snapshot de portefeuille, cycle, décision, évaluation de risque, exécution et fill.

Les timestamps techniques sont timezone-aware et normalisés en UTC.

Un cycle complet devra à terme permettre de relier :

```text
cycle_id
market_state_id
portfolio_state_id
decision_id
risk_assessment_id
execution_id
fill_id(s)
```

Le `Fill` référence directement `market_state_id` et `pricing_as_of`, ce qui conserve la provenance du prix PAPER.

Le format final de logs structurés, la persistance et la rétention restent à décider.

---

## 15. Horloge injectable et no look-ahead

### Confirmé

`Clock.now()` et `SystemClock` UTC permettent timestamps déterministes et replays.

Le Batch 04 interdit les observations futures dans un `MarketState` historique. Le Batch 05 ajoute :

```text
market_state.as_of <= execution_intent.created_at <= fill.filled_at
```

Le Paper Broker rejette un contexte de pricing futur et ne fait aucun lookup réseau pendant une exécution/replay.

---

## 16. Interfaces externes

### Confirmé après Batch 05

Ports canoniques :

- `MarketDataSource.snapshot(symbol) -> MarketState` ;
- `MarketObservationSource.observation(symbol) -> MarketObservation` ;
- `LLMProvider.generate_decision(agent_input) -> DecisionCandidate` ;
- `Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]`.

Les détails Kraken, le SDK LLM, credentials, retries et prompt restent isolés de ces contrats.

---

## 17. Comparaison Luna / Sol

### Confirmé

Luna est le modèle initial pour raison de coût ; Sol est sélectionnable par configuration. Une future comparaison devra utiliser un protocole comparable : mêmes Market States, Portfolio States, limites de risque, coûts PAPER, mapping d'agressivité et versions de prompts/contracts lorsque possible.

---

## 18. Conditions minimales avant discussion LIVE

**Hors périmètre pour l'instant.** Les conditions candidates restent : stabilité PAPER significative, journal d'audit complet, modèle de coûts validé, limites de risque chiffrées et testées, réconciliation de portefeuille, gestion robuste des erreurs réseau, credentials séparés, aucune permission de retrait, activation explicite et revue de sécurité.

La satisfaction de ces points ne constitue pas automatiquement une autorisation de passage en LIVE.
