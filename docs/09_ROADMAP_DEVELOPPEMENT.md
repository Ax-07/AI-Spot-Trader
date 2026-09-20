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

Validation locale Windows finale confirmée avant intégration : **92 tests**, Ruff OK, mypy OK sur 40 fichiers source, `git diff --check` sans erreur.

---

## Batch 06 — Risk Engine

**Statut : intégré sur `main` au commit `d3271d6404ea2af38a42ff09e5a1df1eed5e141e` (`feat: add deterministic risk engine`).**

Intégré :

- `DecisionCandidate.proposed_quantity` obligatoire pour BUY/SELL, absente pour HOLD ;
- `RiskAssessment` avec quantité demandée/autorisée, limites évaluées et raisons structurées ;
- package canonique `ai_spot_trader.risk` ;
- `RiskPolicy` explicitement injectée ;
- sorties `ALLOW`, `MODIFY`, `REJECT` ;
- `MODIFY` limité à une réduction de quantité ;
- HOLD audité sans `ExecutionIntent` ;
- symboles canoniques partagés via `domain.symbols` ;
- whitelist, stale métier et max order notional optionnels ;
- BUY contrôlé avec coût PAPER prévisible complet ;
- SELL borné par la position disponible ;
- snapshots futurs rejetés ;
- aucune stratégie algorithmique introduite.

Validation locale Windows finale confirmée avant intégration :

- `pytest backend` : **131 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 47 source files** ;
- `git diff --check` : aucune erreur ;
- warnings LF → CRLF habituels uniquement ;
- 2 warnings FastAPI/Starlette sans échec.

---

## Batch 07 — Agent Luna

**Statut : intégré sur `main` au commit `caff3851d8299630f328b955c69eb31eb11baef0` (`feat: add Luna agent provider`).**

Objectif : implémenter le premier provider LLM canonique derrière `LLMProvider` sans créer de chemin d'exécution direct.

Intégré :

- package `ai_spot_trader.agent` ;
- `OpenAIDecisionProvider` commun Luna/Sol ;
- OpenAI Responses API avec Structured Outputs stricts ;
- prompt versionné `agent-luna-v1` ;
- sortie stratégique limitée à action/symbole/quantité/rationale ;
- UUID/timestamp/cycle contrôlés par l'application ;
- symbole strictement limité au `MarketState` fourni ;
- parsing `Decimal` sans réparation/coercition silencieuse ;
- erreurs transport / fournisseur / validation / contrat séparées ;
- clé OpenAI via `SecretStr` et environnement ;
- aucun retry automatique ;
- aucun import Risk/Broker/Kraken/FastAPI dans l'agent ;
- aucun nouvel appel marché ;
- aucune nouvelle dépendance runtime : réutilisation de `httpx`.

Validation ChatGPT réellement exécutée sur le patch :

- suite ciblée Agent/OpenAI/configuration : **42 tests passés** ;
- aucun réseau réel ;
- `compileall` : OK ;
- aucune ligne Python > 100 caractères ;
- aucun espace de fin de ligne détecté.

Validation locale Windows finale confirmée :

- `pytest backend` : **168 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 54 source files** ;
- `git diff --check` : aucune erreur ;
- warnings LF → CRLF habituels uniquement ;
- 2 warnings FastAPI/Starlette sans échec.

---

## Batch 08 — Boucle autonome

**Prochaine étape prévue.**

Objectif : orchestrer `MarketState + PortfolioState + Agent + Risk + Paper Broker`, corréler les IDs, définir cadence/start/stop, timeouts et comportement sûr en erreur.

Le pipeline devra être explicite :

```text
Agent -> DecisionCandidate -> Risk -> ExecutionIntent éventuel -> Paper Broker
```

`REJECT` ne déclenche rien ; `HOLD` reste journalisé ; aucune sortie LLM ne contourne Risk.

---

## Batch 09 — Persistance et journal d'audit

Objectif : PostgreSQL, schéma/migrations, cycles, décisions, `RiskAssessment`, intents, fills, métriques et reprise cohérente.

À décider : ORM, migrations, granularité des snapshots et rétention.

---

## Batch 10 — API FastAPI de contrôle

Objectif : état moteur, portefeuille, décisions, risque, performance, réglages autorisés, start/stop si retenu et WebSocket utiles au cockpit.

---

## Batch 11 — Frontend cockpit

Objectif : dashboard marché/portefeuille/décisions/trades PAPER/performance/état système. Le frontend reste indépendant du moteur.

---

## Batch 12 — Analytics, P&L et expérimentation reproductible

Objectif : P&L brut/net, drawdown, frais, spread/slippage, exposition, nombre de trades, quotidien/cumulé et replay.

Ce batch fournira les données nécessaires à d'éventuelles limites Risk de drawdown/daily loss.

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
- cadence de décision ;
- valeurs produit du max order notional, whitelist et stale métier ;
- éventuelles limites d'exposition ;
- drawdown/daily loss une fois les données disponibles ;
- mapping agressivité ;
- valeurs expérimentales fee/spread/slippage ;
- ORM/migrations/rétention ;
- frontière de journée ;
- auth/déploiement ;
- activation éventuelle du LIVE.
