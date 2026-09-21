# 10 — Décisions et changelog

## 1. Règle d'utilisation

Ce document conserve les décisions architecturales durables et un changelog synthétique.

Statuts : **ACCEPTÉE**, **PROPOSÉE**, **SUPERSEDÉE**, **ABANDONNÉE**.

Le Batch 15 reste intégré au commit fonctionnel `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6`. Le Batch 15.1 est intégré sur `main` au commit `4b9701f07854a943cf47a14287aadfdf4aa48232`. Le Batch 15.2 est intégré au commit fonctionnel `97d529647179c6769a6bdc528b9d9f5e7c85c119` et son état documentaire est finalisé par `bb1aa047157deb1b62d27de952fa53ec14992f09`. Le Batch 15.3 est intégré sur `main` au commit fonctionnel `d0f6d46b9adb37117051a7a497a8d55075c41d32` (`fix: decouple market context from engine cadence`).

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

### ADR-073 — Chat opérateur séparé du provider stratégique
**ACCEPTÉE.** `OpenAIChatProvider` est distinct de `OpenAIDecisionProvider`, les deux utilisant le même `LLMModel` configuré sans créer un deuxième agent stratégique.

### ADR-074 — Le chat n'est jamais un chemin d'exécution ou de mutation implicite
**ACCEPTÉE.** Le chat ne construit aucun artefact Risk/Broker/exécution et une demande conversationnelle ne déclenche jamais un trade.

### ADR-075 — Historique chat mémoire seulement et borné pour la V1
**ACCEPTÉE.** Aucun schéma PostgreSQL ni migration ; messages exclus des digests et analytics.

### ADR-076 — Contexte chat uniquement depuis les surfaces canoniques de lecture
**ACCEPTÉE.** Cycle historique ancré sur son `agent_input` persisté exact ; présent séparé.

### ADR-077 — REST sans streaming pour le Chat V1
**ACCEPTÉE.** Aucun WebSocket/SSE sans besoin mesuré ; erreurs fournisseur sanitizées.

### ADR-078 — Frontend Chat indépendant du lifecycle moteur
**ACCEPTÉE.** Aucun start/stop via le code Chat.

### ADR-079 — Redaction best-effort avant conservation conversationnelle
**ACCEPTÉE.** Défense additionnelle ; aucun secret ne doit être fourni au chat.

---

## 5 quinquies. Décisions Batch 15.1 — runtime PAPER exécutable

Le patch Batch 15.1 est **intégré sur `main`** au commit `4b9701f07854a943cf47a14287aadfdf4aa48232`.

### ADR-080 — Un composition root PAPER canonique pour l'application exécutable
**ACCEPTÉE.** La composition assemble uniquement les composants canoniques existants ; `main:app` ne démarre jamais automatiquement le moteur.

### ADR-081 — Valeurs produit du premier run explicites et fail-closed
**ACCEPTÉE.** Paire, capital, devise, cadence, agressivité, timeouts, Risk et coûts sont fournis explicitement ; PostgreSQL/OpenAI obligatoires pour le runtime exécutable ; PAPER uniquement.

### ADR-082 — Identité des dépendances partagées dans le runtime PAPER
**ACCEPTÉE.** Cost model, ledger, DB/session factory et modèle Luna/Sol sont partagés par les composants qui doivent l'être.

### ADR-083 — Le contrôle mono-cycle appelle uniquement `TradingEngine.run_cycle()`
**ACCEPTÉE.** `POST /api/v1/engine/run-cycle` ne reçoit aucune action/quantité et conserve le chemin Market -> Agent -> Risk -> Paper Broker -> audit.

### ADR-084 — Après une erreur d'audit, le runner se verrouille fail-closed
**ACCEPTÉE.** Préflight avant cycle, propagation de la première panne et refus des cycles ultérieurs jusqu'au redémarrage ; aucune garantie exactly-once n'est revendiquée.

---

## 5 sexies. Décisions Batch 15.2 — contexte marché multi-horizon PAPER

### ADR-085 — `MarketStateBuilder` est la voie canonique du snapshot Kraken enrichi
**ACCEPTÉE.** `KrakenMarketDataSource.snapshot()` ne construit plus un `MarketState` parallèle/minimal. Les horizons 5 min / 30 min restent inchangés et `TradingCycleRunner` continue à consommer exactement un `MarketDataSource.snapshot(symbol)`.

### ADR-086 — Bootstrap historique Kraken par OHLC public 1 minute clôturé uniquement
**ACCEPTÉE.** L'OHLC public 1 min remplit les horizons existants sans stratégie parallèle. La dernière entrée OHLC est exclue, les clôtures sont horodatées à `started_at + interval`, seules les valeurs causalement antérieures au ticker courant sont utilisables et la fraîcheur est recontrôlée après l'appel historique.

---

## 5 septies. Décisions Batch 15.3 — contexte indépendant de la cadence moteur

### ADR-087 — Séparer la série statistique de l'observation courante dans le builder canonique
**ACCEPTÉE.** Les observations ajoutées à `MarketStateBuilder` sont la série statistique retenue. `build(...)` accepte une `current_observation` snapshot-only qui fournit `MarketState.last_price` et la fraîcheur sans modifier les fenêtres statistiques.

Raisons :

- conserver un seul moteur Market State ;
- éviter que chaque cycle ajoute un point statistique artificiel ;
- préserver le ticker Kraken courant comme prix de référence pour Agent/Risk/Broker ;
- conserver le contrat de domaine et les ports existants.

### ADR-088 — Ancrer les fenêtres sur une horloge statistique causale distincte
**ACCEPTÉE.** `MarketStateBuilder.build(...)` accepte `statistics_as_of`, toujours inférieur ou égal à `MarketState.as_of`. Pour Kraken, cette valeur est la dernière clôture OHLC 1 minute retenue.

Conséquences :

- sans nouvelle clôture OHLC, les fenêtres restent identiques même si plusieurs cycles supplémentaires sont exécutés ;
- un changement de `trading_cadence_seconds` ne modifie pas l'échantillonnage ;
- une nouvelle bougie clôturée fait avancer la série et les fenêtres naturellement ;
- les fenêtres partielles restent honnêtes ;
- aucun look-ahead n'est introduit.

### ADR-089 — Contrôler séparément la chronologie des tickers courants Kraken
**ACCEPTÉE.** `KrakenMarketDataSource` mémorise uniquement le dernier ticker courant réussi par symbole afin de rejeter un timestamp qui recule ou une valeur conflictuelle au même timestamp. Cette mémoire n'est jamais injectée dans les calculs statistiques.

Aucun changement n'est requis dans `KrakenPublicRestClient`, les ports domaine, `TradingCycleRunner`, `TradingEngine`, l'Agent, le Risk Engine, le Broker ou le frontend.

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

- données marché supplémentaires au-delà du contexte 5/30 min actuel ;
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

Les valeurs concrètes du premier essai PAPER restent des paramètres explicites de run, pas des defaults produit. L'OHLC 1 minute est une granularité technique de bootstrap et d'échantillonnage descriptif, pas une politique stratégique.

---

## 8. Changelog

### 2026-09-21 — Batch 15.3 Contexte marché indépendant de la cadence du moteur

**État : intégré sur `main` au commit fonctionnel `d0f6d46b9adb37117051a7a497a8d55075c41d32` (`fix: decouple market context from engine cadence`). Validation locale complète confirmée avant le push.**

- Cause racine confirmée : le ticker de chaque cycle était ajouté au même historique `MarketStateBuilder` que les clôtures OHLC 1 minute.
- Un deuxième effet a été traité : des fenêtres ancrées directement sur l'heure de chaque cycle pouvaient glisser entre deux clôtures OHLC même sans nouveau point statistique.
- Le builder canonique sépare désormais série statistique retenue, observation courante et ancre `statistics_as_of`.
- Kraken conserve uniquement les clôtures OHLC 1 min dans la série statistique.
- La dernière clôture retenue devient l'ancre des fenêtres descriptives.
- Le ticker courant reste `MarketState.last_price` et la source de fraîcheur du snapshot.
- La chronologie des tickers successifs est contrôlée sans les injecter dans les statistiques.
- Aucun changement du chemin `Market -> Agent -> DecisionCandidate -> Risk -> ExecutionIntent -> Paper Broker`.
- Aucun signal stratégique, aucune modification Luna/Risk, aucun Kraken privé, aucun LIVE, aucune migration DB.

Validation exécutée par ChatGPT :

- tests ciblés Market State + Kraken Market Data : **38 passés** ;
- `compileall` des fichiers Python modifiés : **réussi** ;
- cas déterministes couvrant snapshots supplémentaires sans nouvelle OHLC, cadence simulée 10 s vs 120 s, ticker courant, fraîcheur, no-look-ahead, fenêtres partielles, ordre strict et snapshots successifs.

Validation complète exécutée localement par l'utilisateur le 21 septembre 2026 : `pytest` **315 passés** avec 2 warnings externes ; Ruff **All checks passed** ; mypy **94 fichiers sans erreur** ; `git diff --check` sans erreur avec uniquement des warnings LF -> CRLF sous Windows.

La présente clôture documentaire aligne les documents avec cet état intégré et ne modifie aucun comportement fonctionnel.

### 2026-09-21 — Batch 15.2 Contexte marché multi-horizon PAPER

**État : intégré sur `main` au commit fonctionnel `97d529647179c6769a6bdc528b9d9f5e7c85c119` (`feat: add multi-horizon market context`) ; état documentaire finalisé par `bb1aa047157deb1b62d27de952fa53ec14992f09`.**

- Cause racine de `market_state.context = null` confirmée : `KrakenMarketDataSource.snapshot()` contournait `MarketStateBuilder` et construisait directement un snapshot minimal.
- Réutilisation du `MarketStateBuilder` existant ; aucune architecture de contexte parallèle.
- Horizons canoniques 5 min / 30 min conservés.
- Ajout de la récupération Kraken public OHLC 1 minute avec normalisation/sanitization dédiées.
- Exclusion de la bougie finale non clôturée et horodatage causal des clôtures.
- Ticker WebSocket courant conservé comme dernier prix.
- Gestion explicite des fenêtres partielles, ordre strict, doublons et absence de look-ahead.
- Freshness recheck après récupération historique.
- Propagation des erreurs fournisseur ; aucun fallback silencieux vers un contexte nul.
- Test d'intégration ajouté pour confirmer que le contexte multi-horizon atteint l'`AgentInput` du cycle canonique inchangé.
- Aucun changement frontend, aucun LIVE, aucune API Kraken privée, aucune migration DB.

Validation confirmée :

- tests ciblés : **71 passés** ;
- suite complète : **306 passés**, 2 warnings externes ;
- Ruff : **All checks passed** ;
- mypy : **94 fichiers sans erreur** ;
- `git diff --check` sans erreur, warnings LF -> CRLF uniquement ;
- cycle PAPER réel `BTC/USDC` `d2ea6e10-a64c-4bb1-abab-c80068b96da4` : **COMPLETED**, contexte non nul, fenêtres 300 s / 1800 s complètes (6 et 31 observations), âge de donnée ~0,63 s, no-look-ahead respecté et rationale Luna exploitant explicitement les deux horizons.

Les runs autonomes ultérieurs ont montré que les counts pouvaient ensuite dépendre de la cadence moteur à cause des tickers retenus ; ce comportement historique a motivé le Batch 15.3.

### 2026-09-21 — Batch 15.1 Composition runtime du premier essai PAPER réel

**État : intégré sur `main` au commit `4b9701f07854a943cf47a14287aadfdf4aa48232` (`feat: compose executable PAPER runtime`).**

- Composition canonique Kraken public -> Agent -> Risk -> Paper Broker -> audit PostgreSQL.
- Configuration de run explicite, mono-cycle HTTP, partage des dépendances, shutdown ordonné et audit fail-closed.
- Le premier essai PAPER réel post-intégration a confirmé le chemin exécutable puis révélé l'absence de contexte historique traitée par le Batch 15.2.

### 2026-09-21 — Batch 15 Chat opérateur avec l'Agent

**État : intégré et validé. Commit fonctionnel : `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6`.**

- Package conversationnel séparé du provider stratégique, même modèle Luna/Sol, contexte en lecture seule, no-look-ahead historique, sessions mémoire bornées, API/panneau Chat sans chemin d'exécution.
- Validation locale : **277 tests backend**, Ruff OK, mypy 89 fichiers, pnpm lint/typecheck/build OK.

### 2026-09-21 — Batch 14 Comparaison contrôlée GPT-5.6 Luna / GPT-5.6 Sol

**État : intégré au commit fonctionnel `dc60033f60bf5d98a68e6131a9320e575d46cc8d`.**

`paper-experiment-v2`, groupe/répétitions, `source_digest` obligatoire, comparaison appariée sans score/ranking automatique.

### 2026-09-21 — Batch 13 Expérimentation agressivité 1–10

**État : intégré au commit `1747beb5efd1fe9763bc9b2d23f3a115575daaec`.**

`aggressiveness-map-v1`, `AggressivenessContext`, `paper-experiment-v1`, prompt `agent-strategy-v2`.

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
