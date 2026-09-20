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

La séquence ci-dessous est **proposée**. Les invariants du Project Master restent confirmés, mais l'ordre peut évoluer si un audit technique le justifie.

---

## Batch 00 — Documentation initiale

**Statut : intégré sur `main`.**

Objectif :

- établir la source de vérité documentaire ;
- fixer les invariants ;
- expliciter les zones encore à décider ;
- préparer la roadmap.

Livrables :

- `docs/00_ETAT_ACTUEL.md`
- `docs/01_PROJECT_MASTER.md`
- `docs/02_ARCHITECTURE_TECHNIQUE.md`
- `docs/03_AGENT_TRADING_RISK.md`
- `docs/09_ROADMAP_DEVELOPPEMENT.md`
- `docs/10_DECISIONS_ET_CHANGELOG.md`
- correction documentaire de `README.md`

Critère de sortie : documentation cohérente, liens valides, aucun choix non décidé présenté comme acquis.

---

## Batch 01 — Bootstrap du projet

**Statut : patch préparé et validé localement sous Windows, non intégré au moment de sa génération.**

**Objectif :** créer un socle exécutable et testable sans logique de trading.

Implémenté dans le patch :

- structure repository `backend/` + `frontend/` ;
- backend Python installable avec layout `src/` ;
- FastAPI minimal et endpoint `GET /health` ;
- configuration typée avec `pydantic-settings` ;
- cycle de vie asynchrone prêt à accueillir de futures tâches `asyncio` ;
- tests `pytest` ;
- Ruff et mypy configurés côté backend ;
- squelette Next.js + TypeScript + shadcn/ui + Tailwind CSS ;
- `pnpm` comme gestionnaire de paquets frontend ;
- ESLint et type-check TypeScript côté frontend ;
- `.env.example` sans secret ;
- `.gitignore` commun ;
- commandes de développement documentées.

Critère de sortie :

- backend démarre ;
- endpoint health minimal ;
- tests de bootstrap passent ;
- frontend démarre indépendamment ;
- aucun secret versionné.

Les validations Windows sont confirmées : backend sous Python `3.13.14` (`pytest`, Ruff, mypy) et frontend via `pnpm 10.15.1` (install, ESLint, type-check, build Next.js). L'intégration Git reste à effectuer avant de considérer le batch intégré.

---

## Batch 02 — Contrats de domaine et configuration

**Pourquoi avant Kraken :** stabiliser les frontières évite de laisser le format de l'exchange dicter tout le domaine.

Objectif :

- modèles Pydantic initiaux ;
- types d'action ;
- identifiants/corrélation ;
- abstraction de clock si retenue ;
- mode `PAPER`;
- configuration du modèle LLM et agressivité ;
- interfaces Kraken/LLM/Broker sans implémentation métier complète.

Contrats candidats :

- `MarketState`
- `PortfolioState`
- `AgentInput`
- `DecisionCandidate`
- `RiskAssessment`
- `ExecutionIntent`
- `Fill`

Tests :

- validation stricte ;
- sérialisation ;
- enums/invariants de base.

---

## Batch 03 — Kraken Market Data

Objectif :

- connexion aux données publiques Kraken ;
- WebSocket pour les flux nécessaires ;
- récupération/normalisation des métadonnées utiles ;
- reconnexion et stale detection ;
- aucune clé privée nécessaire.

Le batch ne construit pas encore toute la stratégie ni le Paper Broker.

Tests :

- unitaires avec messages fixtures ;
- intégration réseau publique optionnelle et clairement séparée.

À décider avant/pendant le batch :

- paires initiales ;
- flux Kraken requis ;
- politique de reconnexion.

---

## Batch 04 — Market State

Objectif :

- agréger les flux Kraken en snapshots canoniques ;
- calculer statistiques/indicateurs de contexte retenus ;
- gérer fraîcheur et timestamps ;
- ne produire aucun signal de trading autonome.

Tests :

- construction à partir de fixtures ;
- données manquantes/périmées ;
- calculs déterministes ;
- absence de look-ahead.

---

## Batch 05 — Portfolio State + Paper Broker

Objectif :

- portefeuille PAPER canonique ;
- balances/positions ;
- exécution simulée ;
- frais/spread/slippage ;
- invariant "pas de vente non détenue".

À décider :

- capital initial ;
- devise de référence ;
- modèle de fill/slippage ;
- barème de frais.

Tests critiques :

- BUY avec cash insuffisant ;
- SELL supérieur à la position ;
- calculs de frais ;
- mise à jour des positions ;
- P&L de base.

---

## Batch 06 — Risk Engine

Objectif :

- autorité finale déterministe ;
- `ALLOW` / `MODIFY` / `REJECT` ;
- limites de risque configurables ;
- snapshot des raisons et limites appliquées.

À décider :

- limites numériques ;
- mapping initial agressivité 1–10.

Tests :

- limites de taille/exposition ;
- vente non couverte ;
- stale market ;
- drawdown/perte si retenus ;
- agressivité ne contourne jamais une limite absolue.

---

## Batch 07 — Agent Luna

Objectif :

- abstraction LLM ;
- provider Luna ;
- prompt/contrat versionné ;
- sortie structurée validée ;
- aucune exécution directe.

Tests :

- provider mocké ;
- réponses invalides ;
- actions inconnues ;
- BUY/SELL/HOLD ;
- vérification qu'une sortie invalide n'atteint pas le broker.

L'accès réel au LLM peut rester un test manuel/intégration séparé selon credentials et coûts.

---

## Batch 08 — Boucle autonome

Objectif :

- orchestrer Market State + Portfolio State + Agent + Risk + Paper Broker ;
- cycle IDs ;
- cadence ;
- start/stop propre ;
- gestion timeouts/retries ;
- comportement sûr en cas d'erreur.

Critère de sortie :

- plusieurs cycles PAPER peuvent tourner sans frontend ;
- `HOLD` inclus ;
- aucune dépendance au cockpit.

---

## Batch 09 — Persistance et journal d'audit

Objectif :

- PostgreSQL ;
- schéma/migrations ;
- cycles, décisions, risk assessments, fills, métriques ;
- reprise cohérente des données nécessaires.

À décider :

- ORM ;
- migrations ;
- rétention ;
- stratégie de snapshots.

Tests :

- migrations ;
- contraintes DB ;
- reconstruction d'un cycle ;
- absence de secret dans les champs journalisés.

---

## Batch 10 — API FastAPI de contrôle

Objectif :

- exposer l'état du moteur ;
- portefeuille ;
- décisions ;
- performance ;
- réglages autorisés ;
- start/stop si retenu ;
- flux WebSocket utiles au cockpit.

Tests :

- API contracts ;
- erreurs ;
- moteur indépendant de la connexion frontend.

---

## Batch 11 — Frontend cockpit

Objectif :

- compléter le bootstrap Next.js + TypeScript déjà présent ;
- étendre shadcn/ui + Tailwind ;
- dashboard ;
- marché ;
- portefeuille ;
- décisions ;
- trades PAPER ;
- performance ;
- état système ;
- réglages autorisés.

Critère central :

- arrêter/redémarrer le frontend ne change pas l'état du moteur backend.

---

## Batch 12 — Analytics, P&L et expérimentation reproductible

Objectif :

- P&L brut/net ;
- drawdown ;
- frais ;
- spread/slippage ;
- exposition ;
- nombre de trades ;
- quotidien/cumulé ;
- export ou vue d'expérience ;
- premières capacités de replay si les données le permettent.

Tests :

- fixtures comptables ;
- cohérence brut/net ;
- frontières de journée ;
- replay sans données futures.

---

## Batch 13 — Expérimentation agressivité 1–10

Objectif :

- figer un mapping versionné ;
- tester plusieurs niveaux sur un protocole comparable ;
- mesurer rendement, drawdown, turnover, coûts et comportement du Risk Engine.

Règle :

- ne pas choisir rétrospectivement uniquement les runs favorables ;
- documenter toutes les configurations.

---

## Batch 14 — Comparaison Luna / Sol

Objectif :

- passer de Luna à Sol par configuration ;
- exécuter un protocole comparable ;
- mesurer performance, stabilité de format, latence et coût.

Le résultat peut justifier de conserver Luna, passer à Sol ou continuer les tests ; aucune conclusion n'est présupposée.

---

## Batch 15 — Préparation éventuelle du LIVE

**Hors périmètre jusqu'à décision explicite.**

Objectif potentiel :

- audit de readiness ;
- adapter privé Kraken ;
- réconciliation ;
- permissions minimales ;
- aucun retrait ;
- garde-fous LIVE ;
- mode explicite ;
- tests et checklist.

Ce batch ne doit être démarré qu'après une décision dédiée. Sa présence dans la roadmap ne vaut pas autorisation de trading réel.

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
- limites de risque ;
- mapping agressivité ;
- modèle PAPER ;
- ORM/migrations ;
- auth cockpit ;
- déploiement ;
- frontière de journée ;
- activation éventuelle du LIVE.
