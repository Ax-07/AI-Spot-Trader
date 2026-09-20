# 01 — Project Master

## 1. Rôle de ce document

Ce document est la spécification fonctionnelle et architecturale principale d'**AI Spot Trader**. Les détails spécialisés sont complétés par `02_ARCHITECTURE_TECHNIQUE.md`, `03_AGENT_TRADING_RISK.md`, `09_ROADMAP_DEVELOPPEMENT.md` et `10_DECISIONS_ET_CHANGELOG.md`.

Statuts utilisés : **Confirmé**, **Proposé**, **À décider** et **Hors périmètre pour l'instant**.

---

## 2. Vision et invariants

**Confirmé.** AI Spot Trader est une application expérimentale de trading crypto **SPOT** pilotée par **un agent IA unique**. L'agent conserve la décision stratégique ; les composants déterministes construisent le contexte, imposent les contraintes de risque, exécutent en PAPER et mesurent les résultats.

Invariants principaux :

- Kraken est l'exchange initial ;
- SPOT uniquement : aucun short, levier, margin, future ou perpetual ;
- actions stratégiques `BUY`, `SELL`, `HOLD` ;
- aucune vente d'un actif non détenu ;
- GPT-5.6 Luna pour les premiers essais, Sol sélectionnable par configuration ;
- Risk Engine déterministe avec autorité finale ;
- aucune sortie LLM ne déclenche directement une exécution ;
- premières versions exclusivement en PAPER ;
- frais, spread et slippage pris en compte ;
- toutes les décisions, y compris `HOLD`, doivent être journalisées ;
- aucun secret dans Git, prompts ou logs ;
- aucun look-ahead ;
- frontend indépendant du moteur backend.

La cible expérimentale de **+4 %/jour** reste une métrique de recherche très agressive, jamais une garantie, une hypothèse de rendement attendu ou une obligation de forcer des trades.

---

## 3. Périmètre V0 / V1

### V0 — socle expérimental

V0 est atteinte lorsque le backend peut, sans frontend obligatoire :

1. recevoir des données publiques Kraken ;
2. construire un `MarketState` cohérent ;
3. maintenir un `PortfolioState` PAPER ;
4. obtenir une décision structurée de l'agent Luna ;
5. soumettre toute proposition tradable au Risk Engine ;
6. produire `ALLOW`, `MODIFY` ou `REJECT` ;
7. simuler l'exécution autorisée via le Paper Broker ;
8. mettre à jour le portefeuille et journaliser le cycle ;
9. répéter le cycle de manière autonome ;
10. exposer suffisamment d'état via FastAPI.

### V1 — cockpit et expérimentation instrumentée

V1 ajoute le cockpit Next.js/shadcn, historique, analytics P&L/drawdown/coûts/exposition, replay reproductible, expérimentations d'agressivité et comparaison Luna/Sol. Le LIVE n'est pas une condition de V1.

---

## 4. Architecture et flux de confiance

**Confirmé :** backend Python + `asyncio` + FastAPI + Pydantic ; frontend Next.js + TypeScript + shadcn/ui + Tailwind ; PostgreSQL cible ; REST/WebSocket selon le besoin.

```text
Kraken public data
        |
        v
normalized observations
        |
        v
MarketState -----+
                 |
PortfolioState --+--> Agent IA --> DecisionCandidate
                                    |
                                    v
                               Risk Engine
                            /       |       \
                        REJECT    MODIFY    ALLOW
                            \       |       /
                                    v
                              RiskAssessment
                                    |
                       ExecutionIntent si tradable
                                    |
                                    v
                              Paper Broker
                                    |
                         Fill + PortfolioState
```

Principe absolu : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Le package Agent ne possède aucun chemin direct vers Risk, Broker, Kraken, FastAPI ou une base de données. Le Batch 08 sera responsable de l'orchestration explicite de ces frontières.

---

## 5. Contrats de domaine canoniques

Les frontières critiques utilisent des modèles Pydantic stricts avec champs supplémentaires interdits, UUID explicites et timestamps timezone-aware normalisés UTC.

### Marché et portefeuille

- `MarketObservation` : fait marché fournisseur-agnostique minimal ;
- `MarketState` : snapshot déterministe, symbole canonique, dernier prix et contexte optionnel ;
- `MarketContext` : fraîcheur descriptive et fenêtres multi-horizon ;
- `PortfolioState` : snapshot PAPER avec `balances` et `positions` disjoints ;
- `AssetBalance` : actif de règlement disponible ;
- `AssetPosition` : quantité détenue et quantité disponible à la vente.

### Agent, Risk et exécution

`DecisionCandidate` contient :

```text
decision_id
cycle_id
created_at
action = BUY | SELL | HOLD
symbol
proposed_quantity?   # obligatoire pour BUY/SELL, interdite pour HOLD
rationale?
```

Le sizing initial est **stratégique** : le Risk Engine ne choisit pas arbitrairement une taille de départ.

`RiskAssessment` contient :

```text
risk_assessment_id
cycle_id
decision_id
assessed_at
status = ALLOW | MODIFY | REJECT
requested_quantity?
authorized_quantity?
evaluated_limits[]
reasons[]
```

Les raisons sont des codes déterministes (`RiskReason`) et `evaluated_limits` utilise des identifiants `RiskLimit` stables. `MODIFY` doit strictement réduire la quantité demandée. `REJECT` n'autorise aucune quantité.

`ExecutionIntent` reste uniquement PAPER, BUY/SELL, et n'existe que si le Risk Engine autorise une quantité strictement positive. `HOLD` ne produit jamais d'intention d'exécution.

`Fill` reste le fait d'exécution PAPER auditable avec contexte de pricing, prix de référence, prix exécuté, notional, frais, spread et slippage.

---

## 6. Market State

### Confirmé au Batch 04

`MarketStateBuilder` est mono-symbole, déterministe et mémoire. Il garde un historique borné, impose un ordre temporel strict et construit les horizons descriptifs configurés.

Les statistiques restent descriptives et en `Decimal`. Elles ne produisent aucun signal stratégique.

Pour un snapshot à `T`, seules les observations `observed_at <= T` sont utilisées. Le seuil technique de stale du Market State reste distinct de la politique métier Risk.

---

## 7. Portfolio State et Paper Broker

### Confirmé au Batch 05

`balances` est la source canonique des actifs de règlement ; `positions` est la source canonique des actifs détenus/vendables. Les rôles sont uniques et non chevauchants.

`PaperPortfolioLedger` reçoit un état initial explicitement injecté. Aucun capital PAPER, devise de référence ou univers produit n'est imposé globalement. Les mutations sont copy-on-write et atomiques.

`PaperBroker` reçoit explicitement `ExecutionIntent` et `MarketState` :

```text
Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]
```

Il ne consulte jamais Kraken, fait un fill complet immédiat ou un rejet explicite, et conserve les garde-fous comptables SPOT comme dernière frontière d'intégrité.

### Pricing PAPER partagé

Le calcul des coûts est factorisé dans une fonction pure partagée par le Risk Engine et le Paper Broker. `PaperExecutionCostModel` reste injecté : `fee_rate`, `spread_bps`, `slippage_bps`.

---

## 8. Risk Engine — intégré au Batch 06

### Autorité et pureté

Le package canonique est `ai_spot_trader.risk`. Le moteur est synchrone, déterministe, sans FastAPI, Kraken, LLM ou I/O réseau. Il ne mute ni `MarketState` ni `PortfolioState` et n'exécute jamais lui-même un ordre.

### RiskPolicy injectée

Aucune limite produit arbitraire n'est ajoutée à `Settings` ou `.env`. La policy peut actuellement porter :

- `max_order_notional` optionnel ;
- `allowed_pairs` optionnel ;
- `stale_after` métier optionnel ;
- `allow_quantity_reduction` explicite.

### Contrôles effectivement supportés

- symbole canonique `BASE/QUOTE` et cohérence avec `MarketState` ;
- chronologie sans look-ahead ;
- whitelist optionnelle ;
- fraîcheur métier optionnelle ;
- max order notional au prix de référence ;
- balance quote nécessaire ;
- coût PAPER BUY estimé complet ;
- position SELL réellement détenue et disponible ;
- rôles base/quote compatibles ;
- impossibilité d'une quantité résultante nulle ou négative.

`MODIFY` ne peut que réduire la quantité. Il ne change jamais BUY↔SELL, le symbole ou l'actif et n'augmente jamais la taille stratégique.

### HOLD

`HOLD` traverse la frontière Risk afin de produire un `RiskAssessment` auditable `ALLOW` avec raison `HOLD_NO_EXECUTION`, mais aucun `ExecutionIntent`.

### Limites volontairement non implémentées

Drawdown, daily loss, VaR, corrélations, allocation optimale, exposition portefeuille avancée, cooldown/turnover, précision/minimum Kraken et mapping agressivité 1–10 restent différés tant que les données ou décisions produit nécessaires n'existent pas.

---

## 9. Agent IA — Batch 07 préparé

Le port canonique reste inchangé :

```text
LLMProvider.generate_decision(AgentInput) -> DecisionCandidate
```

### Frontière stratégique

Le modèle fournisseur ne produit que :

```text
action
symbol
proposed_quantity
rationale
```

`decision_id`, `cycle_id` et `created_at` ne sont pas laissés au LLM :

- `decision_id` vient d'une factory UUID injectable ;
- `cycle_id` est recopié depuis `AgentInput` ;
- `created_at` vient d'un `Clock` injectable.

Cette enveloppe rend les tests et replays déterministes sans transformer le LLM lui-même en composant déterministe.

### Symbole autorisé

L'Agent Luna est limité au symbole porté par `agent_input.market_state.symbol`. Une sortie structurée proposant un autre symbole est rejetée avant construction d'un `DecisionCandidate` utilisable.

Cette contrainte empêche l'IA de trader un actif dont aucun `MarketState` ne lui a été fourni. Le Risk Engine conserve indépendamment son propre contrôle de cohérence symbole/snapshot.

### Structured Outputs

L'adapter OpenAI utilise la Responses API et un JSON Schema strict. Les quatre clés sont requises ; les champs optionnels au sens métier sont représentés par `null` lorsque nécessaire. Les champs supplémentaires sont interdits.

La réponse est ensuite parsée et revalidée côté application sans coercition stratégique silencieuse. Sont rejetés notamment : JSON invalide, action inconnue, champ manquant/inattendu, quantité string, quantité nulle/négative, BUY/SELL sans quantité et HOLD avec quantité.

### Prompt

Le prompt système `agent-luna-v1` est versionné dans le code. Il rappelle : SPOT/PAPER uniquement, BUY/SELL/HOLD, aucun short/levier/margin/future/perpetual, SELL couvert, sizing obligatoire pour BUY/SELL, agressivité 1–10 non mappée définitivement, objectif +4 % non obligatoire, aucune garantie, aucune donnée inventée et décision limitée au seul `AgentInput` fourni.

### Modèles et configuration

Les identifiants API vérifiés pour ce batch sont :

- Luna : `gpt-5.6-luna` ;
- Sol : `gpt-5.6-sol`.

`OpenAIDecisionProvider` est commun aux deux modèles. Le choix reste porté par `Settings.llm_model`.

### Secrets et transport

`Settings.openai_api_key` est un `SecretStr | None` chargé via l'environnement. Aucune clé n'est codée en dur, injectée dans le prompt ou incluse dans une exception.

L'adapter REST réutilise `httpx`, déjà dépendance runtime du projet ; aucun SDK supplémentaire n'est ajouté. Les tests utilisent un client HTTP injecté et `MockTransport`.

Aucun retry automatique n'est implémenté au Batch 07. Les catégories d'erreur sont explicites : transport, enveloppe fournisseur inutilisable, sortie structurée invalide, invariant Agent violé.

---

## 10. Chronologie et no look-ahead

Avant d'appeler le fournisseur LLM :

```text
MarketState.as_of    <= AgentInput.created_at
PortfolioState.as_of <= AgentInput.created_at
```

La décision créée respecte ensuite :

```text
AgentInput.created_at <= DecisionCandidate.created_at
```

Le provider ne fait aucun nouveau lookup Kraken, refresh de prix ou enrichissement réseau. Le Risk Engine conserve en plus ses propres contrôles temporels avant toute intention d'exécution.

---

## 11. Orchestration, persistance et analytics

La boucle autonome reste au Batch 08. Le Batch 07 ne relie pas automatiquement Agent, Risk et Broker.

PostgreSQL reste la cible future. Le Batch 07 n'ajoute aucune persistance.

P&L brut/net, drawdown, frais, slippage, exposition, nombre de trades et performance quotidienne/cumulée restent des objectifs Analytics ultérieurs.

---

## 12. Sécurité et séparation PAPER / LIVE

`ExecutionMode` ne contient que `PAPER`. Le LIVE reste non représentable et nécessitera une décision dédiée. Aucune clé Kraken privée n'est requise.

Le provider OpenAI ne dispose d'aucun outil d'exécution et ne connaît ni Broker ni Kraken. Une `rationale` reste du texte d'audit et ne peut jamais être interprétée comme commande.

---

## 13. Stratégie de tests

Les tests du Batch 07 restent offline et déterministes. Cas critiques : BUY/SELL/HOLD valides, structure invalide, action inconnue, quantité absente/non positive, HOLD avec quantité, champs inattendus, absence de coercition sûre, symbole divergent, IDs/timestamps injectables, prompt versionné, Luna/Sol via le même provider, erreurs HTTP/refus/incomplétude et absence d'import Risk/Broker/Kraken/FastAPI dans `agent`.

Aucun test réussi ne doit être déclaré s'il n'a pas réellement été exécuté.

---

## 14. Questions ouvertes prioritaires

- capital PAPER et devise de référence produit ;
- univers initial de paires ;
- cadence de décision ;
- valeurs produit des limites Risk ;
- mapping agressivité 1–10 ;
- valeurs de référence fee/spread/slippage ;
- exposition portefeuille à introduire plus tard ;
- frontière de journée et données P&L nécessaires au drawdown/daily loss ;
- ORM, migrations, rétention et reprise après panne ;
- conditions futures d'un éventuel LIVE.

Ces choix doivent être consignés dans `10_DECISIONS_ET_CHANGELOG.md` lorsqu'ils deviennent canoniques.
