# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité, base du Batch 04 : `e7ac37955f08853024528fa9b9e10b5a75e05e3b`
- Commit : `feat: add Kraken public market data` — 20 septembre 2026
- Batch 03 intégré sur `main`.

## État courant intégré

- Projet expérimental de trading crypto SPOT piloté par un agent IA unique.
- Kraken comme exchange initial ; premières versions exclusivement en PAPER.
- Backend Python + `asyncio` + FastAPI + Pydantic ; frontend Next.js indépendant du moteur.
- Agent stratégique ; Risk Engine déterministe avec autorité finale.
- Contrats Pydantic stricts et ports externes intégrés.
- Adapter public Kraken Spot intégré : découverte `AssetPairs`, normalisation des symboles, ticker WebSocket v2, retry borné, fermeture propre et stale detection technique optionnelle.
- Aucun secret, aucune API Kraken privée, aucun ordre, aucun LIVE.

## Validation finale du Batch 03 avant intégration

Validation locale Windows confirmée :

- Python `3.13.14` ;
- `pytest` : **40 tests passés** ;
- Ruff : **OK** ;
- mypy : **OK sur 21 fichiers source** ;
- `git diff --check` : aucune erreur ;
- 2 warnings de dépréciation FastAPI/Starlette dans les dépendances de test, sans échec ;
- aucun test réseau Kraken requis par la suite principale.

## Patch Batch 04 préparé dans cette livraison

- Nouveau package fournisseur-agnostique `ai_spot_trader.market`.
- Nouvelle observation normalisée `MarketObservation` et port `MarketObservationSource` ; l'adapter Kraken expose cette observation sans fuite de structure fournisseur.
- `MarketState` reste le snapshot canonique unique et reçoit un `MarketContext` optionnel.
- Deux horizons descriptifs par défaut, 5 min et 30 min, surchargeables au constructeur ; ils ne définissent aucune cadence de trading.
- Statistiques déterministes : nombre d'observations, min/max, amplitude, return simple et volatilité réalisée simple.
- Fraîcheur explicite : timestamp de dernière observation, âge, seuil technique optionnel et résultat stale seulement lorsqu'un seuil est évalué.
- Historique en mémoire borné à 10 000 observations par builder ; insertion strictement temporelle ; doublons/hors ordre rejetés.
- No look-ahead : un snapshot à `T` ignore explicitement toute observation postérieure à `T`, y compris lors d'un replay.
- Aucune interpolation, aucun signal `BUY/SELL/HOLD`, aucune stratégie déterministe, aucun Risk Engine, aucune persistance.

## Validation du patch Batch 04 dans l'environnement ChatGPT

- Python `3.13.5`.
- `pytest` : **59 tests passés**.
- `compileall` : **OK**.
- Ruff et mypy ne sont pas installés dans l'environnement ChatGPT utilisé pour cette livraison ; validation locale Windows requise.
- Aucun test réseau Kraken n'a été exécuté ni ajouté à la suite par défaut.

## Dernier batch intégré

**Batch 03 — Kraken Market Data** : intégré sur `main` au HEAD `e7ac37955f08853024528fa9b9e10b5a75e05e3b`.

## Batch en cours

**Batch 04 — Market State** : patch préparé et testé offline ; intégration Git par l'utilisateur encore à effectuer.

## Prochain batch recommandé

**Batch 05 — Portfolio State + Paper Broker** après intégration et validation locale du Batch 04.

## Points encore à décider

- Capital PAPER initial et devise de référence.
- Univers d'actifs/paires Kraken initial.
- Cadence de la boucle de décision.
- Éventuelle évolution des horizons 5 min / 30 min selon les besoins mesurés.
- Seuil métier global de fraîcheur/stale du futur Risk Engine.
- Représentation du sizing stratégique dans `DecisionCandidate`.
- Limites chiffrées du Risk Engine et traduction exacte de l’agressivité 1–10.
- Modèle précis de spread/slippage/fill en PAPER.
- Frontière journalière des statistiques et politique de rétention/persistance.
