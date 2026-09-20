# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité, base du Batch 02 : `d9af0ca293dd9f2712969b246e394c4a8c188b5e`
- Commit : `feat: bootstrap backend and frontend` — 20 septembre 2026
- Batch 01 intégré sur `main` et validé localement sous Windows.

## État courant

**Confirmé sur `main` avant Batch 02**
- Projet expérimental de trading crypto SPOT piloté par un agent IA unique.
- Kraken comme exchange initial ; premières versions exclusivement en PAPER.
- Backend Python + `asyncio` + FastAPI + Pydantic.
- Frontend Next.js + TypeScript + shadcn/ui + Tailwind CSS, indépendant du moteur de trading.
- Agent stratégique ; Risk Engine déterministe avec autorité finale.
- GPT-5.6 Luna pour les premiers tests ; Sol sélectionnable par configuration.
- PostgreSQL comme base cible.
- Bootstrap backend/frontend du Batch 01 intégré au HEAD `d9af0ca`.

**Patch Batch 02 préparé, non intégré au moment de sa génération**
- Contrats Pydantic stricts initiaux dans `backend/src/ai_spot_trader/domain/`.
- Enums canoniques `BUY` / `SELL` / `HOLD`, `PAPER`, `ALLOW` / `MODIFY` / `REJECT`.
- Identifiants UUID explicites pour snapshots, cycles, décisions, évaluations de risque, exécutions et fills.
- Timestamps techniques timezone-aware normalisés en UTC ; frontière statistique journalière toujours ouverte.
- Configuration enrichie : mode PAPER uniquement, Luna par défaut, Sol sélectionnable, agressivité optionnelle validée de 1 à 10, sans valeur par défaut décidée.
- Horloge injectable minimale via `Clock` + `SystemClock`.
- Ports `MarketDataSource`, `LLMProvider` et `Broker` sans provider réel.
- Aucun Kraken réel, appel LLM, Risk Engine fonctionnel, Paper Broker fonctionnel ou LIVE.

**Validation du Batch 02**
- Environnement ChatGPT : `pytest` 20/20 et `compileall` OK.
- Validation locale Windows : `pytest` 20/20, Ruff OK, mypy OK.
- Deux warnings de dépréciation Starlette/FastAPI persistent dans les dépendances de test, sans échec.

## Dernier batch intégré

**Batch 01 — Bootstrap du projet** : intégré sur `main` au HEAD `d9af0ca293dd9f2712969b246e394c4a8c188b5e`.

## Batch en cours

**Batch 02 — Contrats de domaine et configuration** : patch préparé et validé localement sous Windows ; intégration Git par l'utilisateur encore à effectuer.

## Prochain batch recommandé

**Batch 03 — Kraken Market Data** : données publiques Kraken et normalisation vers les contrats de domaine, sans trading privé.

## Points encore à décider

- Capital PAPER initial et devise de référence.
- Univers d'actifs/paires Kraken initial.
- Cadence de la boucle de décision et horizon(s) de marché.
- Contenu détaillé du `MarketState` au-delà du snapshot minimal.
- Représentation du sizing stratégique dans `DecisionCandidate`.
- Limites chiffrées du Risk Engine et traduction exacte de l’agressivité 1–10.
- Modèle précis de spread/slippage/fill en PAPER.
- Frontière journalière utilisée pour les statistiques (`UTC` ou autre).
- Politique de rétention des logs et des données de marché.
