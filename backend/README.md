# AI Spot Trader — Backend

Backend Python/FastAPI autonome d'AI Spot Trader. Le frontend Next.js est uniquement un cockpit : fermer ou recharger le frontend ne stoppe jamais le moteur backend.

Le runtime exécutable est **PAPER** et supporte un univers typé composé de marchés **SPOT** et de
**PERPETUAL linéaires** autorisés. Kraken public fournit les données de marché ; le même Agent
Luna/Sol sélectionne le marché puis propose BUY/SELL/HOLD ; le Risk Engine déterministe
autorise/modifie/refuse ; le Paper Broker exécute seulement un `ExecutionIntent` créé par Risk ;
et chaque résultat de cycle est persisté dans PostgreSQL. Aucun endpoint Kraken privé d'ordre
n'est utilisé.

## Développement

Toutes les commandes ci-dessous sont à exécuter depuis la **racine du repository** sous PowerShell :

```powershell
uv venv --python 3.13.14 --seed backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
backend\.venv\Scripts\python.exe -m pytest backend
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m mypy backend\src backend\tests
backend\.venv\Scripts\python.exe -m uvicorn ai_spot_trader.main:app --app-dir backend\src
```

Le package demande Python `>=3.12`.

L'API est disponible par défaut sur `http://127.0.0.1:8000` et le healthcheck sur `GET /health`.

## Configuration du premier run PAPER

Copier `backend/.env.example` vers `backend/.env`, puis renseigner localement les valeurs explicitement requises :

- marché bootstrap PAPER, univers exécutable typé et devise de règlement ;
- capital initial ;
- cadence et agressivité ;
- timeouts Market/Agent/Broker ;
- max order notional, whitelist Risk et politique de réduction ;
- fee rate, spread et slippage ;
- paramètres Derivatives/Risk requis si un `PERPETUAL` appartient à l'univers ;
- `AI_SPOT_TRADER_DATABASE_URL` PostgreSQL/asyncpg ;
- `AI_SPOT_TRADER_OPENAI_API_KEY` ;
- modèle Luna/Sol selon le run.

Aucun de ces paramètres produit n'est inventé par la composition. Le démarrage de `ai_spot_trader.main:app` échoue de façon fermée si un paramètre indispensable manque. `ExecutionMode` reste PAPER uniquement.

Les secrets restent exclusivement dans l'environnement local. Ne jamais versionner `backend/.env`.

## Contrôle du moteur

Le backend ne démarre pas le moteur automatiquement au lancement.

```text
GET  /api/v1/engine
POST /api/v1/engine/run-cycle
POST /api/v1/engine/start
POST /api/v1/engine/stop
```

`POST /api/v1/engine/run-cycle` n'accepte aucune décision de trading : il demande uniquement au `TradingEngine` canonique d'exécuter exactement un cycle. La commande est refusée si la boucle autonome est déjà active.

Avant chaque cycle, le writer d’audit exécute un préflight PostgreSQL minimal. Si la DB est déjà indisponible, le cycle est refusé avant Market/Agent/Risk/Broker. Après toute erreur de préflight ou d’écriture, le runner audité se verrouille fail-closed jusqu’au redémarrage. Cette protection ne prétend pas fournir d’exactly-once global entre ledger mémoire et PostgreSQL si la DB tombe entre le préflight et le commit.
