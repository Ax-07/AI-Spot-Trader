# 09 — Roadmap de développement

## 1. Principes

La roadmap est organisée en batches cohérents, limités et testables. Chaque batch part du HEAD GitHub `main`, audite l'existant, modifie uniquement le nécessaire, teste réellement ce qui peut l'être, met à jour la documentation et livre un ZIP root-relative lorsqu'il touche plusieurs fichiers.

---

## Batch 00 — Documentation initiale

**Statut : intégré sur `main`.**

Établissement de la source de vérité documentaire, invariants et roadmap.

---

## Batch 01 — Bootstrap du projet

**Statut : intégré sur `main` au commit `d9af0ca293dd9f2712969b246e394c4a8c188b5e`.**

Backend Python/FastAPI installable, configuration typée, lifecycle asynchrone, tests et frontend Next.js/TypeScript/shadcn/Tailwind avec `pnpm`.

---

## Batch 02 — Contrats de domaine et configuration

**Statut : intégré sur `main` au commit `bff0f8b03740da4a01072af90111a2e5d9f208ef`.**

Contrats Pydantic stricts, UUID, timestamps UTC aware, horloge injectable, ports externes, PAPER uniquement, Luna/Sol configurable et agressivité 1–10.

---

## Batch 03 — Kraken Market Data

**Statut : intégré sur `main` au commit `e7ac37955f08853024528fa9b9e10b5a75e05e3b`.**

Données publiques Kraken Spot, normalisation des symboles, REST AssetPairs, WebSocket ticker, reconnexion bornée et aucune API privée.

---

## Batch 04 — Market State

**Statut : intégré sur `main` au commit `73acc4758427ea7575ddf0a43505e1c95fab5e9c`.**

`MarketObservation`, `MarketStateBuilder`, historique borné, horizons 5/30 min, statistiques `Decimal`, fraîcheur descriptive et no-look-ahead.

Validation locale Windows finale : **59 tests**, Ruff OK, mypy OK sur 24 fichiers source, `git diff --check` sans erreur.

---

## Batch 05 — Portfolio State + Paper Broker

**Statut : intégré sur `main` au commit `c24551d36a863abbb5fdb86b79658b235c852772` (`feat: add paper portfolio and broker`).**

Intégré :

- rôles `balances` / `positions` canoniques et disjoints ;
- `PaperPortfolioLedger` mémoire et état initial injecté ;
- mutations copy-on-write atomiques ;
- `PaperBroker` full-fill immédiat ;
- `Broker.execute(execution_intent, market_state)` ;
- coûts PAPER injectés en `Decimal` ;
- frais/spread/slippage auditables dans `Fill` ;
- aucun lookup Kraken caché ;
- aucun capital ou coût produit imposé globalement.

Validation locale Windows finale confirmée avant intégration :

- `pytest backend` : **92 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 40 source files** ;
- `git diff --check` : aucune erreur ;
- warnings LF → CRLF habituels uniquement ;
- 2 warnings FastAPI/Starlette sans échec ;
- aucun test réseau requis.

---

## Batch 06 — Risk Engine

**Statut : patch livré, validation locale utilisateur et intégration Git à effectuer.**

Objectif : premier Risk Engine déterministe canonique, indépendant de l'agent et du broker.

Implémentation du patch :

- `DecisionCandidate.proposed_quantity` : sizing stratégique obligatoire pour BUY/SELL, absent pour HOLD ;
- `RiskAssessment` enrichi de la quantité demandée/autorisée, des limites réellement évaluées et de raisons structurées ;
- enum `RiskReason` stable et testable ;
- package `ai_spot_trader.risk` ;
- `RiskPolicy` explicitement injectée ;
- sorties `ALLOW`, `MODIFY`, `REJECT` ;
- `MODIFY` limité à une réduction de quantité ;
- HOLD audité sans `ExecutionIntent` ;
- symboles canoniques partagés via `domain.symbols` ;
- whitelist optionnelle ;
- seuil stale métier optionnel ;
- max order notional optionnel ;
- BUY contrôlé avec coût PAPER complet prévisible ;
- SELL borné par la position réellement disponible ;
- rejet de snapshots futurs ;
- aucune mutation de portefeuille/marché ;
- aucune dépendance Kraken/FastAPI/LLM dans Risk ;
- estimateur de pricing PAPER pur partagé entre Risk et Paper Broker ;
- aucune variable d'environnement Risk ajoutée ;
- aucune stratégie algorithmique introduite.

Volontairement non implémenté : drawdown/daily loss sans historique P&L, VaR/corrélations, exposition avancée, cooldown, précision Kraken, mapping agressivité 1–10.

Validation ChatGPT réellement exécutée sur le patch : suite ciblée domaine + Risk + régressions Paper Broker **77/77**, `compileall` et contrôle de longueur de lignes. Ruff/mypy et la suite backend complète restent à valider localement.

---

## Batch 07 — Agent Luna

Objectif : implémenter le provider Luna derrière `LLMProvider`, prompt/contrat versionné, parsing structuré et aucune exécution directe.

Point d'intégration désormais fixé : toute décision BUY/SELL doit fournir `proposed_quantity`; HOLD ne porte aucune quantité.

Tests attendus : provider mocké, sortie invalide, action inconnue, quantité invalide/absente, BUY/SELL/HOLD et preuve qu'une sortie invalide n'atteint jamais Risk/Broker.

---

## Batch 08 — Boucle autonome

Objectif : orchestrer Market State + Portfolio State + Agent + Risk + Paper Broker, corréler les IDs, cadence, start/stop propre, timeouts et comportement sûr en erreur.

Le Risk Engine doit être invoqué avant toute exécution tradable ; `REJECT` ne déclenche rien et `HOLD` reste journalisé.

---

## Batch 09 — Persistance et journal d'audit

Objectif : PostgreSQL, schéma/migrations, cycles, décisions, RiskAssessment, intents, fills, métriques et reprise cohérente.

À décider : ORM, migrations, granularité de snapshots et rétention.

---

## Batch 10 — API FastAPI de contrôle

Objectif : état moteur, portefeuille, décisions, risque, performance, réglages autorisés, start/stop si retenu et WebSocket utiles au cockpit.

---

## Batch 11 — Frontend cockpit

Objectif : dashboard marché/portefeuille/décisions/trades PAPER/performance/état système. Le frontend reste indépendant du moteur.

---

## Batch 12 — Analytics, P&L et expérimentation reproductible

Objectif : P&L brut/net, drawdown, frais, spread/slippage, exposition, nombre de trades, quotidien/cumulé et replay.

Ce batch fournira les données qui permettront d'introduire honnêtement des limites Risk de drawdown/daily loss si elles sont décidées.

---

## Batch 13 — Expérimentation agressivité 1–10

Objectif : figer un mapping versionné et comparer plusieurs niveaux sur un protocole identique. Aucune agressivité ne contourne les limites absolues Risk.

---

## Batch 14 — Comparaison Luna / Sol

Objectif : protocole comparable entre Luna et Sol, mêmes snapshots, RiskPolicy, coûts PAPER et configuration expérimentale.

---

## Batch 15 — Préparation éventuelle du LIVE

**Hors périmètre jusqu'à décision explicite.**

Audit de readiness, adaptateur privé Kraken, réconciliation, permissions minimales, aucun retrait, garde-fous LIVE et activation volontaire. Sa présence dans la roadmap ne vaut pas autorisation de trading réel.

---

## Dépendances principales

```text
00 Docs
  |
01 Bootstrap
  |
02 Domain contracts
  |
03 Kraken data
  |
04 Market State
  |
05 Portfolio + Paper Broker
  |
06 Risk Engine
  |
07 Luna Agent
  |
08 Autonomous Loop
  |
09 Persistence
  |
10 API
  |
11 Frontend
  |
12 Analytics
  |
13 Aggressiveness experiments
  |
14 Luna/Sol comparison
  |
15 Optional LIVE readiness
```

---

## Décisions encore ouvertes

- capital PAPER et devise de référence produit ;
- univers initial de paires ;
- cadence de décision ;
- valeurs produit du max order notional, whitelist et stale métier ;
- éventuelles limites d'exposition ;
- drawdown/daily loss une fois les données disponibles ;
- mapping agressivité ;
- valeurs de référence fee/spread/slippage PAPER ;
- ORM/migrations/rétention ;
- frontière de journée ;
- auth/déploiement ;
- activation éventuelle du LIVE.
