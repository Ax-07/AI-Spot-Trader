# 09 — Roadmap de développement

Cette roadmap découpe AI Spot Trader en batches cohérents, limités et testables. Un batch n'est considéré comme intégré qu'après validation locale et commit/push confirmés sur `main`.

---

## Batch 00 — Documentation initiale

**Statut : intégré sur `main`.**

Vision, architecture cible, responsabilités Agent/Risk/Broker, roadmap et décisions initiales.

---

## Batch 01 — Bootstrap backend/frontend

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

`MarketObservation`, `MarketStateBuilder`, historique borné, horizons multi-fenêtres, statistiques `Decimal`, fraîcheur descriptive et no-look-ahead.

Validation locale Windows finale : **59 tests**, Ruff OK, mypy OK sur 24 fichiers source, `git diff --check` sans erreur.

---

## Batch 05 — Portfolio State + Paper Broker

**Statut : intégré sur `main` au commit `c24551d36a863abbb5fdb86b79658b235c852772` (`feat: add paper portfolio and broker`).**

Intégré : ledger PAPER mémoire, rôles `balances`/`positions`, mutations atomiques, Paper Broker full-fill, pricing via `MarketState` explicite et coûts PAPER `Decimal` injectés.

Validation locale Windows finale : **92 tests**, Ruff OK, mypy OK sur 40 fichiers source, `git diff --check` sans erreur.

---

## Batch 06 — Risk Engine

**Statut : intégré sur `main` au commit `d3271d6404ea2af38a42ff09e5a1df1eed5e141e` (`feat: add deterministic risk engine`).**

Intégré : sizing stratégique dans `DecisionCandidate`, `RiskAssessment`, `RiskPolicy`, ALLOW/MODIFY/REJECT, HOLD audité, intent créé uniquement par Risk, contrôles de symbole/chronologie/cash/position et estimation PAPER partagée.

Validation locale Windows finale :

- `pytest backend` : **131 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 47 source files** ;
- `git diff --check` : aucune erreur.

---

## Batch 07 — Agent Luna

**Statut : intégré sur `main` au commit `caff3851d8299630f328b955c69eb31eb11baef0` (`feat: add Luna agent provider`).**

Intégré : `OpenAIDecisionProvider` commun Luna/Sol, Responses API, Structured Outputs stricts, prompt `agent-luna-v1`, sortie stratégique limitée, IDs/timestamps applicatifs, symbole limité au snapshot, erreurs distinctes et aucun chemin direct vers Risk/Broker/Kraken.

Commit documentaire post-intégration : `6415064b0f9bb0ee625cc42e8209cdf4388167e0` (`docs: record Batch 07 integration`).

Validation locale Windows finale :

- `pytest backend` : **168 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 54 source files** ;
- `git diff --check` : aucune erreur ;
- warnings LF → CRLF habituels et 2 warnings FastAPI/Starlette sans échec.

---

## Batch 08 — Boucle autonome

**Statut : patch préparé dans cette livraison, non encore intégré.**

HEAD intégré de départ audité : `6415064b0f9bb0ee625cc42e8209cdf4388167e0`.

Objectif : orchestrer explicitement `MarketState + PortfolioState + Agent + Risk + Paper Broker`, fournir un cycle testable et le répéter de manière strictement séquentielle.

Patch préparé :

- package `ai_spot_trader.trading` ;
- `TradingCycleRunner.run_cycle()` comme primitive un-cycle ;
- `TradingEngine` comme boucle autonome séquentielle ;
- `cycle_id` via factory injectable ;
- même `MarketState` pour Agent/Risk/Broker ;
- même `PortfolioState` pré-cycle pour Agent/Risk ;
- aucun refresh marché caché ;
- verrou de cycle partagé entre appels manuels et loop ;
- HOLD traverse Risk et n'appelle jamais Broker ;
- REJECT traité comme résultat métier normal ;
- MODIFY/ALLOW transmettent uniquement l'`ExecutionIntent` produit par Risk ;
- `TradingCycleResult` mémoire pour audit futur ;
- erreurs techniques par étape, sans faux HOLD ;
- timeouts explicites Market/Agent/Broker via `asyncio.timeout` ;
- Risk sans timeout artificiel ;
- cadence explicitement injectée et positive ;
- aucun rattrapage de cadence par concurrence ;
- start double interdit ;
- stop coopératif et réveil immédiat pendant l'attente de cadence ;
- `AppRuntime` arrête un moteur injecté au shutdown FastAPI ;
- aucun démarrage automatique de trading ;
- aucune valeur produit de paire/capital/cadence/Risk/coûts inventée ;
- aucune persistance durable, aucune API de contrôle trading, aucun frontend et aucun LIVE.

Validation réellement exécutée dans l'environnement ChatGPT :

- `pytest -q backend/tests/test_trading_engine.py` : **34 tests passés** ;
- `pytest -q backend/tests/test_health.py backend/tests/test_trading_engine.py` : **37 tests passés** ;
- aucun appel OpenAI/Kraken réel ;
- `compileall` ciblé : OK ; lignes Python <= 100 et espaces de fin de ligne : OK.

Validation locale Windows confirmée par l'utilisateur avant le correctif Ruff final :

- `pytest backend` : **203 tests passés** ;
- mypy : **Success: no issues found in 57 source files** ;
- `git diff --check` : aucune erreur ;
- 2 warnings de dépréciation FastAPI/Starlette sans échec ;
- Ruff a relevé uniquement `SIM105` dans `trading/engine.py` et un ordre d'imports dans `test_trading_engine.py`.

Le correctif de cette livraison traite ces deux défauts. Avant intégration, relancer au minimum :

```powershell
ruff check backend
pytest backend
```

Le Batch 08 ne devra être marqué intégré qu'après confirmation finale puis commit/push sur `main`.

---

## Batch 09 — Persistance et journal d'audit

**Prochaine étape après validation et intégration du Batch 08.**

Objectif : PostgreSQL, schéma/migrations, cycles, décisions, `RiskAssessment`, intents, fills, erreurs techniques, métriques et reprise cohérente.

À décider : ORM, migrations, granularité des snapshots, rétention, idempotence/réconciliation et stratégie de reprise après crash.

---

## Batch 10 — API FastAPI de contrôle

Objectif : état moteur, portefeuille, décisions, risque, performance, réglages autorisés, start/stop si retenu et WebSocket utiles au cockpit.

---

## Batch 11 — Frontend cockpit

Objectif : dashboard marché/portefeuille/décisions/trades PAPER/performance/état système. Le frontend reste indépendant du moteur.

---

## Batch 12 — Analytics, P&L et expérimentation reproductible

Objectif : P&L brut/net, drawdown, frais, spread/slippage, exposition, nombre de trades, quotidien/cumulé et replay.

---

## Batch 13 — Expérimentation agressivité 1–10

Objectif : figer un mapping versionné et comparer plusieurs niveaux sur un protocole identique. Aucune agressivité ne contourne les limites absolues Risk.

---

## Batch 14 — Comparaison Luna / Sol

Objectif : protocole comparable entre Luna et Sol, mêmes snapshots, RiskPolicy, coûts PAPER, versions de prompt et configuration expérimentale.

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
- valeur produit de cadence ;
- valeurs produit du max order notional, whitelist et stale métier ;
- éventuelles limites d'exposition ;
- drawdown/daily loss une fois les données disponibles ;
- mapping agressivité ;
- valeurs expérimentales fee/spread/slippage ;
- ORM/migrations/rétention ;
- frontière de journée ;
- reprise/réconciliation/idempotence ;
- auth/déploiement ;
- activation éventuelle du LIVE.
