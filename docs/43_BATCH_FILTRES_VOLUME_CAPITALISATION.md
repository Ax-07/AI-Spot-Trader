# 43 — Filtres volume et capitalisation du Market Attention Radar

## Statut

```text
État       : intégré
Commit     : 32320e268722c6e431ae722924bca487ae45d004
Contrat    : market-attention-radar-v6
```

## Objectif

Permettre à l'utilisateur de réduire l'univers du Market Attention Radar depuis le cockpit selon :

- un minimum de volume notionnel 24h en USD ;
- une vraie capitalisation de marché, par catégories applicatives et/ou bornes numériques.

Les filtres restent informatifs. Ils ne créent aucune décision `BUY / SELL / HOLD` et ne modifient ni Agent, ni Risk Engine, ni Broker.

## Audit du volume

Le Radar canonique charge déjà jusqu'à 720 candles 5m et réutilise `CandleStreamService`. Il est donc inutile d'ajouter un appel Kraken `/Ticker` par marché uniquement pour ce filtre.

Pour un marché `SPOT` directement coté en `USD`, le Batch 43 calcule causalement :

```text
volume_24h_usd = somme(volume_base × close)
```

sur les candles 5m finalisées appartenant aux 24 dernières heures et déjà connaissables à `observed_at`.

Le calcul est fail-closed :

- `SPOT/USD` avec profondeur causale suffisante => valeur disponible ;
- autre devise cotée => `UNKNOWN` ;
- `PERPETUAL` sans sémantique notionnelle USD explicitement prouvée => `UNKNOWN` ;
- historique insuffisant => `UNKNOWN`.

Si aucun filtre volume n'est actif, ces inconnues n'excluent pas le marché. Si un seuil minimum est actif, `UNKNOWN` ne satisfait pas le seuil.

## Audit de la capitalisation

Une vraie capitalisation exige la supply circulante. Kraken ne constitue pas une source complète de cette métadonnée. Le Batch 43 n'utilise donc jamais un proxy de liquidité comme s'il s'agissait d'une market cap.

Architecture :

```text
MarketMetadataProvider
        ↓
CoinPaprikaMarketMetadataProvider
        ↓
circulating_supply
market_cap_usd
market_cap_rank
observed_at
provider
```

Le provider est read-only, sans secret, avec cache de six heures et comportement fail-soft. Une panne du provider n'arrête pas le Radar.

## Catégories applicatives

Les seuils sont centralisés dans `attention_filters.py` :

```text
MICRO  <   100 000 000 $
SMALL  < 1 000 000 000 $
MID    <10 000 000 000 $
LARGE >=10 000 000 000 $
```

Ces classes sont des catégories applicatives configurées, pas une classification universelle du marché.

## Ordre du pipeline

```text
catalogue Kraken
        ↓
scope SPOT / PERPETUAL / ALL
        ↓
metadata market cap
        ↓
filtre capitalisation
        ↓
rotation / scan OHLCV 5m
        ↓
volume 24h causal
        ↓
filtre volume
        ↓
activité / tendance / shortlist
        ↓
microstructure SPOT si applicable
        ↓
Market Structure 5m / 15m / 1h / 4h
```

Ainsi, les marchés exclus par capitalisation ne déclenchent pas de scan OHLCV et les marchés exclus par volume n'atteignent ni `/Depth`/`/Trades`, ni les quatre analyses de structure.

## Runtime et API

Le backend conserve l'état canonique :

```text
market_scope
min_volume_24h_usd
market_cap_categories
min_market_cap_usd
max_market_cap_usd
```

Endpoints :

```text
GET /api/v1/market-attention/filters
PUT /api/v1/market-attention/filters
PUT /api/v1/market-attention/scope   # compatibilité conservée
```

Lors d'un changement, le service publie d'abord un snapshot `PARTIAL` vide portant les nouveaux filtres, puis recalcule le Radar sous verrou. L'ancienne shortlist n'est donc pas présentée comme correspondant aux nouveaux réglages.

## Contrat v6

Le snapshot global expose :

```text
protocol_version = market-attention-radar-v6
filters
market_cap_metadata_status
market_cap_metadata_provider
```

Chaque candidat expose en plus lorsque disponible :

```text
volume_24h_usd
market_cap_usd
market_cap_category
market_cap_rank
circulating_supply
market_cap_provider
market_cap_observed_at
```

Les contrats v4/v5 restent acceptés par les routes pour compatibilité avec les services/tests existants.

## Cockpit

Le panneau Market Attention ajoute, près du scope marché :

- presets Volume 24h : Tous, >100 k$, >500 k$, >1 M$, >5 M$, >10 M$ ;
- catégories Capitalisation : Toutes, Micro, Small, Mid, Large ;
- affichage des filtres réellement renvoyés par le backend ;
- affichage `Vol. 24h` et `Capitalisation` dans la ligne candidat et le détail lorsque disponibles.

La vue indique explicitement que la donnée de capitalisation provient d'un provider externe read-only alors que les données de marché restent Kraken.

## Isolation

Le Batch 43 n'importe aucune couche Agent/Risk/Broker dans le Radar. Le provider de métadonnées n'a aucune capacité d'exécution et aucune donnée externe n'est transformée en signal stratégique.

L'exécution du projet reste SPOT sur Kraken. Le scope Radar `PERPETUAL / ALL` reste une capacité d'observation uniquement.

## Tests couverts par le Batch 43

Backend :

- bornes de catégories de capitalisation ;
- validation min/max ;
- calcul causal volume 24h et borne minimum inclusive ;
- mapping CoinPaprika avec rejet fail-closed des symboles ambigus ;
- cache/fail-soft provider ;
- capitalisation avant OHLCV ;
- volume avant microstructure et structure ;
- combinaison scope + volume + market cap ;
- API GET/PUT filters et validation Pydantic.

Frontend :

- formatage USD ;
- labels catégories ;
- fallback des filtres ;
- requête runtime `/filters` ;
- conservation du comportement des helpers existants.

## Validation finale

Validations exécutées localement avant le push du commit fonctionnel :

```text
backend pytest -q       : PASS
frontend pnpm typecheck : PASS
frontend pnpm test      : PASS — 57/57
git diff --check        : PASS
```

Le Batch 43 est intégré sur `main` au commit `32320e268722c6e431ae722924bca487ae45d004`.
