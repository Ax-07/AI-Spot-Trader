# AI Spot Trader

AI Spot Trader est une application expérimentale de **trading crypto SPOT pilotée par un agent IA unique**.

Le projet vise à étudier jusqu'où un agent IA peut prendre des décisions de trading autonomes à partir d'un état de marché structuré, tout en restant encadré par un **Risk Engine déterministe** qui conserve l'autorité finale avant toute exécution.

> **Statut du projet :** phase de conception et de documentation. Les premières versions seront exclusivement en **PAPER trading**.

## Principes du projet

- Exchange initial : **Kraken**.
- Trading **SPOT uniquement**.
- Aucun short, levier, margin, future ou perpetual.
- Actions stratégiques de l'agent : `BUY`, `SELL`, `HOLD`.
- Impossible de vendre un actif non détenu.
- Un seul agent IA conserve la décision stratégique.
- Les indicateurs et calculs déterministes fournissent du contexte, sans devenir silencieusement une stratégie algorithmique parallèle.
- Le **Risk Engine** déterministe peut autoriser, modifier ou refuser une décision avant exécution.
- Aucune sortie LLM ne peut déclencher directement un ordre Kraken.
- Toutes les décisions, y compris `HOLD`, doivent être journalisées.
- Les frais, le spread et le slippage doivent être pris en compte dans les mesures de performance.
- Le passage au **LIVE** sera explicite, séparé du PAPER et traité dans une phase ultérieure.

## Agent IA

Les premiers tests utiliseront **GPT-5.6 Luna** afin de réduire les coûts d'expérimentation. L'architecture doit permettre de sélectionner **GPT-5.6 Sol** par configuration sans modifier le moteur de trading.

Le niveau d'agressivité de l'agent est prévu sur une échelle configurable de **1 à 10**. Sa traduction exacte en contraintes et comportement reste à définir et devra être mesurée expérimentalement.

## Objectif expérimental

Le projet utilise une cible expérimentale de **+4 % de rendement journalier** comme objectif de recherche et de mesure.

Cette cible n'est **ni une promesse, ni une garantie de rendement**. Les résultats devront être évalués sans look-ahead ni sélection rétrospective, en mesurant notamment le P&L brut et net, le drawdown, les frais, le slippage, l'exposition et le nombre de trades.

## Architecture cible

Le **backend constitue l'application de trading**. Il doit continuer à fonctionner indépendamment du frontend.

Le frontend est uniquement un cockpit de contrôle et de visualisation : le fermer ou le redémarrer ne doit jamais arrêter le moteur de trading.

Stack décidée :

- **Backend** : Python, `asyncio`, FastAPI, Pydantic.
- **Frontend** : Next.js, TypeScript, shadcn/ui, Tailwind CSS.
- **Communication** : REST et WebSocket selon le besoin.
- **Base cible** : PostgreSQL.
- **Intégrations externes** : Kraken et le fournisseur LLM derrière des interfaces dédiées.

Rust ne sera introduit que si un besoin mesuré ou une décision architecturale explicite le justifie.

## Flux de décision simplifié

```text
Kraken / Market Data
        │
        ▼
   Market State
        │
        ├──────────────┐
        ▼              │
 Portfolio State       │
        │              │
        └──────┬───────┘
               ▼
          Agent IA
      BUY / SELL / HOLD
               │
               ▼
         Risk Engine
      autorise / modifie
            / refuse
               │
               ▼
         Paper Broker
               │
               ▼
      Journal / Analytics
```

Aucun chemin direct entre l'agent IA et Kraken ne doit exister.

## Documentation

La documentation versionnée constitue la référence détaillée du projet :

- [`docs/00_ETAT_ACTUEL.md`](docs/00_ETAT_ACTUEL.md) — mémoire courte pour reprendre le projet rapidement.
- [`docs/01_PROJECT_MASTER.md`](docs/01_PROJECT_MASTER.md) — spécification fonctionnelle et principes généraux.
- [`docs/02_ARCHITECTURE_TECHNIQUE.md`](docs/02_ARCHITECTURE_TECHNIQUE.md) — architecture et frontières techniques.
- [`docs/03_AGENT_TRADING_RISK.md`](docs/03_AGENT_TRADING_RISK.md) — responsabilités de l'agent, du trading et du Risk Engine.
- [`docs/09_ROADMAP_DEVELOPPEMENT.md`](docs/09_ROADMAP_DEVELOPPEMENT.md) — roadmap par batches cohérents et testables.
- [`docs/10_DECISIONS_ET_CHANGELOG.md`](docs/10_DECISIONS_ET_CHANGELOG.md) — décisions architecturales et changelog.

## État de développement

La documentation initiale est en place. Le prochain chantier recommandé est le **bootstrap technique du projet** : structure backend/frontend, configuration, outillage qualité et tests minimaux, avant l'implémentation de Kraken ou de l'agent de trading.

Pour l'état exact du repository et les prochaines décisions ouvertes, consulter [`docs/00_ETAT_ACTUEL.md`](docs/00_ETAT_ACTUEL.md).

## Sécurité

- Aucun secret ou clé API ne doit être versionné, journalisé ou injecté dans les prompts.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- PAPER et LIVE doivent rester explicitement séparés.
- Toute exécution LIVE future devra passer par des garde-fous dédiés et une activation volontaire.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et de développement. Il ne constitue pas un conseil financier et ne garantit aucun résultat de trading.
