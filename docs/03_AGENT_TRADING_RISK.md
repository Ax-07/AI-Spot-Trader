# 03 — Agent, trading et Risk

## 1. Principe d'autorité

**L'Agent propose. Le Risk Engine autorise, modifie ou refuse.**

L'Agent est stratégique. Risk, Broker, comptabilité, monitoring et contraintes structurelles restent déterministes.

## 2. Agent unique aujourd'hui

Le pipeline intégré possède deux phases stratégiques liées au cycle :

```text
MarketSelectionInput -> select_market() -> MarketSelection
AgentInput           -> generate_decision() -> DecisionCandidate
```

Il s'agit du même `OpenAIDecisionProvider`, du même modèle et du même rôle stratégique.

La sélection peut utiliser des tools publics read-only. Après acquisition du `MarketState` exécutable, la décision finale réutilise les traces de sélection sans relancer de nouveaux tools dans le chemin causal multi-marchés.

## 3. Évolution planifiée : trois rythmes, toujours un seul Agent

Le cadrage futur sépare :

1. monitoring/mark-to-market déterministe — **sans LLM** ;
2. décision stratégique de trading — **même Agent IA** ;
3. découverte/révision de watchlist — **même Agent IA**, cadence plus lente.

Cette séparation ne crée pas un second agent. La découverte périodique est une nouvelle tâche du même rôle stratégique.

## 4. Contrat Agent protégé

Le contrat applicatif doit continuer d'imposer notamment :

- PAPER uniquement ;
- sorties structurées BUY/SELL/HOLD ;
- décision limitée au contexte exécutable fourni ;
- SPOT sans short/levier/marge ;
- sémantique LONG/SHORT PERPETUAL ;
- levier et `reduce_only` déterministes ;
- aucune invention de faits absents de l'input/tools ;
- aucun LLM -> Broker/Kraken ;
- aucun tool -> Broker/Risk ;
- Risk final ;
- respect des schémas structurés.

Les nouveaux modes devront étendre ce contrat sans créer de chemin d'exécution parallèle.

## 5. Rationale et explicabilité

Le `DecisionCandidate` contient déjà un `rationale` stratégique issu de la réponse structurée Agent. Le prompt précise que ce champ est explicatif uniquement et ne constitue jamais une instruction d'exécution.

Cible UI :

```text
Pourquoi l'IA ?
  -> rationale stratégique enregistré

Risk Engine
  -> ALLOW / MODIFY / REJECT
  -> raisons déterministes enregistrées
```

Il est interdit de présenter le `rationale` comme une explication de l'algorithme interne du modèle ou comme une chaîne de pensée cachée. Il s'agit uniquement de l'explication explicitement produite et persistée.

## 6. SPOT

`BUY` acquiert la base. `SELL` réduit un actif détenu. Risk vérifie notamment :

- symbole/type ;
- whitelist ;
- chronologie/fraîcheur ;
- cash quote ;
- position disponible ;
- max notional ;
- coûts PAPER.

Aucun short, leverage ou margin SPOT.

### Évolution comptable

L'Agent devra recevoir un `PortfolioState` enrichi permettant de connaître pour chaque position SPOT, au minimum lorsque disponible :

- quantité ;
- prix/coût moyen d'entrée ;
- P&L latent au mark courant ;
- P&L réalisé ;
- coûts pertinents.

Ces valeurs seront calculées par le backend canonique et non par le LLM ou le frontend.

## 7. PERPETUAL

`BUY` exprime/augmente LONG ou réduit SHORT. `SELL` exprime/augmente SHORT ou réduit LONG.

Risk garde le contrôle de :

- contrat linéaire supporté ;
- taille minimale/maximale ;
- levier configuré et cap de levier ;
- marge disponible ;
- notional de position ;
- exposition dérivée totale ;
- buffer de liquidation ;
- `reduce_only` ;
- anti-reversal accidentel ;
- marge `ISOLATED`.

Le LLM ne choisit jamais le levier effectif.

Le monitoring déterministe pourra actualiser mark, P&L latent, marge, liquidation et funding sans changer la décision stratégique.

## 8. Mode gestion quand aucune nouvelle exposition n'est possible

Le backend peut constater de manière déterministe qu'une nouvelle exposition est interdite par les contraintes actuelles.

Dans ce cas :

- l'Agent ne doit pas rechercher de nouvelles ouvertures ;
- son contexte stratégique doit porter sur les positions ouvertes ;
- HOLD, réduction et clôture restent autorisés ;
- une proposition qui augmenterait l'exposition reste soumise/refusée par les règles déterministes applicables ;
- le backend ne choisit jamais la position à fermer à la place de l'Agent ;
- le retour au mode normal est automatique lorsque la capacité revient.

### Mesure de l'économie IA

Prévoir des métriques auditables permettant au minimum de comparer :

- nombre de phases/appels IA évités ;
- nombre de tool calls évités ;
- tokens input/output évités si l'API fournisseur les expose de manière fiable ;
- durée passée en mode gestion.

La méthode exacte de calcul du « token saving » reste **à décider** selon les métriques réellement disponibles auprès du fournisseur.

## 9. Découverte périodique des marchés

Le backend fournit un univers techniquement admissible ; le même Agent produit la sélection stratégique/watchlist.

Le déterministe peut filtrer :

- marchés actifs/tradables ;
- quote/règlement compatible ;
- SPOT / PERPETUAL linéaire supportés ;
- caractéristiques de contrat compatibles ;
- contraintes structurelles et Risk connues.

Le déterministe ne doit pas calculer un score d'opportunité qui remplace la sélection stratégique de l'Agent.

Le mode manuel reste nécessaire pour la reproductibilité.

## 10. Watchlist et positions ouvertes

Invariant cible :

```text
univers surveillé = watchlist IA actuelle + toutes les positions ouvertes
```

Une position ouverte ne disparaît donc jamais du monitoring à cause d'une révision de watchlist.

La watchlist doit être versionnée/auditée avec au minimum timestamp, univers admissible de référence, sélection résultante et cause de révision. Le niveau de détail exact des traces/tokens conservés reste soumis aux règles de confidentialité et de coût.

## 11. Recovery

Le recovery restaure un `PortfolioState` durable et ne réexécute jamais sélection, Agent, Risk, Broker ou Fill.

Les futures extensions devront également restaurer de façon cohérente :

- comptabilité SPOT enrichie ;
- état de positions nécessaire au mark-to-market ;
- référence de watchlist/version lorsque nécessaire pour l'audit.

Il ne faut pas reconstruire post-hoc une décision ou un coût moyen à partir d'informations futures.

## 12. Interdits maintenus

- aucun LIVE ;
- aucun second Agent ;
- aucun scanner/ranking déterministe choisissant le trade ;
- aucun ordre direct LLM/tool ;
- aucune modification post-hoc d'une décision ;
- aucun look-ahead ;
- aucune obligation de trader ;
- aucun calcul stratégique déporté dans le frontend.

Le séquencement détaillé est documenté dans `docs/11_AMELIORATIONS_PLANIFIEES.md`.
