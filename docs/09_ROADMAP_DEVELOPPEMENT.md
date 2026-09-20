# 09 — Roadmap de développement

## 1. Principes

La roadmap est organisée en **batches cohérents, limités et testables**. Chaque batch doit :

- partir du HEAD GitHub `main` resynchronisé ;
- auditer les composants existants ;
- ne modifier que ce qui est nécessaire ;
- inclure des tests adaptés ;
- mettre à jour la documentation concernée ;
- livrer un ZIP root-relative si plusieurs fichiers changent ;
- distinguer tests réellement exécutés et tests à lancer localement.

La séquence ci-dessous est proposée. Les invariants du Project Master restent confirmés, mais l'ordre peut évoluer si un audit technique le justifie.

---

## Batch 00 — Documentation initiale

**Statut : intégré sur `main`.**

Objectif : établir la source de vérité documentaire, fixer les invariants, expliciter les zones à décider et préparer la roadmap.

---

## Batch 01 — Bootstrap du projet

**Statut : intégré sur `main` au commit `d9af0ca293dd9f2712969b246e394c4a8c188b5e` (`feat: bootstrap backend and frontend`).**

Intégré : backend Python installable, FastAPI minimal, configuration typée, lifecycle asynchrone, pytest/Ruff/mypy, frontend Next.js/TypeScript/shadcn/Tailwind, `pnpm`, `.env.example` sans secret.

Validation locale Windows confirmée : Python `3.13.14`, `pytest` 4/4, Ruff OK, mypy OK et validations frontend OK.

---

## Batch 02 — Contrats de domaine et configuration

**Statut : intégré sur `main` au commit `bff0f8b03740da4a01072af90111a2e5d9f208ef` (`feat: add domain contracts and configuration`).**

Intégré :

- package `ai_spot_trader.domain` ;
- enums `BUY|SELL|HOLD`, `PAPER`, `ALLOW|MODIFY|REJECT` et modèles Luna/Sol ;
- contrats Pydantic stricts initiaux ;
- UUID explicites ;
- timestamps UTC aware ;
- horloge injectable ;
- ports `MarketDataSource`, `LLMProvider`, `Broker` ;
- PAPER uniquement ; Luna par défaut ; Sol sélectionnable ; agressivité 1–10.

Validation locale Windows confirmée avant intégration : Python `3.13.14`, `pytest` 20/20, Ruff OK et mypy OK.

---

## Batch 03 — Kraken Market Data

**Statut : intégré sur `main` au commit `e7ac37955f08853024528fa9b9e10b5a75e05e3b` (`feat: add Kraken public market data`).**

Intégré :

- package `ai_spot_trader.integrations.kraken` ;
- REST public `AssetPairs` avec `assetVersion=1` ;
- normalisation des alias Kraken vers symbole canonique ;
- WebSocket Spot v2 `ticker` ;
- parsing `last` / `symbol` / `timestamp` ;
- heartbeat/messages système ignorés ;
- reconnexion bornée/configurable ;
- fermeture propre ;
- stale detection technique optionnelle via `Clock` ;
- erreurs fournisseur dédiées ;
- `httpx` et `websockets` en runtime ;
- aucune clé, API privée, ordre ou logique de trading.

Validation locale Windows finale avant intégration :

- Python `3.13.14` ;
- `pytest` : **40 tests passés** ;
- Ruff : **OK** ;
- mypy : **OK sur 21 fichiers source** ;
- `git diff --check` : aucune erreur ;
- 2 warnings FastAPI/Starlette dans les dépendances, sans échec ;
- aucun test réseau Kraken requis par défaut.

---

## Batch 04 — Market State

**Statut : intégré sur `main` au commit `73acc4758427ea7575ddf0a43505e1c95fab5e9c` (`feat: add deterministic market state`).**

Intégré :

- `MarketObservation` fournisseur-agnostique ;
- port `MarketObservationSource` ;
- adapter Kraken capable d'émettre l'observation normalisée ;
- package `ai_spot_trader.market` sans dépendance Kraken ;
- `MarketStateBuilder` mono-symbole ;
- historique mémoire borné à 10 000 observations par défaut ;
- ordre temporel strict, doublons/hors ordre rejetés ;
- horizons 5 min et 30 min par défaut, surchargeables ;
- min/max/amplitude, return simple et volatilité réalisée simple en `Decimal` ;
- fenêtres vides/partielles explicites ;
- âge des données et évaluation stale optionnelle avec seuil injecté ;
- no look-ahead explicite pour tout `build(as_of=T)` ;
- `MarketState` enrichi par `MarketContext` optionnel ;
- aucune interpolation, aucun label de marché, aucun `BUY/SELL/HOLD`, aucun Risk Engine, aucun LLM.

Validation locale Windows finale avant intégration :

- Python `3.13.14` ;
- `pytest` : **59 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **OK sur 24 fichiers source** ;
- `git diff --check` : aucune erreur ;
- uniquement les warnings habituels LF → CRLF ;
- 2 warnings FastAPI/Starlette dans les dépendances, sans échec ;
- aucun test réseau requis ;
- working tree propre après commit/push.

Frontière : le Batch 04 consomme uniquement des observations déjà normalisées ; il ne parse aucun payload Kraken.

---

## Batch 05 — Portfolio State + Paper Broker

**Statut : validation locale complète réussie ; intégration Git en attente.**

Objectif : portefeuille PAPER canonique, état mutable mémoire, exécution simulée déterministe, frais/spread/slippage auditables et invariant « pas de vente non détenue ».

Implémentation du patch :

- `PortfolioState` valide l'unicité des actifs et interdit qu'un même actif apparaisse simultanément comme balance et position ;
- `balances` sont la source canonique des actifs de règlement disponibles ;
- `positions` sont la source canonique des quantités détenues et disponibles à la vente ;
- `PaperPortfolioLedger` mémoire construit exclusivement depuis un état initial injecté ;
- aucun capital ou devise produit globale par défaut ;
- mutations BUY/SELL copy-on-write sans état partiellement appliqué ;
- `PaperBroker` derrière le port canonique `Broker` ;
- évolution du port en `Broker.execute(execution_intent, market_state)` afin de rendre le pricing explicite et d'interdire tout lookup réseau caché ;
- fill immédiat complet ou exception métier explicite ;
- aucun order book simulé, partial fill complexe, limite, pending order ou hasard ;
- `PaperExecutionCostModel` injecté : `fee_rate`, `spread_bps`, `slippage_bps` ;
- `spread_bps` = impact adverse par côté, pas spread bid/ask total ;
- BUY : `price = reference * (1 + spread + slippage)` ;
- SELL : `price = reference * (1 - spread - slippage)` ;
- frais calculés sur le notional exécuté ;
- `Fill` enrichi avec contexte de pricing et décomposition des coûts ;
- rejet d'un `MarketState` plus récent que l'`ExecutionIntent` ;
- aucune dépendance Kraken dans `portfolio` ou `broker` ;
- aucune nouvelle dépendance runtime ;
- aucune variable d'environnement Batch 05 ;
- aucune base de coût/P&L complet : les fills auditables conservent les données nécessaires au futur Batch Analytics.

Validation locale Windows finale avant intégration : `pytest backend` **92/92**, Ruff **All checks passed**, mypy **Success: no issues found in 40 source files**, `git diff --check` sans erreur ; uniquement les warnings LF → CRLF habituels et 2 warnings FastAPI/Starlette sans échec. Aucun test réseau requis. Validation complémentaire ChatGPT : Python `3.13.5`, suite ciblée **64/64**, `compileall` OK et lignes Python du patch `<= 100` OK.

Tests critiques couverts : état initial explicite, snapshot UTC, BUY/SELL, cash/position insuffisants, vente non détenue, frais, spread, slippage, combinaison des coûts, `Decimal`, atomicité, symbol mismatch, pricing futur, HOLD/LIVE impossibles, corrélation des fills, déterminisme et absence de dépendance Kraken.

---

## Batch 06 — Risk Engine

Objectif : autorité finale déterministe, `ALLOW` / `MODIFY` / `REJECT`, limites configurables et snapshot des raisons/limites appliquées.

À décider : limites numériques, mapping initial de l’agressivité 1–10 et règle métier stale réellement appliquée par le Risk Engine.

Tests : taille/exposition, vente non couverte, stale market, drawdown/perte si retenus, impossibilité pour l'agressivité de contourner une limite absolue.

---

## Batch 07 — Agent Luna

Objectif : provider Luna derrière le port LLM, prompt/contrat versionné, sortie structurée validée et aucune exécution directe.

Tests : provider mocké, réponses invalides, actions inconnues, BUY/SELL/HOLD et vérification qu'une sortie invalide n'atteint pas le broker.

---

## Batch 08 — Boucle autonome

Objectif : orchestrer Market State + Portfolio State + Agent + Risk + Paper Broker, cycle IDs, cadence, start/stop propre, timeouts/retries et comportement sûr en erreur.

Critère : plusieurs cycles PAPER tournent sans frontend ; `HOLD` inclus ; aucune dépendance au cockpit.

---

## Batch 09 — Persistance et journal d'audit

Objectif : PostgreSQL, schéma/migrations, cycles, décisions, risk assessments, fills, métriques et reprise cohérente des données nécessaires.

À décider : ORM, migrations, rétention, snapshots.

---

## Batch 10 — API FastAPI de contrôle

Objectif : exposer état moteur, portefeuille, décisions, performance, réglages autorisés, start/stop si retenu et WebSocket utiles au cockpit.

---

## Batch 11 — Frontend cockpit

Objectif : compléter le bootstrap Next.js, dashboard, marché, portefeuille, décisions, trades PAPER, performance, état système et réglages autorisés.

Critère central : arrêter/redémarrer le frontend ne change pas l'état du moteur backend.

---

## Batch 12 — Analytics, P&L et expérimentation reproductible

Objectif : P&L brut/net, drawdown, frais, spread/slippage, exposition, nombre de trades, quotidien/cumulé, export/vue d'expérience et premières capacités de replay si les données le permettent.

Tests : fixtures comptables, cohérence brut/net, frontières de journée, replay sans données futures.

---

## Batch 13 — Expérimentation agressivité 1–10

Objectif : figer un mapping versionné, tester plusieurs niveaux sur un protocole comparable et mesurer rendement, drawdown, turnover, coûts et comportement du Risk Engine.

Règle : aucun cherry-picking ; toutes les configurations sont documentées.

---

## Batch 14 — Comparaison Luna / Sol

Objectif : passer de Luna à Sol par configuration, exécuter un protocole comparable et mesurer performance, stabilité de format, latence et coût.

Aucune conclusion n'est présupposée.

---

## Batch 15 — Préparation éventuelle du LIVE

**Hors périmètre jusqu'à décision explicite.**

Objectif potentiel : audit de readiness, adaptateur privé Kraken, réconciliation, permissions minimales, aucun retrait, garde-fous LIVE, mode explicite, tests et checklist.

Sa présence dans la roadmap ne vaut pas autorisation de trading réel.

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

## Décisions à prendre au fil de la roadmap

À consigner lorsqu'elles deviennent canoniques :

- capital PAPER ;
- devise de référence produit ;
- univers initial ;
- cadence ;
- éventuelle évolution des horizons 5 min / 30 min ;
- données marché supplémentaires ;
- seuil métier de fraîcheur ;
- limites de risque ;
- mapping agressivité ;
- valeurs de référence expérimentales pour fee/spread/slippage PAPER ;
- éventuelle évolution du modèle de fill au-delà du full fill immédiat ;
- ORM/migrations ;
- auth cockpit ;
- déploiement ;
- frontière de journée ;
- activation éventuelle du LIVE.
