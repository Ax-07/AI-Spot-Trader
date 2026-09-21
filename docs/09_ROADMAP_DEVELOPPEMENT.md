# 09 — Roadmap de développement

## 1. Règle de lecture

La roadmap décrit l'ordre de construction. Un batch n'est considéré **intégré** qu'après validation locale puis commit/push confirmé sur `main`.

---

## Batch 00 — Documentation initiale

**État : intégré.** Vision, invariants, architecture cible et méthode de travail.

---

## Batch 01 — Bootstrap backend/frontend

**État : intégré.** FastAPI/Python et Next.js initialisés en applications séparées.

---

## Batch 02 — Contrats domaine et configuration

**État : intégré.** Pydantic strict, horloge injectable, ports, PAPER, Luna/Sol et agressivité 1–10.

---

## Batch 03 — Kraken Market Data

**État : intégré.** APIs publiques Kraken SPOT, normalisation et aucune clé privée.

---

## Batch 04 — Market State

**État : intégré.** Market State déterministe, multi-horizon, historique borné et sans look-ahead.

---

## Batch 05 — Portfolio State + Paper Broker

**État : intégré.** Ledger PAPER mémoire, état initial injecté, pricing explicite, frais/spread/slippage.

---

## Batch 06 — Risk Engine

**État : intégré.** ALLOW/MODIFY/REJECT, HOLD audité, checks déterministes, seul Risk produit `ExecutionIntent`.

---

## Batch 07 — Agent Luna

**État : intégré.** Provider Luna/Sol unique, prompt versionné, Structured Outputs stricts, aucune exécution directe.

---

## Batch 08 — Boucle autonome PAPER

**État : intégré.** `TradingCycleRunner.run_cycle()` + `TradingEngine`, cycles séquentiels, timeouts bornés et stop coopératif.

---

## Batch 09 — Persistance et journal d'audit

**État : intégré fonctionnellement.** SQLAlchemy async + PostgreSQL + `asyncpg` + Alembic, journal durable corrélé par `cycle_id`, idempotence et transactions.

Limite conservée : pas encore d'exactly-once global entre ledger mémoire et commit PostgreSQL.

---

## Batch 10 — API FastAPI de contrôle et d'observation

**État : intégré.** Façade REST d'observation/lifecycle, query service durable, start/stop uniquement sur le moteur canonique, aucune logique Agent/Risk/Broker parallèle.

---

## Batch 11 — Frontend cockpit

**État : intégré.** Cockpit Next.js/shadcn, polling présentatif borné, vues moteur/portfolio/marché/cycles/Risk/exécutions, aucune logique stratégique frontend.

---

## Batch 12 — Analytics et expérimentation reproductible

**État : intégré.**

P&L brut/net, coûts, equity/drawdown, exposition, trades, compteurs HOLD/REJECT/MODIFY/FAILED, séries par cycle/daily UTC, endpoint analytics, panneau cockpit et digest/version reproductibles.

---

## Batch 13 — Expérimentation agressivité 1–10

**État : intégré** au commit fonctionnel `1747beb5efd1fe9763bc9b2d23f3a115575daaec`.

- `aggressiveness-map-v1` discret ;
- `AggressivenessContext` dans `AgentInput` ;
- prompt `agent-strategy-v2` ;
- `paper-experiment-v1` + digest ;
- identité du protocole : niveau/mapping, modèle, prompt, univers, Risk, coûts, source et analytics ;
- aucune migration ;
- comparaison factuelle de rapports Batch 12 ;
- aucun changement API/frontend.

Validation : **249 tests backend**, Ruff OK, mypy 81 fichiers, `git diff --check` OK, commit/push confirmé.

---

## Batch 14 — Comparaison Luna / Sol

**État : intégré** au commit fonctionnel `dc60033f60bf5d98a68e6131a9320e575d46cc8d`, suivi du commit documentaire `b2c74672744639f86c38e873f25d56c77f899c76`.

- maintien de `paper-experiment-v1` pour l'agressivité ;
- `paper-experiment-v2` avec `comparison_variable = LLM_MODEL` ;
- `experiment_group_digest` + `experiment_digest` ;
- répétitions `replicate_index/count` appariées Luna/Sol ;
- `source_digest` obligatoire ;
- comparaison factuelle via `PaperAnalyticsReport` ;
- aucun score/ranking/gagnant automatique ;
- aucune migration/API/frontend.

Validation : **266 tests backend**, Ruff OK, mypy 81 fichiers, `git diff --check` OK, commit/push confirmé.

---

## Batch 15 — Chat opérateur avec l'Agent

**État : intégré et validé — commit fonctionnel `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6`.**

### Objectif

Permettre à l'opérateur de dialoguer avec le même modèle Agent configuré pendant que le moteur PAPER reste actif, afin d'obtenir des explications sur décisions, marché, portefeuille, Risk, cycles et analytics, sans créer de voie alternative d'exécution.

### Périmètre intégré

- package `ai_spot_trader.chat` séparé du provider stratégique ;
- `OpenAIChatProvider` utilisant le même `LLMModel` Luna/Sol ;
- prompt `operator-chat-v1` ;
- REST uniquement : envoi message + lecture historique session ;
- contexte lu depuis runtime, portefeuille, journal durable et analytics canoniques ;
- ancrage optionnel sur un `cycle_id` historique ;
- distinction stricte entre `historical_cycle` et état courant ;
- historique chat mémoire seulement, borné, sans migration PostgreSQL ;
- redaction best-effort des secrets ;
- erreurs chat sanitizées et séparées des cycles `FAILED` ;
- panneau Chat Next.js et session UUID locale ;
- aucune commande lifecycle dans le code Chat.

### Invariants vérifiés par conception

```text
Market -> Agent -> DecisionCandidate -> Risk -> ExecutionIntent -> Paper Broker
```

reste le seul chemin d'exécution.

### Validation confirmée

Validation locale finale du 21 septembre 2026 :

- `pytest backend` : **277 tests passés**, 2 warnings externes ;
- Ruff : **All checks passed** ;
- mypy : **89 fichiers sans erreur** ;
- `pnpm lint` : **réussi** ;
- `pnpm typecheck` : **réussi** ;
- `pnpm build` : **réussi** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push fonctionnel : `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6`.

---

## Batch 15.1 — Composition runtime du premier essai PAPER réel

**État : intégré sur `main` au commit `4b9701f07854a943cf47a14287aadfdf4aa48232`.**

### Objectif

Assembler les composants déjà intégrés dans un composition root exécutable, sans créer de second orchestrateur et sans ouvrir de voie LIVE.

### Périmètre intégré

- `main:app` compose au lifespan le runtime PAPER complet mais laisse le moteur arrêté ;
- configuration explicite et fail-closed des valeurs du premier run ;
- Kraken public uniquement ;
- même modèle Luna/Sol pour Agent et Chat ;
- même `PaperExecutionCostModel` pour Risk et Broker ;
- même `PaperPortfolioLedger` pour moteur/API/Chat ;
- même PostgreSQL pour writer d'audit, lecteurs et analytics ;
- runner canonique enveloppé par `AuditedTradingCycleRunner` ;
- `POST /api/v1/engine/run-cycle` appelle seulement `TradingEngine.run_cycle()` ;
- fermeture ordonnée des ressources ;
- audit fail-closed après erreur durable.

### Validation réelle post-intégration

Le premier essai PAPER réel a confirmé un cycle manuel puis un smoke run autonome propres. Il a également révélé que le snapshot Kraken intégré restait minimal (`market_state.context = null`), ce qui a motivé le Batch 15.2.

---

## Batch 15.2 — Contexte marché multi-horizon pour les essais PAPER

**État : intégré sur `main`. Commit fonctionnel `97d529647179c6769a6bdc528b9d9f5e7c85c119` (`feat: add multi-horizon market context`), état documentaire finalisé par `bb1aa047157deb1b62d27de952fa53ec14992f09`.**

### Objectif

Rendre le `MarketState.context` du runtime PAPER canonique exploitable dès le premier cycle sans introduire de deuxième moteur de contexte.

### Périmètre intégré

- `MarketStateBuilder` existant devient la voie canonique de construction du snapshot Kraken ;
- horizons existants conservés : **5 min / 30 min** ;
- bootstrap descriptif via Kraken public OHLC **1 min** ;
- suppression systématique de la dernière bougie OHLC non clôturée ;
- clôtures historiques horodatées à leur disponibilité causale ;
- ticker WebSocket courant conservé comme dernier prix ;
- ordre strict, pas de look-ahead, fenêtres partielles explicites si historique insuffisant ;
- fraîcheur recontrôlée après la récupération historique ;
- erreurs fournisseur/timeout propagées par le stage Market ;
- aucune stratégie déterministe, aucun signal BUY/SELL/HOLD, aucun frontend, aucun LIVE.

### Validation confirmée

- tests ciblés Market State/Kraken/cycle canonique : **71 passés** ;
- suite complète : **306 passés**, 2 warnings externes ;
- Ruff : **All checks passed** ;
- mypy : **94 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- cycle PAPER réel `BTC/USDC` : `COMPLETED`, contexte non nul, fenêtres 5 min / 30 min complètes et rationale Agent exploitant effectivement ces horizons.

Les runs autonomes post-intégration ont toutefois montré que les tickers de chaque cycle étaient retenus avec les OHLC, ce qui faisait varier l'échantillonnage selon `trading_cadence_seconds`. Ce défaut est le périmètre du Batch 15.3.

---

## Batch 15.3 — Contexte marché indépendant de la cadence du moteur

**État : intégré sur `main` au commit fonctionnel `d0f6d46b9adb37117051a7a497a8d55075c41d32` (`fix: decouple market context from engine cadence`). Validation locale complète confirmée avant le push.**

### Objectif

Faire dépendre les statistiques descriptives du `MarketState.context` uniquement de la série marché à granularité fixe, et non du nombre de cycles exécutés.

### Architecture retenue

- `MarketStateBuilder` reste l'unique calculateur canonique ;
- son historique retenu devient explicitement la **série statistique** ;
- le ticker courant est transmis au build comme observation de snapshot non persistée ;
- `MarketState.last_price` et la fraîcheur restent basés sur le ticker courant ;
- les fenêtres sont ancrées par un `statistics_as_of` causal ;
- pour Kraken, `statistics_as_of` est la dernière clôture OHLC 1 minute retenue ;
- sans nouvelle bougie OHLC, les statistiques ne bougent pas artificiellement lors de snapshots supplémentaires ;
- quand une nouvelle bougie clôturée devient disponible, la série et son ancre avancent naturellement ;
- ordre temporel des tickers successifs contrôlé séparément ;
- aucun changement du runner, de l'Agent, du Risk Engine, du Broker, des ports, du REST Kraken privé ou du frontend.

### Validation exécutée par ChatGPT

- tests ciblés `test_market_state.py` + `test_kraken_market_data.py` : **38 passés** ;
- `compileall` des fichiers Python modifiés : **réussi** ;
- tests ajoutés pour snapshots répétés sans nouvelle OHLC, simulations 10 s / 120 s, ticker courant, fraîcheur, no-look-ahead, fenêtres partielles et ordre strict.

Validation complète exécutée localement par l'utilisateur avant le push : **315 tests passés**, 2 warnings externes ; Ruff **All checks passed** ; mypy **94 fichiers sans erreur** ; `git diff --check` sans erreur, warnings LF -> CRLF uniquement.

---

## Batch 16 — Préparation éventuelle du LIVE

**État : hors périmètre jusqu'à décision explicite.**

Readiness, adaptateur privé Kraken, réconciliation, permissions minimales sans retrait, garde-fous LIVE et activation volontaire séparée.

Le LIVE demeure postérieur au chat, au runtime PAPER réel et à la validation complète des Batches 15.2/15.3.

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
15 Operator Agent chat
  |
15.1 Executable PAPER composition
  |
15.2 Canonical multi-horizon market context
  |
15.3 Fixed-sampling market context independent of engine cadence
  |
16 Optional LIVE readiness
```

---

## Décisions encore ouvertes

- limites avancées d'exposition/drawdown comme contraintes Risk ;
- politique de rétention ;
- reconstruction du ledger et réconciliation après crash ;
- dataset/replay canonique pour comparaisons strictement appariées ;
- statistiques descriptives éventuelles de dispersion LLM ;
- éventuelle persistance durable du chat ;
- mécanisme audité/versionné d'instructions opérateur modifiant réellement la stratégie ;
- source d'événements/protocole d'un futur WebSocket ;
- auth/déploiement pour exposition non locale ;
- éventuel LIVE.

Les valeurs du premier essai PAPER (capital, paire, cadence, limites Risk, coûts) restent des **paramètres explicites de run**, pas des defaults produit. La granularité OHLC 1 min est un choix technique de bootstrap et d'échantillonnage descriptif, pas un horizon stratégique supplémentaire. La cadence du moteur ne doit pas définir l'échantillonnage statistique.
