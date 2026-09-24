# 11 — Guide opérateur

> Guide pratique du cockpit AI Spot Trader. Le backend reste le moteur de trading ; le frontend
> contrôle et visualise uniquement.

## 1. Périmètre actuel

AI Spot Trader fonctionne actuellement en **PAPER uniquement**.

Le cockpit permet de configurer et d'observer :

- SPOT ;
- PERPETUAL linéaire ;
- un seul Agent IA stratégique ;
- le Risk Engine déterministe ;
- le Broker PAPER ;
- les positions, coûts, performances et journaux durables.

**LIVE n'est pas disponible dans ce périmètre.** Tout passage au LIVE reste séparé et ultérieur.

## 2. Démarrage rapide — premier test PAPER

Pour un premier test, suivre cet ordre :

1. créer ou choisir une `Strategy` ;
2. créer une `StrategyRevision` avec le texte opérateur souhaité ;
3. créer une `Campaign` à partir de cette révision ;
4. choisir les marchés `SPOT` ou `PERPETUAL` ;
5. vérifier capital PAPER, modèle, agressivité, coûts et paramètres Risk ;
6. activer fraîchement la Campaign si elle n'a jamais été exécutée ;
7. lancer `run-cycle` pour un test isolé ou `Start` pour la boucle autonome ;
8. observer la décision Agent, le résultat Risk puis l'éventuel résultat PAPER ;
9. utiliser `Stop` pour arrêter explicitement une boucle `RUNNING`.

Pour une nouvelle configuration, commencer de préférence par `run-cycle`. Il est plus simple à
observer car un seul cycle est exécuté.

## 3. Architecture mentale

Le pipeline canonique est :

```text
Marché / contexte
      ↓
Agent IA stratégique
      ↓
BUY / SELL / HOLD proposé
      ↓
Risk Engine déterministe
      ↓
ALLOW / MODIFY / REJECT
      ↓
Broker PAPER
      ↓
Ledger / positions / performance / audit
```

Principe central :

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Une sortie LLM ne déclenche jamais directement un ordre. Le frontend ne contient ni moteur de
trading, ni logique Risk, ni Broker.

## 4. Strategy et StrategyRevision

### Strategy

Une `Strategy` est l'identité durable d'une stratégie opérateur.

Elle possède notamment un nom et peut être archivée. Le nom peut évoluer sans modifier l'historique
des révisions.

### StrategyRevision

Une `StrategyRevision` est une version **immuable** du texte opérateur.

Modifier le prompt ne remplace jamais une ancienne version : cela crée une nouvelle révision. Une
Campaign référence toujours une révision précise.

Conséquence pratique : si une Campaign utilise `r3` et que tu crées ensuite `r4`, la Campaign
existante reste liée à `r3`.

## 5. Campaign

Une `Campaign` fige l'environnement d'une expérience PAPER.

Elle contient notamment :

- Strategy et StrategyRevision ;
- modèle LLM ;
- agressivité ;
- cadence ;
- capital PAPER ;
- univers exécutable ;
- frais ;
- spread ;
- slippage ;
- paramètres PERPETUAL ;
- limites Risk ;
- deadlines de cycle.

Une Campaign est immuable. Pour changer un paramètre structurel, créer une nouvelle Campaign.

## 6. Configuration Agent

Le cockpit permet de sélectionner le modèle prévu par la configuration intégrée, notamment Luna ou
Sol.

L'agressivité est un contexte stratégique de 1 à 10. Elle influence le comportement demandé à
l'Agent, mais ne contourne jamais les limites du Risk Engine.

Le texte opérateur provient de la StrategyRevision choisie. Le contrat Agent protégé reste géré par
le backend et n'est pas éditable depuis le cockpit.

## 7. Configuration Risk

Les champs Risk du cockpit configurent le **Risk Engine backend**.

Le frontend ne reproduit pas les validations métier. Le backend peut refuser une configuration ou
une action avec une réponse 409, 422 ou 503 selon le cas.

Le Risk Engine conserve l'autorité finale sur l'exécution.

## 8. SPOT

En SPOT :

- aucun short ;
- aucun levier ;
- aucune marge ;
- BUY augmente une position ;
- SELL ne peut réduire qu'un actif réellement détenu et disponible ;
- HOLD ne crée aucune exécution.

## 9. PERPETUAL

Le périmètre actuel couvre les PERPETUAL linéaires en PAPER.

Points importants :

- marge `ISOLATED` ;
- levier PAPER configuré de manière déterministe ;
- le levier n'est jamais choisi librement par le LLM ;
- Risk contrôle les caps de levier, position, exposition et protections dérivées ;
- CROSS, contrats inverses et futures datés restent hors périmètre exécutable actuel.

## 10. Frais, spread et slippage

Les tests PAPER prennent en compte les coûts configurés.

- **Frais** : coût explicite de transaction simulé ;
- **Spread** : écart simulé entre prix de référence et prix de passage ;
- **Slippage** : dégradation supplémentaire simulée du prix d'exécution.

Le P&L net inclut ces coûts. Le P&L brut ne doit donc pas être interprété comme le résultat final du
run.

## 11. Activation fraîche et reprise

### Activation fraîche

Utiliser l'activation fraîche pour démarrer une Campaign qui ne reprend pas un run historique.

L'activation prépare explicitement un runtime backend et un nouveau contexte PAPER.

### Reprise

La reprise sert à continuer une Campaign déjà exécutée à partir d'un `paper_run` compatible.

Elle est toujours explicite. Le backend ne reprend jamais silencieusement un run après redémarrage.

La reprise crée un nouveau `paper_run_id`, conserve le lineage via
`resumed_from_paper_run_id` et restaure le ledger durable selon le recovery canonique.

## 12. run-cycle, Start et Stop

### run-cycle

`run-cycle` exécute exactement un cycle puis laisse le moteur `STOPPED`.

C'est la commande recommandée pour :

- vérifier une nouvelle Campaign ;
- observer une décision étape par étape ;
- confirmer Agent → Risk → Broker PAPER sans lancer une boucle continue.

### Start

`Start` lance la boucle autonome côté backend à la cadence définie dans la Campaign.

Le frontend n'héberge pas cette boucle. Fermer ou recharger l'interface ne l'arrête pas.

### Stop

`Stop` envoie explicitement la commande d'arrêt au moteur backend.

Utiliser cette commande pour arrêter proprement une boucle `RUNNING`.

## 13. États moteur

### STOPPED

Un runtime est disponible mais la boucle autonome ne tourne pas.

`run-cycle` ou `Start` peuvent être disponibles selon l'état courant.

### RUNNING

La boucle autonome backend est active.

Un nouveau `run-cycle` ou un nouveau `Start` est normalement désactivé pendant cet état.

### UNAVAILABLE

Aucun runtime Campaign contrôlable n'est actuellement actif.

C'est notamment l'état attendu après un restart backend avant activation ou reprise explicite.

## 14. Lire une décision Agent

Les décisions stratégiques possibles sont :

- `BUY` ;
- `SELL` ;
- `HOLD`.

`HOLD` est une décision normale : l'Agent choisit de ne pas proposer de trade sur ce cycle. Elle est
journalisée comme les autres décisions.

BUY ou SELL restent seulement des propositions tant que Risk ne les a pas traitées.

## 15. Lire le résultat Risk

Le résultat Risk est distinct de la décision Agent :

- `ALLOW` : proposition compatible avec les contraintes ;
- `MODIFY` : proposition ajustée avant exécution, par exemple quantité réduite ;
- `REJECT` : aucune exécution n'est autorisée.

Un `BUY` Agent suivi de `REJECT` ne produit donc aucun ordre PAPER.

## 16. Broker PAPER, positions et ledger

Après un résultat Risk permettant l'exécution, le chemin canonique peut créer un
`ExecutionIntent` puis une exécution PAPER.

Les positions et balances affichées dans le cockpit proviennent du backend. Le frontend ne calcule
pas un portefeuille alternatif.

Le ledger durable permet notamment le recovery explicite d'un run compatible.

## 17. Lire les performances

La vue Performance expose notamment :

- P&L brut ;
- P&L net ;
- frais ;
- coût de spread ;
- slippage ;
- drawdown maximum ;
- exposition ;
- nombre de trades ;
- BUY / SELL ;
- HOLD ;
- MODIFY / REJECT ;
- cycles en échec ;
- performance quotidienne et cumulée.

Les métriques sont calculées côté backend à partir des faits durables.

## 18. Assistant opérateur

Le chat du cockpit est informatif.

Il peut aider à expliquer le marché, le portefeuille ou un cycle historique, mais :

- il ne crée aucun trade ;
- il ne modifie pas Risk ;
- ses messages ne sont pas injectés dans les cycles autonomes.

## 19. Erreurs fréquentes

### Le moteur affiche UNAVAILABLE

Après un restart backend, aucune Campaign n'est reprise automatiquement. Activer une Campaign
fraîche ou reprendre explicitement un run compatible.

### run-cycle ou Start est désactivé

Vérifier qu'un runtime Campaign est configuré. `run-cycle` n'est pas lancé pendant `RUNNING` et
`Start` n'est pas relancé si la boucle tourne déjà.

### BUY/SELL apparaît mais aucun fill

Lire le résultat Risk. `MODIFY` peut changer la quantité ; `REJECT` bloque l'exécution. Une erreur
technique peut également interrompre le cycle avant le Broker PAPER.

### La création de Campaign est refusée

Le backend reste l'autorité de validation. Vérifier notamment univers exécutable, paires autorisées,
levier, caps dérivés et champs requis.

### Le P&L brut est supérieur au P&L net

C'est attendu lorsque frais, spread ou slippage sont non nuls.

## 20. Glossaire

| Terme | Signification opérateur |
| --- | --- |
| Strategy | identité durable d'une stratégie |
| StrategyRevision | version immuable du texte opérateur |
| Campaign | snapshot immuable d'une expérience et de sa configuration |
| paper run | session d'exécution/recovery d'une Campaign |
| HOLD | décision Agent de ne pas proposer de trade |
| ALLOW | Risk autorise la proposition compatible |
| MODIFY | Risk ajuste la proposition avant exécution |
| REJECT | Risk refuse l'exécution |
| STOPPED | runtime disponible, boucle autonome arrêtée |
| RUNNING | boucle backend autonome active |
| UNAVAILABLE | aucun runtime Campaign contrôlable actif |
| ISOLATED | mode de marge PERPETUAL utilisé dans le périmètre actuel |

## 21. Rappels de sécurité et d'architecture

- PAPER uniquement ;
- LIVE séparé et ultérieur ;
- aucune clé Kraken avec droit de retrait ;
- aucun secret dans les prompts, logs ou fichiers versionnés ;
- aucune sortie LLM ne déclenche directement un ordre ;
- le Risk Engine déterministe garde l'autorité finale ;
- le frontend peut être fermé sans arrêter le moteur backend ;
- toutes les décisions, HOLD inclus, restent journalisées.
