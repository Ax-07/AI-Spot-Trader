# Batch 44 — Liquidité PERPETUAL et couverture du Market Attention Radar

## Statut

Patch préparé à partir du HEAD GitHub `main` audité :

```text
df1cc36633d4c94dcc94fd31d202b1dac94a5983
docs: close batch 43.2
```

Le patch n'est pas intégré à GitHub au moment de cette livraison.

## Objectif

Corriger la référence de liquidité des PERPETUAL sans inventer de notionnalisation et rendre observable la capacité du Radar à couvrir son univers avant expiration du cache d'activité.

Le Radar reste `market-attention-radar-v6`, informatif, déterministe, causal et read-only.

## Audit

### Confirmé

- la référence de liquidité canonique est dérivée des `baseline_notional_usd` des horizons ;
- ces notionnels utilisent `_spot_usd_notional()` et sont donc volontairement absents pour les PERPETUAL ;
- un PERP obtient ainsi `LiquidityRegime.UNKNOWN` même lorsqu'un `volumeQuote` 24h USD fiable est disponible ;
- `HIGH / VERY_HIGH` augmente déjà le niveau d'intérêt canonique, alors que `MICRO` peut le diminuer ;
- la classification de base sépare déjà les populations de percentiles par `MarketType`, ce qui évite une contamination SPOT/PERP ;
- le Batch 43.2 fournit déjà le `volumeQuote` 24h USD validé dans `attention_filters.py` ; aucun nouvel appel réseau n'est nécessaire ;
- la rotation possède déjà deux curseurs indépendants, SPOT et PERPETUAL ;
- `_scan_allocations()` répartit `scan_limit` de façon déterministe entre familles, proportionnellement à leur taille tout en conservant une représentation des familles présentes ;
- `activity_ttl_seconds` filtre le cache frais sans exposer actuellement de diagnostic global de couverture.

### Obsolète

- l'hypothèse d'un unique curseur global n'est pas vraie au HEAD audité ;
- l'approximation `ceil(total / scan_limit)` n'est pas toujours exacte en scope `ALL`, car le Radar applique une allocation par famille ;
- la documentation de reprise pointait encore le commit fonctionnel `25dcb5c` comme HEAD alors que `df1cc366` a ensuite clôturé la documentation du Batch 43.2.

### Manquant avant ce batch

- référence de liquidité exploitable pour les PERP linear/USD ;
- diagnostic explicite du ratio de couverture de l'univers de scan ;
- distinction entre marchés jamais vus et marchés sortis du TTL ;
- estimation de la durée d'une rotation complète basée sur l'allocation réelle ;
- indicateur signalant qu'une configuration ne peut théoriquement pas revisiter tout l'univers avant le TTL ;
- affichage cockpit de ces diagnostics.

### À décider ultérieurement

- modification automatique de `scan_limit`, `refresh_seconds` ou du TTL : non décidée et hors périmètre ;
- filtres Market Structure ;
- baseline statistique adaptative ;
- Open Interest, Funding, Liquidations, CVD ;
- microstructure Futures ;
- connexion du Radar à l'Agent.

## Liquidité PERPETUAL

Le mécanisme SPOT reste inchangé.

Pour un PERPETUAL/USD, la couche v6 réutilise la mesure 24h existante uniquement si elle est `Volume24hStatus.AVAILABLE` :

```text
volumeQuote Kraken Futures validé
-> Volume24hMeasurement.value_usd
-> liquidity_reference_usd
-> percentile dans la population PERPETUAL mesurable
-> liquidity_regime
-> recalcul de l'intérêt via le scoring canonique existant
```

Si la mesure est absente, invalide ou techniquement indisponible :

```text
liquidity_reference_usd = None
liquidity_regime = UNKNOWN
```

Aucun calcul `candle.volume * close` n'est introduit pour les PERP. Aucune conversion FX n'est ajoutée. Les seuils de percentiles et le scoring général ne changent pas.

## Couverture et rotation

Le contrat v6 ajoute `coverage` avec :

```text
eligible_market_count
fresh_market_count
expired_market_count
unseen_market_count
coverage_ratio
effective_scan_limit
estimated_refreshes_per_full_rotation
estimated_full_rotation_seconds
activity_ttl_seconds
oldest_activity_age_seconds
rotation_within_activity_ttl
status
```

L'univers éligible correspond aux marchés après :

```text
catalogue
-> scope SPOT / PERPETUAL / ALL
-> filtre capitalisation
```

Le filtre volume reste post-OHLCV, comme dans le pipeline canonique. Il ne réduit donc pas artificiellement l'univers à couvrir avant que le Radar ait observé les candles nécessaires au calcul SPOT.

L'estimation d'une rotation complète reprend `_scan_allocations()` et calcule, pour chaque famille présente, le nombre de refreshs nécessaire. La durée estimée est :

```text
max(refreshs nécessaires SPOT, refreshs nécessaires PERPETUAL)
* refresh_seconds
```

Le diagnostic ne modifie aucune configuration.

Statuts :

- `NO_MARKETS` : aucun marché éligible ;
- `COVERED` : tous les marchés éligibles disposent d'une activité encore fraîche ;
- `ROTATING` : couverture incomplète mais la rotation théorique tient dans le TTL ;
- `TTL_EXPIRED` : au moins un marché observé est déjà sorti du TTL alors que la rotation théorique reste compatible ;
- `CONFIGURATION_TOO_SLOW` : la rotation théorique dépasse `activity_ttl_seconds`.

Les compteurs `expired_market_count` et `unseen_market_count` restent visibles même lorsque le statut principal est `CONFIGURATION_TOO_SLOW`.

## Invariants préservés

- un seul Agent IA stratégique ;
- Radar informatif uniquement ;
- déterministe et causal ;
- Risk Engine autorité finale ;
- SPOT/PAPER comme invariants d'exécution actuels ;
- aucun short, levier, margin, future ou perpetual rendu exécutable ;
- aucune nouvelle clé privée ;
- aucune donnée future ;
- aucune modification Agent / Risk Engine / Broker ;
- aucune augmentation silencieuse des limites réseau ou de concurrence.

## Tests du batch

Le nouveau fichier `backend/tests/test_market_attention_batch44_liquidity_coverage.py` couvre notamment :

- conservation de la classification SPOT par la couche Batch 44 ;
- classification PERP avec `volumeQuote` valide ;
- `UNKNOWN` lorsqu'une mesure PERP fiable manque ;
- isolation des percentiles SPOT/PERP ;
- petit univers entièrement couvert ;
- univers mixte supérieur au `scan_limit` ;
- détection d'une rotation théorique plus longue que le TTL ;
- distinction rotation en cours / TTL expiré ;
- cohérence des scopes ;
- conservation de la rotation déterministe par curseurs de famille.

Le test frontend `market-attention.test.mjs` couvre aussi le formatage et les messages des diagnostics de couverture.

Les tests historiques des Batches 43/43.1/43.2 restent la couverture de non-régression des filtres volume/capitalisation, du fail-closed et de la causalité SPOT.

## Validation à effectuer avant intégration

Depuis la racine du repository :

```powershell
cd E:\AI-Spot-Trader\backend
pytest -q

cd E:\AI-Spot-Trader\frontend
pnpm typecheck
pnpm test

cd E:\AI-Spot-Trader
git diff --check
git status --short
```

Un smoke read-only Kraken peut compléter la validation pour observer des PERP/USD réels, mais aucune donnée LIVE privée n'est requise pour valider ce batch.
