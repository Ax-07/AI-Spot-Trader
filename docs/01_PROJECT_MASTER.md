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

### 5.2 Flux de confiance

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

Aucun adaptateur LIVE n'est autorisé dans l'état actuel.

---

## 6. Architecture backend / frontend

### Backend

**Confirmé :** Python, `asyncio`, FastAPI, Pydantic.

Responsabilités futures : ingestion/normalisation marché, `MarketState`, `PortfolioState`, orchestration, agent, validation, Risk Engine, Paper Broker, P&L/analytics, persistance/audit, API et santé opérationnelle.

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
10. en PAPER, simuler l'exécution avec coûts ;
11. mettre à jour le portefeuille ;
12. calculer les métriques ;
13. journaliser le cycle complet, y compris `HOLD`, refus et erreurs.

### 7.2 Points à décider

Cadence, déclenchement temporel/événementiel/hybride, nombre de paires par cycle, budget de latence LLM, politique sur données périmées, retries et durée d'ordres PAPER restent ouverts.

---

## 8. Contrats de domaine initiaux — Batch 02

### 8.1 Principe confirmé

Les frontières critiques reposent sur des modèles Pydantic stricts, `extra="forbid"`, avec UUID explicites et timestamps timezone-aware normalisés en UTC.

### 8.2 Contrats canoniques initiaux

- `MarketState` : identifiant, timestamp, symbole, dernier prix positif.
- `PortfolioState` : identifiant, timestamp, mode PAPER, balances et positions minimales non négatives.
- `AgentInput` : cycle, timestamp, `MarketState`, `PortfolioState`, agressivité optionnelle validée de 1 à 10, sans valeur par défaut décidée.
- `DecisionCandidate` : décision, cycle, timestamp, action, symbole, rationale optionnelle.
- `RiskAssessment` : évaluation, cycle, décision, timestamp, statut `ALLOW|MODIFY|REJECT`, raisons.
- `ExecutionIntent` : exécution corrélée au cycle/décision/risk, PAPER uniquement, `BUY|SELL`, quantité positive.
- `Fill` : fill corrélé à l'exécution, `BUY|SELL`, quantité et prix positifs.

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

Le `MarketState` est le snapshot déterministe présenté à l'agent.

### Confirmé au Batch 02

Le sous-ensemble canonique initial comprend : `market_state_id`, `as_of`, `symbol`, `last_price`.

### À décider/étendre lors des batches marché

Bid/ask, spread, bougies, volume, qualité/fraîcheur, indicateurs, horizons, profondeur de carnet, univers initial et normalisation des symboles Kraken.

Les indicateurs ne déclenchent jamais eux-mêmes `BUY` ou `SELL`.

---

## 10. Portfolio State

Le `PortfolioState` est la vue canonique de ce que le système considère comme détenu et disponible.

### Confirmé au Batch 02

Le sous-ensemble initial comprend timestamp, mode PAPER, balances disponibles et positions avec quantité détenue/quantité disponible. Les quantités négatives sont interdites et la quantité disponible d'une position ne peut pas dépasser la quantité détenue.

### Invariant confirmé

Une décision `SELL` ne peut jamais produire une vente supérieure à la quantité réellement détenue et disponible. Le contrôle effectif sera implémenté dans les futurs composants Risk/Broker.

P&L, base de coût, prix de marquage, exposition, frais et drawdown seront ajoutés lorsqu'ils deviennent nécessaires.

---

## 11. Interface de l'agent IA

### 11.1 Rôle confirmé

L'agent prend la décision stratégique à partir d'un contexte préparé par le backend. Il ne reçoit jamais de secrets et n'a aucun accès direct à Kraken.

### 11.2 Modèle initial

- **Confirmé :** GPT-5.6 Luna par défaut.
- **Confirmé :** GPT-5.6 Sol sélectionnable par configuration.
- **À décider :** paramètres exacts, budget tokens, retries et outils éventuels.

### 11.3 Port confirmé au Batch 02

```text
LLMProvider.generate_decision(AgentInput) -> DecisionCandidate
```

Le provider réel et le prompt restent hors périmètre.

---

## 12. Risk Engine

### 12.1 Autorité confirmée

Le Risk Engine déterministe est **l'autorité finale** avant exécution. Il peut `ALLOW`, `MODIFY` ou `REJECT` et ne doit pas inventer une nouvelle stratégie de marché.

### 12.2 Contraintes futures à chiffrer

Actifs autorisés, taille maximale, exposition, cash minimum, quantité avant SELL, drawdown/perte, fraîcheur, fréquence/turnover, cooldown, précision/minimum Kraken.

Aucune valeur chiffrée n'est décidée au Batch 02.

---

## 13. Paper Trading

### 13.1 Confirmé

Les premières versions sont exclusivement PAPER. `ExecutionMode` ne contient actuellement que `PAPER`.

Le port Broker initial accepte un `ExecutionIntent` déjà autorisé/modifié et retourne des `Fill`. L'implémentation doit à terme prendre en compte frais, spread et slippage, refuser les ventes non couvertes et mettre à jour le `PortfolioState`.

### 13.2 À décider

Modèle de fill, slippage, barème de frais, fills partiels, minimums/précision, capital initial et devise de référence.

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

### Confirmé au Batch 02

Les contrats portent des identifiants corrélables pour snapshots, cycles, décisions, évaluations de risque, exécutions et fills. Les timestamps techniques sont UTC-aware.

### Toujours à décider

Format final des logs structurés, rétention, verbosité et schéma de persistance. Aucun secret ne doit apparaître dans les logs ou prompts.

---

## 17. Stockage

### Confirmé

PostgreSQL est la base cible.

### Données candidates

Cycles, snapshots/références de marché et portefeuille, décisions agent, résultats Risk Engine, exécutions/fills PAPER, métriques P&L, configuration/version d'expérience et erreurs utiles.

ORM, migrations, granularité de conservation et rétention restent à décider.

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

Au Batch 02, le choix est plus strict : `ExecutionMode` ne possède que la valeur `PAPER`, donc `LIVE` n'est pas activable.

---

## 20. Horloge et timestamps

### Confirmé au Batch 02

Une interface `Clock.now()` et une implémentation `SystemClock` UTC fournissent un point d'injection minimal pour tests déterministes, futurs replays et prévention du look-ahead.

Les timestamps techniques sont stockés/échangés en UTC après normalisation. Cette convention **ne décide pas** de la frontière journalière des métriques.

---

## 21. Stratégie de tests

### Principes confirmés

- ne jamais présenter un test non exécuté comme réussi ;
- tester les composants déterministes indépendamment du LLM/Kraken ;
- ne pas nécessiter le frontend pour tester le moteur ;
- éviter toute exécution LIVE dans les suites automatiques.

Pyramide : unitaires, contrats, intégration offline, intégration réseau publique contrôlée, replay, frontend/API, expérimentation modèles.

Cas critiques : vente impossible au-delà du solde, sortie LLM invalide => zéro ordre, Risk reject => zéro exécution, HOLD journalisé, coûts visibles, frontend indépendant, reprise cohérente, données périmées => comportement sûr.

---

## 22. Mesure des performances

### Métriques confirmées

P&L brut/net, drawdown, frais, slippage, exposition, nombre de trades, performance quotidienne et cumulée.

### Intégrité expérimentale

Conserver pertes et périodes défavorables, versionner configurations, ne pas réécrire l'historique, ne pas utiliser de données futures, éviter sélection post-hoc et comparer Luna/Sol avec un protocole comparable.

---

## 23. Questions ouvertes prioritaires

- capital PAPER et devise de référence ;
- univers initial de paires Kraken ;
- fréquence de décision ;
- horizons et indicateurs ;
- enrichissement du `MarketState` ;
- représentation du sizing dans `DecisionCandidate` ;
- limites chiffrées du Risk Engine ;
- mapping agressivité 1–10 ;
- modèle d'exécution PAPER ;
- persistance des données de marché ;
- frontière de journée ;
- règles de reprise après panne.

Ces choix doivent être consignés dans `10_DECISIONS_ET_CHANGELOG.md` lorsqu'ils deviennent confirmés.
