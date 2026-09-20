# 10 — Décisions et changelog

## 1. Règle d'utilisation

Ce document conserve les décisions architecturales durables et un changelog synthétique.

Statuts : **ACCEPTÉE**, **PROPOSÉE**, **SUPERSEDÉE**, **ABANDONNÉE**.

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
**ACCEPTÉE.** Mapping exact encore à décider ; aucune valeur ne contourne Risk.

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
**ACCEPTÉE.** Même provider pour Luna/Sol, pas de retry automatique au Batch 07.

### ADR-041 — Boucle autonome séquentielle sur snapshots cohérents
**ACCEPTÉE.** `TradingCycleRunner.run_cycle()` est canonique ; `TradingEngine` le répète, avec un seul cycle à la fois et un stop coopératif.

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
- **Statut : ACCEPTÉE**
- FastAPI expose observation et lifecycle, mais ne crée aucun artefact Agent/Risk/Broker.
- Les modèles HTTP sont dédiés et n'exposent pas directement les records ORM.

### ADR-048 — Query service de lecture durable
- **Statut : ACCEPTÉE**
- `CycleAuditReader` constitue la frontière de lecture.
- `SqlAlchemyCycleAuditQueryService` est l'implémentation SQLAlchemy.
- Les routes FastAPI ne doivent pas dépendre directement des records SQLAlchemy.

### ADR-049 — Start/stop uniquement sur moteur canonique injecté
- **Statut : ACCEPTÉE**
- L'API peut appeler `TradingEngine.start()` / `stop()` mais ne construit aucune boucle alternative.
- Aucun auto-start au lifecycle FastAPI.
- Sans moteur injecté, la commande est indisponible explicitement.

### ADR-050 — Pas de WebSocket au Batch 10
- **Statut : ACCEPTÉE**
- Aucun bus d'événements canonique n'existe encore.
- REST est suffisant pour le premier cockpit.
- Un WebSocket sera ajouté uniquement avec une source d'événements et un besoin de fréquence explicitement définis.

### ADR-051 — Réutiliser le schéma Batch 09 sans migration API
- **Statut : ACCEPTÉE**
- Les besoins de lecture du Batch 10 sont satisfaits par `0001_audit_journal`.
- Le schéma ne doit pas être modifié uniquement pour simplifier les routes.

### ADR-052 — Erreurs API sanitizées et DB lifecycle explicite
- **Statut : ACCEPTÉE**
- Erreur de cycle : `stage`, `error_type`, `timed_out` seulement.
- Aucun message brut, DSN ou secret dans les réponses.
- Si FastAPI crée la DB depuis `database_url`, il en possède la fermeture.

---

## 4. Décisions acceptées au Batch 11

Ces décisions sont intégrées avec le Batch 11 au commit fonctionnel `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7`, après validation locale et smoke test runtime.

### ADR-053 — Rewrite Next.js same-origin vers FastAPI
- **Statut : ACCEPTÉE**
- Le navigateur appelle uniquement `/backend/*` sur l'origine Next.js.
- Next.js réécrit ces appels vers `AI_SPOT_TRADER_BACKEND_URL`, par défaut `http://127.0.0.1:8000`.
- Aucune modification CORS backend n'est nécessaire pour le développement standard.
- L'adresse backend n'est pas exposée via une variable `NEXT_PUBLIC_*`.

### ADR-054 — Polling cockpit borné et purement présentatif
- **Statut : ACCEPTÉE**
- Le cockpit relit les ressources REST toutes les 10 secondes lorsque l'onglet est visible.
- Le polling s'arrête implicitement lorsque l'onglet n'est pas visible et ne pilote jamais la cadence du moteur.
- Aucun WebSocket n'est ajouté au Batch 11.

### ADR-055 — Types frontend alignés sur les contrats HTTP Batch 10
- **Statut : ACCEPTÉE**
- Les types TypeScript du cockpit reflètent `api/schemas.py` sans inventer de champ métier.
- UUID/timestamps restent des chaînes JSON et les `Decimal` sérialisés restent des chaînes côté frontend.
- Le frontend se limite au formatage d'affichage.

### ADR-056 — États d'indisponibilité explicites dans le cockpit
- **Statut : ACCEPTÉE**
- 404 = donnée encore absente ; 503 = ressource non configurée/indisponible ; échec réseau = backend inaccessible.
- Les listes vides restent des états métier normaux.
- Les boutons Start/Stop sont verrouillés pendant une commande et désactivés lorsque l'état ne l'autorise pas.
- Aucune stack trace ni payload brut inutile n'est affiché.

---

## 5. Propositions historiques

### ADR-P001 — Contrats Pydantic versionnés entre composants
**SUPERSEDÉE par ADR-020** pour le principe des contrats stricts ; version de schéma explicite encore à décider si nécessaire.

### ADR-P002 — Horloge injectable
**SUPERSEDÉE par ADR-023.**

### ADR-P003 — Architecture modulaire dans un backend unique
**SUPERSEDÉE par ADR-018.**

### ADR-P004 — Logs structurés corrélés
**PROPOSÉE.** UUID présents ; format/bibliothèque encore à décider.

---

## 6. Décisions encore ouvertes

- capital PAPER initial produit ;
- devise de référence produit ;
- univers initial de paires ;
- valeur produit de cadence ;
- données marché supplémentaires ;
- valeurs chiffrées des limites Risk ;
- limites d'exposition/drawdown quand les données le permettent ;
- mapping agressivité 1–10 ;
- valeurs expérimentales fee/spread/slippage ;
- base de coût et frontière de journée ;
- politique de rétention PostgreSQL ;
- reconstruction du ledger et stratégie de reprise après panne ;
- auth et déploiement ;
- logs structurés ;
- source d'événements/protocole d'un futur WebSocket ;
- éventuel LIVE.

---

## 7. Changelog

### 2026-09-20 — Batch 11 Frontend cockpit

**État : intégré sur `main` au commit fonctionnel `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7` (`feat: add frontend paper cockpit`).**

- Resynchronisation initiale confirmée sur GitHub `main` au HEAD `f29c51545cd63763ea9fefbfd37d441e52850609` (`docs: record Batch 10 integration`).
- Remplacement du cockpit Batch 01 par une interface de contrôle/observation PAPER.
- Ajout d'un client REST centralisé et de types TypeScript alignés sur les schémas HTTP Batch 10.
- Ajout du rewrite `/backend/*` vers une URL FastAPI configurable côté serveur Next.js.
- Polling d'affichage borné à 10 secondes, suspendu onglet masqué, sans rôle d'ordonnanceur.
- Gestion explicite des états 404, 503, listes vides, backend hors ligne et erreurs API.
- Start/Stop uniquement via les routes lifecycle Batch 10, avec protection contre les doubles clics.
- Vues intégrées : portefeuille, marché durable, cycles, décisions, Risk, executions/fills et dernière erreur.
- Aucun appel OpenAI/Kraken direct, aucune logique Risk, aucun WebSocket, aucun LIVE et aucune modification backend.

Validation finale locale confirmée :

- `pnpm --dir frontend lint` : **réussi** ;
- `pnpm --dir frontend typecheck` : **réussi** ;
- `pnpm --dir frontend build` : **réussi**, Next.js 16.3.3 ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- smoke test runtime confirmé pour backend accessible, moteur non configuré, données vides/503 et backend hors ligne ;
- commit/push confirmé sur `main` : `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7` ;
- working tree confirmé propre après push.

### 2026-09-20 — Batch 10 API FastAPI de contrôle/observation

**État : intégré sur `main` au commit fonctionnel `e6bcfd4dd345c934769b2f90fa7822232a80dd80`, avec commit documentaire post-intégration `f29c51545cd63763ea9fefbfd37d441e52850609`.**

- Resynchronisation initiale Batch 10 confirmée sur GitHub `main` au HEAD `328cdcea155905e2859e73ab3c46a195dc52047e` (`docs: record Batch 09 integration`).
- Référence fonctionnelle Batch 09 confirmée : `c53d04f14bcda82359d11c2e14fc1eb601ed14e0`.
- Ajout de modèles HTTP Pydantic dédiés.
- Ajout d'un `CycleAuditReader` et d'un query service SQLAlchemy pour le journal durable.
- Endpoints intégrés pour moteur, portefeuille, cycles, décisions, Risk, exécutions/fills, dernière erreur et dernier marché durable.
- Pagination `limit`/`offset`, ordre déterministe et filtres simples.
- Start/stop uniquement via le moteur canonique injecté ; aucun auto-start.
- Lifecycle DB possédé par FastAPI seulement lorsque créé depuis `database_url`.
- Erreurs DB et cycle sanitizées ; aucun secret exposé.
- Aucune nouvelle migration, aucun WebSocket, aucune API Kraken privée, aucun LIVE.
- Le bootstrap produit (capital/paire/cadence/RiskPolicy) reste volontairement non inventé.

Validation finale locale confirmée :

- `pytest backend` : **222 tests passés**, 2 warnings de dépréciation non bloquants ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 70 source files** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement.

### 2026-09-20 — Batch 09 Persistance et journal d'audit

**État : intégré fonctionnellement sur `main` au commit `c53d04f14bcda82359d11c2e14fc1eb601ed14e0`.**

SQLAlchemy async + `asyncpg` + Alembic, journal cycles/décisions/Risk/intents/fills, snapshots et erreurs sanitizées, idempotence par `cycle_id`, transaction/rollback, PostgreSQL Docker Compose.

Validation locale confirmée : **209 tests**, Ruff OK, mypy 63 fichiers OK, `git diff --check` OK et migration PostgreSQL `0001_audit_journal` validée.

### 2026-09-20 — Batch 08 Boucle autonome PAPER

**État : intégré.** `TradingCycleRunner` + `TradingEngine`, snapshots cohérents, cycles séquentiels, timeouts explicites et stop coopératif.

### 2026-09-20 — Batches 07 à 01

**État : intégrés.** Agent Luna/Sol, Risk Engine, Portfolio/Paper Broker, Market State, Kraken public, contrats domaine/configuration et bootstrap ont été intégrés successivement avec validations locales documentées lors de chaque batch.

### 2026-09-20 — Batch 00 Documentation initiale

**État : intégré.**
