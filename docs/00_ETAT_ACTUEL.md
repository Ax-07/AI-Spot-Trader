# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité : `f5b967d8736075781d8142c8cc80a99cbd96fae3`
- Commit : `first commit` — 20 septembre 2026
- Contenu intégré observé : `README.md` uniquement ; aucun dossier `docs/` avant ce batch.

## État courant

**Confirmé**
- Projet expérimental de trading crypto SPOT piloté par un agent IA unique.
- Exchange initial : Kraken.
- Backend : Python + `asyncio` + FastAPI + Pydantic.
- Frontend : Next.js + TypeScript + shadcn/ui + Tailwind CSS.
- PAPER obligatoire pour les premières versions ; LIVE séparé et ultérieur.
- Agent stratégique, Risk Engine déterministe avec autorité finale.
- Modèle initial : GPT-5.6 Luna ; Sol doit rester sélectionnable par configuration.
- PostgreSQL est la base cible.

**Patch préparé, non intégré tant qu'il n'est pas commité**
- Batch 00 : documentation initiale du projet.
- Création de la documentation canonique sous `docs/`.
- Correction dans `README.md` du placeholder du repository.

## Dernier batch intégré

Aucun batch applicatif. Le repository est au commit initial.

## Prochain batch recommandé

**Batch 01 — Bootstrap du projet** : arborescence backend/frontend, configuration, qualité, tests minimaux et contrats de démarrage, sans implémenter encore une stratégie de trading.

## Points encore à décider

- Capital PAPER initial et devise de référence.
- Univers d'actifs/paires Kraken initial.
- Cadence de la boucle de décision et horizon(s) de marché.
- Limites chiffrées du Risk Engine et traduction exacte de l'agressivité 1–10.
- Modèle précis de spread/slippage/fill en PAPER.
- Frontière journalière utilisée pour les statistiques (`UTC` ou autre).
- Politique de rétention des logs et des données de marché.
