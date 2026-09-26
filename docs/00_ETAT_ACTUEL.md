# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` vérifié avant préparation du Batch 19.9C :
  `792711217513db6e9825a96e15ec59c74d33b192`
  (`docs: sync post-19.9B state`).
- Parent fonctionnel 19.9B :
  `88be7d50111c2e6210225071d3f1af3f7f07b4f0`
  (`feat: add strategic multi-timeframe context`).
- Référence fonctionnelle 19.9A :
  `4b6a851addea74d72af2c433827c935a87d4bc04`
  (`feat: add canonical scalp swing trading style`).

## État fonctionnel intégré + Batch 19.9C préparé

- un seul Agent IA stratégique ; pipeline Risk déterministe inchangé ;
- Session = concept principal du parcours utilisateur ;
- Discovery dynamique, Market Selection puis BUY/SELL/HOLD par le même Agent ;
- Trading Style canonique `SCALP` / `SWING` avec `trading-style-map-v1` ;
- `SCALP` : `1m/5m/15m/30m` ; `SWING` : `1h/4h/1d` ;
- contexte stratégique multi-timeframes `strategic-mtf-v1` opérationnel côté données ;
- `CandleStreamService` backend partagé entre cockpit et Campaign runtimes, sans second pipeline/cache OHLC ;
- lecture causale `history_as_of(...)`, sans interpolation des gaps ni donnée candle indisponible à `as_of` ;
- disponibilité explicite `AVAILABLE` / `PARTIAL` / `MISSING`, stale et profondeur bornée ;
- snapshot construit pour Market Selection puis réutilisé inchangé pour la décision finale ;
- Batch 19.9C : le configurateur Session expose le style dans la configuration simple et avancée ;
- les quatre dimensions restent indépendantes : style de trading, agressivité, sélection des marchés et Risk ;
- nouvelles Sessions : `SCALP` est le choix UX initial avec cadence recommandée `60 s` et refresh watchlist `300 s` ;
- recommandations `SWING` : cadence `900 s` et refresh watchlist `1800 s` ;
- changer de style ne modifie aucune valeur avancée ; une action explicite permet de réappliquer les recommandations ;
- les Sessions legacy sans style restent affichées `Hérité / non défini` et aucun style n'est inféré ;
- l'édition reconstruit cadence, Discovery, coûts, Risk, timeouts, marché et agressivité depuis les valeurs persistées ;
- les timeframes sont affichées en lecture seule comme dérivées du mapping versionné, sans sélecteur indépendant ;
- `agent-contract-v1` et Campaigns historiques sans `trading_style` restent compatibles ;
- aucune règle technique déterministe `indicateur -> BUY/SELL/HOLD` et aucun timer de fermeture lié au style.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Détails 19.9B : `docs/19_BATCH_19_9B_MULTI_TIMEFRAMES.md`.
Détails 19.9C : `docs/20_BATCH_19_9C_SESSION_TRADING_STYLE_UX.md`.

## Validation du patch 19.9C

Exécuté par ChatGPT sur le patch isolé :

- tests unitaires `session-config` via Node 22 type stripping : **12/12 passés** ;
- vérification syntaxique TypeScript/TSX du patch : **passée** ;
- `tsc --strict --noEmit` ciblé sur `api/types.ts` + `session-config.ts` : **passé** ;
- la suite frontend complète (`pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm build`) reste à exécuter dans le repository local opérateur avec ses dépendances.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer clairement état intégré GitHub, modifications locales fournies par l'opérateur et éventuel patch proposé.
