# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` audité au démarrage du Batch 19.9B :
  `a4f841c7c23e3af1b44a9cbb104ccc44d5cad2d9`
  (`docs: sync post-19.9A state`).
- Référence fonctionnelle Batch 19.9A :
  `4b6a851addea74d72af2c433827c935a87d4bc04`
  (`feat: add canonical scalp swing trading style`).
- Batch 19.9A et son sync documentaire post-intégration sont donc présents sur `main`.

## État fonctionnel intégré au départ

- un seul Agent IA stratégique ; Kraken ; PAPER ; pipeline Risk déterministe inchangé ;
- Session = concept principal du parcours utilisateur ;
- Discovery dynamique, Market Selection puis BUY/SELL/HOLD par le même Agent ;
- candles backend canoniques : `Candle`, `CandleKey`, `CandleCache`, backfill, streaming, recovery, stale et API cockpit ;
- Trading Style canonique `SCALP` / `SWING` avec `trading-style-map-v1` ;
- `SCALP` : `1m/5m/15m/30m` ; `SWING` : `1h/4h/1d` ;
- `TradingStyleContext` et `ExecutionCostContext` déjà propagés vers Discovery, Market Selection et décision finale ;
- `agent-contract-v1` préservé et campagnes historiques sans `trading_style` supportées.

## Batch 19.9B — patch local proposé

Le patch 19.9B rend le style opérationnel côté données stratégiques multi-timeframes :

- réutilisation du `CandleStreamService` backend-owned par le cockpit **et** les Campaign runtimes ; aucun second pipeline/cache OHLC ;
- lecture candles causale `history_as_of(...)` : aucune révision `updated_at > as_of`, aucune candle finale `close_time > as_of` ;
- une candle active non finalisée n'est utilisable que si sa révision exacte était déjà connue à `as_of` ;
- contexte versionné `strategic-mtf-v1`, compact et borné, avec disponibilité, couverture, profondeur, gaps, stale, dernière candle/finalité et statistiques descriptives de fenêtre ;
- profondeur bornée par timeframe et taille sérialisée bornée à 128 KiB ; univers borné à 32 marchés ;
- snapshot construit une seule fois au `MarketSelectionInput.created_at`, puis réutilisé inchangé par l'`AgentInput` final ;
- Discovery conserve son contexte candidat léger ; l'enrichissement multi-timeframes intervient après Discovery sur l'univers réellement sélectionnable ;
- `ExecutionCostContext` reste distinct ; Risk Engine, règles de trading et contrat de sortie LLM inchangés ;
- compatibilité legacy : sans `trading_style`, aucun chargement multi-timeframes et sérialisation historique inchangée.

Détails : `docs/19_BATCH_19_9B_MULTI_TIMEFRAMES.md`.

## Validation exécutée par ChatGPT sur le patch local

Dans l'environnement disponible, sans checkout Git complet :

- compilation Python (`py_compile`) des fichiers Python modifiés/créés : passée ;
- tests ciblés `backend/tests/test_strategic_multi_timeframe.py` : **7/7 passés** ;
- contrôle manuel d'un contexte SCALP complet sérialisé : passé.

Le `pytest` complet du repository reste à exécuter localement après extraction du ZIP, car l'environnement ChatGPT ne disposait pas du checkout complet et l'accès Git réseau direct était indisponible.

## Règle de reprise

Avant intégration : extraire le ZIP à la racine, exécuter les validations locales, inspecter `git status --short` / `git diff --check`, puis seulement committer/pousser si les résultats sont conformes.
