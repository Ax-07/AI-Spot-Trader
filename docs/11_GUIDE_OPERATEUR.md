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

Le bloc **Action suivante** propose l'action cohérente avec l'état backend : création d'un premier
test, démarrage, cycle unique, surveillance, arrêt, reprise explicite ou renvoi vers le mode avancé
lorsqu'une décision automatique serait ambiguë.

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

Regroupe l'apparence, l'aide complète, l'assistant opérateur informatif et les fonctions avancées du
Control Plane.

## 3. Apparence : clair, sombre ou système

Le cockpit propose trois modes :

- **Clair** : thème clair forcé ;
- **Sombre** : thème sombre forcé ;
- **Système** : suit le thème du système d'exploitation.

Le sélecteur est disponible dans la barre supérieure et dans **Réglages > Apparence**. Le choix est
conservé localement par `next-themes`.

Les couleurs d'état sont accompagnées de texte ou de signes. Par exemple, un P&L positif affiche
`+`, un P&L négatif affiche `−`, et l'Historique indique explicitement `Exécuté` ou `Non exécuté`.

## 4. Créer son premier test PAPER

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

## 5. SPOT et PERPETUAL

### SPOT

- pas de short ;
- pas de levier ;
- pas de marge ;
- SELL ne peut réduire qu'un actif réellement détenu et disponible.

### PERPETUAL

Périmètre actuel : contrats linéaires PAPER avec LONG/SHORT, marge `ISOLATED` uniquement, levier
déterministe configuré et caps de levier/position/exposition contrôlés par Risk.

CROSS, contrats inverses et futures datés restent hors périmètre exécutable actuel.

## 6. IA : modèle, agressivité et instructions

Le choix Luna/Sol et l'agressivité font partie de la configuration immuable du test. L'agressivité
est un contexte stratégique, pas une permission de contourner Risk. Une agressivité 10/10 ne relève
aucune limite déterministe.

Le texte saisi dans **Instructions opérateur** devient la partie éditable de la stratégie. Le contrat
Agent protégé du backend reste séparé et non modifiable depuis le cockpit. Ne jamais placer de
secret, clé API ou credential dans ces instructions.

## 7. Profils de sécurité

Les profils sont des **raccourcis UX** vers des valeurs explicites de `CampaignConfiguration`. Ils ne
constituent pas un second Risk Engine.

| Profil | Ordre max | Levier PERP | Position dérivée max | Exposition dérivée totale max | Buffer liquidation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prudent | 5 % du capital | 1x | 10 % du capital | 20 % du capital | 1.25 |
| Équilibré | 10 % du capital | 2x | 20 % du capital | 40 % du capital | 1.15 |
| Agressif | 20 % du capital | 3x | 35 % du capital | 70 % du capital | 1.10 |
| Personnalisé | saisi par l'opérateur | saisi | saisi | saisi | saisi |

Le backend valide toujours la configuration et peut la refuser.

## 8. Paramètres avancés

Dans l'assistant, **Paramètres avancés** permet de modifier sans encombrer le parcours normal :
cadence, frais PAPER, spread, slippage, deadlines et champs Risk détaillés du profil Personnalisé.
Les validations métier restent exclusivement côté backend.

## 9. Créer, démarrer et tester un cycle

`Créer le test` persiste la configuration via les routes canoniques sans l'activer.

`Créer et démarrer` crée Strategy/Revision/Campaign puis effectue une activation fraîche explicite et
envoie `Start` au TradingEngine backend.

`Tester 1 cycle` appelle `run-cycle`, exécute un cycle puis laisse le moteur `STOPPED`.

## 10. Démarrer, arrêter et reprendre

`Démarrer` lance la boucle autonome **dans le backend**. Fermer le navigateur ou le frontend ne
l'arrête pas. `Arrêter` envoie explicitement Stop.

Après un restart backend, aucune Campaign n'est reprise silencieusement. La reprise reste explicite
et passe par le recovery canonique ; le backend refuse une session incompatible.

## 11. Lire Positions

### PERPETUAL

Le contrat backend expose directement côté LONG/SHORT, quantité, prix d'entrée moyen, mark price,
P&L, notional, levier, marge et liquidation. Le cockpit les affiche sans les recalculer. Le P&L est
aussi préfixé par `+` ou `−` pour ne pas dépendre uniquement du rouge/vert.

### SPOT

Le contrat portefeuille SPOT expose actuellement seulement l'actif, la quantité et la quantité
disponible. Il n'expose pas un prix d'entrée moyen ni un P&L par position. Ces champs restent donc à
`—` au lieu d'être reconstruits côté frontend.

## 12. Lire Historique

Chaque carte de cycle regroupe autant que possible : décision Agent `BUY`, `SELL` ou `HOLD`, résultat
Risk `ALLOW`, `MODIFY` ou `REJECT`, état `Exécuté` / `Non exécuté`, fills PAPER et erreur technique.
Les payloads techniques restent derrière **Détails techniques**.

## 13. Réglages > Avancé

La surface avancée conserve Strategies, historique des StrategyRevision, comparaison de révisions,
prompt preview, Campaigns, activation fraîche, recovery, digests et IDs. Elle reste secondaire.

## 14. Rappels d'architecture et de sécurité

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
