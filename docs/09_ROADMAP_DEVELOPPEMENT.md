# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub audité        : 1850ff8783d0d29a5dd6628bdf1e9bb11a08ca63
Batch 28 Radar v1         : intégré
Batch 29 Observabilité    : intégré
Batch 30 Robustesse       : intégré
Batch 31 Liquidité USD    : intégré
Batch 32 Couverture       : patch proposé/local, non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve :

- un seul Agent IA stratégique ;
- backend Python/FastAPI comme application de trading ;
- frontend comme cockpit uniquement ;
- Risk Engine déterministe comme autorité finale ;
- PAPER comme mode des premières versions ;
- SPOT comme périmètre de trading cible du projet, avec les capacités PAPER PERPETUAL historiques conservées là où elles sont déjà intégrées ;
- aucune sortie LLM directement exécutable sur Kraken ;
- aucun secret versionné ;
- LIVE explicitement séparé et ultérieur.

## Cadences distinctes

1. monitoring / mark-to-market : déterministe, sans LLM ;
2. cycle stratégique IA : plan ordonné `BUY / SELL / HOLD` ;
3. Market Discovery : même Agent, cadence distincte ;
4. streaming marché / candles : technique, déterministe ;
5. Market Attention Radar : observation déterministe + recherche publique auxiliaire, cadence/cache/TTL propres, sans influence sur le trading.

## Market Attention — état intégré

### Batch 28 — Radar v1

Intégré. Le Radar observe SPOT + PERPETUAL, agrège les candles `5m / 15m / 1h / 4h`, présélectionne l'activité inhabituelle, puis enrichit une shortlist bornée par recherche publique sourcée.

### Batch 29 — Observabilité

Intégré. L'overview expose les distributions de statut/activité et les activités sous seuil afin de distinguer « aucun événement inhabituel » d'une couverture dégradée.

### Batch 30 — Robustesse activité

Intégré. Les gaps SPOT sans trade peuvent être interprétés comme zéro-volume uniquement lorsque la fenêtre est réellement couverte ; PERPETUAL reste strict sur les discontinuités et utilise les candles Futures `trade` pour mesurer l'activité échangée.

### Batch 31 — Liquidité USD

Intégré au HEAD `1850ff8`.

- SPOT directement coté USD : estimation notionnelle `volume_base × close_5m` exposée comme `SPOT_BASE_VOLUME_X_5M_CLOSE_ESTIMATE` ;
- SPOT non USD : notionnel `null` ;
- PERPETUAL : notionnel `null` faute de sémantique de volume contractuelle reliée canoniquement au Radar ;
- régimes descriptifs : `MICRO / LOW / MEDIUM / HIGH / VERY_HIGH / UNKNOWN` ;
- faible liquidité jamais utilisée comme filtre d'éligibilité.

## Batch 32 — Couverture équilibrée SPOT/PERPETUAL

**État : patch proposé/local, à valider puis intégrer explicitement.**

Objectifs :

- remplacer la rotation globale séquentielle par une rotation stratifiée par `MarketType` ;
- garder un curseur indépendant par famille ;
- allouer `scan_limit` proportionnellement aux populations avec représentation minimale et redistribution ;
- garantir l'absence de starvation ;
- afficher la répartition du scan courant et de la couverture fraîche ;
- conserver les seuils, budgets web et règles de shortlist ;
- ne produire aucun faux notionnel USD PERPETUAL.

Le Batch 32 ne change pas :

- `candidate_limit = 20` ;
- `max_web_searches_per_refresh = 8` ;
- seuils `1.40 / 1.75 / 2.50` et accélérations associées ;
- logique Agent/Risk/Broker/Market Discovery ;
- stratégie, sizing ou prompts Agent ;
- mode PAPER/LIVE.

Voir `docs/32_BATCH_MARKET_ATTENTION_BALANCED_COVERAGE.md`.

## Périmètres ultérieurs possibles

À décider seulement sur besoin démontré :

- persistance PostgreSQL durable des snapshots Radar ;
- normalisation USD multi-quote/FX canonique ;
- notionnel PERPETUAL uniquement lorsqu'une unité de volume explicitement documentée et transportée par le pipeline est disponible ;
- amélioration de la couverture du catalogue si la cadence/charge réelle le justifie ;
- éventuelle exposition d'un contexte Radar à l'Agent : **non décidée** et hors périmètre actuel ;
- LIVE reste séparé et ultérieur.

Aucune promesse de rendement et aucun ranking algorithmique stratégique ne doivent être introduits silencieusement.
