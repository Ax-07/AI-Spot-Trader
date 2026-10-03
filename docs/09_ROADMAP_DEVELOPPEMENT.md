# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel       : df1cc36633d4c94dcc94fd31d202b1dac94a5983
Commit                 : docs: close batch 43.2
Batch 39               : intégré
Batch 40               : intégré
Batch 41               : intégré
Batch 42               : intégré
Batch 43               : intégré
Batch 43.1             : intégré
Batch 43.2             : intégré
Batch 44               : patch proposé, non intégré
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

## État intégré jusqu'au Batch 43.2

Les Batches 28 à 35 ont construit et durci Market Attention. Le Batch 36 a amélioré la terminologie financière. Le Batch 37 a aligné la cadence stratégique sur les clôtures de bougies. Le Batch 38 a ajouté le préfiltrage Kraken et des caractéristiques descriptives. Le Batch 39 a supprimé la couche Web/IA du Radar. Le Batch 40 a ajouté la microstructure Kraken SPOT et le contrat Radar v3. Le Batch 41 a ajouté le scope `SPOT / PERPETUAL / ALL`, les directions récentes par horizon et le contrat Radar v4. Le Batch 42 a ajouté la Market Structure multi-timeframe et le contrat Radar v5. Le Batch 43 ajoute les filtres runtime de volume 24h et de capitalisation réelle ainsi que le contrat Radar v6. Le Batch 43.1 corrige la fenêtre causale SPOT/USD et ajoute les diagnostics typés du filtre volume. Le Batch 43.2 rend le filtre volume opérationnel pour les linear perpetuals USD via le turnover quote public Kraken Futures.

Le HEAD GitHub actuel `df1cc36633d4c94dcc94fd31d202b1dac94a5983` clôt la documentation du Batch 43.2. Le dernier commit fonctionnel du Radar est `25dcb5c069a519af8b92ae386f3d21d0aa4db9f3`.

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

- le volume 24h `SPOT/USD` est dérivé causalement des candles Kraken déjà chargées ;
- pour les linear perpetuals cotés USD, le volume 24h utilise le `volumeQuote` du ticker public bulk Kraken Futures ;
- aucune requête volume additionnelle par marché n'est introduite ;
- une vraie capitalisation utilise `MarketMetadataProvider`, initialement CoinPaprika, read-only, sans secret, avec TTL long et fail-soft ;
- la capitalisation est un filtre de métadonnée, jamais un signal ;
- la capitalisation filtre avant OHLCV ; le volume filtre après OHLCV mais avant L2/trades et structure multi-timeframe ;
- contrat intégré `market-attention-radar-v6` ;
- cockpit piloté par l'état backend, sans configuration frontend-only.

Le terme « Radar Kraken-only » n'est plus exact depuis l'intégration du Batch 43. La formulation à utiliser est : données de marché/structure/microstructure Kraken, métadonnée de capitalisation via provider externe read-only, exécution toujours Kraken.

## Batch 43.1 — correctif du filtre Volume 24h

**État : intégré via `85cbd01`.**

Le correctif :

- ancre la fenêtre 24h sur la dernière clôture 5m finalisée causalement disponible afin de conserver exactement les 288 intervalles lorsque l'historique est présent ;
- maintient `UNKNOWN` fail-closed lorsqu'un seuil est actif ;
- expose les raisons `UNKNOWN_UNSUPPORTED_QUOTE`, `UNKNOWN_UNSUPPORTED_MARKET_TYPE`, `UNKNOWN_INSUFFICIENT_HISTORY`, `UNKNOWN_TECHNICAL_ERROR` ;
- distingue une valeur fiable mais `BELOW_THRESHOLD` ;
- ajoute une régression `market_scope = ALL` + `min_volume_24h_usd = 100000` garantissant qu'un `SPOT/USD` valide au-dessus du seuil reste présent ;
- n'ajoute aucune conversion implicite `EUR/USDT/USDC -> USD` ni notionnalisation PERPETUAL non démontrée.

## Batch 43.2 — Radar PERPETUAL et volume 24h Futures

**État : intégré via `25dcb5c`.**

Éléments intégrés :

- conservation du fonctionnement `PERPETUAL + Volume Tous` avec une régression garantissant qu'un PERP valide et objectivement actif est réellement scanné ;
- utilisation du ticker public bulk Kraken Futures pour obtenir `volumeQuote` sans requête par marché ;
- utilisation directe de `volumeQuote` comme volume 24h USD uniquement pour les linear perpetuals cotés `USD` ;
- aucun volume PERP dérivé par une formule non démontrée `candle.volume * close` ;
- conservation d'un `UNKNOWN_*` explicite lorsque la donnée n'est pas exploitable ;
- diagnostic cockpit de la cause d'un résultat vide lorsque le filtre volume est en cause ;
- distinction entre panne du Radar PERP et marché valide sans activité assez inhabituelle ;
- aucune modification Agent, Risk Engine, Broker ni des invariants d'exécution SPOT/PAPER.

Commit fonctionnel intégré : `25dcb5c069a519af8b92ae386f3d21d0aa4db9f3` (`fix: repair perpetual market attention radar`).

Voir `docs/43_2_CORRECTIF_RADAR_PERPETUAL.md`.

## Batch 44 — liquidité PERPETUAL et couverture du Radar

**État : patch proposé, non intégré.**

Objectifs du patch :

- conserver intégralement la référence de liquidité canonique SPOT/USD ;
- pour les PERP linear/USD, réutiliser uniquement le `volumeQuote` 24h USD validé par le Batch 43.2 comme `liquidity_reference_usd` ;
- calculer les percentiles PERP dans une population PERP distincte de la population SPOT ;
- conserver `UNKNOWN` lorsque le `volumeQuote` fiable n'existe pas ;
- recalculer le niveau d'intérêt avec le scoring canonique existant après attribution du régime de liquidité, sans modifier les seuils ;
- exposer une observabilité déterministe de couverture/rotation : éligibles, frais, expirés, jamais vus, ratio de couverture, scan effectif, nombre estimé de refreshs par rotation, durée de rotation, TTL, âge de la plus vieille activité et invariant rotation/TTL ;
- conserver les curseurs SPOT/PERP et la répartition proportionnelle canonique du `scan_limit` ;
- afficher ces diagnostics dans le cockpit sans ajouter de capacité d'exécution.

Le diagnostic théorique utilise l'allocation réellement calculée par le Radar pour chaque famille de marché. Il n'augmente ni `scan_limit`, ni la concurrence, ni la cadence réseau.

Voir `docs/44_LIQUIDITE_PERPETUAL_ET_COUVERTURE_RADAR.md`.

## Validation connue

Batch 43.2 intégré :

```text
backend pytest -q       : PASS
frontend pnpm typecheck : PASS
frontend pnpm test      : PASS — 57/57
git diff --check        : PASS
```

Pour le Batch 44, la suite complète doit être rejouée localement avant intégration.

## Périmètres ultérieurs possibles

- filtres explicites par structure/tendance dans un batch séparé ;
- baseline statistique adaptative ;
- Open Interest, Funding, Liquidations et CVD ;
- conversion multi-devise du volume uniquement derrière une source FX explicite et testée ;
- extension future de la microstructure aux dérivés uniquement si un besoin est démontré ;
- éventuelle utilisation explicite des données Radar comme contexte Agent après décision architecturale ;
- LIVE, séparé et ultérieur.

Aucun ranking déterministe stratégique, quota de trades ou promesse de rendement ne doit être introduit silencieusement.
