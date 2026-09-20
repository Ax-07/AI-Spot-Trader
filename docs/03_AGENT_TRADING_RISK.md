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

Les systèmes déterministes peuvent calculer et présenter :

- prix ;
- spread ;
- volume ;
- bougies ;
- statistiques ;
- indicateurs ;
- volatilité ;
- exposition ;
- P&L ;
- contraintes ;
- fraîcheur des données.

Ils ne doivent pas décider silencieusement qu'un signal technique implique un `BUY` ou `SELL`.

### Exemple de frontière correcte

```text
Déterministe : RSI=72, volatilité=..., spread=...
Agent : interprète ce contexte et propose HOLD.
Risk Engine : vérifie que HOLD est valide, journalise.
```

### Exemple à éviter

```text
if RSI < 30 and MACD_cross:
    BUY
```

Une telle règle deviendrait une stratégie algorithmique parallèle et contredirait la philosophie actuelle, sauf décision architecturale explicite ultérieure.

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

---

## 4. AgentInput

### Proposé

L'entrée de l'agent devrait être un objet structuré, pas un assemblage de texte arbitraire.

```text
AgentInput
- schema_version
- cycle_id
- timestamp
- market_state
- portfolio_state
- aggressiveness
- allowed_actions
- risk_context
- experiment_context
```

`allowed_actions` doit respecter les invariants du portefeuille. Par exemple, si aucun actif n'est détenu, une vente doit être impossible ou explicitement présentée comme non disponible.

Le Risk Engine doit malgré tout revalider la sortie : on ne fait jamais confiance au seul prompt.

---

## 5. DecisionCandidate

### Confirmé

L'action appartient à `BUY | SELL | HOLD`.

### Proposé

```text
DecisionCandidate
- schema_version
- decision_id
- cycle_id
- created_at
- action
- symbol
- sizing_intent
- rationale
- confidence
- horizon
```

Le contenu de `rationale` doit rester exploitable pour l'audit, mais ne doit pas être interprété comme une commande d'exécution.

### À décider

- représentation du sizing : montant en devise, pourcentage de cash, pourcentage de position, cible d'exposition ;
- confidence obligatoire ou non ;
- longueur et stockage du raisonnement/rationale ;
- horizon ;
- décision sur une seule paire ou sélection parmi plusieurs paires par cycle.

---

## 6. Validation de sortie LLM

### Confirmé par principe de sécurité

- JSON/structure attendue ;
- validation Pydantic stricte ;
- enum d'action ;
- symbole autorisé ;
- nombres finis et bornables ;
- aucune action inconnue ;
- aucune exécution si parsing/validation échoue.

### Proposé

En cas d'échec :

1. journaliser l'erreur ;
2. éventuellement effectuer un retry borné si la politique le prévoit ;
3. si l'échec persiste, traiter le cycle comme non tradable ;
4. ne jamais "deviner" une décision depuis du texte invalide.

---

## 7. Risk Engine

### Mission confirmée

Le Risk Engine impose les règles de sécurité et d'intégrité. Il a autorité finale.

Il ne doit pas :

- inventer un signal de marché ;
- convertir un `HOLD` en `BUY` ;
- choisir un actif alternatif "meilleur" ;
- devenir la stratégie principale.

Il peut :

- refuser ;
- réduire une taille ;
- normaliser précision/notional ;
- empêcher une vente non couverte ;
- bloquer des données trop anciennes ;
- imposer des limites absolues.

### Sortie proposée

```text
RiskAssessment
- decision_id
- status: ALLOW | MODIFY | REJECT
- reasons[]
- original_intent
- approved_intent
- limits_snapshot
- assessed_at
```

### Règles candidates

**Proposées, valeurs à décider :**

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

## 8. PAPER Broker

### Confirmé

Le Paper Broker est l'unique cible d'exécution des premières versions.

### Responsabilités proposées

- valider à nouveau les contraintes d'exécution triviales ;
- simuler prix et quantité exécutés ;
- appliquer frais ;
- appliquer spread ;
- appliquer slippage ;
- produire un ou plusieurs `Fill` ;
- mettre à jour balances et positions ;
- conserver une trace reproductible de la méthode utilisée.

### À décider

Trois niveaux de réalisme possibles :

1. **simple** : fill immédiat au bid/ask + slippage paramétrique ;
2. **intermédiaire** : fill selon taille et profondeur observée ;
3. **avancé** : simulation d'ordres et fills partiels.

Le choix doit être fait en fonction de la qualité de données disponible et du besoin expérimental. Le modèle retenu doit rester déterministe pour un même snapshot/configuration lorsque possible.

---

## 9. Frais, spread et slippage

### Confirmé

Les trois doivent être pris en compte.

### Règles d'intégrité

- ne pas afficher uniquement le P&L avant coûts ;
- distinguer coût de frais, spread et slippage ;
- versionner les hypothèses ;
- ne pas ajuster rétroactivement le modèle de coûts pour améliorer les résultats ;
- conserver le modèle utilisé pour chaque expérience.

Le barème précis Kraken et le modèle de slippage restent à décider.

---

## 10. Agressivité

### Confirmé

Valeur entière de 1 à 10.

### Proposition de sémantique

L'agressivité est un paramètre d'expérience qui peut agir sur :

- exposition maximale autorisée ;
- taille maximale d'une nouvelle position ;
- réserve de cash ;
- fréquence/cooldown ;
- contexte transmis à l'agent.

Elle ne peut jamais :

- autoriser short/margin/levier ;
- permettre de vendre plus que détenu ;
- bypasser le Risk Engine ;
- contourner une limite absolue de sécurité.

### À décider

Le mapping chiffré. Il devra être :

- monotone ;
- documenté ;
- testable ;
- versionné ;
- visible dans les logs/expériences.

---

## 11. Objectif quotidien +4 %

### Confirmé

Cible expérimentale : +4 % par jour.

### Garde-fous d'interprétation

Le système ne doit pas :

- générer un trade uniquement parce que la journée est sous +4 % ;
- augmenter automatiquement l'agressivité pour "rattraper" une perte, sauf expérience explicitement décidée ;
- masquer les jours négatifs ;
- réinitialiser une expérience pour supprimer une mauvaise période ;
- utiliser le résultat futur pour modifier une décision passée.

L'objectif est évalué comme métrique, pas comme obligation d'exécution.

---

## 12. Journal d'audit d'un cycle

### Proposé

Un cycle complet devrait pouvoir être reconstruit avec :

```text
cycle_id
timestamps
model + config
aggressiveness
market_state_id
portfolio_state_before_id
agent_input_version
decision_candidate
validation_result
risk_assessment
execution_intent
fills
costs
portfolio_state_after_id
performance_snapshot
errors/retries
```

Le stockage exact de l'entrée/sortie brute LLM est à décider en fonction de l'auditabilité, du coût de stockage et des exigences de confidentialité, mais aucun secret ne peut y apparaître.

---

## 13. Comparaison Luna / Sol

### Confirmé

Luna est le modèle initial pour raison de coût ; l'architecture doit permettre Sol par configuration.

### Protocole proposé

Pour éviter une comparaison trompeuse :

- même univers d'actifs ;
- mêmes Market States ;
- mêmes Portfolio States lorsque l'expérience le permet ;
- mêmes limites de risque ;
- mêmes coûts PAPER ;
- même mapping d'agressivité ;
- prompts/contracts versionnés ;
- reporting des coûts et latences LLM ;
- pas de sélection post-hoc des seuls cas favorables.

### À décider

Le protocole exact d'A/B ou de replay et la métrique principale de comparaison.

---

## 14. Conditions minimales avant discussion LIVE

**Hors périmètre pour l'instant**, mais les conditions candidates incluent :

- stabilité PAPER sur une durée significative ;
- journal d'audit complet ;
- modèle de coûts validé ;
- limites de risque chiffrées et testées ;
- réconciliation de portefeuille ;
- gestion robuste des erreurs réseau ;
- séparation credentials PAPER/LIVE ;
- aucune permission de retrait ;
- activation explicite ;
- revue de sécurité ;
- limites financières initiales très basses.

La satisfaction de ces points ne constitue pas automatiquement une autorisation de passage en LIVE.
