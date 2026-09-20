# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité, base du Batch 03 : `bff0f8b03740da4a01072af90111a2e5d9f208ef`
- Commit : `feat: add domain contracts and configuration` — 20 septembre 2026
- Batch 02 intégré sur `main` et validé localement sous Windows.

## État courant

**Confirmé sur `main` avant Batch 03**
- Projet expérimental de trading crypto SPOT piloté par un agent IA unique.
- Kraken comme exchange initial ; premières versions exclusivement en PAPER.
- Backend Python + `asyncio` + FastAPI + Pydantic ; frontend Next.js indépendant du moteur.
- Agent stratégique ; Risk Engine déterministe avec autorité finale.
- Contrats Pydantic stricts et ports `MarketDataSource`, `LLMProvider`, `Broker` intégrés.
- `MarketState` reste minimal : UUID, timestamp UTC aware, symbole canonique et dernier prix positif.
- Luna par défaut, Sol sélectionnable ; agressivité optionnelle validée de 1 à 10.

**Patch Batch 03 préparé, non intégré au moment de sa génération**
- Adapter public Kraken sous `ai_spot_trader.integrations.kraken`.
- Découverte des paires Spot via REST `AssetPairs` avec `assetVersion=1`, sans authentification.
- Normalisation explicite des alias Kraken vers un symbole canonique slash-separated, sans table `XBT/BTC` codée en dur.
- WebSocket Spot v2 `ticker` pour `last`, `symbol` et `timestamp` ; heartbeat et messages système non pertinents ignorés.
- Reconnexion bornée/configurable et fermeture propre ; aucune tâche de fond ni boucle de trading lancée.
- Stale detection testable via l'horloge injectable ; seuil technique optionnel et non défini par défaut.
- Dépendances runtime explicites : `httpx` et `websockets`.
- Aucun secret, aucune clé Kraken, aucune API privée, aucun ordre, aucun LIVE.

**Validation du patch Batch 03 dans l'environnement ChatGPT**
- `pytest` : 40/40 tests passés.
- `compileall` : OK.
- Ruff et mypy ne sont pas installés dans l'environnement d'exécution ChatGPT utilisé pour cette livraison ; validation locale Windows requise.
- Aucun test réseau Kraken n'est inclus dans la suite par défaut.

## Dernier batch intégré

**Batch 02 — Contrats de domaine et configuration** : intégré sur `main` au HEAD `bff0f8b03740da4a01072af90111a2e5d9f208ef`.

## Batch en cours

**Batch 03 — Kraken Market Data** : patch préparé et testé offline ; intégration Git par l'utilisateur encore à effectuer.

## Prochain batch recommandé

**Batch 04 — Market State** : enrichissement déterministe du contexte marché, horizons/statistiques/indicateurs, sans logique stratégique autonome.

## Points encore à décider

- Capital PAPER initial et devise de référence.
- Univers d'actifs/paires Kraken initial.
- Cadence de la boucle de décision et horizon(s) de marché.
- Contenu détaillé du `MarketState` au-delà du snapshot minimal.
- Seuil métier global de fraîcheur/stale à appliquer aux futurs composants Risk/Market State.
- Représentation du sizing stratégique dans `DecisionCandidate`.
- Limites chiffrées du Risk Engine et traduction exacte de l’agressivité 1–10.
- Modèle précis de spread/slippage/fill en PAPER.
- Frontière journalière utilisée pour les statistiques (`UTC` ou autre).
- Politique de rétention des logs et des données de marché.
