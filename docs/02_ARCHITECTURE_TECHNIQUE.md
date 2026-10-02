# 02 — Architecture technique

## 1. Référence

```text
Repository            : Ax-07/AI-Spot-Trader
Branche               : main
HEAD GitHub audité    : f5de73270c23c6c4e2a6114ac78b3e57c17c65b1
Batch 41              : intégré
Batch 42              : intégré
Batch 43              : patch proposé, non intégré
Contrat Radar v4      : intégré — market-attention-radar-v4
Contrat Radar v5      : intégré — market-attention-radar-v5
Contrat Radar v6      : proposé — market-attention-radar-v6
```

## 2. Architecture générale

```text
Next.js cockpit
  -> FastAPI
     -> Control Plane / runtime PAPER
        -> CandleStreamService partagé
        -> Agent IA stratégique unique
        -> Risk Engine déterministe
        -> Paper Broker / Portfolio

     -> FilteredStructuredMarketAttentionRadar (v6, observation uniquement)
        -> StructuredMarketAttentionRadar (v5)
           -> ScopedTrendMarketAttentionRadar (v4)
              -> MicrostructureMarketAttentionRadar (v3)
                 -> MarketAttentionRadar canonique
                    -> catalogue Kraken
                    -> CandleStreamService partagé / OHLCV 5m canonique
                 -> couche microstructure SPOT
                    -> GET /0/public/Depth
                    -> GET /0/public/Trades
              -> scope runtime SPOT / PERPETUAL / ALL
              -> direction récente déterministe multi-timeframe
           -> MarketStructureAnalyzer
              -> CandleStreamService.history_as_of(...)
              -> CandleKey(market, 5m / 15m / 1h / 4h)
              -> pivots confirmés / HH HL LH LL
              -> BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN
        -> MarketMetadataProvider
           -> CoinPaprika GET /v1/tickers?quotes=USD
           -> cache long / fail-soft / aucun secret
        -> filtres runtime volume 24h + market cap
        -> API /api/v1/market-attention
        -> zéro OpenAI / zéro recherche Web
        -> aucun lien vers Agent / Market Discovery / Risk / Broker
```

Le frontend n'appartient jamais à la chaîne d'exécution.

## 3. Scope avant scan

`ScopedTrendMarketAttentionRadar` conserve en mémoire le catalogue complet fourni par le composant canonique, mais retourne au cycle de scan uniquement la population compatible avec `market_scope` :

```text
catalogue complet
-> filtre scope
-> filtre market cap Batch 43
-> _next_scan_batch / scan_limit
-> CandleStreamService
-> filtre volume 24h Batch 43
-> microstructure / shortlist / Market Structure
```

Le scope vaut `ALL` par défaut. Les curseurs de rotation par famille existants sont conservés. La Market Structure n'analyse que les éléments présents dans la shortlist déjà produite après filtrage ; aucun marché exclu n'est réintroduit.

## 4. Caches et compteurs

Les snapshots peuvent rester physiquement dans les caches historiques, mais `_fresh_activities(...)` filtre toujours selon le scope courant et, avec le Batch 43, selon les filtres capitalisation/volume actifs. Les compteurs, la classification de liquidité, les diagnostics et la shortlist sont donc construits uniquement sur la population active.

Le `catalogue_market_count` reflète la population éligible après scope et filtre de capitalisation. Le filtre volume intervient après la disponibilité OHLCV ; `cached_activity_market_count` reflète donc la population restante après ce filtre.

## 5. Changement runtime

La route historique reste disponible :

```http
PUT /api/v1/market-attention/scope
```

Le Batch 43 ajoute :

```http
GET /api/v1/market-attention/filters
PUT /api/v1/market-attention/filters
```

Le payload v6 complet est :

```json
{
  "market_scope": "SPOT",
  "min_volume_24h_usd": "1000000",
  "market_cap_categories": ["MID", "LARGE"],
  "min_market_cap_usd": null,
  "max_market_cap_usd": null
}
```

Le changement est sérialisé par le verrou runtime du Radar. Avant le nouveau refresh, `latest` est invalidé au profit d'un snapshot `PARTIAL` vide correspondant déjà aux nouveaux filtres, afin de ne pas exposer une shortlist de l'ancien état comme si elle correspondait au nouveau.

## 6. Tendance récente Batch 41

Les seuils `_MATERIAL_RETURN` du Radar existant restent la source unique de la tendance récente :

```text
5m  = 0.003
15m = 0.005
1h  = 0.010
4h  = 0.020
```

Par horizon : `UP`, `DOWN`, `NEUTRAL` ou `UNKNOWN`. La synthèse globale peut être `MIXED`. `TRENDING` continue d'être normalisé avec cette synthèse. Le Batch 43 ne modifie aucune de ces règles.

## 7. Historique natif de Market Structure

`StructuredMarketAttentionRadar` ne réutilise pas les agrégations 5m du calcul d'activité pour déduire la structure H1/H4. Pour chaque marché de shortlist et chaque timeframe :

```python
await CandleStreamService.history_as_of(
    CandleKey(symbol=..., market_type=..., timeframe=...),
    as_of=observed_at,
    limit=100,
)
```

La limite est portée par `MarketStructurePolicy.history_limit`, bornée entre 40 et 300, avec 100 par défaut.

Le service candles décide lui-même si le cache causal est suffisant. S'il dispose déjà de la profondeur demandée et de la dernière clôture finalisée attendue, il ne relance pas un backfill inutile.

## 8. Détection causale des pivots

Politique par défaut :

```text
pivot_left_bars       = 2
pivot_right_bars      = 2
min_history_candles   = 20
history_limit         = 100
equality_tolerance_bps= 2
swing_display_limit   = 8
fetch_concurrency     = 8
```

Un pivot d'indice `i` n'est parcouru que lorsque `pivot_right_bars` candles finalisées existent après lui. Son `confirmed_at` est la clôture de la dernière candle de confirmation à droite. Tant que cette clôture n'existe pas, le pivot n'apparaît dans aucune sortie.

Avant analyse, les lignes sont filtrées :

```text
is_final == True
candle.timeframe == timeframe demandé
close_time <= observed_at
updated_at <= observed_at
```

`history_as_of(...)` applique déjà une barrière causale fournisseur/cache ; l'analyseur réapplique une défense locale.

## 9. Classification HH / HL / LH / LL

Chaque nouveau swing high est comparé au swing high précédent :

```text
plus haut -> HH
plus bas  -> LH
```

Chaque nouveau swing low est comparé au swing low précédent :

```text
plus haut -> HL
plus bas  -> LL
```

Une différence absolue inférieure ou égale à `equality_tolerance_bps` reste non directionnelle (`classification=None`) au lieu d'être forcée en HH/LH/HL/LL.

## 10. États structurels

La classification exige une séquence de pivots confirmés :

- deux `HH` récents et deux `HL` récents => `BULLISH` ;
- deux `LH` récents et deux `LL` récents => `BEARISH` ;
- coexistence récente de géométries opposées ou derniers high/low contradictoires => `TRANSITION` ;
- pivots répétés sans direction au-delà de la tolérance => `RANGE` ;
- preuve insuffisante => `UNKNOWN`.

Un `LH` ou `LL` isolé ne suffit pas à déclarer `BEARISH`.

## 11. BOS / CHOCH

Les événements sont descriptifs :

- structure `BULLISH` avec dernier swing high classé `HH` => `BOS_UP` ;
- structure `BEARISH` avec dernier swing low classé `LL` => `BOS_DOWN` ;
- transition issue d'une géométrie haussière vers `LH + LL` => `CHOCH_DOWN` ;
- transition issue d'une géométrie baissière vers `HH + HL` => `CHOCH_UP`.

Ils n'ont aucune autorité stratégique et ne constituent jamais un signal de trading automatique.

## 12. Synthèse multi-timeframe

Les quatre structures individuelles sont conservées. La synthèse ne les écrase jamais :

- moins de deux timeframes connus => `UNKNOWN` ;
- tous les timeframes connus identiques => état correspondant ;
- états connus divergents => `MIXED`.

Cette synthèse reste descriptive.

## 13. Volume 24h Batch 43

Le filtre volume réutilise le cache `CandleStreamService` déjà alimenté par le scan d'activité. Pour un marché SPOT coté directement en USD, le Radar somme sur une fenêtre causale de 24h :

```text
volume_24h_usd = Σ(volume_base_5m × close_5m)
```

Seules les candles finalisées et connues à `observed_at` sont retenues. Le calcul exige également une profondeur de cache antérieure au début de la fenêtre de 24h.

Aucun taux FX implicite n'est introduit. Les marchés dont le notionnel USD ne peut pas être prouvé restent `UNKNOWN`. Lorsqu'un seuil `min_volume_24h_usd` est actif, `UNKNOWN` est exclu (fail-closed).

Le filtre volume intervient après OHLCV mais **avant** :

```text
microstructure L2/trades
Market Structure 5m/15m/1h/4h
```

## 14. Capitalisation Batch 43

Une vraie capitalisation requiert la supply circulante ; Kraken ne constitue donc pas la source de cette métadonnée. La v6 introduit l'interface `MarketMetadataProvider` et l'implémentation initiale `CoinPaprikaMarketMetadataProvider`.

Une seule lecture agrégée `/v1/tickers?quotes=USD` alimente un cache long (6h par défaut). Aucun appel n'est réalisé par candle ou par cycle stratégique IA. Aucun secret n'est nécessaire.

Le mapping est basé sur l'actif de base canonique du marché Kraken. Si plusieurs actifs externes partagent le même symbole, le provider retient déterministement la meilleure position de classement puis la plus grande capitalisation en cas d'égalité.

Données descriptives exposées :

```text
market_cap_usd
market_cap_category
market_cap_rank
circulating_supply
market_cap_provider
market_cap_observed_at
```

Catégories centralisées :

```text
MICRO  < 100 M$
SMALL  100 M$ à < 1 Md$
MID    1 Md$ à < 10 Md$
LARGE  >= 10 Md$
```

## 15. Performance réseau

L'ordre logique est désormais :

```text
catalogue Kraken
-> scope
-> market cap metadata/filter
-> rotation + OHLCV
-> volume 24h/filter
-> shortlist descriptive
-> microstructure SPOT applicable
-> Market Structure uniquement sur shortlist finale
```

La Market Structure conserve son maximum nominal de 40 lectures `history_as_of` pour 10 candidats × 4 timeframes, mais les filtres Batch 43 réduisent en amont le nombre de marchés pouvant atteindre cette étape.

## 16. Contrat API et compatibilité

`market-attention-radar-v6` conserve tous les champs v5 et ajoute :

```text
filters
market_cap_metadata_status
market_cap_metadata_provider
shortlist[].volume_24h_usd
shortlist[].market_cap_*
```

Les routes continuent d'accepter et sérialiser les modèles v4/v5 injectés dans les tests/intégrations existants. `/scope` reste compatible ; `/filters` devient le contrat complet pour le cockpit Batch 43.

## 17. Cockpit

Le cockpit affiche désormais trois groupes de contrôles pilotés par le backend :

```text
Marché         SPOT / PERP / TOUS
Volume 24h     Tous / >100k / >500k / >1M / >5M / >10M
Capitalisation Toutes / Micro / Small / Mid / Large
```

Les catégories de capitalisation sont combinables. Les lignes candidates peuvent afficher le volume 24h et la capitalisation ; le détail expose provider, rang et catégorie.

## 18. Isolation

Le Radar reste `informative_only=True`. Les données de prix, OHLCV, tendance, structure et microstructure proviennent de Kraken. La market cap est une métadonnée externe read-only et n'a aucune autorité stratégique.

Aucun module Batch 43 n'importe Agent, Risk ou Broker. Le Radar peut observer `SPOT / PERPETUAL / ALL`, mais l'exécution du projet reste SPOT.
