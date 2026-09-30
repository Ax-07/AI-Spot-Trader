# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel          : 4a516fde33853fe84d18bd8c4780753c0db58214
Commit                    : fix: harden market attention runtime
Batch 28 Radar v1         : intégré
Batch 29 Observabilité    : intégré
Batch 30 Robustesse       : intégré
Batch 31 Liquidité USD    : intégré
Batch 32 Couverture       : intégré
Batch 33 Runtime hardening: intégré
Batch 34 / 34.1           : local utilisateur, runtime SPOT encore en erreur
Batch 34.2                : cause runtime 721 lignes OHLC démontrée, correctif final à valider
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve :

- un seul Agent IA stratégique ;
- backend Python/FastAPI comme application de trading ;
- frontend comme cockpit uniquement ;
- Risk Engine déterministe comme autorité finale ;
- PAPER comme mode des premières versions ;
- Kraken comme exchange initial ;
- SPOT uniquement pour le moteur de trading dans le périmètre actuel ;
- PERPETUAL du Radar strictement informatif dans ce batch ;
- aucune sortie LLM directement exécutable sur Kraken ;
- aucun secret versionné ;
- LIVE explicitement séparé et ultérieur.

## Cadences distinctes

1. monitoring / mark-to-market : déterministe, sans LLM ;
2. cycle stratégique IA : plan ordonné `BUY / SELL / HOLD` ;
3. Market Discovery : même Agent, cadence distincte ;
4. streaming marché / candles : technique, déterministe ;
5. Market Attention Radar : observation déterministe + recherche publique auxiliaire, cadence/cache/TTL propres, sans influence sur le trading.

## Market Attention — état

### Batches 28 à 32

Intégrés : Radar v1, observabilité, robustesse activité, notionnel USD SPOT/régimes de liquidité et couverture équilibrée SPOT/PERPETUAL. Les limites restent `scan_limit=120`, `candidate_limit=20`, `max_web_searches_per_refresh=8`.

### Batch 33 — Runtime Hardening

**État : intégré dans `4a516fde33853fe84d18bd8c4780753c0db58214`.**

Le runtime utilise notamment un `KrakenPairRegistry` partagé/lazy et verrouillé, une politique anti-stampede/cooldown, une classification transport/API/payload et les corrections de cohérence d'activité/public attention prévues par le batch.

### Batch 34 / 34.1 — Diagnostic SPOT

**État : local utilisateur.**

Les validations locales passent à 100 %, mais le refresh réel du 29/09/2026 conserve `100/100` SPOT en `ERROR`, tous classés `KrakenPayloadError`, alors que PERPETUAL reste sans erreur technique. Batch 34.1 attache un stage borné à l'exception mais ne l'agrège pas dans l'overview.

### Batch 34.2 — Cause SPOT et diagnostic borné

**État : cause runtime finale démontrée ; correctif `721` local à valider.**

Cause runtime finale confirmée le 29/09/2026 : le client Kraken réel peut renvoyer `721` lignes OHLC pour la fenêtre utilisée par le Radar, alors que le parseur rejetait toute réponse `> 720`. Le diagnostic `activity_payload_stage_counts` a isolé `OHLC_SERIES = 100`, puis une reproduction `httpx + _parse_ohlcv_payload` a confirmé `ROW_COUNT: 721` et le même stage.

Le correctif conserve la profondeur provider demandée à `720` et autorise uniquement `721` lignes de réponse ; `722+` reste fail-closed.

Objectifs réalisés :

- exposer `activity_payload_stage_counts` avec uniquement les stages allowlistés ;
- ne jamais exposer payload/body/URL privée/provider key/symbole brut via ce diagnostic ;
- traiter les clés `AssetPairs.result` comme des aliases REST possibles au lieu d'exiger un `/` dans chaque clé ;
- dériver le symbole canonique depuis `wsname`, puis une clé déjà affichable, puis `base/quote` avec mapping legacy exact ;
- préserver les aliases `XBT/BTC`, `XDG/DOGE`, les identifiants REST internes et les noms display ;
- conserver un échec strict si une entrée ne permet aucune identité de paire sûre ;
- conserver la validation OHLC stricte tout en classifiant ses erreurs par stage ;
- ne modifier ni Public Attention, ni Agent, ni Market Discovery, ni Risk, ni Broker, ni ordre, ni PAPER/LIVE.

Validation locale attendue après extraction : tests ciblés, `pytest -q`, `git diff --check`, puis refresh Radar et vérification des compteurs SPOT/stages.

Voir `docs/34_2_BATCH_MARKET_ATTENTION_SPOT_ROOT_CAUSE.md`.

## Périmètres ultérieurs possibles

À décider seulement sur besoin démontré :

- après validation du correctif `721`, confirmer par refresh que les SPOT quittent `ERROR` et que `OHLC_SERIES` retombe à zéro ;
- diagnostiquer ACE/AAVE/2Z Public Attention seulement à partir d'un échec de validation borné et reproductible ;
- persistance PostgreSQL durable des snapshots Radar ;
- normalisation USD multi-quote/FX canonique ;
- notionnel PERPETUAL uniquement lorsqu'une unité de volume explicitement documentée et transportée par le pipeline est disponible ;
- éventuelle exposition d'un contexte Radar à l'Agent : **non décidée** ;
- LIVE reste séparé et ultérieur.

Aucune promesse de rendement ni aucun ranking algorithmique stratégique ne doivent être introduits silencieusement.
