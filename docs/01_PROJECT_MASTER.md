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

Le projet n'a pas vocation à devenir silencieusement un bot algorithmique classique. Les indicateurs, statistiques et règles déterministes fournissent du contexte et imposent des garde-fous ; l'agent IA conserve la décision stratégique.

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
- Pouvoir sélectionner GPT-5.6 Sol par configuration sans réécrire la logique métier.
- Faire valider toute décision tradable par un Risk Engine déterministe avant toute exécution.
- Commencer exclusivement en PAPER.
- Prendre en compte frais, spread et slippage.
- Journaliser toutes les décisions, y compris `HOLD`.
- Séparer strictement PAPER et un éventuel LIVE futur.
- Fournir un cockpit frontend sans rendre le moteur de trading dépendant de l'interface.

### 3.2 Non-objectifs immédiats

**Hors périmètre pour l'instant :** multi-exchange, short, margin, levier, futures, perpetuals, options, stratégie multi-agents, HFT, copy trading, custody/retraits, application mobile native, optimisation Rust sans besoin mesuré et passage automatique en LIVE.

---

## 4. Périmètre V0 / V1

### V0 — socle expérimental

**Proposé comme définition de V0.**

V0 est atteinte lorsque le backend peut, en PAPER et sans frontend obligatoire :

1. recevoir des données publiques Kraken ;
2. construire un `MarketState` cohérent ;
3. maintenir un `PortfolioState` PAPER ;
4. interroger l'agent Luna avec un contrat structuré ;
5. obtenir une décision `BUY` / `SELL` / `HOLD` ;
6. soumettre cette décision au Risk Engine ;
7. simuler l'exécution autorisée via le Paper Broker ;
8. mettre à jour portefeuille, P&L et journal ;
9. répéter la boucle de manière autonome ;
10. exposer assez d'état via FastAPI pour être inspectée et contrôlée.

### V1 — cockpit et expérimentation instrumentée

**Proposé comme définition de V1.**

V1 ajoute cockpit Next.js/shadcn, historique décisions/exécutions, analytics P&L/drawdown/coûts/exposition, réglage contrôlé de l'agressivité, comparaisons Luna/Sol reproductibles, capacités de replay sans look-ahead et préparation des prérequis de sécurité pour évaluer un futur LIVE. Le LIVE lui-même n'est pas une condition de V1.

---

## 5. Principes architecturaux

### 5.1 Principes confirmés

1. **Backend = application de trading.**
2. **Frontend = cockpit** de contrôle et visualisation.
3. **Indépendance du frontend.** Fermer ou redémarrer le frontend ne doit jamais arrêter le moteur.
4. **Interfaces aux frontières externes.** Kraken, LLM et Broker sont masqués derrière des ports dédiés.
5. **Asynchrone côté backend.** Python + `asyncio`.
6. **API de contrôle.** FastAPI + Pydantic.
7. **REST et WebSocket** selon le besoin.
8. **Risk Engine final.** Le LLM ne parle jamais directement à l'exchange/broker.
9. **PAPER uniquement pour les premières versions.** Aucun chemin LIVE implicite.
10. **PostgreSQL cible.** Schéma et ORM restent à décider.
11. **Pas de Rust sans besoin mesuré.**
12. **No look-ahead.** Tout contexte historique utilisé pour une décision ou une exécution à `T` doit être daté de `T` ou avant.

### 5.2 Flux de confiance

```text
Kraken public data
        |
        v
normalized observations
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
                         Market State pricing
                                      |
                                      v
                               Paper Broker
                                      |
                          +-----------+-----------+
                          v                       v
                  Portfolio State             Journal
```

Aucun adaptateur LIVE n'est autorisé dans l'état actuel. Le Paper Broker ne consulte jamais Kraken pour obtenir un prix caché : le contexte de pricing canonique lui est fourni explicitement.

---

## 6. Architecture backend / frontend

### Backend

**Confirmé :** Python, `asyncio`, FastAPI, Pydantic.

Responsabilités : ingestion/normalisation marché, `MarketState`, `PortfolioState`, orchestration, agent, validation, Risk Engine, Paper Broker, P&L/analytics, persistance/audit, API et santé opérationnelle.

### Frontend

**Confirmé :** Next.js + TypeScript + shadcn/ui + Tailwind CSS, géré avec `pnpm`.

Le frontend affiche et contrôle l'état autorisé mais ne contient pas la stratégie de trading et ne devient jamais l'ordonnanceur du moteur.

---

## 7. Boucle de trading

### 7.1 Séquence conceptuelle confirmée

À chaque cycle :

1. vérifier santé et fraîcheur des données ;
2. figer un `MarketState` daté ;
3. figer un `PortfolioState` daté ;
4. fournir ces états et la configuration autorisée à l'agent ;
5. recevoir une sortie LLM ;
6. parser et valider strictement via Pydantic ;
7. si invalide, ne rien exécuter et journaliser ;
8. soumettre toute décision à conséquence financière au Risk Engine ;
9. autoriser, réduire/modifier ou refuser ;
10. en PAPER, simuler l'exécution avec un contexte de prix explicite et des coûts déterministes ;
11. mettre à jour atomiquement le portefeuille ;
12. calculer les métriques ;
13. journaliser le cycle complet, y compris `HOLD`, refus et erreurs.

### 7.2 Points à décider

Cadence, déclenchement temporel/événementiel/hybride, nombre de paires par cycle, budget de latence LLM, politique métier sur données périmées, retries et politique avancée d'ordres PAPER restent ouverts.

---

## 8. Contrats de domaine

### 8.1 Principe confirmé

Les frontières critiques reposent sur des modèles Pydantic stricts, `extra="forbid"`, avec UUID explicites et timestamps timezone-aware normalisés en UTC.

### 8.2 Contrats canoniques

- `MarketObservation` : observation normalisée fournisseur-agnostique avec timestamp, symbole et dernier prix positif.
- `MarketState` : identifiant, timestamp de snapshot, symbole, dernier prix positif et `MarketContext` optionnel.
- `MarketContext` : dernière observation utilisée, âge des données, seuil technique stale éventuellement évalué et fenêtres descriptives.
- `MarketWindowStats` : horizon, bornes temporelles disponibles, nombre d'observations, complétude d'historique, min/max/amplitude, return et volatilité lorsque calculables.
- `AssetBalance` : actif de règlement/cash PAPER et quantité disponible correspondante.
- `AssetPosition` : actif détenu, quantité totale et quantité disponible à la vente.
- `PortfolioState` : identifiant, timestamp, mode PAPER, balances et positions non négatives, uniques et sans chevauchement d'actif entre les deux collections.
- `AgentInput` : cycle, timestamp, `MarketState`, `PortfolioState`, agressivité validée de 1 à 10.
- `DecisionCandidate` : décision, cycle, timestamp, action, symbole, rationale optionnelle.
- `RiskAssessment` : évaluation, cycle, décision, timestamp, statut `ALLOW|MODIFY|REJECT`, raisons.
- `ExecutionIntent` : exécution corrélée au cycle/décision/risk, PAPER uniquement, `BUY|SELL`, quantité positive.
- `Fill` : fait d'exécution corrélé à l'intention et au `MarketState`, avec timestamps, action, symbole, quantité, prix de référence, prix exécuté, notional, frais et coûts de spread/slippage.

Le sizing stratégique n'est pas encore figé dans `DecisionCandidate`. La présence d'une quantité exacte dans `ExecutionIntent` exprime uniquement la frontière d'exécution après Risk Engine.

### 8.3 Types confirmés

```text
TradingAction = BUY | SELL | HOLD
ExecutionMode = PAPER
RiskDecision = ALLOW | MODIFY | REJECT
LLMModel = gpt-5.6-luna | gpt-5.6-sol
```

Le LIVE ne peut pas être configuré dans l'état actuel du code.

---

## 9. Market State

Le `MarketState` est le snapshot déterministe présenté aux couches supérieures et utilisé comme contexte de pricing PAPER.

### Confirmé au Batch 04

Le contrat conserve un unique `MarketState`. Le noyau historique reste :

```text
market_state_id
as_of
symbol
last_price
```

Il est enrichi par un `MarketContext` optionnel :

```text
MarketContext
- last_observed_at
- data_age_seconds
- stale_after_seconds?
- is_stale?
- windows[]
```

Deux horizons descriptifs par défaut sont versionnés dans le code : **5 minutes** et **30 minutes**. Ils sont surchargeables lors de l'instanciation du builder. Ils ne représentent ni une cadence de décision, ni une fréquence de tick Kraken, ni une règle d'entrée/sortie.

Pour chaque horizon, le Batch 04 calcule uniquement des faits descriptifs : nombre d'observations, minimum, maximum, amplitude absolue, return simple et volatilité réalisée simple lorsque calculables. Les calculs utilisent `Decimal` et n'introduisent pas NumPy/Pandas.

### Complétude, données manquantes et fraîcheur

- Une fenêtre est complète seulement si l'historique retenu atteint ou précède son début et qu'au moins une observation existe dans la fenêtre.
- La complétude ne garantit pas une cadence de tick sans trou.
- Une fenêtre vide reste explicitement vide ; aucune interpolation.
- `data_age_seconds` reste descriptif ; `is_stale` n'est évalué que si un seuil technique est fourni.
- Le seuil métier de refus de trader relève du futur Risk Engine.

### Historique et ordre temporel

Le builder garde un historique mémoire borné à **10 000 observations par instance** par défaut. Les observations sont ajoutées en ordre strictement croissant ; doublons temporels, données hors ordre et symboles différents dans une même instance sont rejetés.

Pour un snapshot à l'instant `T`, toute observation postérieure à `T` est ignorée, même si elle a déjà été injectée dans l'historique.

### Principe stratégique

Aucune statistique du Market State ne produit `BUY`, `SELL`, `HOLD`, score de trading, label bullish/bearish ou autre signal. L'agent IA conserve la décision stratégique.

Bid/ask, spread marché réel, volume, bougies, carnet et profondeur restent à ajouter uniquement si un besoin concret le justifie.

---

## 10. Portfolio State

Le `PortfolioState` est la vue canonique de ce que le système considère comme détenu et disponible.

### Confirmé au Batch 05

Le contrat conserve deux rôles explicitement séparés :

- `balances` est la source canonique des actifs de règlement disponibles à débiter/créditer ;
- `positions` est la source canonique des actifs de base détenus, avec quantité totale et quantité disponible à la vente.

Un actif ne peut pas apparaître simultanément dans `balances` et `positions`, et chaque actif doit être unique dans sa collection. Les quantités négatives sont interdites ; `AssetPosition.available` ne peut pas dépasser `quantity`.

Le capital initial et la devise de référence produit **ne sont pas figés**. Le `PaperPortfolioLedger` reçoit explicitement un `PortfolioState` initial. Une fixture de test peut utiliser EUR ou BTC/EUR sans transformer ce choix en décision produit.

Le ledger mémoire est l'unique état mutable du portefeuille PAPER dans ce batch. Il produit à tout instant un nouveau snapshot `PortfolioState` canonique, trié de manière déterministe par actif. Les mutations BUY/SELL sont préparées sur copies et ne remplacent l'état interne qu'après validation complète.

### Invariant confirmé

Une vente ne peut jamais dépasser la quantité détenue et disponible. Un achat ne peut jamais produire un solde quote négatif. Le Paper Broker conserve ces invariants d'intégrité même si le futur Risk Engine les contrôle aussi en amont.

### Base de coût et P&L

Le Batch 05 n'introduit pas de base de coût ni de moteur comptable P&L. Les informations d'exécution nécessaires aux analytics futures sont portées par `Fill`. Le P&L complet, drawdown et reporting restent au Batch 12.

---

## 11. Interface de l'agent IA

### 11.1 Rôle confirmé

L'agent prend la décision stratégique à partir d'un contexte préparé par le backend. Il ne reçoit jamais de secrets et n'a aucun accès direct à Kraken.

### 11.2 Modèle initial

- **Confirmé :** GPT-5.6 Luna par défaut.
- **Confirmé :** GPT-5.6 Sol sélectionnable par configuration.
- **À décider :** paramètres exacts, budget tokens, retries et outils éventuels.

### 11.3 Port confirmé

```text
LLMProvider.generate_decision(AgentInput) -> DecisionCandidate
```

Le provider réel et le prompt restent hors périmètre jusqu'au Batch 07.

---

## 12. Risk Engine

### 12.1 Autorité confirmée

Le Risk Engine déterministe est **l'autorité finale** avant exécution. Il peut `ALLOW`, `MODIFY` ou `REJECT` et ne doit pas inventer une nouvelle stratégie de marché.

### 12.2 Contraintes futures à chiffrer

Actifs autorisés, taille maximale, exposition, cash minimum, quantité avant SELL, drawdown/perte, fraîcheur, fréquence/turnover, cooldown, précision/minimum Kraken.

Le Paper Broker du Batch 05 protège uniquement les invariants absolus d'exécution et de comptabilité ; il ne remplace pas le Risk Engine du Batch 06.

---

## 13. Paper Trading

### 13.1 Confirmé au Batch 05

Les premières versions sont exclusivement PAPER. `ExecutionMode` ne contient actuellement que `PAPER`.

Le port canonique est désormais :

```text
Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]
```

Le `MarketState` est explicitement fourni afin que le broker n'effectue aucun lookup réseau caché. Le symbole doit correspondre à l'intention et le snapshot de pricing ne peut pas être postérieur à `ExecutionIntent.created_at`.

Le premier modèle PAPER est volontairement simple :

- fill immédiat et complet ou rejet explicite ;
- aucun order book simulé ;
- aucun partial fill ;
- aucun ordre limit/pending ;
- aucun matching engine ;
- aucun aléatoire.

Les coûts sont injectés via un objet `PaperExecutionCostModel` :

- `fee_rate` : taux décimal appliqué au notional exécuté ;
- `spread_bps` : impact adverse **par côté** exprimé en basis points ;
- `slippage_bps` : impact adverse déterministe additionnel par côté.

Pour un prix de référence `P` :

```text
BUY price  = P + spread impact + slippage impact
SELL price = P - spread impact - slippage impact
```

Les frais sont débités en plus du notional sur BUY et déduits du produit sur SELL. Aucun arrondi Kraken, minimum fournisseur ou quantification arbitraire n'est appliqué au Batch 05.

`Fill` mémorise les coûts et le contexte de pricing pour qu'un futur moteur Analytics puisse expliquer une mutation sans reconstruire les coûts depuis une configuration qui aurait changé.

### 13.2 Toujours à décider

- valeurs produit par défaut de frais/spread/slippage ;
- éventuel modèle plus réaliste basé sur bid/ask ou order book lorsque ces données existeront ;
- partial fills, minimums/précision fournisseur et comportement avancé d'ordres ;
- capital PAPER initial et devise de référence globale.

---

## 14. Agressivité 1–10

### Confirmé

L'utilisateur peut configurer un entier de **1 à 10**. La validation existe au niveau configuration et `AgentInput`.

Le mapping chiffré exact reste **À DÉCIDER** et devra être monotone, documenté, testable et versionné. Aucune valeur ne peut contourner les invariants SPOT ou le Risk Engine.

---

## 15. Cible quotidienne +4 %

### Confirmé

+4 %/jour est une cible expérimentale, pas une promesse. Elle ne doit pas forcer un trade, masquer les pertes, provoquer de cherry-picking, ni conduire à une modification post-hoc des décisions.

La frontière exacte d'une journée, la devise de référence et le calcul du capital de début de journée restent à décider.

---

## 16. Observabilité et journalisation

### Confirmé

Toutes les décisions sont journalisées, y compris `HOLD`.

Les contrats portent des identifiants corrélables pour snapshots, cycles, décisions, évaluations de risque, exécutions et fills. Le `Fill` du Batch 05 référence aussi le `MarketState` qui a servi au pricing. Les timestamps techniques sont UTC-aware.

### Toujours à décider

Format final des logs structurés, rétention, verbosité et schéma de persistance. Aucun secret ne doit apparaître dans les logs ou prompts.

---

## 17. Stockage

### Confirmé

PostgreSQL est la base cible.

### Données candidates

Cycles, snapshots/références de marché et portefeuille, décisions agent, résultats Risk Engine, exécutions/fills PAPER, métriques P&L, configuration/version d'expérience et erreurs utiles.

ORM, migrations, granularité de conservation et rétention restent à décider. Les Batch 04 et 05 conservent uniquement des états mémoire techniques ; aucune persistance n'est introduite.

---

## 18. Sécurité des secrets

### Confirmé

- aucun secret dans Git ;
- aucun secret dans prompts/logs ;
- aucun secret dans les fichiers de configuration versionnés ;
- aucune clé Kraken avec droit de retrait ;
- fournisseur LLM et Kraken derrière interfaces dédiées ;
- futur LIVE séparé du PAPER.

---

## 19. Séparation PAPER / LIVE

### Confirmé

Le passage en LIVE doit être explicite, séparé et ultérieur. Le mode ne doit jamais être déduit d'une clé présente ou de l'environnement.

`ExecutionMode` ne possède que la valeur `PAPER`, donc `LIVE` n'est pas activable.

---

## 20. Horloge, timestamps et no look-ahead

### Confirmé

Une interface `Clock.now()` et une implémentation `SystemClock` UTC fournissent un point d'injection pour tests déterministes et replays.

Les timestamps techniques sont stockés/échangés en UTC après normalisation. Cette convention ne décide pas de la frontière journalière des métriques.

Le Batch 04 garantit qu'un `MarketState` construit à `T` ne contient aucune observation postérieure à `T`. Le Batch 05 prolonge cet invariant à l'exécution : un broker PAPER refuse un `MarketState.as_of` postérieur à `ExecutionIntent.created_at` et n'interroge jamais Kraken « maintenant » pendant un replay.

---

## 21. Stratégie de tests

### Principes confirmés

- ne jamais présenter un test non exécuté comme réussi ;
- tester les composants déterministes indépendamment du LLM/Kraken ;
- ne pas nécessiter le frontend pour tester le moteur ;
- éviter toute exécution LIVE dans les suites automatiques ;
- tester explicitement absence de look-ahead, ordre temporel, fenêtres partielles et historique borné ;
- tester les mutations portfolio atomiques et l'absence de solde/position négatif ;
- tester précisément frais, spread, slippage et exactitude `Decimal` ;
- tester qu'un rejet PAPER ne produit ni mutation partielle ni faux `Fill`.

Pyramide : unitaires, contrats, intégration offline, intégration réseau publique contrôlée, replay, frontend/API, expérimentation modèles.

Cas critiques : vente impossible au-delà du solde, cash insuffisant, symbole/pricing incohérent, sortie LLM invalide => zéro ordre, Risk reject => zéro exécution, HOLD journalisé, coûts visibles, frontend indépendant, reprise cohérente, données périmées => comportement sûr.

---

## 22. Mesure des performances

### Métriques confirmées

P&L brut/net, drawdown, frais, slippage, exposition, nombre de trades, performance quotidienne et cumulée.

### Intégrité expérimentale

Conserver pertes et périodes défavorables, versionner configurations, ne pas réécrire l'historique, ne pas utiliser de données futures, éviter sélection post-hoc et comparer Luna/Sol avec un protocole comparable.

Le `Fill` enrichi du Batch 05 fournit désormais les faits d'exécution nécessaires pour mesurer ultérieurement frais et impacts de prix sans les masquer dans les balances.

---

## 23. Questions ouvertes prioritaires

- capital PAPER et devise de référence ;
- univers initial de paires Kraken ;
- fréquence de décision ;
- éventuelle évolution des horizons 5 min / 30 min ;
- données marché supplémentaires réellement nécessaires (bid/ask, volume, bougies, etc.) ;
- représentation du sizing dans `DecisionCandidate` ;
- limites chiffrées du Risk Engine ;
- seuil métier global de fraîcheur ;
- mapping agressivité 1–10 ;
- valeurs de coûts PAPER de référence et éventuel modèle de fill plus réaliste ;
- persistance des données de marché et portefeuille ;
- frontière de journée ;
- règles de reprise après panne.

Ces choix doivent être consignés dans `10_DECISIONS_ET_CHANGELOG.md` lorsqu'ils deviennent confirmés.
