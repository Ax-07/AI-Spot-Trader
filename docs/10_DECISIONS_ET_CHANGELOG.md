# 10 — Décisions et changelog

## 1. Règle d'utilisation

Ce document conserve les décisions architecturales durables et un changelog synthétique.

Statuts : **ACCEPTÉE**, **PROPOSÉE**, **SUPERSEDÉE**, **ABANDONNÉE**.

Le Batch 15 reste **intégré et validé** au commit fonctionnel `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6` sur `main`. Le Batch 15.1 ci-dessous est livré sous forme de patch et doit encore être validé/intégré localement.

---

## 2. Décisions acceptées existantes

### ADR-001 — Un agent IA unique
**ACCEPTÉE.** Un seul agent conserve la décision stratégique.

### ADR-002 — SPOT uniquement
**ACCEPTÉE.** Aucun short, levier, margin, future ou perpetual ; aucune vente non couverte.

### ADR-003 — Kraken comme exchange initial
**ACCEPTÉE.** Kraken reste derrière des interfaces fournisseur-agnostiques.

### ADR-004 — Backend Python asynchrone
**ACCEPTÉE.** Python, `asyncio`, FastAPI et Pydantic ; pas de Rust sans besoin mesuré.

### ADR-005 — Frontend cockpit Next.js
**ACCEPTÉE.** Next.js + TypeScript + shadcn/ui + Tailwind.

### ADR-006 — Backend autonome vis-à-vis du frontend
**ACCEPTÉE.** Fermer le frontend ne doit jamais arrêter le moteur.

### ADR-007 — Agent stratégique, calculs déterministes de contexte
**ACCEPTÉE.** Les composants déterministes ne deviennent pas une stratégie parallèle.

### ADR-008 — Risk Engine déterministe avec autorité finale
**ACCEPTÉE.** Toute proposition tradable passe par Risk avant exécution.

### ADR-009 — Actions BUY / SELL / HOLD
**ACCEPTÉE.** HOLD reste une décision valide et auditée ; SELL reste couvert uniquement.

### ADR-010 — PAPER en premier, LIVE séparé
**ACCEPTÉE.** `ExecutionMode` reste PAPER uniquement à ce stade.

### ADR-011 — Frais, spread et slippage inclus
**ACCEPTÉE.** Les coûts PAPER sont explicites et auditables.

### ADR-012 — Luna initial, Sol configurable
**ACCEPTÉE.** Luna pour les premiers essais ; Sol sélectionnable par configuration.

### ADR-013 — Agressivité configurable de 1 à 10
**ACCEPTÉE.** La plage `1..10` est canonique ; `aggressiveness-map-v1` est intégré depuis Batch 13.

### ADR-014 — Cible expérimentale de +4 % par jour
**ACCEPTÉE.** Cible de recherche, jamais garantie ni obligation de trader.

### ADR-015 — Journaliser toutes les décisions
**ACCEPTÉE.** HOLD, refus et modifications doivent être conservés.

### ADR-016 — PostgreSQL comme base durable
**ACCEPTÉE.** PostgreSQL est la base cible du journal durable PAPER.

### ADR-017 — Sécurité des secrets
**ACCEPTÉE.** Aucun secret dans Git/prompts/logs et aucune clé Kraken avec retrait.

### ADR-018 — Bootstrap en deux applications découplées
**ACCEPTÉE.** Backend et frontend séparés, pas de microservices prématurés.

### ADR-019 — pnpm comme gestionnaire frontend
**ACCEPTÉE.**

### ADR-020 — Contrats Pydantic stricts aux frontières du domaine
**ACCEPTÉE.** Contrats centraux sous `ai_spot_trader.domain`.

### ADR-021 — PAPER est le seul mode actuellement représentable
**ACCEPTÉE.**

### ADR-022 — Timestamps aware normalisés en UTC
**ACCEPTÉE.**

### ADR-023 — Horloge injectable minimale
**ACCEPTÉE.** `Clock.now()` et `SystemClock` permettent des tests déterministes.

### ADR-024 — Ports externes minimaux via Protocol
**ACCEPTÉE.** Les frontières externes restent étroites et testables.

### ADR-025 — Adapter Kraken Spot public minimal
**ACCEPTÉE.** APIs publiques uniquement, aucune clé ni ordre.

### ADR-026 — Market State déterministe, multi-horizon et sans look-ahead
**ACCEPTÉE.** Historique borné et statistiques descriptives sans stratégie.

### ADR-027 — Rôles canoniques du Portfolio State
**ACCEPTÉE.** `balances` et `positions` ont des rôles disjoints.

### ADR-028 — Ledger PAPER mémoire et état initial injecté
**ACCEPTÉE.** Aucun capital/devise produit par défaut ; mutations atomiques.

### ADR-029 — Pricing PAPER explicite via MarketState
**ACCEPTÉE.** Le Broker reçoit explicitement le même contexte marché du cycle.

### ADR-030 — Modèle de coûts PAPER déterministe et auditable
**ACCEPTÉE.** Fee/spread/slippage sont injectés et calculés en `Decimal`.

### ADR-031 — Sizing stratégique explicite dans DecisionCandidate
**ACCEPTÉE.** BUY/SELL portent une quantité proposée ; Risk peut la réduire.

### ADR-032 — RiskAssessment porte quantités et raisons structurées
**ACCEPTÉE.** MODIFY réduit strictement ; REJECT n'autorise rien.

### ADR-033 — RiskPolicy injectée, sans limites produit implicites
**ACCEPTÉE.** Aucune valeur chiffrée produit n'est codée en dur.

### ADR-034 — Estimation PAPER partagée entre Risk et Paper Broker
**ACCEPTÉE.** La mathématique de coûts reste commune.

### ADR-035 — MODIFY abaisse le risque sans changer la stratégie
**ACCEPTÉE.** Risk ne change jamais le sens ou le symbole.

### ADR-036 — HOLD traverse la frontière Risk pour audit
**ACCEPTÉE.** HOLD produit un assessment sans intent.

### ADR-037 — Le LLM ne produit que les champs stratégiques
**ACCEPTÉE.** IDs/timestamps restent sous contrôle applicatif.

### ADR-038 — L'Agent est limité au symbole du MarketState fourni
**ACCEPTÉE.**

### ADR-039 — Prompt versionné et Structured Outputs stricts
**ACCEPTÉE.** Pas de tool-calling ni de réparation stratégique silencieuse.

### ADR-040 — Adapter OpenAI minimal sur httpx, secrets via SecretStr
**ACCEPTÉE.** Même provider stratégique pour Luna/Sol, pas de retry automatique au Batch 07.

### ADR-041 — Boucle autonome séquentielle sur snapshots cohérents
**ACCEPTÉE.** `TradingCycleRunner.run_cycle()` est canonique ; `TradingEngine` le répète avec un seul cycle à la fois et stop coopératif.

### ADR-042 — SQLAlchemy async + asyncpg + Alembic pour PostgreSQL
**ACCEPTÉE.** `aiosqlite` reste réservé aux tests offline.

### ADR-043 — Journal durable factuel derrière CycleAuditWriter
**ACCEPTÉE.** La persistance observe les résultats sans devenir une source de stratégie.

### ADR-044 — Un graphe durable immuable par cycle_id
**ACCEPTÉE.** Replay identique idempotent, conflit explicite si faits différents, transaction unique.

### ADR-045 — PostgreSQL Docker Compose pour le développement local
**ACCEPTÉE.** Commodité locale, pas définition du déploiement production.

### ADR-046 — Pas de fausse garantie exactly-once au Batch 09
**ACCEPTÉE.** Ledger mémoire et commit PostgreSQL ne sont pas encore atomiques globalement.

---

## 3. Décisions acceptées au Batch 10

### ADR-047 — Façade REST séparée du métier de trading
**ACCEPTÉE.** FastAPI expose observation/lifecycle mais ne crée aucun artefact Agent/Risk/Broker.

### ADR-048 — Query service de lecture durable
**ACCEPTÉE.** `CycleAuditReader` est la frontière de lecture ; SQLAlchemy reste derrière son implémentation.

### ADR-049 — Start/stop uniquement sur moteur canonique injecté
**ACCEPTÉE.** L'API appelle seulement `TradingEngine.start()/stop()` ; aucun auto-start ni boucle alternative.

### ADR-050 — Pas de WebSocket au Batch 10
**ACCEPTÉE.** REST suffit tant qu'aucun bus d'événements canonique n'existe.

### ADR-051 — Réutiliser le schéma Batch 09 sans migration API
**ACCEPTÉE.** Le schéma durable n'est pas modifié pour simplifier les routes.

### ADR-052 — Erreurs API sanitizées et DB lifecycle explicite
**ACCEPTÉE.** Aucun message brut/DSN/secret ; la DB possédée par FastAPI est fermée explicitement.

---

## 4. Décisions acceptées au Batch 11

Batch 11 intégré au commit fonctionnel `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7`.

### ADR-053 — Rewrite Next.js same-origin vers FastAPI
**ACCEPTÉE.** Le navigateur appelle `/backend/*`; Next.js réécrit vers l'URL backend non publique.

### ADR-054 — Polling cockpit borné et purement présentatif
**ACCEPTÉE.** Polling 10 s lorsque l'onglet est visible, jamais cadence moteur.

### ADR-055 — Types frontend alignés sur les contrats HTTP
**ACCEPTÉE.** UUID/timestamps en chaînes JSON, `Decimal` en chaînes, formatage présentatif seulement.

### ADR-056 — États d'indisponibilité explicites dans le cockpit
**ACCEPTÉE.** 404/503/offline différenciés, boutons lifecycle verrouillés pendant commande.

---

## 5. Décisions acceptées au Batch 12

Batch 12 intégré au commit `3f39999736b6fc3800ecfd36ddee0253c734d25d`.

### ADR-057 — Journal durable comme source canonique des analytics
**ACCEPTÉE.** Les analytics dérivent uniquement des faits persistés.

### ADR-058 — Analytics calculés à la volée par un reducer pur
**ACCEPTÉE.** Pas de table/vue dédiée tant que le volume ne le justifie pas.

### ADR-059 — Définitions PAPER du P&L, drawdown et exposition
**ACCEPTÉE.** P&L net/brut, coûts, drawdown/exposition et définition du trade fixés par les faits durables.

### ADR-060 — UTC et no look-ahead pour les séries historiques
**ACCEPTÉE.** Chaque point utilise le `MarketState` durable du même cycle.

### ADR-061 — Reproductibilité versionnée des métriques
**ACCEPTÉE.** `calculation_version` + SHA-256 de `(cycle_id, result_digest)` ordonné.

---

## 5 bis. Décisions acceptées au Batch 13

Batch 13 intégré au commit `1747beb5efd1fe9763bc9b2d23f3a115575daaec`.

### ADR-062 — Mapping discret d'agressivité versionné
**ACCEPTÉE.** `aggressiveness-map-v1`, sans seuil Risk ni formule déterministe de sizing.

### ADR-063 — Agressivité limitée à la stratégie Agent
**ACCEPTÉE.** Elle n'est jamais passée à `RiskEngine.evaluate(...)`.

### ADR-064 — Prompt Agent `agent-strategy-v2`
**ACCEPTÉE.** Mapping stratégique explicite ; validation du manifeste avant appel LLM.

### ADR-065 — Manifeste expérimental durable dans AgentInput
**ACCEPTÉE.** `paper-experiment-v1` + digest, persistance dans JSON/JSONB existant.

### ADR-066 — Comparaison d'agressivité par réutilisation directe de Batch 12
**ACCEPTÉE.** Aucun recalcul divergent ni ranking automatique.

### ADR-067 — Pas d'API/frontend expérimental au Batch 13
**ACCEPTÉE.** Le cockpit ne mute pas agressivité/Risk/coûts.

---

## 5 ter. Décisions acceptées au Batch 14

Batch 14 intégré au commit fonctionnel `dc60033f60bf5d98a68e6131a9320e575d46cc8d`.

### ADR-068 — Versionner la comparaison modèle en `paper-experiment-v2`
**ACCEPTÉE.** `comparison_variable = LLM_MODEL`, compatibilité v1 préservée.

### ADR-069 — Séparer identité de groupe et identité de run
**ACCEPTÉE.** `experiment_group_digest` pour les champs contrôlés ; `experiment_digest` pour le run complet.

### ADR-070 — Dataset figé obligatoire pour une comparaison modèle stricte
**ACCEPTÉE.** `source_digest` obligatoire en v2 ; pas de replay parallèle ajouté.

### ADR-071 — Répétitions appariées pour le non-déterminisme LLM
**ACCEPTÉE.** `1..N` requis pour Luna et Sol ; pas de seed fictif ni suppression post-hoc.

### ADR-072 — Comparaison modèle factuelle sans score ni gagnant automatique
**ACCEPTÉE.** Réutilisation de `PaperAnalyticsReport`, aucun ranking automatique.

---

## 5 quater. Décisions acceptées au Batch 15

Ces décisions sont acceptées après validation locale complète et intégration du commit fonctionnel sur `main`.

### ADR-073 — Chat opérateur comme interface conversationnelle séparée du provider stratégique
- **Statut : ACCEPTÉE**
- `OpenAIChatProvider` est distinct de `OpenAIDecisionProvider`.
- Les deux utilisent le même `LLMModel` configuré afin de conserver Luna/Sol comme identité de modèle Agent.
- Le provider chat ne retourne que du texte conversationnel et n'utilise aucun schéma stratégique ni tool-calling.
- Aucun deuxième agent stratégique n'est créé.

### ADR-074 — Le chat n'est jamais un chemin d'exécution ou de mutation implicite
- **Statut : ACCEPTÉE**
- Le package `chat` n'importe ni Risk, ni Broker, ni Kraken, ni trading.
- Il ne construit pas `DecisionCandidate`, `RiskAssessment`, `ExecutionIntent` ou `RiskPolicy`.
- « BUY maintenant », « agressivité 8 » et « ignore Risk » restent non exécutables depuis le chat.
- Toute future instruction opérateur réellement mutante nécessitera un mécanisme explicite, audité, versionné et rattaché à un cycle d'application.

### ADR-075 — Historique chat mémoire seulement et borné pour la V1
- **Statut : ACCEPTÉE**
- Par défaut : 20 messages par session, 32 sessions process-locales, éviction des plus anciennes.
- Aucun schéma PostgreSQL ni migration.
- Les messages chat ne participent ni au journal de trading, ni aux digests expérimentaux, ni aux analytics.
- Un redémarrage backend perd les sessions, comportement assumé pour cette V1.

### ADR-076 — Contexte chat construit uniquement depuis les surfaces canoniques de lecture
- **Statut : ACCEPTÉE**
- Le contexte lit `AppRuntime`, le portefeuille, `CycleAuditReader` et `PaperAnalyticsReader`.
- Un cycle historique expose son `agent_input` persisté exact.
- L'état courant est séparé du cycle historique et ne peut pas être invoqué comme cause rétroactive.
- Pour un cycle historique explicite, la liste `recent_cycles` est omise afin de réduire le risque de mélange temporel.

### ADR-077 — REST sans streaming pour le Chat V1
- **Statut : ACCEPTÉE**
- `POST /api/v1/chat/messages` et `GET /api/v1/chat/sessions/{session_id}` suffisent.
- Aucun WebSocket/SSE n'est introduit sans besoin mesuré.
- Les erreurs fournisseur chat sont sanitizées et séparées des cycles `FAILED`.

### ADR-078 — Le frontend Chat reste indépendant du lifecycle moteur
- **Statut : ACCEPTÉE**
- Le hook/panneau Chat n'appelle ni `startEngine` ni `stopEngine`.
- Recharger ou fermer le frontend ne stoppe pas le backend.
- Le navigateur ne conserve que l'UUID de session ; l'historique reste côté service backend mémoire.

### ADR-079 — Redaction best-effort avant conservation conversationnelle
- **Statut : ACCEPTÉE**
- Les formes courantes de clés/tokens/secrets sont redigées avant historique et provider.
- Les messages bruts d'erreur LLM ne sont jamais renvoyés à l'API.
- Cette défense ne remplace pas la règle « aucun secret dans le chat ».

---

## 5 quinquies. Décisions Batch 15.1

Ces décisions correspondent au patch de composition du premier essai PAPER. Leur intégration sur `main` reste à confirmer après validation locale.

### ADR-080 — Un composition root PAPER canonique pour l'application exécutable
- **Statut : ACCEPTÉE pour le patch**
- La composition assemble uniquement les composants canoniques existants.
- `main:app` construit ce graphe au lifespan FastAPI mais ne démarre pas automatiquement le moteur.
- Aucun second runner, broker, ledger, agent stratégique ou chemin d'exécution n'est créé.

### ADR-081 — Les valeurs produit du premier run restent explicites et fail-closed
- **Statut : ACCEPTÉE pour le patch**
- Paire, capital, devise, cadence, agressivité, timeouts, limites Risk et coûts PAPER doivent être fournis explicitement.
- PostgreSQL et OpenAI sont obligatoires pour le runtime exécutable.
- Une configuration incomplète refuse le démarrage du runtime réel.
- `ExecutionMode` reste PAPER uniquement ; aucune notion LIVE n'est ajoutée.

### ADR-082 — Identité des dépendances partagées dans le runtime PAPER
- **Statut : ACCEPTÉE pour le patch**
- Un même `PaperExecutionCostModel` est injecté à Risk et au Paper Broker.
- Un même `PaperPortfolioLedger` est utilisé par le runner et exposé par FastAPI/Chat.
- Un même `Database`/session factory PostgreSQL alimente writer d'audit, lecteurs et analytics.
- Le même `LLMModel` Luna/Sol est transmis à l'Agent et au Chat.

### ADR-083 — Le contrôle mono-cycle appelle uniquement `TradingEngine.run_cycle()`
- **Statut : ACCEPTÉE pour le patch**
- `POST /api/v1/engine/run-cycle` ne reçoit aucune action ni quantité de trading.
- La commande est sérialisée avec start/stop et refusée pendant une boucle autonome active.
- Elle conserve le chemin Market -> Agent -> Risk -> Paper Broker -> audit.

### ADR-084 — Après une erreur d'audit, le runner se verrouille fail-closed
- **Statut : ACCEPTÉE pour le patch**
- Le writer PostgreSQL est préflighté avant chaque cycle ; une indisponibilité déjà présente bloque le delegate avant Market/Agent/Risk/Broker.
- La première erreur de préflight ou de persistance est propagée, jamais convertie en HOLD ou masquée.
- Tout appel ultérieur au runner audité est refusé avant son delegate jusqu’au redémarrage.
- Cette mesure empêche de continuer à trader sans audit mais ne crée aucune garantie exactly-once ni mécanisme de recovery/réconciliation.

---

## 6. Propositions historiques

### ADR-P001 — Contrats Pydantic versionnés entre composants
**SUPERSEDÉE par ADR-020** pour le principe des contrats stricts ; version de schéma explicite encore à décider si nécessaire.

### ADR-P002 — Horloge injectable
**SUPERSEDÉE par ADR-023.**

### ADR-P003 — Architecture modulaire dans un backend unique
**SUPERSEDÉE par ADR-018.**

### ADR-P004 — Logs structurés corrélés
**PROPOSÉE.** UUID présents ; format/bibliothèque encore à décider.

---

## 7. Décisions encore ouvertes

- données marché supplémentaires ;
- limites d'exposition/drawdown ;
- dataset/replay canonique pour comparaisons appariées ;
- statistiques descriptives de dispersion LLM ;
- politique de rétention PostgreSQL ;
- reconstruction du ledger et reprise après panne ;
- éventuelle persistance durable du chat ;
- contrat d'un futur mécanisme d'instructions opérateur mutantes ;
- auth et déploiement ;
- logs structurés ;
- source d'événements/protocole futur WebSocket ;
- éventuel LIVE.

Les valeurs concrètes du premier essai PAPER sont désormais des paramètres explicites de run, pas des defaults produit.

---

## 8. Changelog

### 2026-09-21 — Batch 15.1 Composition runtime du premier essai PAPER réel

**État : patch livré ; validation/intégration locale à confirmer. Référence GitHub auditée au démarrage : `59e3bc26c7b4d6acca25bc7d21c85c3c14eeb336`.**

- Ajout d'un composition root PAPER réutilisant Kraken public, Agent, Risk, Broker, ledger, audit, analytics et Chat existants.
- Configuration explicite obligatoire pour les valeurs du premier run ; aucun nouveau default produit chiffré.
- PostgreSQL unique partagé entre writer d'audit et surfaces de lecture/analytics.
- `PaperExecutionCostModel` unique partagé entre Risk et Paper Broker.
- `PaperPortfolioLedger` unique partagé entre moteur, API et contexte Chat.
- Même modèle Luna/Sol transmis à l'Agent et au Chat.
- `main:app` compose au startup mais garde le moteur arrêté.
- Ajout de `POST /api/v1/engine/run-cycle`, sans entrée stratégique, appelant uniquement `TradingEngine.run_cycle()`.
- Sérialisation des commandes moteur et refus du mono-cycle pendant l'autonome.
- Fermeture explicite des ressources réseau possédées en plus du moteur et de la DB.
- Préflight PostgreSQL avant le delegate puis latch fail-closed après la première erreur d’audit ; aucune fausse garantie exactly-once.
- Aucun changement frontend et aucun LIVE/Kraken privé.
- Tests ciblés ajoutés pour configuration, composition, partage des dépendances, modèle Agent/Chat, portefeuille initial, mono-cycle/concurrence, sanitization, lifecycle et fail-closed audit.

Validation exécutée par ChatGPT sur le patch isolé : compilation Python et contrôles/dynamiques ciblés documentés dans `docs/00_ETAT_ACTUEL.md`. La suite backend complète, Ruff et mypy restent à exécuter localement avant intégration.

### 2026-09-21 — Batch 15 Chat opérateur avec l'Agent

**État : intégré et validé. Commit fonctionnel : `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6` (`feat: add operator agent chat`).**

- Resynchronisation initiale confirmée sur le commit documentaire Batch 14 `b2c74672744639f86c38e873f25d56c77f899c76`, puis intégration fonctionnelle Batch 15 sur `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6`.
- Ajout d'un package conversationnel séparé du provider stratégique.
- Même `settings.llm_model` Luna/Sol utilisé par le chat ; aucune duplication d'agent stratégique.
- Extension du client Responses API avec un appel texte `store=false`, sans tools ni schéma de décision.
- Prompt `operator-chat-v1` avec séparation explicite conversation/exécution et règles no-look-ahead.
- Contexte canonique en lecture seule depuis moteur, portefeuille, audit et analytics.
- Cycle historique explicite ancré sur son `AgentInput` durable exact ; présent séparé.
- Sessions mémoire bornées, aucune migration PostgreSQL, aucune contamination des digests/analytics.
- Redaction best-effort des secrets et erreurs fournisseur chat sanitizées.
- Routes REST Chat ajoutées ; aucun WebSocket/SSE.
- Panneau Chat cockpit ajouté ; aucun chemin frontend Chat vers start/stop moteur.
- Tests Batch 15 ajoutés pour les invariants conversation/exécution, Luna/Sol, no-look-ahead, non-contamination d'`AgentInput`, Risk immuable, erreurs distinctes et bornage historique.
- La préparation LIVE auparavant nommée Batch 15 est déplacée au Batch 16 et reste hors périmètre.

Validation exécutée par ChatGPT sur le patch isolé :

- `py_compile` des fichiers Python modifiés/ajoutés : **réussi** ;
- contrôle AST du package `chat` contre imports/symboles d'exécution interdits : **réussi** ;
- contrôle statique frontend Chat contre `startEngine`/`stopEngine` : **réussi**.

Validation locale finale confirmée avant le commit fonctionnel :

- `pytest backend` : **277 tests passés**, 2 warnings externes ;
- Ruff : **All checks passed** ;
- mypy : **89 fichiers sans erreur** ;
- `pnpm lint` : **réussi** après correction de l'unique erreur initiale `react-hooks/set-state-in-effect` dans `use-chat.ts` ;
- `pnpm typecheck` : **réussi** ;
- `pnpm build` : **réussi** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push fonctionnel : `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6`.

### 2026-09-21 — Batch 14 Comparaison contrôlée GPT-5.6 Luna / GPT-5.6 Sol

**État : intégré sur `main` au commit fonctionnel `dc60033f60bf5d98a68e6131a9320e575d46cc8d`, suivi du commit documentaire `b2c74672744639f86c38e873f25d56c77f899c76`.**

- `paper-experiment-v2`, groupe/répétitions, `source_digest` obligatoire et comparaison appariée Luna/Sol.
- Aucun score composite/ranking, aucune migration/API/frontend, aucun LIVE.
- Validation finale : **266 tests backend**, Ruff OK, mypy 81 fichiers, `git diff --check` OK.

### 2026-09-21 — Batch 13 Expérimentation agressivité 1–10

**État : intégré sur `main` au commit `1747beb5efd1fe9763bc9b2d23f3a115575daaec`.**

- `aggressiveness-map-v1`, `AggressivenessContext`, `paper-experiment-v1`, prompt `agent-strategy-v2`.
- Validation finale : **249 tests backend**, Ruff OK, mypy 81 fichiers.

### 2026-09-20 — Batch 12 Analytics et expérimentation reproductible

**État : intégré** au commit `3f39999736b6fc3800ecfd36ddee0253c734d25d`.

Journal durable comme source analytics, reducer PAPER pur, no-look-ahead, endpoint/panneau analytics.

### 2026-09-20 — Batch 11 Frontend cockpit

**État : intégré** au commit `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7`.

Cockpit Next.js/shadcn, client REST, polling borné, Start/Stop via FastAPI uniquement.

### 2026-09-20 — Batch 10 API FastAPI de contrôle/observation

**État : intégré** au commit `e6bcfd4dd345c934769b2f90fa7822232a80dd80`.

Façade REST, query service durable, lifecycle moteur injecté, erreurs sanitizées.

### 2026-09-20 — Batch 09 Persistance et journal d'audit

**État : intégré fonctionnellement** au commit `c53d04f14bcda82359d11c2e14fc1eb601ed14e0`.

SQLAlchemy async + PostgreSQL + Alembic, journal cycles/décisions/Risk/intents/fills.

### 2026-09-20 — Batches 08 à 00

**État : intégrés.** Boucle autonome, Agent Luna/Sol, Risk, Portfolio/Paper Broker, Market State, Kraken public, contrats, bootstrap et documentation initiale ont été intégrés successivement avec validations documentées.
