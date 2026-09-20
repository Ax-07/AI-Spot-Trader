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

- `BUY` ;
- `SELL` ;
- `HOLD`.

Pour `BUY` et `SELL`, l'agent/proposition stratégique fournit également la **quantité proposée**. Le Risk Engine n'est pas le sourceur principal du sizing : il peut uniquement conserver ou réduire cette quantité selon une policy explicite.

Les systèmes déterministes peuvent calculer et présenter prix, spread, volume, bougies, statistiques, indicateurs, volatilité, exposition, P&L, contraintes et fraîcheur des données. Ils ne doivent pas décider silencieusement qu'un signal technique implique un `BUY` ou `SELL`.

Le Risk Engine reste déterministe et possède l'autorité finale d'autoriser, modifier ou refuser une proposition tradable.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

---

## 3. Chaîne de décision

### Confirmé après Batch 06

```text
MarketState + PortfolioState + config
                  |
                  v
              Agent IA
                  |
                  v
         DecisionCandidate
   action + proposed_quantity
                  |
        validation Pydantic
                  |
                  v
            Risk Engine
         /       |        \
     REJECT    MODIFY      ALLOW
         |        |          |
   aucun intent   +----------+
                  |
                  v
          ExecutionIntent PAPER
                  |
          MarketState pricing
                  |
                  v
            Paper Broker
                  |
             Fill + ledger
```

Aucune sortie LLM ne déclenche directement un ordre Kraken. Le Risk Engine n'appelle ni Kraken, ni le LLM, ni le Paper Broker.

Le Batch 06 stabilise la frontière Risk que l'Agent Luna du Batch 07 alimentera et que la boucle autonome du Batch 08 orchestrera.

---

## 4. AgentInput

### Confirmé au Batch 02

```text
AgentInput
- cycle_id
- created_at
- market_state
- portfolio_state
- aggressiveness (1..10)
```

Les snapshots imbriqués sont des modèles Pydantic stricts. Les timestamps techniques sont timezone-aware et normalisés en UTC.

Les champs `risk_context`, `experiment_context` et métadonnées de politique ne sont pas encore figés. Le Risk Engine revalide toujours une proposition tradable, même si l'agent a déjà reçu des contraintes dans son contexte.

---

## 5. DecisionCandidate et sizing stratégique

### Confirmé au Batch 06

```text
DecisionCandidate
- decision_id
- cycle_id
- created_at
- action = BUY | SELL | HOLD
- symbol
- proposed_quantity?   # obligatoire BUY/SELL, interdite HOLD
- rationale?
```

Décision architecturale : la taille proposée est portée directement par le contrat stratégique canonique plutôt que par une interface parallèle.

Conséquences :

- `BUY` et `SELL` sans `proposed_quantity` sont invalides ;
- `HOLD` avec une quantité est invalide ;
- le Risk Engine peut réduire une quantité uniquement si sa policy l'autorise ;
- le Risk Engine ne peut jamais augmenter la taille proposée ;
- le Risk Engine ne peut jamais changer BUY en SELL, SELL en BUY ou changer de symbole ;
- la future implémentation Luna devra donc produire action, symbole et taille proposée dans son contrat structuré.

La `rationale` est une donnée d'audit optionnelle ; elle n'est jamais interprétée comme une commande d'exécution.

---

## 6. Validation de sortie LLM

### Confirmé par principe de sécurité

- structure attendue ;
- validation Pydantic stricte ;
- enum d'action ;
- BUY/SELL avec taille positive ;
- HOLD sans taille ;
- aucune action inconnue ;
- aucune exécution si parsing/validation échoue ;
- aucune donnée textuelle du LLM ne devient directement une commande Kraken.

Le parsing d'une réponse fournisseur réelle, les retries et le prompt restent hors Batch 06.

---

## 7. Risk Engine

### Mission confirmée

Le Risk Engine impose les règles de sécurité et d'intégrité. Il a autorité finale.

Il ne doit pas inventer un signal de marché, convertir un `HOLD` en trade, choisir un actif alternatif, appeler Kraken/LLM/Broker, muter les snapshots ou devenir la stratégie principale.

### Contrats Batch 06

```text
RiskPolicy
- max_order_notional?
- allowed_pairs?
- stale_after?
- allow_quantity_reduction = false
```

Aucune valeur produit n'est choisie silencieusement. `None` signifie qu'une limite optionnelle n'est pas appliquée. Une whitelist vide est invalide ; l'absence de whitelist signifie « pas de contrainte de paire par cette policy ».

```text
RiskAssessment
- risk_assessment_id
- cycle_id
- decision_id
- assessed_at
- status = ALLOW | MODIFY | REJECT
- requested_quantity?
- authorized_quantity?
- evaluated_limits[] : RiskLimit
- reasons[] : RiskReason
```

Les `RiskReason` sont des codes stables et testables, pas du texte libre dépendant de l'exécution. `evaluated_limits` enregistre les contrôles réellement atteints par le pipeline, y compris sur un `ALLOW`.

### Sémantique

- `ALLOW` : proposition acceptée sans changement matériel ; pour un trade, quantité autorisée = quantité demandée.
- `MODIFY` : quantité strictement réduite ; la réduction doit être explicitement activée par la policy.
- `REJECT` : aucun `ExecutionIntent` n'est produit.
- `HOLD` : reste une décision stratégique valide ; l'évaluation porte `ALLOW` + `HOLD_NO_EXECUTION`, sans quantité ni `ExecutionIntent`.

### Contrôles effectivement implémentés

- format canonique `BASE/QUOTE` ;
- symbole du `MarketState` identique à la proposition ;
- whitelist de paire optionnelle ;
- `MarketState.as_of <= DecisionCandidate.created_at` ;
- `PortfolioState.as_of <= DecisionCandidate.created_at` ;
- stale métier optionnel évalué depuis `MarketContext.last_observed_at` jusqu'à `RiskAssessment.assessed_at` ;
- seuil stale strict : égalité au seuil = encore acceptable, dépassement = stale ;
- présence du quote asset nécessaire ;
- cohérence des rôles balance/position ;
- max order notional optionnel calculé sur `market_state.last_price * quantity` ;
- solvabilité BUY avec estimation complète du coût PAPER prévisible ;
- position SELL réellement disponible ;
- aucune vente non couverte.

### Limites volontairement non implémentées au Batch 06

- drawdown maximal ;
- daily loss ;
- VaR, corrélations, bêta ;
- allocation optimale ;
- exposition portefeuille multi-actifs globale ;
- cooldown/frequency ;
- précision/minimum Kraken ;
- spread réel bid/ask maximal ;
- mapping numérique de l'agressivité.

Ces règles nécessitent soit des données encore absentes, soit une décision produit séparée. Elles ne sont pas simulées à partir d'informations insuffisantes.

---

## 8. MODIFY et réductions autorisées

### Confirmé au Batch 06

La réduction est désactivée par défaut (`allow_quantity_reduction=False`). Lorsqu'elle est activée, le Risk Engine peut borner une quantité par :

- le max order notional configuré ;
- le cash BUY réellement disponible, coûts PAPER prévisibles inclus ;
- la quantité SELL disponible.

Le résultat est toujours le minimum sûr des limites effectivement rencontrées. Une quantité finale nulle ou négative devient un `REJECT`.

Le Risk Engine ne peut jamais :

- augmenter la quantité ;
- changer l'action ;
- changer le symbole ;
- transformer HOLD en ordre ;
- choisir une « meilleure » opportunité.

---

## 9. ExecutionIntent

### Confirmé

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

Au Batch 06, `ExecutionIntent.created_at` est le timestamp de l'évaluation Risk. L'ID d'exécution, l'ID d'évaluation et l'horloge sont injectables pour les tests/replays.

La quantité de l'intention est exactement `RiskAssessment.authorized_quantity`. HOLD et REJECT ne produisent jamais d'intention.

---

## 10. PAPER Broker et estimation commune des coûts

### Confirmé après Batch 06

Le Paper Broker reste l'unique composant qui exécute et mute le portefeuille.

Le port canonique reste :

```text
Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]
```

Le Batch 06 factorise la mathématique PAPER dans `broker/pricing.py` :

- `PaperExecutionCostModel` ;
- `PaperExecutionEstimate` ;
- `estimate_paper_execution(...)`.

Cette fonction est pure et sans effet de bord. Elle est utilisée :

- par le Risk Engine pour anticiper le cash BUY nécessaire ;
- par le Paper Broker pour construire le fill réel.

Il n'existe donc pas deux formules divergentes pour fee/spread/slippage. Le Risk Engine n'exécute jamais l'ordre pour connaître l'estimation.

Le modèle reste **fill immédiat complet ou rejet explicite**. Aucun partial fill, carnet simulé, ordre limite/pending, matching engine ou aléatoire.

---

## 11. Frais, spread et slippage

### Confirmé au Batch 05, factorisé au Batch 06

```text
PaperExecutionCostModel
- fee_rate
- spread_bps
- slippage_bps
```

Sémantique :

- `fee_rate` = taux décimal sur le notional exécuté ;
- `spread_bps` = impact adverse appliqué à chaque côté ;
- `slippage_bps` = impact adverse additionnel par côté ;
- aucun composant aléatoire.

Avec `P` comme prix de référence :

```text
BUY  = P * (1 + spread_bps/10000 + slippage_bps/10000)
SELL = P * (1 - spread_bps/10000 - slippage_bps/10000)
```

BUY débite `notional + fee`. SELL crédite `notional - fee`. Tous les calculs financiers utilisent `Decimal`, sans quantification fournisseur silencieuse.

Le max order notional Risk reste distinct : il est évalué sur le notional de référence `P * quantity`, tandis que la solvabilité BUY utilise le coût PAPER estimé complet.

---

## 12. Portfolio PAPER et invariants SPOT

### Confirmé

Le `PortfolioState` distingue :

- `balances` : actifs de règlement disponibles ;
- `positions` : actifs détenus et disponibles à la vente.

BUY : le Risk Engine anticipe la solvabilité ; le Paper Broker garde son contrôle final puis débite le quote et crédite la base.

SELL : le Risk Engine refuse ou réduit selon la quantité disponible ; le Paper Broker conserve également ce garde-fou d'intégrité avant mutation.

Cette duplication est volontaire :

- Risk Engine = décision de sécurité ;
- Paper Broker = intégrité finale d'exécution.

Aucune balance ni position négative n'est permise.

---

## 13. Agressivité

### Confirmé

Valeur entière de 1 à 10, validée dans la configuration et dans `AgentInput`.

Le mapping exact reste à décider. Le Batch 06 ne fige aucun coefficient. L'agressivité ne peut jamais autoriser short/margin/levier, vendre plus que détenu, bypasser le Risk Engine ou contourner une limite absolue.

---

## 14. Objectif quotidien +4 %

### Confirmé

Cible expérimentale : +4 % par jour, jamais une garantie.

Le système ne doit pas générer un trade uniquement parce que la journée est sous +4 %, augmenter automatiquement l'agressivité pour « rattraper » une perte sans expérience dédiée, masquer les jours négatifs, supprimer une mauvaise période ou utiliser le résultat futur pour modifier une décision passée.

L'objectif est une métrique, pas une obligation d'exécution.

---

## 15. Identifiants, timestamps et audit

### Confirmé après Batch 06

Un cycle complet pourra relier :

```text
cycle_id
market_state_id
portfolio_state_id
decision_id
risk_assessment_id
execution_id
fill_id(s)
```

Relations temporelles de la frontière Risk :

```text
market_state.as_of    <= decision_candidate.created_at
portfolio_state.as_of <= decision_candidate.created_at
                         <= risk_assessment.assessed_at
                         == execution_intent.created_at   # si intent
```

Le Paper Broker ajoute ensuite :

```text
market_state.as_of <= execution_intent.created_at <= fill.filled_at
```

Aucun lookup réseau n'est nécessaire pendant une évaluation Risk ou une exécution PAPER/replay.

---

## 16. Interfaces externes

### Confirmé après Batch 06

Ports canoniques :

- `MarketDataSource.snapshot(symbol) -> MarketState` ;
- `MarketObservationSource.observation(symbol) -> MarketObservation` ;
- `LLMProvider.generate_decision(agent_input) -> DecisionCandidate` ;
- `Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]`.

Le Risk Engine est une frontière métier interne synchrone et déterministe ; il n'introduit pas de port externe supplémentaire.

---

## 17. Comparaison Luna / Sol

### Confirmé

Luna est le modèle initial pour raison de coût ; Sol est sélectionnable par configuration. Une future comparaison devra utiliser des Market States, Portfolio States, Risk Policies, coûts PAPER, mapping d'agressivité et versions de prompts/contracts comparables lorsque possible.

---

## 18. Conditions minimales avant discussion LIVE

**Hors périmètre pour l'instant.** Les conditions candidates restent : stabilité PAPER significative, journal d'audit complet, modèle de coûts validé, limites de risque chiffrées et testées, réconciliation de portefeuille, gestion robuste des erreurs réseau, credentials séparés, aucune permission de retrait, activation explicite et revue de sécurité.

La satisfaction de ces points ne constitue pas automatiquement une autorisation de passage en LIVE.
