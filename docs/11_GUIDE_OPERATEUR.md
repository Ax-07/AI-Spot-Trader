# 11 — Guide opérateur

> Guide pratique du cockpit AI Spot Trader. Le parcours principal est volontairement simple ; les
> objets techniques restent disponibles dans **Réglages > Avancé**.

## 1. Ce qu'il faut savoir avant de commencer

AI Spot Trader fonctionne actuellement en **PAPER uniquement** avec Kraken comme source/exchange
initial. Le frontend est un cockpit : le moteur de trading reste dans le backend.

Principe central :

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Une sortie LLM ne déclenche jamais directement un ordre. LIVE n'est pas disponible.

## 2. Le parcours normal en cinq pages

### Accueil

Répond à la question : **que dois-je faire maintenant ?**

Le bloc **Action suivante** propose l'action cohérente avec l'état backend :

- aucune configuration : `Créer mon premier test` ;
- configuration jamais démarrée : `Démarrer` ;
- session arrêtée mais chargée : `Démarrer` ou `Tester 1 cycle` ;
- moteur en cours : `Surveiller les positions` ou `Arrêter` ;
- session historique récupérable : `Reprendre la dernière session` ;
- situation technique ambiguë : renvoi vers les réglages avancés plutôt que décision silencieuse.

### Configurer

Assistant pour créer un test PAPER sans manipuler Strategy, Revision ou Campaign.

### Positions

Affiche les positions canoniques du backend et les métriques globales de performance/exposition.

### Historique

Présente le chemin d'une décision :

```text
Agent IA -> Risk Engine -> éventuelle exécution PAPER
```

### Réglages

Regroupe :

- aide complète ;
- assistant opérateur informatif ;
- fonctions avancées du Control Plane.

## 3. Créer son premier test PAPER

Dans **Configurer** :

1. choisir `SPOT` ou `PERPETUAL` ;
2. saisir une ou plusieurs paires, par exemple `BTC/USD, ETH/USD, SOL/USD` ;
3. définir le capital PAPER ;
4. choisir Luna ou Sol ;
5. régler l'agressivité de 1 à 10 ;
6. écrire les instructions opérateur destinées à l'Agent ;
7. choisir un profil de sécurité ;
8. vérifier le résumé ;
9. cliquer sur `Créer le test` ou `Créer et démarrer`.

Toutes les paires d'un test simple doivent partager le même actif de quote/règlement, conformément
au contrat backend actuel.

## 4. SPOT et PERPETUAL

### SPOT

- pas de short ;
- pas de levier ;
- pas de marge ;
- SELL ne peut réduire qu'un actif réellement détenu et disponible.

### PERPETUAL

Périmètre actuel : contrats linéaires PAPER avec :

- LONG/SHORT ;
- marge `ISOLATED` uniquement ;
- levier déterministe configuré ;
- caps de levier, position et exposition contrôlés par Risk.

CROSS, contrats inverses et futures datés restent hors périmètre exécutable actuel.

## 5. IA : modèle, agressivité et instructions

Le choix Luna/Sol et l'agressivité font partie de la configuration immuable du test.

L'agressivité est un contexte stratégique, pas une permission de contourner Risk. Une agressivité
10/10 ne relève aucune limite déterministe.

Le texte saisi dans **Instructions opérateur** devient la partie éditable de la stratégie. Le contrat
Agent protégé du backend reste séparé et non modifiable depuis le cockpit.

Ne jamais placer de secret, clé API ou credential dans ces instructions.

## 6. Profils de sécurité

Les profils sont des **raccourcis UX** vers des valeurs explicites de `CampaignConfiguration`.
Ils ne constituent pas un second Risk Engine.

| Profil | Ordre max | Levier PERP | Position dérivée max | Exposition dérivée totale max | Buffer liquidation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prudent | 5 % du capital | 1x | 10 % du capital | 20 % du capital | 1.25 |
| Équilibré | 10 % du capital | 2x | 20 % du capital | 40 % du capital | 1.15 |
| Agressif | 20 % du capital | 3x | 35 % du capital | 70 % du capital | 1.10 |
| Personnalisé | saisi par l'opérateur | saisi | saisi | saisi | saisi |

En SPOT, les limites dérivées ne sont pas utilisées et le levier reste 1x. Les paires sélectionnées
sont ajoutées aux paires autorisées Risk par défaut. La réduction de quantité reste autorisée afin
que Risk puisse `MODIFY` une proposition trop grande plutôt que de devoir l'accepter telle quelle.

Le backend valide toujours la configuration et peut la refuser.

## 7. Paramètres avancés

Dans l'assistant, **Paramètres avancés** permet de modifier sans encombrer le parcours normal :

- cadence ;
- frais PAPER ;
- spread ;
- slippage ;
- deadlines marché/Agent/Broker ;
- champs Risk détaillés pour le profil Personnalisé.

Les validations métier restent exclusivement côté backend.

## 8. Créer le test vs créer et démarrer

### Créer le test

Le frontend orchestre les appels canoniques nécessaires pour persister la configuration mais ne
l'active pas. L'Accueil proposera ensuite de la démarrer.

### Créer et démarrer

Le frontend :

1. crée la Strategy et sa première Revision via l'API canonique ;
2. crée la Campaign immuable ;
3. effectue une activation fraîche explicite ;
4. envoie `Start` au TradingEngine backend.

Ce n'est pas une nouvelle logique métier : chaque étape utilise les routes canoniques existantes.
Si une étape intermédiaire échoue, les objets déjà persistés restent visibles dans
**Réglages > Avancé**.

## 9. Tester un seul cycle

`Tester 1 cycle` appelle la commande backend canonique `run-cycle`.

Elle exécute un cycle puis laisse le moteur `STOPPED`. C'est utile pour observer précisément :

```text
Marché -> décision Agent -> résultat Risk -> éventuel fill PAPER
```

## 10. Démarrer et arrêter

`Démarrer` lance la boucle autonome **dans le backend**. Fermer le navigateur ou le frontend ne
l'arrête pas.

`Arrêter` envoie explicitement la commande Stop au backend.

Libellés opérateur :

- `RUNNING` -> **En cours** ;
- `STOPPED` -> **Arrêté** ;
- `UNAVAILABLE` -> **Aucune session active**.

## 11. Reprendre après un redémarrage backend

Après un restart backend, aucune Campaign n'est reprise silencieusement. Si un historique compatible
existe, l'Accueil peut proposer **Reprendre la dernière session**.

La reprise reste explicite et passe par le recovery backend canonique : nouveau `paper_run_id`,
lineage `resumed_from_paper_run_id` et restauration du ledger durable. Le backend refuse une reprise
incompatible.

## 12. Lire Positions

### PERPETUAL

Le contrat backend expose directement : côté LONG/SHORT, quantité, prix d'entrée moyen, mark price,
P&L réalisé/non réalisé, notional, levier, marge et liquidation. Le cockpit les affiche sans les
recalculer.

### SPOT

Le contrat portefeuille SPOT expose actuellement seulement l'actif, la quantité et la quantité
disponible. Il n'expose pas un prix d'entrée moyen ni un P&L par position. Ces champs sont donc
laissés à `—` dans l'UI plutôt que reconstruits côté frontend.

Le P&L net global, le drawdown et l'exposition restent fournis par les analytics backend.

## 13. Lire Historique

Chaque carte de cycle regroupe autant que possible :

- décision Agent `BUY`, `SELL` ou `HOLD` ;
- résultat Risk `ALLOW`, `MODIFY` ou `REJECT` ;
- exécution et fills PAPER éventuels ;
- erreur technique éventuelle.

`HOLD` est une décision normale et auditée. `REJECT` signifie qu'aucune exécution n'est autorisée.
`MODIFY` signifie que Risk a ajusté la proposition avant exécution.

Les payloads techniques restent disponibles dans les détails à la demande.

## 14. Ce qui se trouve dans Réglages > Avancé

La surface avancée conserve les capacités historiques :

- Strategies existantes ;
- historique des StrategyRevision ;
- comparaison de révisions ;
- prompt preview ;
- Campaigns ;
- activation fraîche et recovery ;
- digests, IDs et autres informations d'audit technique.

Terminologie simplifiée utilisée ailleurs :

| Technique | Libellé opérateur |
| --- | --- |
| Strategy | Stratégie |
| StrategyRevision | Version |
| Campaign | Configuration de test |
| paper_run | Session |
| run-cycle | Tester 1 cycle |
| Start | Démarrer |
| Stop | Arrêter |

## 15. Rappels d'architecture et de sécurité

- PAPER uniquement ;
- un seul Agent IA stratégique ;
- Kraken ;
- SPOT + PERPETUAL linéaire ;
- aucune sortie LLM ne déclenche directement un ordre ;
- Risk Engine déterministe = autorité finale ;
- aucune logique Risk ou Broker dupliquée dans le frontend ;
- toutes les décisions, HOLD inclus, restent journalisées ;
- aucun secret dans le navigateur ou les fichiers versionnés ;
- LIVE reste séparé et ultérieur.
