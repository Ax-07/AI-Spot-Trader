# 11 — Guide opérateur

> Guide pratique du cockpit AI Spot Trader. Le parcours principal est volontairement simple ; les
> objets techniques restent disponibles dans **Réglages > Avancé**.

## 1. Ce qu'il faut savoir avant de commencer

AI Spot Trader fonctionne actuellement en **PAPER uniquement** avec Kraken comme source/exchange
initial. Le frontend est un cockpit : le moteur de trading, le mark-to-market et la découverte des marchés restent dans le backend.

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

Assistant pour créer un test PAPER sans manipuler Strategy, Revision ou Campaign. Depuis le Batch 19.4, le parcours simple active la découverte dynamique : l'opérateur choisit surtout un **type de marché** et une **paire de départ/secours**, pas toute la watchlist.

### Positions

Affiche les positions canoniques du backend et leurs valeurs mark-to-market lorsque les données sont disponibles et fraîches.

### Historique

Présente le chemin d'une décision :

```text
Discovery éventuelle -> Agent IA -> Risk Engine -> éventuelle exécution PAPER
```

La discovery sélectionne des marchés à **surveiller** ; elle n'exécute aucun ordre.

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
2. saisir une paire de départ/secours, par exemple `BTC/USD` ;
3. définir le capital PAPER ;
4. choisir Luna ou Sol ;
5. régler l'agressivité de 1 à 10 ;
6. écrire les instructions opérateur destinées à l'Agent ;
7. choisir un profil de sécurité ;
8. vérifier le résumé ;
9. cliquer sur `Créer le test` ou `Créer et démarrer`.

La paire de départ n'est plus la watchlist complète. Elle joue trois rôles : bootstrap immuable de Campaign, marché de secours si la discovery est indisponible et référence de quote/règlement pour le test simple.

Le backend découvre ensuite les marchés Kraken compatibles avec ce type et cet actif de règlement. Le même Agent IA en retient périodiquement plusieurs dans une watchlist bornée.

## 5. Comment fonctionne la découverte des marchés

Le Batch 19.4 sépare trois niveaux :

```text
1. catalogue Kraken disponible
2. candidats techniquement admissibles
3. watchlist stratégique choisie par le même Agent
```

Le backend peut écarter un marché parce qu'il est indisponible, a un mauvais type/quote, possède un contrat non supporté, manque de données causales ou présente un snapshot trop ancien. Ce filtrage **ne dit pas qu'un marché est un bon ou mauvais trade**.

Le même Agent stratégique sélectionne ensuite la watchlist parmi les candidats. Une watchlist peut contenir plusieurs marchés. Chaque sélection est auditée avec les faits candidats présentés à l’Agent, ses ajouts, maintiens, retraits et rationales.

Valeurs simples par défaut : catalogue/watchlist renouvelés environ toutes les 15 minutes, refresh borné à 45 s, 24 marchés sondés au maximum, 12 candidats maximum et 6 marchés maximum dans la watchlist.

## 6. Que se passe-t-il si Kraken ou l'IA de discovery tombe ?

- si une watchlist valide existe déjà, elle est conservée ;
- sinon la paire de départ/secours reste utilisable ;
- l'erreur de discovery est auditée ;
- le backend attend la prochaine échéance de refresh au lieu de retenter la discovery à chaque cycle ;
- une panne du LLM de décision finale ou des données d'exécution reste un échec technique visible : aucun BUY/SELL/HOLD ou prix n'est inventé.

## 7. Interaction avec NORMAL / MANAGEMENT

Le Batch 19.3 reste prioritaire.

- `NORMAL` : si la watchlist doit être renouvelée, le backend effectue la discovery puis lance le cycle stratégique ;
- `MANAGEMENT` : la discovery destinée à chercher de nouvelles ouvertures est ignorée ; le même Agent ne travaille que sur les positions ouvertes.

Une position reste toujours gérable même si son marché vient d'être retiré de la watchlist :

```text
univers effectif = watchlist actuelle + toutes les positions ouvertes
```

Après un restart, une position durable peut donc être gérée avant toute nouvelle discovery.

## 8. SPOT et PERPETUAL

### SPOT

- pas de short ;
- pas de levier ;
- pas de marge ;
- SELL ne peut réduire qu'un actif réellement détenu et disponible.

Le backend expose pour une position comptablement complète : quantité, prix moyen d'entrée économique, coût restant, P&L réalisé, mark courant, valeur de marché et P&L latent.

Le mark SPOT correspond au dernier prix ticker Kraken causal retenu par le backend. Il n'est pas calculé dans le navigateur.

Si le mark manque ou devient trop ancien, le cockpit affiche `—`. Si une ancienne position ne possède pas de base de coût fiable (`accounting_complete=false`), le backend peut encore afficher sa valeur de marché, mais son P&L latent reste `—` : aucune valeur n'est inventée.

### PERPETUAL

Périmètre actuel : contrats linéaires PAPER avec LONG/SHORT, marge `ISOLATED` uniquement, levier
déterministe configuré et caps de levier/position/exposition contrôlés par Risk.

La discovery 19.4 n'autorise pas un contrat inverse ou un future daté à entrer dans l'univers exécutable.

CROSS, contrats inverses et futures datés restent hors périmètre exécutable actuel.

## 9. IA : modèle, agressivité et instructions

Le choix Luna/Sol et l'agressivité font partie de la configuration immuable du test. L'agressivité
est un contexte stratégique, pas une permission de contourner Risk. Une agressivité 10/10 ne relève
aucune limite déterministe.

Le texte saisi dans **Instructions opérateur** devient la partie éditable de la stratégie. Le contrat
Agent protégé du backend reste séparé et non modifiable depuis le cockpit. Ne jamais placer de
secret, clé API ou credential dans ces instructions.

Le **même modèle et la même stratégie** sont utilisés pour la sélection de watchlist et pour les décisions de trading. Le Batch 19.4 n'ajoute pas de second Agent.

## 10. Profils de sécurité

Les profils sont des **raccourcis UX** vers des valeurs explicites de `CampaignConfiguration`. Ils ne
constituent pas un second Risk Engine.

| Profil | Ordre max | Levier PERP | Position dérivée max | Exposition dérivée totale max | Buffer liquidation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prudent | 5 % du capital | 1x | 10 % du capital | 20 % du capital | 1.25 |
| Équilibré | 10 % du capital | 2x | 20 % du capital | 40 % du capital | 1.15 |
| Agressif | 20 % du capital | 3x | 35 % du capital | 70 % du capital | 1.10 |
| Personnalisé | saisi par l'opérateur | saisi | saisi | saisi | saisi |

En mode discovery simple, la whitelist de paires Risk peut être laissée vide : les frontières déterministes restent type de marché + quote settlement + catalogue Kraken + Risk. En profil personnalisé, une whitelist non vide peut être utilisée comme garde-fou supplémentaire ; elle restreint aussi les candidats de discovery.

Le backend valide toujours la configuration et peut la refuser.

## 11. Paramètres avancés

Dans l'assistant, **Paramètres avancés** permet de modifier sans encombrer le parcours normal :
cadence stratégique, frais PAPER, spread, slippage, deadlines et champs Risk détaillés du profil Personnalisé.
Les validations métier restent exclusivement côté backend.

Le mark-to-market backend possède en plus des paramètres techniques de processus par environnement :

```text
AI_SPOT_TRADER_PAPER_MARK_TO_MARKET_CADENCE_SECONDS=5
AI_SPOT_TRADER_PAPER_DERIVATIVE_MARK_TO_MARKET_CADENCE_SECONDS=15
AI_SPOT_TRADER_PAPER_MARK_TO_MARKET_TIMEOUT_SECONDS=5
AI_SPOT_TRADER_PAPER_MARK_TO_MARKET_STALE_AFTER_SECONDS=30
```

Ils ne déclenchent aucun appel IA.

La configuration avancée historique du Control Plane peut toujours créer une Campaign statique en omettant `market_discovery`. Ce mode reste utile pour les tests reproductibles sur un univers fixe.

## 12. Créer, démarrer et tester un cycle

`Créer le test` persiste la configuration via les routes canoniques sans l'activer.

`Créer et démarrer` crée Strategy/Revision/Campaign puis effectue une activation fraîche explicite et
envoie `Start` au TradingEngine backend.

`Tester 1 cycle` appelle `run-cycle`, exécute un cycle puis laisse le moteur `STOPPED`. Si la Campaign dynamique est en `NORMAL` et que la watchlist est due, ce cycle peut aussi déclencher son renouvellement avant la sélection de marché.

## 13. Démarrer, arrêter et reprendre

`Démarrer` lance la boucle autonome **dans le backend**. Fermer le navigateur ou le frontend ne
l'arrête pas. `Arrêter` envoie explicitement Stop.

Le mark-to-market SPOT/PERPETUAL appartient aussi au runtime backend actif : il ne dépend pas de la page Positions ni du navigateur.

Après un restart backend, aucune Campaign n'est reprise silencieusement. La reprise reste explicite
et passe par le recovery canonique ; le backend refuse une session incompatible.

Pour une Campaign dynamique, la watchlist n'est pas restaurée comme décision stratégique à rejouer. Les positions sont restaurées, restent gérables, puis la watchlist est reconstruite quand un cycle `NORMAL` a besoin d'un refresh.

## 14. Lire Positions

### Vue globale

Lorsque les données sont disponibles, le backend fournit directement :

- cash disponible ;
- valeur de marché SPOT ;
- P&L latent SPOT ;
- equity ;
- exposition courante.

Une valeur `—` signifie que la donnée canonique n'est pas disponible ou n'est plus assez fraîche ; ce n'est pas zéro.

### PERPETUAL

Le contrat backend expose directement côté LONG/SHORT, quantité, prix d'entrée moyen, mark price,
P&L, notional, levier, marge et liquidation. Le cockpit les affiche sans les recalculer.

### SPOT

Le backend expose directement quantité/disponible, prix moyen d'entrée, mark/timestamp, valeur de position, coût restant, P&L réalisé/latent et complétude de valorisation. Le cockpit n'effectue aucun calcul financier parallèle.

## 15. Lire Historique

Chaque carte de cycle regroupe autant que possible : décision Agent `BUY`, `SELL` ou `HOLD`, résultat
Risk `ALLOW`, `MODIFY` ou `REJECT`, état `Exécuté` / `Non exécuté`, fills PAPER et erreur technique.

Pour une Campaign dynamique, `market_selection_input.market_discovery` contient aussi la trace technique de la watchlist : `REFRESHED`, `CACHE_REUSED`, `FALLBACK` ou `SKIPPED_MANAGEMENT`, marchés ajoutés/maintenus/retirés et rationale de sélection. L'exposition produit dédiée de ces informations est prévue pour le Batch 19.5 ; en 19.4 elles restent auditables dans les détails techniques.

## 16. Réglages > Avancé

La surface avancée conserve Strategies, historique des StrategyRevision, comparaison de révisions,
prompt preview, Campaigns, activation fraîche, recovery, digests et IDs. Elle reste secondaire.

## 17. Rappels d'architecture et de sécurité

- PAPER uniquement ;
- un seul Agent IA stratégique ;
- Kraken ;
- SPOT + PERPETUAL linéaire ;
- aucune sélection de watchlist ni sortie BUY/SELL/HOLD ne déclenche directement un ordre ;
- Risk Engine déterministe = autorité finale ;
- aucune logique Risk, Broker, discovery ou mark-to-market canonique dupliquée dans le frontend ;
- toutes les décisions, HOLD inclus, restent journalisées ;
- aucun secret dans le navigateur ou les fichiers versionnés ;
- LIVE reste séparé et ultérieur.
