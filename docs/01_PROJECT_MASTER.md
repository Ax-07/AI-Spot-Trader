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

`DecisionCandidate` contient désormais :

```text
decision_id
cycle_id
created_at
action = BUY | SELL | HOLD
symbol
proposed_quantity?   # obligatoire pour BUY/SELL, interdite pour HOLD
rationale?
```

Le sizing initial est donc **stratégique** : le Risk Engine ne choisit pas arbitrairement une taille de départ.

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

Les raisons sont des codes déterministes (`RiskReason`) et `evaluated_limits` utilise des identifiants `RiskLimit` stables pour tracer les contrôles réellement atteints, même sur ALLOW. `MODIFY` doit strictement réduire la quantité demandée. `REJECT` n'autorise aucune quantité.

`ExecutionIntent` reste uniquement PAPER, BUY/SELL, et n'existe que si le Risk Engine autorise une quantité strictement positive. `HOLD` ne produit jamais d'intention d'exécution.

`Fill` reste le fait d'exécution PAPER auditable avec contexte de pricing, prix de référence, prix exécuté, notional, frais, spread et slippage.

---

## 6. Market State

### Confirmé au Batch 04

`MarketStateBuilder` est mono-symbole, déterministe et mémoire. Il garde un historique borné à 10 000 observations par défaut, impose un ordre temporel strict et construit les horizons 5 min / 30 min par défaut.

Les statistiques restent descriptives et en `Decimal` : count, min, max, amplitude, return simple et volatilité réalisée simple lorsqu'elles sont calculables. Elles ne produisent aucun signal stratégique.

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

Le calcul des coûts est factorisé dans une fonction pure partagée par le Risk Engine et le Paper Broker. `PaperExecutionCostModel` reste injecté :

- `fee_rate` décimal ;
- `spread_bps` = impact adverse par côté ;
- `slippage_bps` = impact adverse additionnel.

Cette factorisation évite qu'un BUY soit autorisé par Risk puis rejeté par le broker uniquement à cause de frais/spread/slippage déjà prévisibles.

---

## 8. Risk Engine — état Batch 06

### Autorité et pureté

Le package canonique est `ai_spot_trader.risk`. Le moteur est synchrone, déterministe, sans FastAPI, Kraken, LLM, Broker ou I/O réseau. Il ne mute ni `MarketState` ni `PortfolioState` et n'exécute jamais lui-même un ordre.

Une même entrée + même `RiskPolicy` + mêmes coûts PAPER + même horloge/factories produit le même résultat métier.

### RiskPolicy injectée

Aucune limite produit arbitraire n'est ajoutée à `Settings` ou `.env`. La policy peut actuellement porter :

- `max_order_notional` optionnel ;
- `allowed_pairs` optionnel ;
- `stale_after` métier optionnel ;
- `allow_quantity_reduction` explicite.

Absence de whitelist = aucune contrainte de paire par cette policy. Absence de `stale_after` = aucun seuil stale inventé. Une policy invalide est rejetée à la construction.

### Contrôles effectivement supportés

Le Batch 06 vérifie honnêtement avec les données disponibles :

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

`HOLD` traverse la frontière Risk afin de produire un `RiskAssessment` auditable `ALLOW` avec raison structurée `HOLD_NO_EXECUTION`, mais aucun `ExecutionIntent`.

### Limites volontairement non implémentées

Faute de données suffisantes ou parce qu'elles appartiennent à d'autres batches : drawdown, daily loss, VaR, corrélations, allocation optimale, exposition portefeuille avancée, cooldown/turnover, précision/minimum Kraken, mapping agressivité 1–10.

---

## 9. Chronologie et no look-ahead

Pour une décision tradable :

```text
MarketState.as_of   <= DecisionCandidate.created_at
PortfolioState.as_of <= DecisionCandidate.created_at
DecisionCandidate.created_at <= RiskAssessment.assessed_at
RiskAssessment.assessed_at = ExecutionIntent.created_at
MarketState.as_of <= ExecutionIntent.created_at <= Fill.filled_at
```

Un `MarketState` ou un `PortfolioState` futur par rapport à la décision est rejeté par Risk. Le Paper Broker conserve indépendamment sa vérification du contexte de pricing.

---

## 10. Agent IA

`LLMProvider.generate_decision(AgentInput) -> DecisionCandidate` reste le port canonique. Le provider Luna réel, prompt, parsing fournisseur et retries appartiennent au Batch 07.

Le contrat Batch 06 impose désormais au futur agent de fournir une `proposed_quantity` pour BUY/SELL. L'agent conserve donc le sourcing du sizing stratégique ; Risk ne peut que le borner pour la sécurité.

L'agressivité 1–10 reste validée dans `Settings` et `AgentInput`, mais son mapping chiffré n'est pas figé. Aucune agressivité ne peut contourner une limite absolue.

---

## 11. Orchestration, persistance et analytics

La boucle autonome reste au Batch 08 ; le Risk Engine peut être invoqué indépendamment.

PostgreSQL reste la cible future. Le Batch 06 n'ajoute aucune persistance.

P&L brut/net, drawdown, frais, slippage, exposition, nombre de trades et performance quotidienne/cumulée restent des objectifs Analytics. Le Batch 06 ne fabrique pas de métrique à partir de données inexistantes.

---

## 12. Sécurité et séparation PAPER / LIVE

`ExecutionMode` ne contient que `PAPER`. Le LIVE reste non représentable et nécessitera une décision dédiée. Aucun secret n'est ajouté ; aucune clé Kraken privée n'est requise.

Le Risk Engine et le Paper Broker dupliquent volontairement certains invariants SPOT : Risk anticipe et explique la décision ; le broker protège l'intégrité finale de l'exécution.

---

## 13. Stratégie de tests

Les tests de Risk doivent rester offline et déterministes. Cas critiques : ALLOW BUY/SELL, REJECT explicite, MODIFY avec réduction, cash insuffisant, SELL non détenu/supérieur au disponible, max notional et frontière exacte, whitelist, stale absent/configuré, snapshots futurs, HOLD sans intent, LIVE impossible, corrélations d'UUID, immutabilité des snapshots, exactitude `Decimal`, déterminisme et absence de dépendance Kraken/LLM/FastAPI.

Aucun test réussi ne doit être déclaré s'il n'a pas réellement été exécuté.

---

## 14. Questions ouvertes prioritaires

- capital PAPER et devise de référence produit ;
- univers initial de paires ;
- cadence de décision ;
- valeurs produit des limites Risk ;
- éventuel seuil stale global d'expérience ;
- mapping agressivité 1–10 ;
- valeurs de référence fee/spread/slippage ;
- exposition simple ou avancée à introduire plus tard ;
- frontière de journée et données P&L nécessaires au drawdown/daily loss ;
- ORM, migrations, rétention et reprise après panne ;
- conditions futures d'un éventuel LIVE.

Ces choix doivent être consignés dans `10_DECISIONS_ET_CHANGELOG.md` lorsqu'ils deviennent canoniques.
