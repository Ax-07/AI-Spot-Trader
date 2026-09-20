# AI Spot Trader — Backend

Bootstrap FastAPI du moteur AI Spot Trader. Ce package ne contient encore aucune logique de trading.

## Développement

Toutes les commandes ci-dessous sont à exécuter depuis la **racine du repository** sous PowerShell :

```powershell
uv venv --python 3.13.14 --seed backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
backend\.venv\Scripts\python.exe -m pytest backend
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m mypy backend\src
backend\.venv\Scripts\python.exe -m uvicorn ai_spot_trader.main:app --reload --app-dir backend\src
```

Le package demande Python `>=3.12`. Le Batch 01 a été validé sous Windows avec Python `3.13.14`.

L'API est alors disponible sur `http://127.0.0.1:8000` et le healthcheck sur `GET /health`.

La configuration locale peut être placée dans `backend/.env` à partir de `backend/.env.example`. Le fichier `.env` ne doit jamais être versionné.
