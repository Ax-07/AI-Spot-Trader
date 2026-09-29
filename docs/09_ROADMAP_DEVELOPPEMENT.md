# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel          : 78607ce6ab9f2b9459de2b1e1a7127509475283a
HEAD fonctionnel Batch 32 : 5a2d07b3fc5208475c1a136690da6648797efde9
Batch 28 Radar v1         : intégré
Batch 29 Observabilité    : intégré
Batch 30 Robustesse       : intégré
Batch 31 Liquidité USD    : intégré
Batch 32 Couverture       : intégré
Batch 33 Runtime hardening: patch proposé/local, non intégré
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

Intégré au commit `1850ff8`.

- SPOT directement coté USD : estimation notionnelle `volume_base × close_5m` exposée comme `SPOT_BASE_VOLUME_X_5M_CLOSE_ESTIMATE` ;
- SPOT non USD : notionnel `null` ;
- PERPETUAL : notionnel `null` faute de sémantique de volume contractuelle reliée canoniquement au Radar ;
- régimes descriptifs : `MICRO / LOW / MEDIUM / HIGH / VERY_HIGH / UNKNOWN` ;
- faible liquidité jamais utilisée comme filtre d'éligibilité.

### Batch 32 — Couverture équilibrée SPOT/PERPETUAL

**État : intégré au commit `5a2d07b3fc5208475c1a136690da6648797efde9`.**

Apports intégrés :

- rotation stratifiée par `MarketType` ;
- curseur indépendant par famille ;
- allocation proportionnelle de `scan_limit` avec représentation minimale et redistribution ;
- absence de starvation ;
- diagnostics de scan courant et couverture fraîche ;
- aucune normalisation notionnelle PERPETUAL inventée.

Le Batch 32 conserve `candidate_limit = 20`, `max_web_searches_per_refresh = 8`, les seuils d'activité existants, les prompts Agent, Risk, Broker, Market Discovery et PAPER/LIVE.

Voir `docs/32_BATCH_MARKET_ATTENTION_BALANCED_COVERAGE.md`.

## Batch 33 — Market Attention Runtime Hardening

**État : patch proposé/local, à valider puis intégrer explicitement.**

Objectifs :

- réutiliser un cache canonique `KrakenPairRegistry` dans `KrakenCandleProvider` afin de supprimer la rafale `AssetPairs` par marché SPOT ;
- synchroniser les chargements/refreshs concurrents et ne rafraîchir le registry qu'au chargement initial ou après symbole absent ;
- distinguer sans fuite les erreurs transport/HTTP, throttling explicitement déclaré, erreur API Kraken et payload structurel invalide ;
- exiger que ratio et accélération satisfassent les seuils `VERY_HIGH / ACCELERATING` sur le même horizon ;
- conserver exactement les seuils `1.40 / 1.75 + 0.25 / 2.50 + 0.50` ;
- aligner `public_attention_v1` sur les contraintes Pydantic de longueur ;
- encapsuler les échecs de validation canonique web en diagnostic auxiliaire borné ;
- réduire les sources web exposées uniquement lorsqu'un lien fiable avec les éléments structurés ou les citations provider est démontrable.

Invariants explicitement inchangés :

- rotation Batch 32 et `scan_limit = 120` ;
- `candidate_limit = 20` ;
- `max_web_searches_per_refresh = 8` ;
- recherche web uniquement après génération des candidats ;
- faible liquidité non filtrante ;
- notionnels Batch 31 inchangés ;
- PERPETUAL notionnel `null` / liquidité `UNKNOWN` ;
- aucune donnée Radar vers Agent, Market Discovery, Risk Engine ou Broker ;
- aucun BUY/SELL/HOLD produit par le Radar.

Voir `docs/33_BATCH_MARKET_ATTENTION_RUNTIME_HARDENING.md`.

## Périmètres ultérieurs possibles

À décider seulement sur besoin démontré :

- persistance PostgreSQL durable des snapshots Radar ;
- normalisation USD multi-quote/FX canonique ;
- notionnel PERPETUAL uniquement lorsqu'une unité de volume explicitement documentée et transportée par le pipeline est disponible ;
- amélioration de la couverture du catalogue si la cadence/charge réelle le justifie ;
- éventuelle exposition d'un contexte Radar à l'Agent : **non décidée** et hors périmètre actuel ;
- LIVE reste séparé et ultérieur.

Aucune promesse de rendement et aucun ranking algorithmique stratégique ne doivent être introduits silencieusement.
