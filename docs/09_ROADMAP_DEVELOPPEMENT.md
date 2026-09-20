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

Fournir au cockpit une façade REST cohérente sans déplacer l'autorité du backend ni du Risk Engine.

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

- `pytest backend` : **222 tests passés**, 2 warnings non bloquants ;
- Ruff : **All checks passed** ;
- mypy : **70 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit fonctionnel : `e6bcfd4dd345c934769b2f90fa7822232a80dd80` ;
- commit documentaire post-intégration / HEAD audité : `f29c51545cd63763ea9fefbfd37d441e52850609`.

---

## Batch 11 — Frontend cockpit

**État : intégré.**

### Objectif

Remplacer le bootstrap Batch 01 par un cockpit Next.js réellement utilisable, exclusivement client des interfaces Batch 10.

### Périmètre intégré

- état backend et audit store ;
- état moteur et commandes Start/Stop ;
- portefeuille PAPER courant ;
- dernier marché durable ;
- dernier cycle et cycles récents ;
- décisions BUY/SELL/HOLD ;
- résultats Risk ALLOW/MODIFY/REJECT ;
- executions/intents et fills ;
- dernière erreur technique ;
- gestion explicite des 404, 503, listes vides, backend hors ligne et erreurs API génériques ;
- responsive desktop/mobile sans librairie de graphiques.

### Architecture retenue

- types TypeScript alignés sur `api/schemas.py` ;
- client HTTP centralisé sous `frontend/src/lib/api/` ;
- rewrite Next.js `/backend/:path*` vers `AI_SPOT_TRADER_BACKEND_URL` ;
- aucune configuration CORS backend nécessaire pour le développement standard ;
- polling de présentation toutes les 10 secondes, suspendu lorsque l'onglet n'est pas visible ;
- commandes lifecycle désactivées pendant leur exécution pour éviter les doubles clics ;
- aucune logique Agent/Risk/Broker/market data dans le frontend ;
- aucun WebSocket.

### Validation d'intégration

- `pnpm --dir frontend lint` : **réussi** ;
- `pnpm --dir frontend typecheck` : **réussi** ;
- `pnpm --dir frontend build` : **réussi** avec Next.js 16.3.3 ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- smoke test runtime : backend accessible, moteur non configuré, données vides/503 et backend hors ligne gérés proprement ;
- commit/push confirmé : `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7`.

---

## Batch 12 — Analytics et expérimentation reproductible

**État : patch préparé, validation locale requise, non intégré.**

### Objectif du patch

Mesurer les performances PAPER honnêtement à partir des faits durables sans modifier la stratégie ni réécrire les décisions.

### Périmètre préparé

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
- version de calcul et digest SHA-256 des faits sources pour vérifier la reproductibilité du recalcul.

### Architecture proposée

- reducer `analytics.paper` pur, sans I/O ni horloge courante ;
- `SqlAlchemyPaperAnalyticsQueryService` en lecture seule au-dessus du journal Batch 09 ;
- aucune nouvelle table, vue matérialisée ou migration ;
- valorisation historique au `MarketState.last_price` du cycle concerné uniquement ;
- refus explicite d'une continuité portefeuille incohérente ou d'un actif non valorisable ;
- frontend strictement présentatif, sans recalcul métier.

### Conventions proposées

- P&L net = equity courante marquée - equity initiale durable ;
- P&L brut = P&L net + frais + spread + slippage cumulés ;
- drawdown = baisse de l'equity nette depuis son plus haut historique ;
- exposition = valeur des positions / equity lorsque l'equity est positive ;
- trade = exécution avec fill ; HOLD/REJECT ne sont pas des trades ;
- jours = UTC ;
- cycles FAILED comptés et valorisés seulement lorsque leurs faits permettent un replay déterministe.

### Limite de reproductibilité

Le Batch 12 reproduit **les métriques** à partir des faits immuables. Il ne prétend pas encore rejouer une décision LLM sous un manifeste complet modèle/prompt/RiskPolicy/coûts : cette expérimentation contrôlée reste le périmètre des Batches 13/14.

### Validation effectuée pendant préparation

- test ciblé `backend/tests/test_analytics.py` : **6 tests réussis**.

La suite backend complète, Ruff, mypy, lint/typecheck/build frontend, `git diff --check` sur le repository réel et le smoke test runtime/PostgreSQL restent à exécuter localement avant intégration.

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
- limites avancées d'exposition/drawdown utilisées comme **contraintes Risk** ;
- mapping agressivité ;
- valeurs de référence fee/spread/slippage ;
- politique de rétention ;
- reconstruction du ledger et réconciliation après crash ;
- manifeste expérimental complet pour rejouer/comparer les décisions ;
- source d'événements et protocole d'un futur WebSocket ;
- auth/déploiement pour une exposition non locale ;
- éventuel LIVE.
