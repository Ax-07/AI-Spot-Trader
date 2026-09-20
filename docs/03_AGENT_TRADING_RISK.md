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
                  v
            Paper Broker
```

Aucune sortie LLM ne déclenche directement un ordre Kraken.

Le Batch 02 stabilise les contrats mais n'implémente ni l'agent réel, ni le Risk Engine, ni le Paper Broker.

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

Les champs `risk_context`, `experiment_context`, `allowed_actions` ou métadonnées de politique ne sont pas figés dans ce batch ; ils pourront être ajoutés lorsqu'un besoin concret apparaîtra.

Le Risk Engine devra toujours revalider une décision tradable, même si le contexte présenté à l'agent indique déjà les contraintes.

---

## 5. DecisionCandidate

### Confirmé au Batch 02

L'action appartient à `BUY | SELL | HOLD`.

Contrat initial :

```text
DecisionCandidate
- decision_id
- cycle_id
- created_at
- action
- symbol
- rationale?
```

Le contrat reste volontairement minimal. En particulier, la représentation du sizing stratégique n'est pas tranchée par le Batch 02. `confidence`, horizon et métadonnées restent également ouverts.

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

Le Batch 02 couvre la validation des contrats ; le parsing d'une réponse fournisseur réelle, les retries et le prompt sont hors périmètre.

---

## 7. Risk Engine

### Mission confirmée

Le Risk Engine impose les règles de sécurité et d'intégrité. Il a autorité finale.

Il ne doit pas inventer un signal de marché, convertir un `HOLD` en `BUY`, choisir un actif alternatif « meilleur » ou devenir la stratégie principale.

Il peut refuser, réduire une taille, normaliser une intention, empêcher une vente non couverte, bloquer des données trop anciennes et imposer des limites absolues.

### Sortie initiale confirmée au Batch 02

```text
RiskAssessment
- risk_assessment_id
- cycle_id
- decision_id
- assessed_at
- status: ALLOW | MODIFY | REJECT
- reasons[]
```

Le Batch 02 ne fige pas encore `limits_snapshot`, ni le détail d'une intention modifiée. Ces éléments seront ajoutés avec le Risk Engine réel lorsque les limites et le sizing seront décidés.

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

---

## 8. ExecutionIntent

### Confirmé au Batch 02

L'intention d'exécution est distincte de la décision stratégique. Elle représente une requête déjà autorisée ou modifiée par le Risk Engine et contient :

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

`HOLD` ne produit jamais d'`ExecutionIntent`. Le mode `LIVE` n'existe pas dans l'enum actuel et ne peut donc pas être activé par configuration.

Le fait de porter une quantité exacte dans `ExecutionIntent` ne tranche pas le mécanisme amont de sizing stratégique ; il fixe uniquement ce dont un broker a besoin à sa frontière d'exécution.

---

## 9. PAPER Broker et Fill

### Confirmé

Le Paper Broker est l'unique cible d'exécution des premières versions.

Le port `Broker` existe au Batch 02 sans implémentation. Il reçoit un `ExecutionIntent` PAPER et retourne zéro ou plusieurs `Fill`.

Contrat initial de `Fill` :

```text
Fill
- fill_id
- execution_id
- filled_at
- action = BUY | SELL
- symbol
- quantity > 0
- price > 0
```

Les frais, spread, slippage, fills partiels et règles précises d'exécution ne sont pas modélisés dans ce batch ; ils restent explicitement hors périmètre.

---

## 10. Frais, spread et slippage

### Confirmé

Les trois devront être pris en compte dans le Paper Broker et les métriques nettes.

Le barème précis Kraken, la méthode de slippage et le modèle de fill restent à décider. Le Batch 02 ne crée aucun paramètre chiffré anticipé pour ces sujets.

---

## 11. Agressivité

### Confirmé

Valeur entière de 1 à 10, validée dans la configuration et dans `AgentInput`.

Le mapping exact reste à décider. L'agressivité ne peut jamais autoriser short/margin/levier, permettre de vendre plus que détenu, bypasser le Risk Engine ou contourner une limite absolue.

---

## 12. Objectif quotidien +4 %

### Confirmé

Cible expérimentale : +4 % par jour.

Le système ne doit pas générer un trade uniquement parce que la journée est sous +4 %, augmenter automatiquement l'agressivité pour « rattraper » une perte sans expérience dédiée, masquer les jours négatifs, supprimer une mauvaise période ou utiliser le résultat futur pour modifier une décision passée.

L'objectif est une métrique, pas une obligation d'exécution.

---

## 13. Identifiants, timestamps et audit

### Confirmé au Batch 02

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

Le format final de logs structurés, la persistance et la rétention restent à décider. La frontière de journée statistique reste ouverte et n'est pas déduite de la convention UTC technique.

---

## 14. Horloge injectable

### Confirmé au Batch 02

Une interface minimale `Clock.now()` et une implémentation `SystemClock` UTC sont introduites. Elles créent un seam de test concret pour :

- timestamps déterministes ;
- futurs replays ;
- prévention du look-ahead dans les composants temporels.

Aucune infrastructure de simulation temporelle supplémentaire n'est introduite à ce stade.

---

## 15. Interfaces externes

### Confirmé au Batch 02

Trois ports minimaux stabilisent les dépendances sans implémenter les providers :

- `MarketDataSource.snapshot(symbol) -> MarketState` ;
- `LLMProvider.generate_decision(agent_input) -> DecisionCandidate` ;
- `Broker.execute(execution_intent) -> tuple[Fill, ...]`.

Les détails Kraken, le SDK LLM, les credentials, les retries, le prompt et l'algorithme Paper Broker restent hors périmètre.

---

## 16. Comparaison Luna / Sol

### Confirmé

Luna est le modèle initial pour raison de coût ; Sol est sélectionnable par configuration. Une future comparaison devra utiliser un protocole comparable : mêmes Market States, Portfolio States, limites de risque, coûts PAPER, mapping d'agressivité et versions de prompts/contracts lorsque possible.

---

## 17. Conditions minimales avant discussion LIVE

**Hors périmètre pour l'instant.** Les conditions candidates restent : stabilité PAPER significative, journal d'audit complet, modèle de coûts validé, limites de risque chiffrées et testées, réconciliation de portefeuille, gestion robuste des erreurs réseau, credentials séparés, aucune permission de retrait, activation explicite et revue de sécurité.

La satisfaction de ces points ne constitue pas automatiquement une autorisation de passage en LIVE.
