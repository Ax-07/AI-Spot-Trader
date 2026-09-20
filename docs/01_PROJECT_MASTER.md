# 01 — Project Master

## 1. Rôle de ce document

Ce document est la spécification fonctionnelle et architecturale principale d'**AI Spot Trader**. Il décrit les invariants confirmés, les interfaces conceptuelles et les objectifs du produit. Les détails plus spécialisés sont complétés par :

- [`02_ARCHITECTURE_TECHNIQUE.md`](02_ARCHITECTURE_TECHNIQUE.md) ;
- [`03_AGENT_TRADING_RISK.md`](03_AGENT_TRADING_RISK.md) ;
- [`09_ROADMAP_DEVELOPPEMENT.md`](09_ROADMAP_DEVELOPPEMENT.md) ;
- [`10_DECISIONS_ET_CHANGELOG.md`](10_DECISIONS_ET_CHANGELOG.md).

### Statuts utilisés

- **Confirmé** : décision déjà prise et à respecter.
- **Proposé** : option de conception recommandée, modifiable avant implémentation.
- **À décider** : choix volontairement laissé ouvert.
- **Hors périmètre pour l'instant** : non prévu dans les premières versions.

---

## 2. Vision

**Confirmé.** AI Spot Trader est une application expérimentale de trading crypto **SPOT** dont la décision stratégique est confiée à **un agent IA unique**. Le système doit fournir à cet agent un contexte de marché et de portefeuille fiable, appliquer des contraintes déterministes de risque, simuler les exécutions de manière honnête en PAPER et mesurer les résultats sans biais rétrospectif.

Le projet n'a pas vocation à devenir silencieusement un bot algorithmique classique dans lequel une somme d'indicateurs déterministes décide directement d'acheter ou vendre. Les indicateurs, statistiques et règles déterministes fournissent du contexte et imposent des garde-fous ; l'agent IA conserve la décision stratégique.

La cible expérimentale annoncée est **+4 % de rendement quotidien**. Il s'agit d'un objectif de recherche très agressif, **jamais d'une garantie ni d'une hypothèse de rendement attendu**. Le système doit rapporter honnêtement les jours où cette cible n'est pas atteinte et ne doit pas forcer des trades pour la poursuivre.

---

## 3. Objectifs produit

### 3.1 Objectifs confirmés

- Exécuter une boucle autonome de décision `BUY`, `SELL` ou `HOLD`.
- Utiliser Kraken comme premier exchange.
- Opérer exclusivement en SPOT.
- Interdire short, levier, margin, futures et perpetuals.
- Ne jamais vendre un actif non détenu.
- Utiliser GPT-5.6 Luna pour les premiers essais afin de réduire les coûts.
- Pouvoir sélectionner GPT-5.6 Sol ultérieurement par configuration, sans réécrire la logique métier.
- Faire valider toute décision tradable par un Risk Engine déterministe avant toute exécution.
- Commencer exclusivement en PAPER.
- Prendre en compte frais, spread et slippage.
- Journaliser toutes les décisions, y compris `HOLD`.
- Séparer strictement PAPER et un éventuel LIVE futur.
- Fournir un cockpit frontend sans rendre le moteur de trading dépendant de l'interface.

### 3.2 Non-objectifs immédiats

**Hors périmètre pour l'instant :**

- trading sur plusieurs exchanges ;
- short, margin, levier, futures, perpetuals ou options ;
- stratégie multi-agents ;
- haute fréquence / HFT ;
- copy trading ;
- custody ou retraits ;
- application mobile native ;
- optimisation Rust avant mesure d'un besoin réel ;
- passage automatique en LIVE.

---

## 4. Périmètre V0 / V1

### V0 — socle expérimental

**Proposé comme définition de V0.**

V0 est atteinte lorsque le backend peut, en PAPER et sans frontend obligatoire :

1. recevoir des données publiques Kraken ;
2. construire un `MarketState` cohérent ;
3. maintenir un `PortfolioState` PAPER ;
4. interroger l'agent Luna avec un contrat structuré ;
5. obtenir une décision structurée `BUY` / `SELL` / `HOLD` ;
6. soumettre cette décision au Risk Engine ;
7. simuler l'exécution autorisée via le Paper Broker ;
8. mettre à jour portefeuille, P&L et journal ;
9. répéter la boucle de manière autonome ;
10. exposer assez d'état via FastAPI pour être inspectée et contrôlée.

Le système doit pouvoir fonctionner sans frontend actif.

### V1 — cockpit et expérimentation instrumentée

**Proposé comme définition de V1.**

V1 ajoute notamment :

- cockpit Next.js/shadcn ;
- historique des décisions et exécutions ;
- analytics P&L, drawdown, coûts et exposition ;
- réglage contrôlé de l'agressivité ;
- comparaisons Luna/Sol sur des protocoles reproductibles ;
- outils de replay/évaluation sur données enregistrées, sans look-ahead ;
- préparation des prérequis de sécurité et d'exploitation pour évaluer un futur LIVE.

Le LIVE lui-même n'est pas une condition de V1.

---

## 5. Principes architecturaux

### 5.1 Principes confirmés

1. **Backend = application de trading.** Il porte la boucle autonome, l'état, les règles de risque, les intégrations et la persistance.
2. **Frontend = cockpit.** Il contrôle et visualise, mais n'héberge aucune logique nécessaire à la continuité du moteur.
3. **Indépendance du frontend.** Fermer, recharger ou redémarrer le frontend ne doit jamais arrêter le moteur de trading.
4. **Interfaces aux frontières externes.** Kraken et le fournisseur LLM sont masqués derrière des interfaces dédiées.
5. **Asynchrone côté backend.** Python + `asyncio`.
6. **API de contrôle.** FastAPI + Pydantic.
7. **REST et WebSocket.** REST pour commandes/états ponctuels ; WebSocket pour flux de cockpit quand utile.
8. **Risk Engine final.** Le LLM ne parle jamais directement à l'exchange/broker.
9. **PAPER par défaut.** Aucun chemin LIVE implicite.
10. **PostgreSQL cible.** Le schéma exact et l'ORM éventuel sont à décider.
11. **Pas de Rust sans besoin mesuré.**

### 5.2 Flux de confiance

Flux logique confirmé :

```text
Kraken public data
        |
        v
Market State ------+
                   |
Portfolio State ---+--> Agent IA --> DecisionCandidate
                                      |
                                      v
                               Risk Engine
                               /    |     \
                           reject  modify  allow
                              \      |      /
                               v     v     v
                               Execution Intent
                                      |
                                      v
                               Paper Broker
                                      |
                          +-----------+-----------+
                          v                       v
                  Portfolio State             Journal
```

En LIVE futur, un broker/exchange adapter LIVE pourrait remplacer le Paper Broker derrière une interface dédiée, mais uniquement via une activation explicite et des contrôles supplémentaires.

---

## 6. Architecture backend / frontend

### Backend

**Confirmé :** Python, `asyncio`, FastAPI, Pydantic.

Responsabilités :

- ingestion de marché ;
- normalisation des données ;
- création du `MarketState` ;
- gestion du `PortfolioState` ;
- orchestration de la boucle ;
- appel à l'agent ;
- validation du contrat de sortie ;
- Risk Engine ;
- Paper Broker ;
- P&L et analytics ;
- persistance et audit ;
- API de contrôle ;
- santé opérationnelle.

### Frontend

**Confirmé :** Next.js + TypeScript + shadcn/ui + Tailwind CSS.

Responsabilités :

- état du moteur ;
- marché suivi ;
- portefeuille PAPER ;
- décisions récentes ;
- ordres/fills simulés ;
- P&L / drawdown / coûts ;
- réglages autorisés ;
- démarrage/arrêt contrôlé de la boucle si l'API le permet ;
- diagnostic lisible des erreurs et de la fraîcheur des données.

Le frontend ne doit pas contenir la stratégie de trading ni devenir l'ordonnanceur du moteur.

---

## 7. Boucle de trading

### 7.1 Séquence conceptuelle confirmée

À chaque cycle :

1. vérifier la santé et la fraîcheur des données ;
2. figer un `MarketState` daté ;
3. figer un `PortfolioState` daté ;
4. fournir ces états, les paramètres autorisés et le contexte nécessaire à l'agent ;
5. recevoir une sortie LLM ;
6. parser et valider strictement la sortie via un modèle Pydantic ;
7. si la sortie est invalide, ne pas exécuter d'ordre et journaliser l'échec ;
8. soumettre toute décision à conséquence financière au Risk Engine ;
9. autoriser, réduire/modifier ou refuser l'intention ;
10. en PAPER, simuler l'exécution avec coûts ;
11. mettre à jour le portefeuille ;
12. calculer les métriques ;
13. journaliser le cycle complet, y compris `HOLD`, refus et erreurs.

### 7.2 Points à décider

- cadence du cycle ;
- déclenchement temporel, événementiel ou hybride ;
- nombre de paires analysées par cycle ;
- budget maximal de latence LLM ;
- comportement lors d'une donnée de marché trop ancienne ;
- politique de retry du LLM et de Kraken ;
- durée maximale d'un ordre PAPER non rempli si une simulation de carnet est retenue.

---

## 8. Market State

Le `MarketState` est le snapshot déterministe présenté à l'agent.

### 8.1 Contenu minimal proposé

- identifiant de snapshot ;
- timestamp de construction ;
- paire / symbole canonique ;
- dernier prix pertinent ;
- bid / ask et spread lorsque disponibles ;
- données de bougies pour les horizons retenus ;
- volume ;
- fraîcheur et qualité de données ;
- indicateurs/statistiques déterministes sélectionnés ;
- informations nécessaires au calcul des coûts et contraintes.

### 8.2 Principe confirmé

Les indicateurs ne doivent pas devenir silencieusement une stratégie. Ils décrivent le contexte ; ils ne déclenchent pas eux-mêmes `BUY` ou `SELL`.

### 8.3 À décider

- horizons de bougies ;
- taille des fenêtres ;
- indicateurs exacts ;
- profondeur de carnet nécessaire ou non ;
- univers initial de paires ;
- normalisation des symboles Kraken.

---

## 9. Portfolio State

Le `PortfolioState` est la vue canonique de ce que le système considère comme détenu et disponible.

### 9.1 Contenu minimal proposé

- timestamp ;
- valeur de référence du portefeuille ;
- soldes cash ;
- positions par actif ;
- quantité disponible et éventuellement réservée ;
- coût moyen / base de coût si retenu ;
- prix de marquage ;
- P&L réalisé et non réalisé ;
- exposition par actif et totale ;
- frais cumulés ;
- drawdown courant ;
- mode `PAPER` ou `LIVE`.

### 9.2 Invariant confirmé

Une décision `SELL` ne peut jamais produire une vente supérieure à la quantité réellement détenue et disponible.

En PAPER, le `PortfolioState` du Paper Broker est l'autorité d'exécution. En LIVE futur, l'état local devra être réconcilié avec Kraken.

---

## 10. Interface de l'agent IA

### 10.1 Rôle confirmé

L'agent prend la décision stratégique à partir d'un contexte préparé par le backend. Il ne reçoit jamais de secrets et ne possède aucun accès direct à Kraken.

L'implémentation doit passer par une abstraction de fournisseur afin que le modèle puisse être changé par configuration.

### 10.2 Modèle initial

- **Confirmé :** GPT-5.6 Luna pour les premiers tests.
- **Confirmé :** GPT-5.6 Sol doit être sélectionnable ultérieurement par configuration.
- **À décider :** paramètres exacts du modèle, budget tokens, stratégie de retry, éventuels outils autorisés à l'agent.

### 10.3 Entrée générale proposée

```text
AgentInput
- cycle_id
- timestamp
- market_state
- portfolio_state
- risk_context
- aggressiveness (1..10)
- experiment_context
- policy/version metadata
```

Le `risk_context` peut exposer des contraintes utiles à la décision, mais l'autorité reste le Risk Engine.

---

## 11. Format général des décisions

### 11.1 Champs confirmés

Toute décision possède au minimum une action :

```text
action = BUY | SELL | HOLD
```

### 11.2 Contrat proposé

```text
DecisionCandidate
- decision_id
- cycle_id
- timestamp
- action
- symbol
- sizing_intent
- rationale
- confidence
- horizon
- metadata
```

Les champs autres que `action` ne sont pas encore tous figés. Le contrat final devra être un modèle Pydantic strict, versionné et validable.

### 11.3 Principes de validation

- sortie non parseable => aucune exécution ;
- symbole non autorisé => refus ;
- `SELL` sans position => refus ;
- taille invalide => refus ou réduction déterministe selon politique ;
- décision `HOLD` => journalisée comme toute autre décision ;
- aucune donnée textuelle du LLM ne devient directement une commande Kraken.

---

## 12. Risk Engine

### 12.1 Autorité confirmée

Le Risk Engine déterministe est **l'autorité finale** avant exécution.

Il peut :

- **ALLOW** : accepter l'intention ;
- **MODIFY** : réduire ou normaliser l'intention dans des limites sûres ;
- **REJECT** : refuser l'intention.

Il ne doit pas inventer une nouvelle stratégie de marché ; sa fonction est de faire respecter les contraintes de sécurité, d'exposition et de validité.

### 12.2 Contraintes attendues

**Proposé, à chiffrer ultérieurement :**

- actifs/paires autorisés ;
- taille maximale par ordre ;
- exposition maximale par actif ;
- exposition totale maximale ;
- cash minimum ;
- quantité disponible avant `SELL` ;
- limites de drawdown/perte ;
- état des données et fraîcheur ;
- garde-fous de fréquence / turnover ;
- éventuel cooldown ;
- limites spécifiques au mode PAPER/LIVE.

Les valeurs numériques ne sont pas décidées dans ce batch documentaire.

---

## 13. Paper Trading

### 13.1 Confirmé

Les premières versions sont exclusivement PAPER.

Le Paper Broker doit :

- recevoir uniquement des intentions déjà validées par le Risk Engine ;
- simuler les fills sans look-ahead ;
- comptabiliser les frais ;
- tenir compte du spread ;
- modéliser le slippage ;
- refuser les ventes non couvertes par une position ;
- produire des événements d'exécution auditables ;
- mettre à jour le `PortfolioState`.

### 13.2 À décider

- modèle de fill : immédiat au bid/ask, carnet simulé, ou autre ;
- modèle de slippage ;
- barème de frais Kraken utilisé et sa configuration ;
- traitement des ordres partiellement remplis ;
- minimums notionnels / précision / arrondis ;
- capital initial et devise de référence.

Le modèle PAPER devra être documenté précisément avant toute comparaison de performance.

---

## 14. Agressivité 1–10

### 14.1 Confirmé

L'utilisateur peut configurer un niveau d'agressivité de **1 à 10**.

### 14.2 Sens fonctionnel proposé

Le niveau doit agir comme un paramètre explicite et traçable qui influence le comportement autorisé, sans court-circuiter le Risk Engine. Une agressivité plus élevée peut, selon les règles retenues, permettre davantage d'exposition, une taille de position supérieure ou une tolérance de fréquence plus élevée.

Principes :

- `1` = profil expérimental le plus conservateur autorisé ;
- `10` = profil expérimental le plus agressif autorisé ;
- le sens doit être monotone et documenté ;
- aucune valeur ne permet de violer les invariants SPOT, les soldes disponibles ou les limites de sécurité absolues ;
- le mapping exact doit être versionné et mesuré.

### 14.3 À décider

Les plafonds chiffrés et la répartition précise entre paramètres de risque, contexte agent et sizing.

---

## 15. Cible quotidienne +4 %

### 15.1 Confirmé

La cible expérimentale est **+4 % de rendement quotidien**.

### 15.2 Interprétation obligatoire

- objectif expérimental, pas promesse ;
- métrique à observer, pas règle qui force à trader ;
- performance affichée en brut **et** net ;
- les coûts doivent rester visibles ;
- aucune sélection rétrospective des journées ;
- aucun changement post-hoc d'une décision ;
- aucune utilisation de données futures ;
- les jours négatifs ou sous la cible restent dans les résultats.

### 15.3 À décider

- frontière exacte d'une journée de trading ;
- devise de référence ;
- règle de calcul du capital de début de journée ;
- traitement des dépôts/retraits si un LIVE futur les introduit.

---

## 16. Observabilité et journalisation

### 16.1 Confirmé

Toutes les décisions sont journalisées, y compris `HOLD`.

### 16.2 Événements à conserver — proposé

Pour chaque cycle :

- `cycle_id` et timestamps ;
- version de l'application ;
- version/configuration de l'agent ;
- modèle sélectionné ;
- identifiants des snapshots de marché et portefeuille ;
- décision brute utile à l'audit, sous réserve de ne jamais contenir de secret ;
- décision structurée ;
- résultat du Risk Engine et raisons ;
- intention finale ;
- événements Paper Broker ;
- frais/spread/slippage estimés ;
- P&L et exposition après cycle ;
- erreurs, retries et latences ;
- consommation/coût LLM lorsqu'ils sont disponibles.

### 16.3 Principes

- logs structurés ;
- corrélation par identifiants stables ;
- timestamps non ambigus ;
- séparation événements métier / logs techniques ;
- jamais de clé API, token ou secret dans les logs ou prompts.

La rétention et le niveau exact de verbosité restent à décider.

---

## 17. Stockage

### 17.1 Confirmé

**PostgreSQL** est la base cible.

### 17.2 Données candidates

**Proposé :**

- cycles de décision ;
- snapshots ou références de `MarketState` ;
- snapshots de `PortfolioState` ;
- décisions agent ;
- résultats Risk Engine ;
- ordres et fills PAPER ;
- métriques P&L ;
- configuration/version d'expérience ;
- erreurs et événements d'exploitation utiles.

### 17.3 À décider

- ORM / couche d'accès ;
- migrations ;
- granularité de conservation des données de marché ;
- stratégie de rétention/archivage ;
- stockage séparé éventuel des séries temporelles volumineuses.

---

## 18. Sécurité des secrets

### 18.1 Confirmé

- aucun secret dans Git ;
- aucun secret dans les prompts ;
- aucun secret dans les logs ;
- aucun secret dans les fichiers de configuration versionnés ;
- aucune clé Kraken avec droit de retrait ;
- fournisseur LLM et Kraken derrière des interfaces dédiées ;
- LIVE futur avec credentials et configuration séparés du PAPER.

### 18.2 Proposé

- configuration par variables d'environnement ou gestionnaire de secrets selon l'environnement ;
- fichiers `.env.example` sans valeurs sensibles ;
- validation au démarrage des paramètres nécessaires ;
- masquage/redaction centralisé des données sensibles dans les logs.

Le mécanisme précis de gestion de secrets en déploiement n'est pas encore décidé.

---

## 19. Séparation PAPER / LIVE

### 19.1 Confirmé

Le passage en LIVE doit être **explicite, séparé et ultérieur**.

Le mode courant ne doit jamais être déduit implicitement d'une clé présente ou d'un environnement.

### 19.2 Garde-fous proposés pour un futur LIVE

- enum explicite de mode ;
- credentials distincts ;
- adaptateur d'exécution distinct ;
- bannière/état très visible dans le cockpit ;
- commande d'activation volontaire ;
- limites de risque dédiées ;
- vérification qu'aucun droit de retrait n'existe ;
- tests d'intégration et checklist avant activation.

Aucun de ces éléments n'autorise le LIVE tant qu'une décision architecturale dédiée n'a pas été prise.

---

## 20. Stratégie de tests

### 20.1 Principes confirmés

- ne jamais présenter un test non exécuté comme réussi ;
- tester les composants déterministes indépendamment du LLM et de Kraken ;
- ne pas nécessiter le frontend pour tester le moteur ;
- éviter toute exécution LIVE dans les suites automatiques.

### 20.2 Pyramide proposée

1. **Unitaires** : modèles, calculs de coûts, Portfolio State, Risk Engine, sizing, P&L.
2. **Contrats** : schémas Pydantic, interfaces Kraken/LLM/Broker.
3. **Intégration offline** : fixtures de marché, réponses LLM simulées, boucle PAPER.
4. **Intégration réseau contrôlée** : flux publics Kraken, sans credentials privés.
5. **Replay** : données enregistrées et horloge contrôlée, sans look-ahead.
6. **Frontend/API** : contrats REST/WS et parcours cockpit.
7. **Expérimentation modèles** : même contexte et protocole pour comparer Luna/Sol.

### 20.3 Cas critiques minimaux

- aucune vente au-delà du solde ;
- sortie LLM invalide => zéro ordre ;
- Risk Engine reject => zéro exécution ;
- HOLD journalisé ;
- frais/spread/slippage réduisent correctement le P&L net ;
- redémarrage frontend sans impact sur la boucle ;
- redémarrage backend avec reprise cohérente lorsque la persistance sera présente ;
- données périmées => comportement sûr et traçable.

---

## 21. Mesure des performances

### 21.1 Métriques confirmées à mesurer honnêtement

- P&L brut ;
- P&L net ;
- drawdown ;
- frais ;
- slippage ;
- exposition ;
- nombre de trades ;
- performance quotidienne ;
- performance cumulée.

### 21.2 Métriques supplémentaires proposées

- spread payé ;
- turnover ;
- taux `BUY` / `SELL` / `HOLD` ;
- taux de rejet/modification du Risk Engine ;
- temps moyen en position ;
- win rate et profit factor, avec prudence sur leur interprétation ;
- latence de décision ;
- coût LLM par cycle et par période ;
- performance par paire ;
- performance par niveau d'agressivité ;
- dérive entre P&L brut et net.

### 21.3 Intégrité expérimentale

- conserver les pertes et périodes défavorables ;
- versionner les configurations ;
- ne pas réécrire les décisions historiques ;
- ne pas utiliser de données futures ;
- ne pas sélectionner uniquement les actifs/périodes ayant bien marché après coup ;
- distinguer clairement apprentissage exploratoire, validation et comparaison ;
- comparer Luna/Sol avec le même protocole lorsque cela est possible.

---

## 22. Questions ouvertes prioritaires

**À décider avant ou pendant les premiers batches d'implémentation :**

- capital PAPER et devise de référence ;
- univers initial de paires Kraken ;
- fréquence de décision ;
- horizons et indicateurs exposés ;
- limites chiffrées du Risk Engine ;
- mapping agressivité 1–10 ;
- modèle d'exécution PAPER ;
- politique de persistance des données de marché ;
- frontière de journée ;
- règles de reprise après panne ;
- contrat exact de `DecisionCandidate`.

Ces choix doivent être consignés dans `10_DECISIONS_ET_CHANGELOG.md` lorsqu'ils deviennent confirmés.
