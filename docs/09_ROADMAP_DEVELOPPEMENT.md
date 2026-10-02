# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel       : 3b8bc6bcb83604cb20eb5ee27ef1b95fcc4210da
Commit                 : docs: close batch 43 documentation
Batch 39               : intégré
Batch 40               : intégré
Batch 41               : intégré
Batch 42               : intégré
Batch 43               : intégré
Batch 43.1             : patch correctif proposé, non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve un seul Agent IA stratégique, Kraken comme exchange initial et source d'exécution, Risk Engine comme autorité finale, backend indépendant du frontend, mode PAPER avant tout LIVE, aucune sortie LLM directement exécutable et Market Attention strictement informatif.

## Cadences distinctes

1. monitoring / mark-to-market : déterministe ;
2. cycle stratégique IA : `INTERVAL` ou `CANDLE_CLOSE` ;
3. Market Discovery : cadence distincte ;
4. streaming/caches marché : technique et déterministe ;
5. Market Attention Radar : observation déterministe avec cadence propre, données marché Kraken et, depuis le Batch 43 intégré, métadonnées de capitalisation externes read-only mises en cache.

## État intégré jusqu'au Batch 43

Les Batches 28 à 35 ont construit et durci Market Attention. Le Batch 36 a amélioré la terminologie financière. Le Batch 37 a aligné la cadence stratégique sur les clôtures de bougies. Le Batch 38 a ajouté le préfiltrage Kraken et des caractéristiques descriptives. Le Batch 39 a supprimé la couche Web/IA du Radar. Le Batch 40 a ajouté la microstructure Kraken SPOT et le contrat Radar v3. Le Batch 41 a ajouté le scope `SPOT / PERPETUAL / ALL`, les directions récentes par horizon et le contrat Radar v4. Le Batch 42 a ajouté la Market Structure multi-timeframe et le contrat Radar v5. Le Batch 43 ajoute les filtres runtime de volume 24h et de capitalisation réelle ainsi que le contrat Radar v6.

Le commit fonctionnel intégré du Batch 43 est `32320e268722c6e431ae722924bca487ae45d004` (`feat: add market attention volume and market cap filters`). Le HEAD GitHub actuel `3b8bc6bcb83604cb20eb5ee27ef1b95fcc4210da` est sa clôture documentaire.

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

**État : intégré.**

Le Radar v6 réduit l'univers observé avant les enrichissements coûteux avec deux familles de filtres pilotées par le backend :

```text
min_volume_24h_usd
market_cap_categories / min_market_cap_usd / max_market_cap_usd
```

Décisions intégrées :

- le volume 24h USD est dérivé causalement des candles Kraken déjà chargées lorsque la devise notionnelle USD est prouvée ;
- aucun appel Kraken additionnel par marché n'est ajouté pour ce volume ;
- une vraie capitalisation utilise `MarketMetadataProvider`, initialement CoinPaprika, read-only, sans secret, avec TTL long et fail-soft ;
- la capitalisation est un filtre de métadonnée, jamais un signal ;
- la capitalisation filtre avant OHLCV ; le volume filtre après OHLCV mais avant L2/trades et structure multi-timeframe ;
- contrat intégré `market-attention-radar-v6` ;
- cockpit piloté par l'état backend, sans configuration frontend-only.

Le terme « Radar Kraken-only » n'est plus exact depuis l'intégration du Batch 43. La formulation à utiliser est : données de marché/structure/microstructure Kraken, métadonnée de capitalisation via provider externe read-only, exécution toujours Kraken.

## Batch 43.1 — correctif du filtre Volume 24h

**État : patch proposé, non intégré.**

Le correctif :

- ancre la fenêtre 24h sur la dernière clôture 5m finalisée causalement disponible afin de conserver exactement les 288 intervalles lorsque l'historique est présent ;
- maintient `UNKNOWN` fail-closed lorsqu'un seuil est actif ;
- expose les raisons `UNKNOWN_UNSUPPORTED_QUOTE`, `UNKNOWN_UNSUPPORTED_MARKET_TYPE`, `UNKNOWN_INSUFFICIENT_HISTORY`, `UNKNOWN_TECHNICAL_ERROR` ;
- distingue une valeur fiable mais `BELOW_THRESHOLD` ;
- ajoute une régression `market_scope = ALL` + `min_volume_24h_usd = 100000` garantissant qu'un `SPOT/USD` valide au-dessus du seuil reste présent ;
- n'ajoute aucune conversion implicite `EUR/USDT/USDC -> USD` ni notionnalisation PERPETUAL non démontrée.

## Validation finale Batch 43

Validations exécutées localement par l'utilisateur avant le push :

```text
backend pytest -q       : PASS
frontend pnpm typecheck : PASS
frontend pnpm test      : PASS — 57/57
git diff --check        : PASS
```

Ces résultats concernent le Batch 43 intégré ; le patch Batch 43.1 doit être revalidé localement.

## Périmètres ultérieurs possibles

- filtres explicites par structure/tendance dans un batch séparé ;
- conversion multi-devise du volume uniquement derrière une source FX explicite et testée ;
- éventuelle notionnalisation PERPETUAL uniquement après preuve de la sémantique du volume et transport explicite de la taille de contrat dans le pipeline Radar ;
- éventuelle utilisation explicite des données Radar comme contexte Agent après décision architecturale ;
- LIVE, séparé et ultérieur.

Aucun ranking déterministe stratégique, quota de trades ou promesse de rendement ne doit être introduit silencieusement.
