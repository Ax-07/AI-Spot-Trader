# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité, base du patch : `c4d6aa6da9dde19a52b12dc54535af3b98aa1523`
- Commit : `docs: refresh project readme and current state` — 20 septembre 2026
- État intégré avant Batch 01 : documentation canonique présente ; aucune implémentation applicative.

## État courant

**Confirmé**
- Projet expérimental de trading crypto SPOT piloté par un agent IA unique.
- Kraken comme exchange initial ; premières versions exclusivement en PAPER.
- Backend Python + `asyncio` + FastAPI + Pydantic.
- Frontend Next.js + TypeScript + shadcn/ui + Tailwind CSS, indépendant du moteur de trading.
- Agent stratégique ; Risk Engine déterministe avec autorité finale.
- GPT-5.6 Luna pour les premiers tests ; Sol sélectionnable ultérieurement par configuration.
- PostgreSQL comme base cible.

**Patch Batch 01 préparé, non intégré**
- Backend installable sous `backend/` avec package `src/ai_spot_trader`.
- FastAPI minimal avec cycle de vie asynchrone et endpoint `GET /health`.
- Configuration typée via `pydantic-settings` et `.env.example` sans secret.
- Tests de bootstrap avec `pytest` ; Ruff et mypy configurés comme checks backend.
- Frontend Next.js 16.3.3 + TypeScript + Tailwind CSS v4 + socle shadcn/ui sous `frontend/`, géré avec `pnpm`.
- Page cockpit initiale sans logique de trading ni dépendance au backend.
- `.gitignore` commun Python/Next.js/secrets, couvrant aussi les venv/caches à la racine.
- Aucun SHA de commit du patch n'existe avant son intégration par l'utilisateur.

**Validation locale Windows confirmée**
- Backend : Python `3.13.14`, installation editable réussie, `pytest` 4/4, Ruff OK, mypy OK.
- Frontend : `pnpm 10.15.1`, installation réussie, ESLint OK, type-check TypeScript OK, build Next.js production OK.
- Deux warnings de dépréciation proviennent actuellement de dépendances Starlette/FastAPI de test ; aucun échec de test.

## Dernier batch intégré

**Batch 00 — Documentation initiale** : documentation canonique intégrée puis README rafraîchi sur `main` jusqu'au HEAD `c4d6aa6`.

## Batch en cours

**Batch 01 — Bootstrap du projet** : patch préparé et validé localement sous Windows ; l'intégration Git reste à effectuer.

## Prochain batch recommandé

**Batch 02 — Contrats de domaine et configuration** : contrats Pydantic initiaux, mode PAPER, configuration du modèle/agressivité et interfaces Kraken/LLM/Broker, sans implémenter encore la logique métier complète.

## Points encore à décider

- Capital PAPER initial et devise de référence.
- Univers d'actifs/paires Kraken initial.
- Cadence de la boucle de décision et horizon(s) de marché.
- Limites chiffrées du Risk Engine et traduction exacte de l'agressivité 1–10.
- Modèle précis de spread/slippage/fill en PAPER.
- Frontière journalière utilisée pour les statistiques (`UTC` ou autre).
- Politique de rétention des logs et des données de marché.
