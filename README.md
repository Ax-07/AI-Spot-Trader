# AI Spot Trader

AI Spot Trader est une application expérimentale de **trading crypto SPOT pilotée par un agent IA unique**.

Le projet vise à étudier jusqu'où un agent IA peut prendre des décisions de trading autonomes à partir d'un état de marché structuré, tout en restant encadré par un **Risk Engine déterministe** qui conserve l'autorité finale avant toute exécution.

> **Statut du projet :** Batch 01 — bootstrap technique préparé. Les premières versions restent exclusivement en **PAPER trading**.

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

Les premiers tests utiliseront **GPT-5.6 Luna** afin de réduire les coûts d’expérimentation. L’architecture doit permettre de sélectionner **GPT-5.6 Sol** par configuration sans modifier le moteur de trading.

Le niveau d’agressivité est prévu sur une échelle configurable de **1 à 10**. Son mapping exact reste à définir et sera traité dans un batch ultérieur.

## Objectif expérimental

Le projet conserve une cible expérimentale de **+4 % de rendement journalier** comme objectif de recherche et de mesure. Cette cible n’est ni une promesse ni une garantie ; les résultats doivent être mesurés sans look-ahead ni sélection rétrospective.

## Architecture

Le **backend constitue l'application de trading**. Il doit fonctionner indépendamment du frontend.

Le frontend est uniquement un cockpit de contrôle et de visualisation : le fermer ou le redémarrer ne doit jamais arrêter le moteur de trading.

Stack décidée :

- **Backend** : Python, `asyncio`, FastAPI, Pydantic.
- **Frontend** : Next.js, TypeScript, shadcn/ui, Tailwind CSS.
- **Communication** : REST et WebSocket selon le besoin.
- **Base cible** : PostgreSQL.
- **Intégrations externes** : Kraken et le fournisseur LLM derrière des interfaces dédiées.

Rust ne sera introduit que si un besoin mesuré ou une décision architecturale explicite le justifie.

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

## Bootstrap actuel

```text
backend/
  src/ai_spot_trader/
    api/
    core/
    main.py
  tests/
  pyproject.toml
frontend/
  src/app/
  src/components/ui/
  src/lib/
  package.json
```

Le backend expose actuellement uniquement un healthcheck `GET /health` et une configuration typée. Le frontend affiche une page d'accueil technique et ne communique pas encore avec le backend.

## Démarrage local

### Backend

Toutes les commandes de développement sont prévues pour être exécutées depuis la racine du repository sous PowerShell.

```powershell
uv venv --python 3.13.14 --seed backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
backend\.venv\Scripts\python.exe -m pytest backend
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m mypy backend\src
backend\.venv\Scripts\python.exe -m uvicorn ai_spot_trader.main:app --reload --app-dir backend\src
```

Le package backend accepte Python `>=3.12`. La validation Windows du Batch 01 a été réalisée avec Python `3.13.14`.

### Frontend

Dans un second terminal, toujours depuis la racine :

```powershell
pnpm --dir frontend install
pnpm --dir frontend dev
```

Checks frontend utiles :

```powershell
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

`pnpm` est le gestionnaire de paquets frontend canonique du projet. La validation du Batch 01 a été réalisée avec pnpm `10.15.1`.

## Documentation

- [`docs/00_ETAT_ACTUEL.md`](docs/00_ETAT_ACTUEL.md) — mémoire courte pour reprendre le projet rapidement.
- [`docs/01_PROJECT_MASTER.md`](docs/01_PROJECT_MASTER.md) — spécification fonctionnelle et principes généraux.
- [`docs/02_ARCHITECTURE_TECHNIQUE.md`](docs/02_ARCHITECTURE_TECHNIQUE.md) — architecture et frontières techniques.
- [`docs/03_AGENT_TRADING_RISK.md`](docs/03_AGENT_TRADING_RISK.md) — responsabilités de l'agent, du trading et du Risk Engine.
- [`docs/09_ROADMAP_DEVELOPPEMENT.md`](docs/09_ROADMAP_DEVELOPPEMENT.md) — roadmap par batches cohérents et testables.
- [`docs/10_DECISIONS_ET_CHANGELOG.md`](docs/10_DECISIONS_ET_CHANGELOG.md) — décisions architecturales et changelog.

## Sécurité

- Aucun secret ou clé API ne doit être versionné, journalisé ou injecté dans les prompts.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- PAPER et LIVE doivent rester explicitement séparés.
- Toute exécution LIVE future devra passer par des garde-fous dédiés et une activation volontaire.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et de développement. Il ne constitue pas un conseil financier et ne garantit aucun résultat de trading.
