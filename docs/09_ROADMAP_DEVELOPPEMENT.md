# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel          : 58b59ba0cab25e9011d26014c51005aac1365af2
Commit                    : fix: recover market attention runtime and clarify historical errors
Batch 28 Radar v1         : intégré
Batch 29 Observabilité    : intégré
Batch 30 Robustesse       : intégré
Batch 31 Liquidité USD    : intégré
Batch 32 Couverture       : intégré
Batch 33 Runtime hardening: intégré
Batch 34 / 34.1 / 34.2    : intégrés dans 58b59ba
Batch 35 UX erreurs hist. : intégré dans 58b59ba
Batch 36 terminologie UX  : patch proposé/local non intégré
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

### Batches 34 / 34.1 — Diagnostic SPOT

**État : intégrés dans `58b59ba0cab25e9011d26014c51005aac1365af2`.**

Les diagnostics de payload/stage et le durcissement du chemin Kraken sont désormais dans `main`. Ils restent des mécanismes d’observabilité bornés et ne modifient ni Agent, ni Market Discovery, ni Risk, ni Broker.

### Batch 34.2 — Cause SPOT et récupération runtime

**État : intégré dans `58b59ba0cab25e9011d26014c51005aac1365af2`.**

La cause runtime démontrée était la possibilité d’une réponse Kraken OHLC de `721` lignes pour la fenêtre Radar alors que le parseur rejetait toute réponse `> 720`. Le correctif intégré conserve la profondeur demandée à `720`, accepte le cas borné `721` et maintient le fail-closed au-delà.

Le même commit intègre les corrections d’aliases REST/symboles et les diagnostics nécessaires à l’isolation de cette cause, sans changement stratégique.

Voir `docs/34_2_BATCH_MARKET_ATTENTION_SPOT_ROOT_CAUSE.md`.

## UX cockpit — Batches 35 / 36

### Batch 35 — erreurs historiques

**État : intégré dans `58b59ba0cab25e9011d26014c51005aac1365af2`.**

Le cockpit distingue une erreur historique dépassée d’une panne courante et évite la duplication d’une même erreur sur le dernier cycle en échec.

### Batch 36 — terminologie financière

**État : patch proposé/local non intégré.**

Le batch remplace uniquement les libellés UX ambigus autour de `notional/notionnel` par `montant`, `valeur de la position` ou `valeur échangée estimée en USD` selon le contexte. Les identifiants techniques, calculs, API et comportements de trading restent inchangés.

## Périmètres ultérieurs possibles

À décider seulement sur besoin démontré :

- surveiller le chemin SPOT Kraken et ses compteurs de stage seulement si une nouvelle régression runtime est observée ;
- diagnostiquer ACE/AAVE/2Z Public Attention seulement à partir d'un échec de validation borné et reproductible ;
- persistance PostgreSQL durable des snapshots Radar ;
- normalisation USD multi-quote/FX canonique ;
- notionnel PERPETUAL uniquement lorsqu'une unité de volume explicitement documentée et transportée par le pipeline est disponible ;
- éventuelle exposition d'un contexte Radar à l'Agent : **non décidée** ;
- LIVE reste séparé et ultérieur.

Aucune promesse de rendement ni aucun ranking algorithmique stratégique ne doivent être introduits silencieusement.
