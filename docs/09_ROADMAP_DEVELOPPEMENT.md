# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel       : f5de73270c23c6c4e2a6114ac78b3e57c17c65b1
Commit                 : docs: close batch 42 documentation
Batch 39               : intégré
Batch 40               : intégré
Batch 41               : intégré
Batch 42               : intégré
Batch 43               : patch proposé, non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve un seul Agent IA stratégique, Kraken comme exchange initial et source d'exécution, Risk Engine comme autorité finale, backend indépendant du frontend, mode PAPER avant tout LIVE, aucune sortie LLM directement exécutable et Market Attention strictement informatif.

## Cadences distinctes

1. monitoring / mark-to-market : déterministe ;
2. cycle stratégique IA : `INTERVAL` ou `CANDLE_CLOSE` ;
3. Market Discovery : cadence distincte ;
4. streaming/caches marché : technique et déterministe ;
5. Market Attention Radar : observation déterministe avec cadence propre, données marché Kraken et, à partir du patch Batch 43, métadonnées de capitalisation externes read-only mises en cache.

## État intégré jusqu'au Batch 42

Les Batches 28 à 35 ont construit et durci Market Attention. Le Batch 36 a amélioré la terminologie financière. Le Batch 37 a aligné la cadence stratégique sur les clôtures de bougies. Le Batch 38 a ajouté le préfiltrage Kraken et des caractéristiques descriptives. Le Batch 39 a supprimé la couche Web/IA du Radar. Le Batch 40 a ajouté la microstructure Kraken SPOT et le contrat Radar v3. Le Batch 41 a ajouté le scope `SPOT / PERPETUAL / ALL`, les directions récentes par horizon et le contrat Radar v4. Le Batch 42 a ajouté la Market Structure multi-timeframe et le contrat Radar v5.

Le commit fonctionnel Batch 42 est `003dae8dbfdc052edbad5bfde2c23fa24852eace`; la clôture documentaire porte le HEAD intégré à `f5de73270c23c6c4e2a6114ac78b3e57c17c65b1`.

## Batch 42 — Market Structure multi-timeframe

**État : intégré.**

Éléments intégrés :

- lecture directe `5m / 15m / 1h / 4h` via `CandleStreamService.history_as_of` ;
- analyse de 100 candles finalisées par timeframe par défaut ;
- confirmation causale des pivots ;
- classification `HH / HL / LH / LL` ;
- états `BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN` ;
- événements descriptifs `BOS / CHOCH` ;
- synthèse multi-timeframe pouvant être `MIXED` ;
- calcul uniquement sur la shortlist déjà filtrée par scope ;
- séparation totale avec Agent/Risk/Broker.

`recent_trend` et `market_structure` restent deux notions indépendantes.

## Batch 43 — filtres volume et capitalisation

**État : patch proposé, non intégré.**

Objectif : réduire l'univers observé avant les enrichissements coûteux avec deux filtres pilotés par le backend :

```text
min_volume_24h_usd
market_cap_categories / min_market_cap_usd / max_market_cap_usd
```

Décisions proposées :

- le volume 24h USD est dérivé causalement des candles Kraken déjà chargées lorsque la devise notionnelle USD est prouvée ;
- aucun appel Kraken additionnel par marché n'est ajouté pour ce volume ;
- une vraie capitalisation utilise `MarketMetadataProvider`, initialement CoinPaprika, read-only, sans secret, avec TTL long et fail-soft ;
- la capitalisation est un filtre de métadonnée, jamais un signal ;
- la capitalisation filtre avant OHLCV ; le volume filtre après OHLCV mais avant L2/trades et structure multi-timeframe ;
- protocole proposé `market-attention-radar-v6` ;
- cockpit piloté par l'état backend, sans configuration frontend-only.

Le terme « Radar Kraken-only » n'est plus exact si ce patch est intégré. La formulation cible est : données de marché/structure/microstructure Kraken, métadonnée de capitalisation via provider externe, exécution toujours Kraken.

## Validation Batch 42

Avant le push du Batch 42, l'utilisateur avait validé localement :

```text
backend pytest -q       : PASS complet — 100 %
frontend pnpm test      : 54/54 PASS
frontend pnpm typecheck : PASS
```

Ces validations restent celles du Batch 42 et ne valent pas validation du Batch 43.

## Validation requise avant intégration Batch 43

```text
backend pytest -q
frontend pnpm test
frontend pnpm typecheck
git diff --check
git status --short
```

## Périmètres ultérieurs possibles

- filtres explicites par structure/tendance dans un batch séparé ;
- conversion multi-devise du volume uniquement derrière une source FX explicite et testée ;
- éventuelle utilisation explicite des données Radar comme contexte Agent après décision architecturale ;
- LIVE, séparé et ultérieur.

Aucun ranking déterministe stratégique, quota de trades ou promesse de rendement ne doit être introduit silencieusement.
