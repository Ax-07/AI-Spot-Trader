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
**ACCEPTÉE.** La plage `1..10` est canonique et aucune valeur ne contourne Risk. Le mapping exact `aggressiveness-map-v1` est intégré avec le Batch 13.

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

## 5. Décisions acceptées au Batch 12

Ces décisions sont intégrées avec le Batch 12 au commit fonctionnel `3f39999736b6fc3800ecfd36ddee0253c734d25d`, après validation locale backend/frontend et push confirmé.

### ADR-057 — Journal durable comme source canonique des analytics
- **Statut : ACCEPTÉE**
- Les analytics dérivent uniquement des faits déjà persistés par le journal Batch 09.
- L'état courant du ledger mémoire ne sert pas à reconstruire l'historique.
- Aucune décision Agent/Risk n'est modifiée par les analytics.

### ADR-058 — Analytics calculés à la volée par un reducer pur
- **Statut : ACCEPTÉE**
- `build_paper_analytics_report` est déterministe et sans I/O/horloge courante.
- `SqlAlchemyPaperAnalyticsQueryService` charge les faits puis délègue le calcul.
- Pas de table/vue matérialisée ni migration tant que le volume ne justifie pas cette complexité.

### ADR-059 — Définitions PAPER du P&L, drawdown et exposition
- **Statut : ACCEPTÉE**
- P&L net = equity marquée - equity initiale durable.
- P&L brut = P&L net + frais + spread + slippage cumulés.
- Les coûts sont les valeurs des fills durables, jamais une réestimation avec la configuration actuelle.
- Drawdown sur l'equity nette ; exposition = valeur des positions / equity positive.
- Un trade est une exécution ayant produit un fill ; HOLD/REJECT ne sont pas des trades.

### ADR-060 — UTC et no look-ahead pour les séries historiques
- **Statut : ACCEPTÉE**
- La frontière de journée analytics est UTC.
- Chaque point est valorisé au prix du `MarketState` durable du même cycle.
- Aucun dernier prix futur/courant n'est appliqué rétroactivement.
- Une rupture de continuité portefeuille ou un actif non valorisable est une erreur d'intégrité explicite.

### ADR-061 — Reproductibilité versionnée des métriques
- **Statut : ACCEPTÉE**
- La réponse analytics contient `calculation_version` et un SHA-256 de la séquence ordonnée `(cycle_id, result_digest)`.
- À faits et version identiques, le rapport doit être identique, quel que soit l'ordre d'entrée.
- Cette garantie ne couvre pas le rejeu déterministe du LLM.

---

## 5 bis. Décisions acceptées au Batch 13

Ces décisions sont intégrées avec le Batch 13 au commit fonctionnel `1747beb5efd1fe9763bc9b2d23f3a115575daaec`, après validation locale complète et push confirmé.

### ADR-062 — Mapping discret d'agressivité versionné
- **Statut : ACCEPTÉE**
- Les niveaux `1..10` sont mappés explicitement par `aggressiveness-map-v1`.
- Le mapping décrit une posture et une instruction stratégique, pas un seuil Risk ni une formule de sizing déterministe.
- Tout changement sémantique futur du mapping exige une nouvelle version.

### ADR-063 — Agressivité limitée à la stratégie Agent
- **Statut : ACCEPTÉE**
- L'agressivité peut influencer la volonté d'agir et la quantité proposée par l'Agent.
- Elle n'est jamais passée comme paramètre au `RiskEngine.evaluate(...)`.
- Elle ne peut modifier balance, position, max notional, whitelist, fraîcheur, solvabilité ou coûts PAPER.
- Seul Risk continue de créer un `ExecutionIntent`.

### ADR-064 — Prompt Agent `agent-strategy-v2`
- **Statut : ACCEPTÉE**
- Le prompt explicite le mapping d'agressivité comme contexte stratégique uniquement.
- Le provider vérifie modèle, prompt et digest du manifeste avant l'appel LLM lorsqu'un manifeste est présent.
- Les anciens `AgentInput` sans contexte restent lisibles ; le provider peut normaliser le contexte avant appel.

### ADR-065 — Manifeste expérimental durable dans AgentInput
- **Statut : ACCEPTÉE**
- `paper-experiment-v1` enregistre niveau/mapping, modèle, prompt, univers, snapshot RiskPolicy, coûts PAPER, source/dataset, fenêtre et version analytics.
- Le manifeste porte un digest SHA-256 de sa représentation canonique.
- Il est persisté via le payload `AgentInput` existant ; aucune migration n'est requise.
- Le digest identifie le protocole, pas une garantie de déterminisme LLM.

### ADR-066 — Comparaison d'agressivité par réutilisation directe de Batch 12
- **Statut : ACCEPTÉE**
- Les comparaisons consomment des `PaperAnalyticsReport` déjà calculés.
- Aucun recalcul divergent de P&L/drawdown/coûts/exposition n'est introduit.
- Les runs doivent être identiques sur tous les champs contrôlés hors agressivité.
- La sortie reste factuelle et ne produit ni classement automatique ni sélection rétrospective.

### ADR-067 — Pas d'API/frontend expérimental au Batch 13
- **Statut : ACCEPTÉE**
- Le protocole expérimental reste backend/domaine.
- Le cockpit n'obtient pas encore de configurateur d'agressivité/Risk/coûts.
- Une surface de lancement d'expériences sera décidée séparément si elle devient nécessaire.

---

## 5 ter. Décisions acceptées au Batch 14

Ces décisions sont intégrées avec le Batch 14 au commit fonctionnel `dc60033f60bf5d98a68e6131a9320e575d46cc8d`, après validation locale complète, push confirmé et working tree propre.

### ADR-068 — Versionner la comparaison modèle en `paper-experiment-v2`
- **Statut : ACCEPTÉE**
- `paper-experiment-v1` reste le contrat Batch 13 et continue d'exclure uniquement l'agressivité de son identité de comparaison.
- `paper-experiment-v2` fixe `comparison_variable = LLM_MODEL` afin que Luna/Sol soit l'unique variable autorisée.
- Les champs v2 sont optionnels dans `ExperimentManifest` pour conserver la lecture des anciens payloads v1.
- Le digest v1 exclut explicitement les nouveaux champs afin de préserver l'identité des manifestes déjà persistés.

### ADR-069 — Séparer identité de groupe et identité de run
- **Statut : ACCEPTÉE**
- `experiment_group_digest` identifie les champs contrôlés communs d'une expérience Luna/Sol.
- Il exclut `llm_model` et `replicate_index`, mais inclut agressivité, prompt, univers, RiskPolicy, coûts PAPER, source/dataset, fenêtre, version analytics et `replicate_count`.
- `experiment_digest` reste l'identité complète de chaque run et inclut modèle, groupe et index de répétition.
- La persistance reste le JSON/JSONB `AgentInput` existant ; aucune table/migration dédiée n'est créée.

### ADR-070 — Dataset figé obligatoire pour une comparaison modèle stricte
- **Statut : ACCEPTÉE**
- `source_digest` est obligatoire dans `paper-experiment-v2`.
- Deux passages live successifs non figés ne sont pas traités comme une comparaison strictement appariée.
- Le batch formalise l'identité du dataset ; il n'ajoute pas de moteur de replay historique parallèle.
- Toute fenêtre/univers/source différente fait changer le groupe et invalide la comparaison.

### ADR-071 — Répétitions appariées pour le non-déterminisme LLM
- **Statut : ACCEPTÉE**
- `replicate_index` et `replicate_count` sont persistés dans le manifeste v2.
- `compare_model_runs(...)` exige les répétitions `1..N` pour Luna et Sol et refuse un groupe incomplet.
- Le protocole ne prétend pas disposer d'un seed fournisseur exact.
- Les répétitions restent des observations brutes ; aucune sélection post-hoc ou exclusion d'une répétition n'est autorisée par le comparateur.

### ADR-072 — Comparaison modèle factuelle sans score ni gagnant automatique
- **Statut : ACCEPTÉE**
- Le comparateur réutilise directement les `PaperAnalyticsReport` Batch 12.
- Les métriques exposées incluent P&L brut/net, coûts, drawdown, exposition, trades BUY/SELL, HOLD/REJECT/MODIFY/FAILED, points cumulés et daily.
- Aucune formule P&L parallèle, score composite, ranking ou choix automatique d'un « meilleur modèle » n'est introduit.
- API et frontend restent inchangés au Batch 14.

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

- capital PAPER initial produit ;
- devise de référence produit ;
- univers initial de paires ;
- valeur produit de cadence ;
- données marché supplémentaires ;
- valeurs chiffrées des limites Risk ;
- limites d'exposition/drawdown quand les données le permettent ;
- valeurs expérimentales fee/spread/slippage ;
- dataset/replay canonique concret pour exécuter les comparaisons strictement appariées ;
- éventuelles statistiques descriptives de dispersion des répétitions LLM ;
- politique de rétention PostgreSQL ;
- reconstruction du ledger et stratégie de reprise après panne ;
- auth et déploiement ;
- logs structurés ;
- source d'événements/protocole d'un futur WebSocket ;
- éventuel LIVE.

---

## 8. Changelog

### 2026-09-21 — Batch 14 Comparaison contrôlée GPT-5.6 Luna / GPT-5.6 Sol

**État : intégré sur `main` au commit fonctionnel `dc60033f60bf5d98a68e6131a9320e575d46cc8d` (`feat: add controlled Luna Sol experiments`).**

- Référence GitHub de départ : `655b66b639c4e9c1803cef3920c9a96e7dd16055` (`docs: record Batch 13 integration`).
- Audit du manifeste Batch 13, du comparateur d'agressivité, des analytics Batch 12, du provider Luna/Sol, du runner et de la persistance JSON/JSONB.
- `paper-experiment-v1` conservé pour l'agressivité ; `paper-experiment-v2` intégré pour l'axe `LLM_MODEL`.
- `experiment_group_digest` intégré pour les champs contrôlés et `experiment_digest` conservé comme identité complète du run.
- `replicate_index` / `replicate_count` intégrés avec obligation d'un ensemble complet de répétitions Luna/Sol.
- `source_digest` obligatoire en v2 pour identifier un dataset/snapshot figé ; aucun replay historique parallèle ajouté.
- Comparaison Luna/Sol basée uniquement sur `PaperAnalyticsReport`, sans score composite ni ranking automatique.
- Compatibilité v1 conservée ; aucune migration PostgreSQL, aucun changement API/frontend, aucun LIVE.

Validation locale finale confirmée :

- `pytest backend` : **266 tests passés**, 2 warnings de dépréciation externes ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 81 source files** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push confirmé sur `main` : `dc60033f60bf5d98a68e6131a9320e575d46cc8d` ;
- working tree confirmé propre après push.

Validation de préparation ChatGPT : **34 tests ciblés** et `py_compile` réussis.

### 2026-09-21 — Batch 13 Expérimentation agressivité 1–10

**État : intégré sur `main` au commit fonctionnel `1747beb5efd1fe9763bc9b2d23f3a115575daaec` (`feat: add versioned aggressiveness experiments`).**

- Référence GitHub de départ : `bc1b06ad25a2aa0ba7781d50c9e642dc113850ad` (`docs: record Batch 12 integration`).
- Mapping discret intégré : `aggressiveness-map-v1` avec dix postures stratégiques.
- `AggressivenessContext` et `ExperimentManifest` ajoutés aux contrats `AgentInput`, avec compatibilité des anciens payloads grâce à des champs optionnels.
- Prompt Agent intégré : `agent-strategy-v2`.
- Manifeste `paper-experiment-v1` avec digest SHA-256 déterministe.
- Snapshot de `RiskPolicy` et des coûts PAPER enregistré dans l'identité expérimentale ; aucune valeur produit inventée.
- Persistance via le JSON/JSONB `AgentInput` existant ; aucune migration.
- Comparaison pure de runs via `PaperAnalyticsReport`, sans recalcul divergent des métriques Batch 12 et sans ranking automatique.
- Comparaison refusée si modèle, prompt, Risk, coûts, univers, source/dataset, fenêtre ou version analytics diffèrent hors dimension expérimentale autorisée.
- Aucun changement API/frontend, aucun LIVE, aucune API Kraken privée.
- Limite conservée : même manifeste + mêmes faits ne garantit pas une sortie LLM bit-à-bit identique.

Validation locale finale confirmée :

- Python : **3.13.14** ;
- `pytest backend` : **249 tests passés**, 2 warnings de dépréciation externes ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 81 source files** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- commit/push confirmé sur `main` : `1747beb5efd1fe9763bc9b2d23f3a115575daaec` ;
- working tree confirmé propre après push.

### 2026-09-20 — Batch 12 Analytics et expérimentation reproductible

**État : intégré sur `main` au commit fonctionnel `3f39999736b6fc3800ecfd36ddee0253c734d25d` (`feat: add reproducible paper analytics`).**

- Journal durable utilisé comme source des analytics.
- Reducer PAPER pur avec P&L brut/net, coûts, drawdown, exposition, trades, HOLD/REJECT/MODIFY/FAILED, séries par cycle et daily UTC.
- No look-ahead par valorisation au prix durable de chaque cycle.
- Reproductibilité via `paper-analytics-v1` + digest des `result_digest`.
- Endpoint analytics et panneau cockpit ajoutés sans modifier Agent/Risk/Broker.

Validation finale locale confirmée : `pytest backend` **231 passés**, Ruff OK, mypy **76 fichiers sans erreur**, frontend lint/typecheck/build réussis et `git diff --check` sans erreur.

### 2026-09-20 — Batch 11 Frontend cockpit

**État : intégré sur `main` au commit fonctionnel `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7` (`feat: add frontend paper cockpit`).**

Cockpit Next.js/shadcn, client REST centralisé, polling borné, états 404/503/offline, Start/Stop via FastAPI uniquement, aucune logique stratégique frontend.

### 2026-09-20 — Batch 10 API FastAPI de contrôle/observation

**État : intégré sur `main` au commit fonctionnel `e6bcfd4dd345c934769b2f90fa7822232a80dd80`.**

Façade REST, query service durable, lifecycle moteur injecté, erreurs sanitizées, aucune migration/API Kraken privée/LIVE.

### 2026-09-20 — Batch 09 Persistance et journal d'audit

**État : intégré fonctionnellement sur `main` au commit `c53d04f14bcda82359d11c2e14fc1eb601ed14e0`.**

SQLAlchemy async + `asyncpg` + Alembic, journal cycles/décisions/Risk/intents/fills, snapshots et erreurs sanitizées, idempotence par `cycle_id`, transaction/rollback, PostgreSQL Docker Compose.

### 2026-09-20 — Batch 08 Boucle autonome PAPER

**État : intégré.** `TradingCycleRunner` + `TradingEngine`, snapshots cohérents, cycles séquentiels, timeouts explicites et stop coopératif.

### 2026-09-20 — Batches 07 à 01

**État : intégrés.** Agent Luna/Sol, Risk Engine, Portfolio/Paper Broker, Market State, Kraken public, contrats domaine/configuration et bootstrap ont été intégrés successivement avec validations locales documentées lors de chaque batch.

### 2026-09-20 — Batch 00 Documentation initiale

**État : intégré.**
