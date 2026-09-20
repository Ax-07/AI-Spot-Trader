# 09 — Roadmap de développement

## 1. Règle de lecture

La roadmap décrit l'ordre de construction. Un batch n'est considéré **intégré** qu'après validation locale puis commit/push confirmé sur `main`.

---

## Batch 00 — Documentation initiale

**État : intégré.**

Vision, invariants, architecture cible et méthode de travail.

---

## Batch 01 — Bootstrap backend/frontend

**État : intégré.**

FastAPI/Python et Next.js initialisés en applications séparées.

---

## Batch 02 — Contrats domaine et configuration

**État : intégré.**

Pydantic strict, horloge injectable, ports, PAPER, Luna/Sol et agressivité 1–10.

---

## Batch 03 — Kraken Market Data

**État : intégré.**

APIs publiques Kraken SPOT, normalisation et aucune clé privée.

---

## Batch 04 — Market State

**État : intégré.**

Market State déterministe, multi-horizon, historique borné et sans look-ahead.

---

## Batch 05 — Portfolio State + Paper Broker

**État : intégré.**

Ledger PAPER mémoire, état initial injecté, pricing explicite, frais/spread/slippage.

---

## Batch 06 — Risk Engine

**État : intégré.**

ALLOW/MODIFY/REJECT, HOLD audité, checks déterministes, seul Risk produit `ExecutionIntent`.

---

## Batch 07 — Agent Luna

**État : intégré.**

Provider Luna/Sol unique, prompt versionné, Structured Outputs stricts, aucune exécution directe.

---

## Batch 08 — Boucle autonome PAPER

**État : intégré.**

`TradingCycleRunner.run_cycle()` + `TradingEngine`, cycles séquentiels, timeouts bornés et stop coopératif.

---

## Batch 09 — Persistance et journal d'audit

**État : intégré fonctionnellement.**

SQLAlchemy async + PostgreSQL + `asyncpg` + Alembic, journal durable corrélé par `cycle_id`, idempotence et transactions.

Limite conservée : pas encore d'exactly-once global entre ledger mémoire et commit PostgreSQL.

---

## Batch 10 — API FastAPI de contrôle et d'observation

**État : intégré.**

### Objectif

Fournir au futur cockpit une façade REST cohérente sans déplacer l'autorité du backend ni du Risk Engine.

### Périmètre intégré

- état moteur ;
- start/stop uniquement via le `TradingEngine` canonique injecté ;
- portefeuille PAPER courant ;
- historique durable des cycles ;
- détail d'un cycle ;
- décisions Agent ;
- assessments Risk ;
- intents/fills ;
- dernière erreur technique sanitizée ;
- dernier `MarketState` durable disponible ;
- pagination, ordre et filtres déterministes ;
- lifecycle DB FastAPI explicite.

### Décisions retenues

- modèles Pydantic HTTP dédiés ;
- `CycleAuditReader` + `SqlAlchemyCycleAuditQueryService` entre routes et ORM ;
- aucune nouvelle migration ;
- aucun démarrage automatique du moteur ;
- endpoints moteur/portfolio explicitement non configurés si leurs composants canoniques ne sont pas injectés ;
- DB absente/indisponible gérée sans fuite de secrets ;
- pas de WebSocket tant qu'aucun bus d'événements canonique n'existe.

### Validation d'intégration

Validation locale confirmée :

- `pytest backend` : **222 tests passés**, 2 warnings non bloquants ;
- Ruff : **All checks passed** ;
- mypy : **70 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push confirmé : `e6bcfd4dd345c934769b2f90fa7822232a80dd80`.

---

## Batch 11 — Frontend cockpit

**État : futur.**

Dashboard marché, portefeuille, décisions, Risk, exécutions, erreurs et lifecycle. Le frontend reste un client du backend, jamais le propriétaire du moteur.

---

## Batch 12 — Analytics et expérimentation reproductible

**État : futur.**

P&L brut/net, drawdown, frais, spread/slippage, exposition, trades, métriques quotidiennes/cumulées et replay.

---

## Batch 13 — Expérimentation agressivité 1–10

**État : futur.**

Figer un mapping versionné et comparer les niveaux sous protocole identique. Aucune agressivité ne contourne Risk.

---

## Batch 14 — Comparaison Luna / Sol

**État : futur.**

Comparer les modèles sur snapshots, RiskPolicy, coûts PAPER, prompts et configuration expérimentale identiques.

---

## Batch 15 — Préparation éventuelle du LIVE

**État : hors périmètre jusqu'à décision explicite.**

Readiness, adaptateur privé Kraken, réconciliation, permissions minimales sans retrait, garde-fous LIVE et activation volontaire séparée.

---

## Dépendances principales

```text
00 Docs
  |
01 Bootstrap
  |
02 Domain contracts
  |
03 Kraken public data
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
- valeurs produit des limites Risk ;
- limites avancées d'exposition/drawdown une fois les données disponibles ;
- mapping agressivité ;
- valeurs de référence fee/spread/slippage ;
- politique de rétention ;
- frontière de journée et P&L ;
- reconstruction du ledger et réconciliation après crash ;
- source d'événements et protocole d'un futur WebSocket ;
- auth/déploiement pour une exposition non locale ;
- éventuel LIVE.
