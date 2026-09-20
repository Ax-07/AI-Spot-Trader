# 10 — Décisions et changelog

## 1. Règle d'utilisation

Ce document conserve les décisions architecturales durables et un changelog synthétique.

Statuts : **ACCEPTÉE**, **PROPOSÉE**, **SUPERSEDÉE**, **ABANDONNÉE**.

---

## 2. Décisions acceptées

### ADR-001 — Un agent IA unique
- **Statut : ACCEPTÉE**
- Un seul agent conserve la décision stratégique.

### ADR-002 — SPOT uniquement
- **Statut : ACCEPTÉE**
- Aucun short, levier, margin, future ou perpetual ; aucune vente non couverte.

### ADR-003 — Kraken comme exchange initial
- **Statut : ACCEPTÉE**
- Kraken reste derrière des interfaces fournisseur-agnostiques.

### ADR-004 — Backend Python asynchrone
- **Statut : ACCEPTÉE**
- Python, `asyncio`, FastAPI et Pydantic ; pas de Rust sans besoin mesuré.

### ADR-005 — Frontend cockpit Next.js
- **Statut : ACCEPTÉE**
- Next.js + TypeScript + shadcn/ui + Tailwind.

### ADR-006 — Backend autonome vis-à-vis du frontend
- **Statut : ACCEPTÉE**
- Fermer le frontend ne doit jamais arrêter le moteur.

### ADR-007 — Agent stratégique, calculs déterministes de contexte
- **Statut : ACCEPTÉE**
- Les composants déterministes ne deviennent pas une stratégie parallèle.

### ADR-008 — Risk Engine déterministe avec autorité finale
- **Statut : ACCEPTÉE**
- Toute proposition tradable passe par Risk avant exécution.

### ADR-009 — Actions BUY / SELL / HOLD
- **Statut : ACCEPTÉE**
- HOLD est une décision valide et doit être auditée ; SELL reste couvert uniquement.

### ADR-010 — PAPER en premier, LIVE séparé
- **Statut : ACCEPTÉE**
- `ExecutionMode` reste PAPER uniquement dans les premières versions.

### ADR-011 — Frais, spread et slippage inclus
- **Statut : ACCEPTÉE**
- Les coûts PAPER sont explicites et auditables.

### ADR-012 — Luna initial, Sol configurable
- **Statut : ACCEPTÉE**
- Luna pour les premiers essais ; Sol sélectionnable par configuration.

### ADR-013 — Agressivité configurable de 1 à 10
- **Statut : ACCEPTÉE**
- Mapping exact encore à décider ; aucune valeur ne contourne Risk.

### ADR-014 — Cible expérimentale de +4 % par jour
- **Statut : ACCEPTÉE**
- Cible de recherche, jamais garantie ni obligation de trader.

### ADR-015 — Journaliser toutes les décisions
- **Statut : ACCEPTÉE**
- HOLD, refus et modifications doivent être conservés.

### ADR-016 — PostgreSQL comme base durable
- **Statut : ACCEPTÉE**
- PostgreSQL est la base cible du journal durable PAPER.

### ADR-017 — Sécurité des secrets
- **Statut : ACCEPTÉE**
- Aucun secret dans Git/prompts/logs et aucune clé Kraken avec retrait.

### ADR-018 — Bootstrap en deux applications découplées
- **Statut : ACCEPTÉE**
- Backend et frontend séparés, pas de microservices prématurés.

### ADR-019 — pnpm comme gestionnaire frontend
- **Statut : ACCEPTÉE**

### ADR-020 — Contrats Pydantic stricts aux frontières du domaine
- **Statut : ACCEPTÉE**
- Contrats centraux dans `ai_spot_trader.domain`, enrichis uniquement lorsqu'un besoin concret le justifie.

### ADR-021 — PAPER est le seul mode actuellement représentable
- **Statut : ACCEPTÉE**

### ADR-022 — Timestamps aware normalisés en UTC
- **Statut : ACCEPTÉE**

### ADR-023 — Horloge injectable minimale
- **Statut : ACCEPTÉE**
- `Clock.now()` et `SystemClock` permettent tests déterministes et replays.

### ADR-024 — Ports externes minimaux via Protocol
- **Statut : ACCEPTÉE**
- `MarketDataSource`, `MarketObservationSource`, `LLMProvider`, `Broker` sont les ports métier canoniques.

### ADR-025 — Adapter Kraken Spot public minimal
- **Statut : ACCEPTÉE**
- APIs publiques Spot uniquement, aucune clé ni ordre.

### ADR-026 — Market State déterministe, multi-horizon et sans look-ahead
- **Statut : ACCEPTÉE**
- Historique borné, ordre strict, statistiques `Decimal`, aucune stratégie.

### ADR-027 — Rôles canoniques du Portfolio State
- **Statut : ACCEPTÉE**
- `balances` = actifs de règlement ; `positions` = actifs détenus/vendables ; rôles disjoints.

### ADR-028 — Ledger PAPER mémoire et état initial injecté
- **Statut : ACCEPTÉE**
- Aucun capital/devise produit par défaut ; mutations atomiques.

### ADR-029 — Pricing PAPER explicite via MarketState
- **Statut : ACCEPTÉE**
- `Broker.execute(execution_intent, market_state)` ; aucun prix réseau caché.

### ADR-030 — Modèle de coûts PAPER déterministe et auditable
- **Statut : ACCEPTÉE**
- `fee_rate`, `spread_bps`, `slippage_bps`, entièrement `Decimal` et injectés.

### ADR-031 — Le sizing stratégique est explicite dans DecisionCandidate
- **Statut : ACCEPTÉE**
- BUY/SELL portent `proposed_quantity > 0` ; HOLD ne porte aucune quantité.
- L'agent source la taille stratégique ; Risk peut la réduire mais ne choisit pas arbitrairement une taille initiale.

### ADR-032 — RiskAssessment porte quantités et raisons structurées
- **Statut : ACCEPTÉE**
- `requested_quantity`, `authorized_quantity`, `evaluated_limits` et `RiskReason` rendent la décision Risk auditable.
- MODIFY signifie strictement une réduction ; REJECT ne crée aucun intent ; HOLD produit un assessment sans intent.

### ADR-033 — RiskPolicy injectée, sans limites produit implicites
- **Statut : ACCEPTÉE**
- Max order notional, whitelist, seuil stale métier et réduction de quantité sont explicites et optionnels.
- Aucune valeur chiffrée produit n'est codée en dur.

### ADR-034 — Estimation PAPER partagée entre Risk et Paper Broker
- **Statut : ACCEPTÉE**
- `broker/pricing.py` contient la mathématique pure commune des coûts PAPER.

### ADR-035 — MODIFY ne peut qu'abaisser le risque sans changer la stratégie
- **Statut : ACCEPTÉE**
- Risk ne change jamais BUY↔SELL ou symbole, n'augmente jamais la quantité et réduit uniquement si la policy l'autorise.

### ADR-036 — HOLD traverse la frontière Risk pour audit
- **Statut : ACCEPTÉE**
- HOLD retourne `ALLOW` avec `HOLD_NO_EXECUTION` et aucun `ExecutionIntent`.

### ADR-037 — Le LLM ne produit que les champs stratégiques
- **Statut : ACCEPTÉE**
- Sortie fournisseur : `action`, `symbol`, `proposed_quantity`, `rationale`.
- IDs et timestamps sont contrôlés par l'application.

### ADR-038 — L'Agent est limité au symbole du MarketState fourni
- **Statut : ACCEPTÉE**
- `decision.symbol` doit être exactement égal à `agent_input.market_state.symbol`.

### ADR-039 — Prompt versionné et Structured Outputs stricts
- **Statut : ACCEPTÉE**
- Prompt initial `agent-luna-v1`, Responses API, JSON Schema strict, revalidation locale et aucun tool-calling.

### ADR-040 — Adapter OpenAI minimal sur httpx, secrets via SecretStr
- **Statut : ACCEPTÉE**
- `gpt-5.6-luna` et `gpt-5.6-sol` utilisent le même provider.
- `httpx` est réutilisé ; clé via environnement/`SecretStr` ; aucun retry automatique au Batch 07.

### ADR-041 — Boucle autonome séquentielle sur snapshots cohérents
- **Statut : ACCEPTÉE**
- La primitive canonique est `TradingCycleRunner.run_cycle()` ; `TradingEngine` ne fait que la répéter.
- Un verrou partagé couvre tout le cycle.
- Chaque cycle utilise un unique `MarketState` pour Agent, Risk et Broker, et un unique `PortfolioState` pré-cycle pour Agent et Risk.
- Seul Risk crée l'`ExecutionIntent`.
- HOLD et REJECT sont des issues métier complètes ; les pannes techniques sont distinctes.
- Market, Agent et Broker ont des timeouts explicitement injectés.
- La cadence est attendue après la fin d'un cycle.
- Le stop est coopératif et FastAPI peut attendre l'arrêt via `AppRuntime`.

### ADR-042 — SQLAlchemy async + asyncpg + Alembic pour PostgreSQL
- **Statut : ACCEPTÉE**
- SQLAlchemy 2 async est la couche d'accès PostgreSQL.
- `asyncpg` est le driver de production.
- Alembic est l'unique mécanisme normal de migration du schéma durable.
- `aiosqlite` reste une dépendance de développement pour les tests offline.

### ADR-043 — Journal durable factuel derrière CycleAuditWriter
- **Statut : ACCEPTÉE**
- `CycleAuditWriter.record(TradingCycleResult)` est la frontière minimale.
- `AuditedTradingCycleRunner` enveloppe le runner canonique après production du résultat.
- Agent, Risk et Broker ne dépendent pas directement de PostgreSQL.
- La persistance ne devient jamais une source de stratégie.

### ADR-044 — Un graphe durable immuable par cycle_id
- **Statut : ACCEPTÉE**
- `cycle_id` est l'identité métier du journal.
- Une empreinte déterministe du résultat permet les replays idempotents.
- Même `cycle_id` + faits différents = conflit explicite.
- Le graphe complet est transactionnel et rollback intégral en cas d'échec.

### ADR-045 — PostgreSQL Docker Compose pour le développement local
- **Statut : ACCEPTÉE**
- `docker-compose.yml` fournit PostgreSQL 18 local avec volume persistant et healthcheck.
- Cette composition est une commodité de développement, pas une définition de production.

### ADR-046 — Pas de fausse garantie exactly-once au Batch 09
- **Statut : ACCEPTÉE**
- Le ledger PAPER reste mémoire.
- L'idempotence du journal n'implique pas une atomicité globale entre mutation du ledger et commit PostgreSQL.
- Reconstruction du ledger et réconciliation après crash restent des étapes futures explicites.

---

## 3. Propositions non encore décidées

### ADR-P001 — Contrats Pydantic versionnés entre composants
- **Statut : SUPERSEDÉE par ADR-020** pour le principe des contrats stricts ; version de schéma explicite encore à décider si nécessaire.

### ADR-P002 — Horloge injectable
- **Statut : SUPERSEDÉE par ADR-023**

### ADR-P003 — Architecture modulaire dans un backend unique
- **Statut : SUPERSEDÉE par ADR-018**

### ADR-P004 — Logs structurés corrélés
- **Statut : PROPOSÉE**
- UUID présents ; format/bibliothèque de logs encore à décider.

---

## 4. Décisions encore ouvertes

- capital PAPER initial produit ;
- devise de référence produit ;
- univers initial de paires ;
- valeur produit de cadence ;
- données marché supplémentaires ;
- valeurs chiffrées produit des limites Risk ;
- éventuelle limite d'exposition ;
- max drawdown / max daily loss quand les données existeront ;
- mapping agressivité 1–10 ;
- valeurs expérimentales fee/spread/slippage ;
- modèle de fill plus riche éventuel ;
- base de coût et frontière de journée ;
- politique de rétention PostgreSQL ;
- reconstruction du ledger, réconciliation et stratégie de reprise après panne ;
- auth et déploiement ;
- versionnement explicite des schémas si nécessaire ;
- éventuelle policy de retry LLM bornée ;
- éventuel LIVE.

---

## 5. Changelog

### 2026-09-20 — Batch 09 Persistance et journal d'audit

**État : intégré fonctionnellement sur `main` au commit `c53d04f14bcda82359d11c2e14fc1eb601ed14e0` (`feat: add durable audit persistence`).**

- Resynchronisation initiale sur GitHub `main` au HEAD `4af32bb6ddf714d71405392d4e515312ba89e2a6` (`docs: record Batch 08 integration`).
- Choix de SQLAlchemy 2 async, `asyncpg` et Alembic.
- Ajout de `ai_spot_trader.persistence` avec `Database`, `CycleAuditWriter`, `AuditedTradingCycleRunner` et `SqlAlchemyCycleAuditRepository`.
- Journal durable des cycles, décisions, RiskAssessment, ExecutionIntent et fills.
- Conservation des snapshots disponibles, IDs, timestamps et erreurs techniques sanitizées.
- Payloads métier canoniques stockés en JSON/JSONB sans seconde logique métier.
- HOLD et REJECT sont persistés sans intent/fill.
- ALLOW et MODIFY conservent l'intent Risk et les fills.
- Idempotence stricte par `cycle_id` et digest du résultat.
- Conflit explicite si la même identité métier est réutilisée avec des faits différents.
- Transaction unique et rollback complet du graphe en cas d'échec.
- Tests offline via `aiosqlite`.
- Ajout d'Alembic avec révision `0001_audit_journal`.
- Ajout de `docker-compose.yml` pour PostgreSQL 18 de développement.
- Aucune API Kraken privée, aucune route FastAPI de contrôle et aucun LIVE.

Validation locale Windows finale confirmée :

- `pytest backend` : **209/209** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 63 source files** ;
- `git diff --check` : aucune erreur ;
- 2 warnings de dépréciation FastAPI/Starlette sans échec ;
- commit/push fonctionnel confirmé et working tree propre.

Validation PostgreSQL réelle :

- Docker Desktop 4.47.0 / Engine 28.4.0 ;
- conteneur PostgreSQL `healthy` ;
- image `postgres:18.6-bookworm` ;
- Alembic `upgrade head` réussi ;
- `alembic_version = 0001_audit_journal` ;
- tables d'audit et table de version vérifiées avec `psql`.

Limite documentée : aucune garantie exactly-once globale entre ledger PAPER mémoire et PostgreSQL. Reconstruction du ledger et réconciliation restent différées.

### 2026-09-20 — Batch 08 Boucle autonome

**État : intégré sur `main` au commit `8deb72faeeaa1ac065189480c64ba16410c0d451` (`feat: add autonomous trading loop`).**

- Resynchronisation initiale sur GitHub `main` au HEAD `6415064b0f9bb0ee625cc42e8209cdf4388167e0` (`docs: record Batch 07 integration`).
- Ajout du package `ai_spot_trader.trading` avec `TradingCycleRunner`, `TradingEngine`, timeouts et résultat de cycle mémoire.
- Un seul `MarketState` est acquis par cycle et réutilisé par Agent/Risk/Broker ; un seul `PortfolioState` pré-cycle est utilisé par Agent/Risk.
- Verrou global de cycle pour empêcher tout chevauchement entre appel manuel et loop autonome.
- HOLD traverse Risk ; REJECT n'appelle pas Broker ; MODIFY/ALLOW exécutent uniquement l'intent Risk.
- Aucun `ExecutionIntent` n'est construit par l'orchestrateur.
- Erreurs techniques Market/Portfolio/Input/Agent/Risk/Broker/Post-Portfolio représentées explicitement, sans faux HOLD.
- Timeouts `asyncio.timeout` injectés pour Market/Agent/Broker ; aucun timeout Risk.
- Cadence positive injectée, attendue après chaque cycle sans rattrapage concurrent.
- Double `start()` interdit ; `stop()` coopératif réveille la cadence et attend la tâche.
- `AppRuntime` et `create_app` acceptent un moteur injecté pour le shutdown, sans démarrage automatique ni réseau au boot.
- Aucun paramètre produit de capital, paire, cadence, RiskPolicy ou coûts PAPER ajouté silencieusement.
- Aucune persistance durable, API de contrôle, API Kraken privée ou fonctionnalité LIVE.

Validation finale locale Windows confirmée avant intégration : `ruff check backend` **All checks passed**, `pytest backend` **203/203**, mypy **Success: no issues found in 57 source files**, `git diff --check` sans erreur ; 2 warnings de dépréciation FastAPI/Starlette sans échec.

### 2026-09-20 — Batch 07 Agent Luna

**État : intégré sur `main` au commit `caff3851d8299630f328b955c69eb31eb11baef0` (`feat: add Luna agent provider`).**

- Provider unique Luna/Sol, prompt `agent-luna-v1`, Structured Outputs stricts, sortie limitée aux champs stratégiques et IDs/timestamps applicatifs.
- Aucun import Risk/Broker/Kraken/FastAPI depuis l'agent ; aucun tool-calling ; aucune exécution directe.
- Commit documentaire post-intégration : `6415064b0f9bb0ee625cc42e8209cdf4388167e0` (`docs: record Batch 07 integration`).

Validation locale finale confirmée : `pytest backend` **168/168**, Ruff **All checks passed**, mypy **Success: no issues found in 54 source files**, `git diff --check` sans erreur.

### 2026-09-20 — Batch 06 Risk Engine

**État : intégré sur `main` au commit `d3271d6404ea2af38a42ff09e5a1df1eed5e141e` (`feat: add deterministic risk engine`).**

`DecisionCandidate.proposed_quantity`, `RiskAssessment`, `RiskPolicy`, ALLOW/MODIFY/REJECT, HOLD audité, intent uniquement après Risk, contrôles cash/position/chronologie et estimation PAPER partagée.

Validation locale finale : **131 tests**, Ruff/mypy OK, `git diff --check` sans erreur.

### 2026-09-20 — Batch 05 Portfolio State + Paper Broker

**État : intégré sur `main` au commit `c24551d36a863abbb5fdb86b79658b235c852772` (`feat: add paper portfolio and broker`).**

Portfolio PAPER canonique, ledger mémoire, état initial injecté, mutations atomiques, Paper Broker full-fill, contexte MarketState explicite et coûts PAPER auditables. Validation locale finale : **92 tests**, Ruff/mypy OK et `git diff --check` sans erreur.

### 2026-09-20 — Batch 04 Market State

**État : intégré sur `main` au commit `73acc4758427ea7575ddf0a43505e1c95fab5e9c`.**

Market State déterministe multi-horizon, fraîcheur descriptive, historique borné et no-look-ahead. Validation locale finale : **59 tests**, Ruff/mypy OK.

### 2026-09-20 — Batch 03 Kraken Market Data

**État : intégré sur `main` au commit `e7ac37955f08853024528fa9b9e10b5a75e05e3b`.**

APIs publiques Kraken Spot et normalisation fournisseur, sans clé privée ni ordre.

### 2026-09-20 — Batch 02 Contrats de domaine et configuration

**État : intégré sur `main` au commit `bff0f8b03740da4a01072af90111a2e5d9f208ef`.**

Contrats Pydantic stricts, horloge injectable, ports, PAPER, Luna/Sol et agressivité 1–10.

### 2026-09-20 — Batch 01 Bootstrap

**État : intégré sur `main` au commit `d9af0ca293dd9f2712969b246e394c4a8c188b5e`.**

Backend FastAPI/Python et frontend Next.js/shadcn initialisés.

### 2026-09-20 — Batch 00 Documentation initiale

**État : intégré sur `main`.**
