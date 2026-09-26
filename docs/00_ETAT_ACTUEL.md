# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` vérifié après intégration du Batch 19.9B :
  `88be7d50111c2e6210225071d3f1af3f7f07b4f0`
  (`feat: add strategic multi-timeframe context`).
- Parent documentaire post-19.9A :
  `a4f841c7c23e3af1b44a9cbb104ccc44d5cad2d9`
  (`docs: sync post-19.9A state`).

## État fonctionnel intégré

- un seul Agent IA stratégique ; pipeline Risk déterministe inchangé ;
- Session = concept principal du parcours utilisateur ;
- Discovery dynamique, Market Selection puis BUY/SELL/HOLD par le même Agent ;
- Trading Style canonique `SCALP` / `SWING` avec `trading-style-map-v1` ;
- `SCALP` : `1m/5m/15m/30m` ; `SWING` : `1h/4h/1d` ;
- contexte stratégique multi-timeframes `strategic-mtf-v1` opérationnel côté données ;
- `CandleStreamService` backend partagé entre cockpit et Campaign runtimes, sans second pipeline/cache OHLC ;
- lecture causale `history_as_of(...)`, sans interpolation des gaps ni donnée candle indisponible à `as_of` ;
- disponibilité explicite `AVAILABLE` / `PARTIAL` / `MISSING`, stale et profondeur bornée ;
- contexte borné à 32 marchés, 128 KiB JSON et concurrence de lecture bornée ;
- snapshot construit pour Market Selection puis réutilisé inchangé pour la décision finale ;
- Discovery reste légère avant l'enrichissement multi-timeframes ;
- `ExecutionCostContext` reste séparé ;
- `agent-contract-v1` et Campaigns historiques sans `trading_style` restent compatibles ;
- aucune règle technique déterministe `indicateur -> BUY/SELL/HOLD` et aucun timer de fermeture lié au style.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Détails : `docs/19_BATCH_19_9B_MULTI_TIMEFRAMES.md`.

## Validation locale post-intégration

Validation fournie par l'opérateur après intégration de 19.9B :

- tests ciblés : **57 passed, 2 warnings** ;
- suite backend complète : **629 passed, 2 warnings** ;
- `git diff --check` : aucune erreur de whitespace ;
- warnings limités aux dépendances Starlette/FastAPI déjà connues et aux notifications Git LF -> CRLF ;
- aucun fichier frontend fonctionnel modifié par 19.9B.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer clairement état intégré GitHub, modifications locales fournies par l'opérateur et éventuel patch proposé.
