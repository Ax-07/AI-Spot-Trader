# 09 — Roadmap de développement

## 1. Principes

La roadmap est organisée en **batches cohérents, limités et testables**. Chaque batch doit :

- partir du HEAD GitHub `main` resynchronisé ;
- auditer les composants existants ;
- ne modifier que ce qui est nécessaire ;
- inclure des tests adaptés ;
- mettre à jour la documentation concernée ;
- livrer un ZIP root-relative si plusieurs fichiers changent ;
- distinguer tests réellement exécutés et tests à lancer localement.

La séquence ci-dessous est proposée. Les invariants du Project Master restent confirmés, mais l'ordre peut évoluer si un audit technique le justifie.

---

## Batch 00 — Documentation initiale

**Statut : intégré sur `main`.**

Objectif : établir la source de vérité documentaire, fixer les invariants, expliciter les zones à décider et préparer la roadmap.

Livrables principaux : `docs/00_ETAT_ACTUEL.md`, `01_PROJECT_MASTER.md`, `02_ARCHITECTURE_TECHNIQUE.md`, `03_AGENT_TRADING_RISK.md`, `09_ROADMAP_DEVELOPPEMENT.md`, `10_DECISIONS_ET_CHANGELOG.md` et correction du README.

---

## Batch 01 — Bootstrap du projet

**Statut : intégré sur `main` au commit `d9af0ca293dd9f2712969b246e394c4a8c188b5e` (`feat: bootstrap backend and frontend`).**

Objectif : créer un socle exécutable et testable sans logique de trading.

Intégré :

- structure repository `backend/` + `frontend/` ;
- backend Python installable avec layout `src/` ;
- FastAPI minimal et endpoint `GET /health` ;
- configuration typée avec `pydantic-settings` ;
- cycle de vie asynchrone ;
- tests `pytest` ;
- Ruff et mypy configurés ;
- squelette Next.js + TypeScript + shadcn/ui + Tailwind CSS ;
- `pnpm` comme gestionnaire de paquets frontend ;
- ESLint et type-check TypeScript ;
- `.env.example` sans secret ;
- `.gitignore` commun ;
- commandes de développement depuis la racine.

Validation locale Windows confirmée : Python `3.13.14`, `pytest` 4/4, Ruff OK, mypy OK, `pnpm 10.15.1`, install/lint/typecheck/build frontend OK. Deux warnings de dépréciation Starlette/FastAPI ont été observés sans échec.

---

## Batch 02 — Contrats de domaine et configuration

**Statut : intégré sur `main` au commit `bff0f8b03740da4a01072af90111a2e5d9f208ef` (`feat: add domain contracts and configuration`).**

Pourquoi avant Kraken : stabiliser les frontières évite de laisser le format de l'exchange dicter le domaine.

Intégré :

- package `ai_spot_trader.domain` ;
- enums `BUY|SELL|HOLD`, `PAPER`, `ALLOW|MODIFY|REJECT` et modèles Luna/Sol ;
- contrats Pydantic stricts initiaux `MarketState`, `PortfolioState`, `AgentInput`, `DecisionCandidate`, `RiskAssessment`, `ExecutionIntent`, `Fill` ;
- UUID explicites de corrélation ;
- timestamps aware normalisés UTC ;
- mode `PAPER` uniquement ;
- Luna par défaut, Sol sélectionnable ;
- agressivité 1–10 lorsqu’elle est configurée ;
- horloge injectable minimale ;
- ports `MarketDataSource`, `LLMProvider`, `Broker` sans providers réels ;
- correction documentaire du statut du Batch 01.

Ce batch ne fige pas : sizing stratégique, limites chiffrées du Risk Engine, capital PAPER, univers Kraken, cadence, frontière statistique journalière, frais/slippage/fill, prompt LLM ou logique d'exécution.

Validation locale Windows confirmée avant intégration : Python `3.13.14`, `pytest` 20/20, Ruff OK et mypy OK. Deux warnings de dépréciation Starlette/FastAPI sont observés dans les dépendances de test, sans échec.

---

## Batch 03 — Kraken Market Data

**Statut : patch préparé et testé offline ; intégration Git en attente au moment de cette livraison.**

Objectif : première intégration publique Kraken derrière `MarketDataSource`, sans API privée ni logique de trading.

Implémentation du patch :

- package `ai_spot_trader.integrations.kraken` ;
- REST public `AssetPairs` avec `assetVersion=1` pour découverte/normalisation des paires Spot ;
- registre d'alias Kraken (`symbol`, `altname`, `wsname`) vers un symbole canonique slash-separated ;
- WebSocket Spot v2 `ticker` comme flux minimal pour `last`, `symbol` et `timestamp` ;
- parsing provider-local avant construction du `MarketState` minimal ;
- heartbeat et messages système non pertinents ignorés ;
- reconnexion bornée et configurable avec réabonnement ;
- fermeture propre sans tâche de fond persistante ;
- stale detection testable avec `Clock`, seuil optionnel non défini par défaut ;
- erreurs fournisseur dédiées et payloads sensibles non propagés ;
- `httpx` et `websockets` comme dépendances runtime directes ;
- aucune clé Kraken, aucun endpoint privé, aucun ordre, aucun LIVE.

Tests dans l'environnement ChatGPT : `pytest` 40/40 et `compileall` OK. Ruff et mypy restent à exécuter localement sous Windows car ils ne sont pas installés dans l'environnement ChatGPT utilisé pour cette livraison. Aucun test réseau Kraken ne fait partie de la suite par défaut.

Restent volontairement ouverts : univers initial, stratégie de streaming persistant du futur moteur, seuil métier global de stale et enrichissement du `MarketState`.

---

## Batch 04 — Market State

Objectif : agréger les données normalisées Kraken en snapshots canoniques, enrichir `MarketState`, calculer statistiques/indicateurs de contexte, gérer horizons et fraîcheur sans produire de signal autonome.

Tests : fixtures, données manquantes/périmées, calculs déterministes, absence de look-ahead.

Frontière : le Batch 04 consomme l'adapter public du Batch 03 ; il ne doit pas réintroduire des structures Kraken dans le domaine.

---

## Batch 05 — Portfolio State + Paper Broker

Objectif : portefeuille PAPER canonique, balances/positions, exécution simulée, frais/spread/slippage et invariant « pas de vente non détenue ».

À décider : capital initial, devise de référence, modèle de fill/slippage, barème de frais.

Tests critiques : cash insuffisant, SELL supérieur à position, frais, mise à jour positions, P&L de base.

---

## Batch 06 — Risk Engine

Objectif : autorité finale déterministe, `ALLOW` / `MODIFY` / `REJECT`, limites configurables et snapshot des raisons/limites appliquées.

À décider : limites numériques, mapping initial de l’agressivité 1–10 et règle métier de stale réellement appliquée par le Risk Engine.

Tests : taille/exposition, vente non couverte, stale market, drawdown/perte si retenus, impossibilité pour l'agressivité de contourner une limite absolue.

---

## Batch 07 — Agent Luna

Objectif : provider Luna derrière le port LLM, prompt/contrat versionné, sortie structurée validée et aucune exécution directe.

Tests : provider mocké, réponses invalides, actions inconnues, BUY/SELL/HOLD et vérification qu'une sortie invalide n'atteint pas le broker.

L'accès réel au LLM peut rester un test d'intégration séparé selon credentials et coûts.

---

## Batch 08 — Boucle autonome

Objectif : orchestrer Market State + Portfolio State + Agent + Risk + Paper Broker, cycle IDs, cadence, start/stop propre, timeouts/retries et comportement sûr en erreur.

Critère : plusieurs cycles PAPER tournent sans frontend ; `HOLD` inclus ; aucune dépendance au cockpit.

---

## Batch 09 — Persistance et journal d'audit

Objectif : PostgreSQL, schéma/migrations, cycles, décisions, risk assessments, fills, métriques et reprise cohérente des données nécessaires.

À décider : ORM, migrations, rétention, snapshots.

---

## Batch 10 — API FastAPI de contrôle

Objectif : exposer état moteur, portefeuille, décisions, performance, réglages autorisés, start/stop si retenu et WebSocket utiles au cockpit.

Tests : contrats API, erreurs, indépendance du moteur vis-à-vis du frontend.

---

## Batch 11 — Frontend cockpit

Objectif : compléter le bootstrap Next.js, dashboard, marché, portefeuille, décisions, trades PAPER, performance, état système et réglages autorisés.

Critère central : arrêter/redémarrer le frontend ne change pas l'état du moteur backend.

---

## Batch 12 — Analytics, P&L et expérimentation reproductible

Objectif : P&L brut/net, drawdown, frais, spread/slippage, exposition, nombre de trades, quotidien/cumulé, export/vue d'expérience et premières capacités de replay si les données le permettent.

Tests : fixtures comptables, cohérence brut/net, frontières de journée, replay sans données futures.

---

## Batch 13 — Expérimentation agressivité 1–10

Objectif : figer un mapping versionné, tester plusieurs niveaux sur un protocole comparable et mesurer rendement, drawdown, turnover, coûts et comportement du Risk Engine.

Règle : aucun cherry-picking ; toutes les configurations sont documentées.

---

## Batch 14 — Comparaison Luna / Sol

Objectif : passer de Luna à Sol par configuration, exécuter un protocole comparable et mesurer performance, stabilité de format, latence et coût.

Aucune conclusion n'est présupposée.

---

## Batch 15 — Préparation éventuelle du LIVE

**Hors périmètre jusqu'à décision explicite.**

Objectif potentiel : audit de readiness, adaptateur privé Kraken, réconciliation, permissions minimales, aucun retrait, garde-fous LIVE, mode explicite, tests et checklist.

Sa présence dans la roadmap ne vaut pas autorisation de trading réel.

---

## Dépendances principales

```text
00 Docs
  |
01 Bootstrap
  |
02 Domain contracts
  |
03 Kraken data
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

Certains travaux peuvent être parallélisés une fois les contrats stables, mais les dépendances de sécurité ne doivent pas être contournées.

---

## Décisions à prendre au fil de la roadmap

Avant de transformer une proposition en implémentation canonique, enregistrer la décision dans `10_DECISIONS_ET_CHANGELOG.md`, notamment pour :

- capital PAPER ;
- devise de référence ;
- univers initial ;
- cadence ;
- indicateurs ;
- seuil métier de fraîcheur ;
- limites de risque ;
- mapping agressivité ;
- modèle PAPER ;
- ORM/migrations ;
- auth cockpit ;
- déploiement ;
- frontière de journée ;
- activation éventuelle du LIVE.
