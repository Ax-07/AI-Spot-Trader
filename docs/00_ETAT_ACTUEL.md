# 00 — État actuel

## Référence GitHub vérifiée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD GitHub vérifié : d011faa98e7e347875186f12cb24b5e7041aa25c
HEAD                : feat: add trading reasoning doctrine
Vérifié              : 2026-09-28
```

Le HEAD `d011faa` intègre désormais la **Trading Reasoning Doctrine v1** qui était encore décrite comme patch local dans la version précédente de ce document. Son parent direct est `b46f463c474e25a38da7ddcaebf588753922031b`, qui intégrait le Batch 25 d'historique économique Session/run. Le recalibrage stratégique net/cost-aware reste issu de `463850d8281faebe86a6ee733d58781c349015d0`.

## État fonctionnel intégré à préserver

- un seul Agent IA stratégique ;
- PAPER uniquement ;
- SPOT + PERPETUAL linéaire ; FUTURE daté interdit ;
- BUY / SELL / HOLD ; SPOT sans short ; PERPETUAL LONG/SHORT ;
- plan multi-marchés / multi-décisions ordonné ;
- Risk Engine déterministe = autorité finale ;
- aucune sortie LLM -> ordre direct ;
- décisions séquentielles et causales ;
- `HOLD` journalisé ; `management_mode` conservé ;
- historique expérimental et replays préservés ;
- `AGENT_SYSTEM_PROMPT` historique `agent-strategy-v4` et `aggressiveness-map-v1` inchangés ;
- mapping LLM courant `aggressiveness-map-v3` ;
- objectif stratégique courant = progression de l'equity nette après coûts, sans obligation de turnover ;
- `trading-reasoning-doctrine-v1` intégrée aux prompts stratégiques courants, pas à Market Discovery.

## Patch proposé — Market Attention Radar v1

Le présent batch ajoute un **Market Attention Radar v1** strictement observationnel.

Architecture :

```text
candles Kraken canoniques 5m
        ↓
calcul déterministe multi-horizon 5m / 15m / 1h / 4h
        ↓
activité inhabituelle / présélection bornée
        +
OpenAI Responses API + hosted web_search
        ↓
facts publics structurés + sources
        ↓
Market Attention shortlist
        ↓
API read-only + cockpit
```

Garanties de v1 :

- aucune donnée du radar n'est fournie à l'Agent stratégique ;
- aucune influence sur `CycleDecisionPlan`, Market Discovery, Risk, Broker, sizing, BUY/SELL/HOLD ou LONG/SHORT ;
- aucun second pipeline OHLCV : le calcul réutilise `CandleStreamService` et les volumes des candles Kraken canoniques ;
- aucune API dédiée X/Reddit/LunarCrush ; la recherche publique utilise le hosted `web_search` OpenAI ;
- cache/TTL, nombre de candidats et nombre de recherches web bornés ;
- une erreur OpenAI/web ne bloque jamais le trading ;
- sources conservées sous forme de métadonnées/citations, sans copie de pages ni posts complets ;
- historique radar v1 agrégé et borné **en mémoire** uniquement ; aucune migration DB ; cet historique ne survit donc pas à un redémarrage ;
- cockpit : panneau global `Market Attention`, avec badge explicite `INFORMATIF — N’INFLUENCE PAS LE TRADING` et liens de sources cliquables.

Voir `docs/28_BATCH_MARKET_ATTENTION_RADAR_V1.md`.

## Trading Reasoning Doctrine v1 — intégré

La doctrine qualitative versionnée `trading-reasoning-doctrine-v1` est intégrée au HEAD GitHub `d011faa`.

Elle demande au LLM de construire une thèse à partir des faits fournis, d'interpréter régime/structure/cohérence multi-timeframe, d'examiner direction, momentum et volatilité lorsque les données le permettent, de comparer cash/positions/opportunités et coûts, puis d'identifier ce qui soutient ou invaliderait la thèse.

La doctrine n'est pas un moteur de signaux : aucun seuil RSI/MACD, score technique, règle profit/stop/timer, quota de trades ou logique BUY/SELL déterministe n'est ajouté. `HOLD` et conserver le cash restent valides lorsqu'aucune thèse suffisamment convaincante après coûts n'est disponible.

Composition auditée :

- singleton Campaign courant : doctrine injectée une fois ;
- plan multi-marchés courant : doctrine injectée une fois ;
- market discovery : doctrine non injectée, car cette phase construit seulement une watchlist ;
- `AGENT_SYSTEM_PROMPT` historique : inchangé ;
- Risk Engine, Broker, planner, mappings d'agressivité et contrats action/quantité : inchangés.

Voir `docs/03_AGENT_TRADING_RISK.md` et `docs/27_BATCH_TRADING_REASONING_DOCTRINE.md`.

## Batch 25 — historique économique Session/run

Le Batch 25 est intégré depuis `b46f463c`. Il fournit une projection de lecture seule des opérations économiques, coûts, turnover et effets SPOT/PERPETUAL à partir des analytics et faits persistés existants, sans second ledger ni modification Agent/Risk/Broker.

## Validation du patch proposé Market Attention

Exécuté dans l'environnement ChatGPT avant livraison initiale :

- `py_compile` sur les sept fichiers Python backend runtime/tests du batch : succès ;
- harness backend isolé : succès ;
- test frontend isolé `market-attention.test.mjs` : `3/3` passés.

Validation locale utilisateur du premier ZIP :

- `pytest -q` : un seul échec, limité au statut `PARTIAL`/`STALE` du scénario de données insuffisantes ;
- `pnpm test` : `42/42` passés ;
- `pnpm lint` : un seul échec `react-hooks/set-state-in-effect` dans le dock Radar ;
- `pnpm typecheck` : succès ;
- `pnpm build` : succès ;
- `git diff --check` : aucune erreur de whitespace, avertissements LF -> CRLF uniquement.

Correctif préparé :

- `AVAILABLE` requiert désormais tous les horizons v1 complets ; couverture incomplète -> `PARTIAL` ; snapshot complet trop ancien -> `STALE` ;
- le test d'insuffisance utilise les candles les plus récentes ;
- le refresh initial du dock quitte l'`useEffect` et est déclenché par l'ouverture utilisateur.

Revalidation ChatGPT du correctif : compilation Python succès, harness Radar PASS incluant `PARTIAL` frais / `STALE` complet, test frontend isolé `3/3` passé.

Le rerun de `pytest -q`, `pnpm lint`, puis des validations frontend complètes reste à effectuer localement après extraction du ZIP correctif.
