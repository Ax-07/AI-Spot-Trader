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

### ADR-016 — PostgreSQL comme base cible
- **Statut : ACCEPTÉE**
- ORM/migrations restent à décider.

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
- `MarketDataSource`, `MarketObservationSource`, `LLMProvider`, `Broker` sont les ports canoniques actuels.

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
- BUY/SELL doivent porter `proposed_quantity > 0`.
- HOLD ne porte aucune quantité.
- L'agent source la taille stratégique ; Risk peut la réduire mais ne choisit pas arbitrairement une taille initiale.

### ADR-032 — RiskAssessment porte quantités et raisons structurées
- **Statut : ACCEPTÉE**
- `requested_quantity`, `authorized_quantity` et `evaluated_limits` rendent ALLOW/MODIFY/REJECT auditables.
- `RiskReason` fournit des codes stables et testables.
- MODIFY signifie strictement une réduction ; REJECT ne crée aucun `ExecutionIntent`.
- HOLD produit un assessment auditable sans intent.

### ADR-033 — RiskPolicy injectée, sans limites produit implicites
- **Statut : ACCEPTÉE**
- La policy supporte max order notional, whitelist, seuil stale métier et autorisation explicite de réduction.
- Aucune valeur chiffrée produit n'est codée en dur ni ajoutée à `Settings` au Batch 06.
- Drawdown/daily loss restent non implémentés tant que l'historique P&L nécessaire n'existe pas.

### ADR-034 — Estimation PAPER partagée entre Risk et Paper Broker
- **Statut : ACCEPTÉE**
- `broker/pricing.py` contient la mathématique pure commune des coûts PAPER.
- Risk l'utilise pour vérifier le cash BUY prévisible sans exécuter l'ordre.
- Paper Broker utilise la même primitive pour le fill réel.

### ADR-035 — MODIFY ne peut qu'abaisser le risque sans changer la stratégie
- **Statut : ACCEPTÉE**
- Risk ne change jamais BUY↔SELL, symbole ou actif.
- Risk n'augmente jamais la quantité proposée.
- Réductions uniquement si la policy les autorise.

### ADR-036 — HOLD traverse la frontière Risk pour audit
- **Statut : ACCEPTÉE**
- HOLD retourne `ALLOW` avec `HOLD_NO_EXECUTION` et aucun `ExecutionIntent`.

### ADR-037 — Le LLM ne produit que les champs stratégiques
- **Statut : ACCEPTÉE**
- La réponse fournisseur contient uniquement `action`, `symbol`, `proposed_quantity`, `rationale`.
- `decision_id` vient d'une factory UUID injectable.
- `cycle_id` est contrôlé par `AgentInput`.
- `created_at` vient d'un `Clock` injectable.
- `DecisionCandidate` reste l'unique contrat métier exposé au reste du moteur.

### ADR-038 — L'Agent est limité au symbole du MarketState fourni
- **Statut : ACCEPTÉE**
- `decision.symbol` doit être exactement égal à `agent_input.market_state.symbol`.
- L'agent ne peut pas choisir un actif pour lequel aucun snapshot marché n'a été fourni.
- Risk conserve indépendamment son propre contrôle de symbole en aval.

### ADR-039 — Prompt versionné et Structured Outputs stricts
- **Statut : ACCEPTÉE**
- Prompt initial : `agent-luna-v1`.
- OpenAI Responses API avec `text.format.type=json_schema`, `strict=true` et champs supplémentaires interdits.
- La sortie est revalidée localement sans réparation stratégique silencieuse.
- Aucun tool-calling ou chemin d'exécution n'est fourni au LLM.

### ADR-040 — Adapter OpenAI minimal sur httpx, secrets via SecretStr
- **Statut : ACCEPTÉE**
- Identifiants vérifiés : `gpt-5.6-luna` et `gpt-5.6-sol`.
- Le même `OpenAIDecisionProvider` supporte Luna et Sol par configuration.
- `httpx`, déjà dépendance runtime, est réutilisé ; aucun SDK runtime supplémentaire au Batch 07.
- Clé OpenAI chargée via environnement en `SecretStr`, jamais incluse dans prompts/logs/exceptions.
- Aucun retry automatique au Batch 07 ; les erreurs restent explicites et testables.

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
- cadence de décision ;
- données marché supplémentaires ;
- valeurs chiffrées produit des limites Risk ;
- éventuelle limite d'exposition simple/avancée ;
- max drawdown / max daily loss quand les données existeront ;
- mapping agressivité 1–10 ;
- valeurs expérimentales fee/spread/slippage ;
- modèle de fill plus riche éventuel ;
- base de coût et frontière de journée ;
- ORM/migrations/rétention ;
- auth, déploiement, reprise après panne ;
- versionnement explicite des schémas si nécessaire ;
- éventuelle policy de retry LLM bornée si le Batch 08 la justifie ;
- éventuel LIVE.

---

## 5. Changelog

### 2026-09-20 — Batch 07 Agent Luna

**État : intégré sur `main` au commit `caff3851d8299630f328b955c69eb31eb11baef0` (`feat: add Luna agent provider`).**

- Resynchronisation confirmée sur GitHub `main` au HEAD `d3271d6404ea2af38a42ff09e5a1df1eed5e141e` (`feat: add deterministic risk engine`).
- Intégration finale du Batch 07 confirmée sur `main` au commit `caff3851d8299630f328b955c69eb31eb11baef0` (`feat: add Luna agent provider`).
- Correction documentaire : Batch 06 enregistré comme intégré avec validation locale finale 131 tests, Ruff OK, mypy OK sur 47 fichiers source et `git diff --check` OK.
- Port `LLMProvider` conservé inchangé.
- Ajout du package `ai_spot_trader.agent`.
- `OpenAIDecisionProvider` commun Luna/Sol et `OpenAIResponsesClient` injectable.
- Prompt versionné `agent-luna-v1`.
- Réponse LLM limitée à action/symbole/quantité/rationale ; IDs et timestamp restent applicatifs.
- Symbole strictement limité au `MarketState` fourni.
- OpenAI Responses API avec Structured Outputs JSON Schema stricts et `additionalProperties=false`.
- Parsing local exact en `Decimal`, sans coercition de chaînes ni réparation d'intention.
- Erreurs transport, fournisseur, validation et invariant Agent séparées.
- Clé OpenAI via `SecretStr`; `.env.example` contient uniquement une valeur vide.
- Aucun import Risk/Broker/Kraken/FastAPI dans l'agent ; aucun tool-calling ; aucune exécution directe.
- Aucun retry automatique et aucune nouvelle dépendance runtime.

Validation réellement exécutée dans l'environnement ChatGPT : suite ciblée Agent/OpenAI/configuration **42/42**, `compileall`, contrôle lignes Python <= 100 et absence d'espaces de fin de ligne. Aucun appel réseau réel.

Validation locale Windows finale confirmée par l'utilisateur : `pytest backend` **168/168**, Ruff **All checks passed**, mypy **Success: no issues found in 54 source files**, `git diff --check` sans erreur ; uniquement warnings LF → CRLF habituels et 2 warnings FastAPI/Starlette sans échec.

### 2026-09-20 — Batch 06 Risk Engine

**État : intégré sur `main` au commit `d3271d6404ea2af38a42ff09e5a1df1eed5e141e` (`feat: add deterministic risk engine`).**

- `DecisionCandidate.proposed_quantity` fixe la frontière de sizing stratégique.
- `RiskAssessment` porte quantités demandée/autorisée, `RiskLimit` évaluées et `RiskReason` structurés.
- Package `ai_spot_trader.risk` avec `RiskPolicy`, `RiskEngine`, `RiskResult` et erreurs dédiées.
- ALLOW/MODIFY/REJECT explicites ; REJECT ne produit aucun intent.
- MODIFY ne peut que réduire la quantité ; jamais de changement d'action/symbole ni augmentation.
- HOLD produit un assessment auditable mais aucun `ExecutionIntent`.
- Contrôles : symbole, whitelist, chronologie, stale métier, max order notional, cash BUY, SELL détenu/disponible et rôles d'actifs.
- Estimation PAPER factorisée dans `broker/pricing.py`, partagée entre Risk et Paper Broker.

Validation locale Windows finale confirmée avant intégration : `pytest backend` **131/131**, Ruff **All checks passed**, mypy **Success: no issues found in 47 source files**, `git diff --check` sans erreur ; uniquement warnings LF → CRLF habituels et 2 warnings FastAPI/Starlette sans échec.

### 2026-09-20 — Batch 05 Portfolio State + Paper Broker

**État : intégré sur `main` au commit `c24551d36a863abbb5fdb86b79658b235c852772` (`feat: add paper portfolio and broker`).**

Portfolio PAPER canonique, ledger mémoire, état initial injecté, mutations atomiques. Paper Broker full-fill, contexte MarketState explicite et coûts PAPER auditables. Validation locale finale : **92 tests**, Ruff/mypy OK et `git diff --check` sans erreur.

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
