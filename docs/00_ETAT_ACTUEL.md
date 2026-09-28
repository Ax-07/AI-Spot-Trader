# 00 — État actuel

## Référence GitHub vérifiée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD GitHub vérifié : 354e8cf083b2c45233c45e019bdaa7f4bf6b1d96
HEAD                : feat: improve market attention observability
Vérifié              : 2026-09-28
```

Le HEAD `354e8cf` intègre **Market Attention Radar v1** ainsi que le **Batch 29 — observabilité Market Attention**. La version précédente de ce document était en retard : elle mentionnait encore `3c609c7` et présentait l'observabilité comme un patch proposé.

## État fonctionnel intégré à préserver

- un seul Agent IA stratégique ;
- PAPER uniquement à ce stade ;
- Kraken ;
- SPOT + PERPETUAL linéaire ; FUTURE daté interdit ;
- BUY / SELL / HOLD ; SPOT sans short ; PERPETUAL LONG/SHORT selon l'état intégré ;
- plan multi-marchés / multi-décisions ordonné ;
- Risk Engine déterministe = autorité finale ;
- aucune sortie LLM -> ordre direct ;
- `HOLD` journalisé ; `management_mode` conservé ;
- objectif stratégique courant = progression de l'equity nette après coûts, sans obligation de turnover ;
- `trading-reasoning-doctrine-v1` intégrée aux prompts stratégiques courants, pas à Market Discovery ;
- frontend = cockpit uniquement ; fermer le frontend n'arrête pas le backend ;
- Market Attention Radar = observation uniquement ; aucune donnée Radar n'est fournie à l'Agent.

## Market Attention Radar — état intégré au HEAD

Architecture intégrée :

```text
catalogue Kraken public
        ↓
rotation / scan borné
        ↓
CandleStreamService canonique 5m
        ↓
activité relative 5m / 15m / 1h / 4h
        ↓
candidats inhabituels bornés
        ↓
OpenAI Responses API + hosted web_search
        ↓
attention publique structurée + sources
        ↓
shortlist informative + API read-only + cockpit
```

Le Batch 29 intégré ajoute déjà :

- compteurs `AVAILABLE / PARTIAL / STALE / ERROR` ;
- compteurs `UNKNOWN / NORMAL / ELEVATED / ACCELERATING / VERY_HIGH` ;
- diagnostic borné des marchés `AVAILABLE + NORMAL` sous seuil ;
- message cockpit cohérent lorsqu'aucun candidat n'est détecté ;
- aucun déclenchement web par les diagnostics.

Garanties :

- aucun second pipeline OHLCV ;
- aucun seuil Radar fourni à l'Agent ;
- aucune influence sur Market Discovery, Risk, Broker, sizing ou ordres ;
- aucune API dédiée X/Reddit/LunarCrush ;
- recherche publique uniquement pour les candidats d'activité inhabituelle ;
- erreurs Radar fail-soft ;
- historique Radar borné en mémoire, sans migration SQL ;
- badge cockpit `INFORMATIF — N’INFLUENCE PAS LE TRADING`.

Voir `docs/28_BATCH_MARKET_ATTENTION_RADAR_V1.md` et `docs/29_BATCH_MARKET_ATTENTION_OBSERVABILITY.md`.

## Batch 30 — patch livré, non intégré

Le patch courant **Market Attention Activity Robustness** part du HEAD intégré `354e8cf` et corrige la production des snapshots d'activité sans modifier les seuils `1.40 / 1.75 / 2.50`.

Principales corrections proposées :

- SPOT : les intervalles OHLC Kraken absents peuvent être comptés comme volume nul uniquement lorsqu'ils sont internes à une fenêtre réellement couverte ; aucun OHLC/prix synthétique n'est créé ;
- PERPETUAL : l'historique du provider canonique utilise les candles Futures `trade` avec fenêtre `from/to`, et non les candles `mark`, afin que l'activité repose sur le volume échangé ;
- diagnostic borné par type d'erreur et par `SPOT / PERPETUAL` ;
- qualité de données explicite : `COMPLETE`, `NO_TRADE_GAPS`, `INSUFFICIENT_HISTORY`, `DISCONTINUOUS_HISTORY`, `TECHNICAL_ERROR` ;
- vrais échecs transport/payload/mapping restent `ERROR` ; données insuffisantes/discontinuités non justifiées restent `PARTIAL` ;
- candidats, recherche web, Agent, Market Discovery, Risk, Broker et ordres inchangés.

Voir `docs/30_BATCH_MARKET_ATTENTION_ACTIVITY_ROBUSTNESS.md`.

## Validation du patch Batch 30

Exécuté dans l'environnement ChatGPT :

- `py_compile` sur les deux fichiers backend modifiés et les deux nouveaux tests ;
- harness pytest isolé robustesse activité : `8/8` ;
- harness pytest isolé provider PERPETUAL : `3/3` ;
- test frontend isolé avec Node type stripping : `7/7`.

Validation locale utilisateur du 2026-09-28 :

- suite backend complète `pytest -q` : **PASS à 100 %**, avec seulement deux avertissements de dépréciation FastAPI/Starlette/AnyIO ;
- suite frontend `pnpm test` : **46/46 PASS** ;
- `pnpm lint` : **PASS** ;
- `pnpm typecheck` : **PASS** ;
- `pnpm build` : **PASS** ;
- `git diff --check` : **PASS**, avec uniquement les avertissements Git LF -> CRLF sous Windows.

Validation fonctionnelle runtime encore recommandée : laisser le Radar effectuer plusieurs rotations et observer la nouvelle ventilation `SPOT / PERPETUAL`, les catégories d'erreur et l'apparition de snapshots `AVAILABLE` lorsque les données Kraken sont suffisantes.
