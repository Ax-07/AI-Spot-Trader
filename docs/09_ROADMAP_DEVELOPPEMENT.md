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

Façade REST d'observation/lifecycle, query service durable, start/stop uniquement sur le moteur canonique, aucune logique Agent/Risk/Broker parallèle.

---

## Batch 11 — Frontend cockpit

**État : intégré.**

Cockpit Next.js/shadcn, polling présentatif borné, vues moteur/portfolio/marché/cycles/Risk/exécutions, aucune logique stratégique frontend.

---

## Batch 12 — Analytics et expérimentation reproductible

**État : intégré.**

### Objectif

Mesurer les performances PAPER honnêtement à partir des faits durables sans modifier la stratégie ni réécrire les décisions.

### Périmètre intégré

- P&L brut et net ;
- frais, spread et slippage cumulés depuis les fills persistés ;
- equity et drawdown ;
- exposition mark-to-market ;
- nombre de trades BUY/SELL effectivement fillés ;
- comptages HOLD, REJECT, MODIFY et FAILED ;
- séries temporelles par cycle ;
- performance quotidienne UTC et cumulée ;
- endpoint `GET /api/v1/analytics` ;
- panneau analytics dans le cockpit ;
- version de calcul et digest SHA-256 des faits sources.

### Limite de reproductibilité

Le Batch 12 reproduit **les métriques** à partir des faits immuables. Il ne prétend pas rejouer une décision LLM sous protocole complet.

---

## Batch 13 — Expérimentation agressivité 1–10

**État : intégré** au commit fonctionnel `1747beb5efd1fe9763bc9b2d23f3a115575daaec`.

### Objectif

Figer un protocole expérimental explicite, versionné, reproductible et mesurable pour l'agressivité `1..10`, sans déplacer l'autorité stratégique vers un bot déterministe et sans contourner Risk.

### Périmètre intégré

- mapping **discret** `aggressiveness-map-v1` ;
- dix postures stratégiques explicites, sans seuil Risk ni multiplicateur d'exécution ;
- `AggressivenessContext` persisté dans `AgentInput` ;
- prompt Agent `agent-strategy-v2` ;
- manifeste `paper-experiment-v1` avec digest SHA-256 ;
- identité enregistrée : niveau/mapping, modèle, prompt, univers, `RiskPolicy`, coûts PAPER, source/dataset, fenêtre éventuelle et version analytics ;
- aucune nouvelle table ni migration : le journal Batch 09 persiste déjà `AgentInput` en JSON/JSONB ;
- comparaison factuelle de plusieurs niveaux à partir des `PaperAnalyticsReport` Batch 12 existants ;
- comparaison refusée si un champ contrôlé hors agressivité diffère ;
- aucune API ni modification frontend dans ce batch.

### Reproductibilité

Le digest du manifeste identifie le protocole/configuration. Il ne garantit pas une sortie LLM bit-à-bit identique. Pour isoler strictement l'agressivité, les runs doivent partager les mêmes faits sources ; un dataset figé avec `source_digest` identique est préférable à deux passages live successifs.

### Validation d'intégration

- Python local : **3.13.14** ;
- `pytest backend` : **249 tests passés**, 2 warnings externes ;
- Ruff : **All checks passed** ;
- mypy : **81 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push confirmé : `1747beb5efd1fe9763bc9b2d23f3a115575daaec` ;
- working tree propre après push.

---

## Batch 14 — Comparaison Luna / Sol

**État : intégré** au commit fonctionnel `dc60033f60bf5d98a68e6131a9320e575d46cc8d`.

### Objectif

Comparer GPT-5.6 Luna et GPT-5.6 Sol avec **le modèle comme unique variable contrôlée**, en réutilisant le provider Agent canonique, le Risk Engine existant, les analytics PAPER Batch 12 et la persistance/manifeste Batch 13.

### Périmètre intégré

- maintien de `paper-experiment-v1` pour les comparaisons d'agressivité existantes ;
- `paper-experiment-v2` avec `comparison_variable = LLM_MODEL` ;
- `experiment_group_digest` pour les champs contrôlés communs et `experiment_digest` comme identité complète du run ;
- `replicate_index` / `replicate_count` pour plusieurs réalisations par modèle ;
- `source_digest` obligatoire pour une identité de dataset figée ;
- refus de comparaison si agressivité, prompt, RiskPolicy, coûts PAPER, dataset/source, univers, fenêtre, version analytics ou nombre de répétitions diffèrent ;
- exigence de toutes les répétitions `1..N` pour Luna et Sol ;
- comparaison factuelle basée uniquement sur les `PaperAnalyticsReport` Batch 12 ;
- aucun score composite, ranking ou sélection automatique d'un « meilleur modèle » ;
- compatibilité des payloads `paper-experiment-v1` préservée ;
- aucune migration DB, API ou modification frontend.

### Décisions expérimentales

- Un dataset/replay figé est **nécessaire pour une comparaison strictement appariée** ; le v2 impose son `source_digest`, mais le moteur de replay concret reste hors de ce batch.
- Le non-déterminisme éventuel du LLM est traité par répétitions explicites, pas par un faux seed fournisseur.
- Les répétitions sont conservées brutes ; aucune agrégation de dispersion n'est inventée dans le batch.
- L'absence d'une répétition annoncée pour l'un des modèles invalide la comparaison afin de limiter le cherry-picking post-hoc.

### Validation d'intégration

- `pytest backend` : **266 tests passés**, 2 warnings externes ;
- Ruff : **All checks passed** ;
- mypy : **81 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push confirmé : `dc60033f60bf5d98a68e6131a9320e575d46cc8d` ;
- working tree propre après push ;
- préparation ChatGPT : **34 tests ciblés** et `py_compile` réussis.

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
- limites avancées d'exposition/drawdown utilisées comme **contraintes Risk** ;
- valeurs de référence fee/spread/slippage ;
- politique de rétention ;
- reconstruction du ledger et réconciliation après crash ;
- choix/format concret d'un dataset/replay canonique pour exécuter les comparaisons strictement appariées ;
- statistiques descriptives éventuelles de dispersion des répétitions LLM ;
- source d'événements et protocole d'un futur WebSocket ;
- auth/déploiement pour une exposition non locale ;
- éventuel LIVE.
