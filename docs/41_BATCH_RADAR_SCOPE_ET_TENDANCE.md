# 41 — Market Attention : scope SPOT/PERP/ALL et direction de tendance

## Statut

**INTÉGRÉ** sur `main` au commit :

```text
e65940b4c773f0de329648f5f3bb1f8960faa696
feat: add market attention scope and trend direction
```

## Référence auditée après intégration

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : e65940b4c773f0de329648f5f3bb1f8960faa696
```

Le statut antérieur « patch proposé / non intégré » est obsolète depuis ce commit.

## Objectif

Ajouter deux dimensions strictement informatives au Radar déterministe Kraken :

1. un scope de scan `SPOT / PERPETUAL / ALL` réellement appliqué avant les appels OHLCV ;
2. une direction de tendance déterministe par horizon et globale.

Le Radar ne produit jamais d'action `BUY`, `SELL` ou `HOLD`.

## Architecture retenue

Le Batch 41 n'altère pas le pipeline OHLCV canonique. Il ajoute `ScopedTrendMarketAttentionRadar`, sous-classe du Radar microstructure Batch 40 :

```text
ScopedTrendMarketAttentionRadar (v4)
  -> MicrostructureMarketAttentionRadar (v3)
     -> MarketAttentionRadar
        -> KrakenAttentionCatalogue
        -> CandleStreamService
```

Cette couche est responsable uniquement du scope runtime, de la normalisation `TRENDING` et de la projection API v4 avec directions.

## Scope

`MarketScope` contient :

```text
SPOT
PERPETUAL
ALL
```

`ALL` est la valeur par défaut.

Le catalogue complet reste en cache dans le Radar canonique. La méthode `_catalogue_if_due(...)` de la couche v4 retourne uniquement la population compatible avec le scope au cycle courant ; `_next_scan_batch(...)` reçoit donc déjà une population filtrée.

Les anciens snapshots peuvent rester physiquement en cache. `_fresh_activities(...)` filtre systématiquement selon le scope avant toute statistique, liquidité, diagnostic ou shortlist.

## Changement runtime

Endpoint :

```text
PUT /api/v1/market-attention/scope
```

Payload :

```json
{"market_scope":"SPOT"}
```

Le changement est sérialisé par un verrou v4 couvrant le refresh OHLCV + microstructure complet, masque immédiatement l'ancien `latest` v4 par un snapshot vide `PARTIAL`, puis déclenche un refresh. La réponse contient le scope réellement actif.

## Microstructure

- `SPOT` : microstructure Batch 40 disponible selon les limites/caches existants ;
- `PERPETUAL` : aucun sous-scan microstructure, cache micro exposé vide, `NOT_APPLICABLE` ;
- `ALL` : seuls les marchés SPOT sont enrichis.

## Direction par horizon

Source unique des seuils : `_MATERIAL_RETURN` existant.

| Horizon | Seuil matériel |
| --- | ---: |
| 5m | 0,30 % |
| 15m | 0,50 % |
| 1h | 1,00 % |
| 4h | 2,00 % |

Règles :

- `price_return >= +seuil` => `UP` ;
- `price_return <= -seuil` => `DOWN` ;
- entre les deux bornes => `NEUTRAL` ;
- horizon incomplet, rendement absent/non fini ou seuil inconnu => `UNKNOWN`.

Les bornes sont inclusives : exactement `+seuil` est `UP`, exactement `-seuil` est `DOWN`.

## Direction globale

La synthèse ne moyenne pas les rendements :

- moins de deux horizons exploitables => `UNKNOWN` ;
- présence simultanée d'au moins un `UP` matériel et un `DOWN` matériel => `MIXED` ;
- au moins deux `UP` et aucun `DOWN` => `UP` ;
- au moins deux `DOWN` et aucun `UP` => `DOWN` ;
- aucun mouvement matériel et au moins deux horizons exploitables => `NEUTRAL` ;
- un seul mouvement matériel isolé, sans consensus multi-timeframe => `UNKNOWN`.

## Relation avec TRENDING

Après le calcul structurel existant, `TRENDING` est normalisé avec la synthèse ci-dessus :

```text
global = UP ou DOWN -> TRENDING présent
global = MIXED / NEUTRAL / UNKNOWN -> TRENDING absent
```

Le niveau d'intérêt et ses raisons sont ensuite recalculés via `_interest_level_and_reasons(...)` existant.

## Causalité

La direction v4 se base uniquement sur les horizons produits par `MarketActivityAnalyzer`. Le filtre canonique reste :

```text
is_final == True
close_time <= observed_at
```

Aucun nouveau chemin candle, aucune donnée future et aucun look-ahead ne sont introduits.

## Contrat API v4

Ajouts :

```text
market_scope
market_activity.trend_direction
market_activity.horizons[].trend_direction
```

Le frontend et le backend utilisent ensemble `market-attention-radar-v4`.

## UX

Le cockpit affiche :

```text
Marché analysé
[ SPOT ] [ PERP ] [ TOUS ]
```

Chaque ligne de shortlist rend immédiatement visible la tendance globale. Le détail OHLCV affiche la direction de chaque timeframe en plus de la variation numérique.

Labels :

```text
UP      -> Haussière ↑
DOWN    -> Baissière ↓
NEUTRAL -> Neutre →
MIXED   -> Mixte ↕
UNKNOWN -> Indéterminée
```

## Hors périmètre

Pas de filtre directionnel stratégique, pas de décision automatique, pas de BUY/SELL/HOLD, pas de transmission à l'Agent, pas d'ordre Kraken, pas de short/levier/margin, pas de nouvelle microstructure dérivés, pas de RSI/MACD/EMA ajouté pour décoration.
