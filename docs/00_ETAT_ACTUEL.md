# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité : `bd58ec3502fecca6c8c693af6fe71daea22b9167`
- Commit : `docs: initialize project documentation` — 20 septembre 2026
- État intégré : documentation initiale présente sous `docs/` ; aucune implémentation fonctionnelle du moteur de trading.

## État courant

**Confirmé**
- Projet expérimental de trading crypto SPOT piloté par un agent IA unique.
- Kraken comme exchange initial ; premières versions exclusivement en PAPER.
- Backend Python + `asyncio` + FastAPI + Pydantic.
- Frontend Next.js + TypeScript + shadcn/ui + Tailwind CSS, indépendant du moteur de trading.
- Agent stratégique ; Risk Engine déterministe avec autorité finale.
- GPT-5.6 Luna pour les premiers tests ; Sol sélectionnable ultérieurement par configuration.
- PostgreSQL comme base cible.

**Patch local proposé, non intégré**
- Refonte de `README.md` en véritable page de présentation du projet.
- Mise à jour de ce fichier pour refléter le HEAD désormais intégré.

## Dernier batch intégré

**Batch 00 — Documentation initiale** : documentation canonique créée et intégrée sur `main`.

## Prochain batch recommandé

**Batch 01 — Bootstrap du projet** : arborescence backend/frontend, configuration, qualité et tests minimaux, sans implémenter encore Kraken ni l'agent IA.

## Points encore à décider

- Capital PAPER initial et devise de référence.
- Univers d'actifs/paires Kraken initial.
- Cadence de la boucle de décision et horizon(s) de marché.
- Limites chiffrées du Risk Engine et traduction exacte de l'agressivité 1–10.
- Modèle précis de spread/slippage/fill en PAPER.
- Frontière journalière utilisée pour les statistiques (`UTC` ou autre).
- Politique de rétention des logs et des données de marché.
