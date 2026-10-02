# 02 — Architecture technique

## 1. Référence

```text
Repository            : Ax-07/AI-Spot-Trader
Branche               : main
HEAD GitHub audité    : 003dae8dbfdc052edbad5bfde2c23fa24852eace
Batch 41              : intégré
Batch 42              : intégré
Contrat Radar v4      : intégré — market-attention-radar-v4
Contrat Radar v5      : intégré — market-attention-radar-v5
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

     -> StructuredMarketAttentionRadar (v5, observation uniquement)
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
-> _next_scan_batch / scan_limit
-> CandleStreamService
```

Le scope vaut `ALL` par défaut. Les curseurs de rotation par famille existants sont conservés. Le Batch 42 n'analyse la structure que des éléments présents dans la shortlist déjà produite après ce filtrage ; aucun marché hors scope n'est réintroduit.

## 4. Caches et compteurs

Les snapshots peuvent rester physiquement dans les caches historiques, mais `_fresh_activities(...)` filtre toujours selon le scope courant. Les compteurs, la classification de liquidité, les diagnostics et la shortlist sont donc construits uniquement sur la population active.

Le `catalogue_market_count` est recalculé sur la population éligible du scope, y compris après un changement runtime.

## 5. Changement runtime

`PUT /api/v1/market-attention/scope` reçoit :

```json
{"market_scope":"SPOT"}
```

Le service sérialise le changement avec le verrou v4 existant, rafraîchit la population cohérente du scope puis, pour le Radar v5, enrichit la shortlist résultante avec la Market Structure. Le frontend utilise uniquement `market_scope` renvoyé par le backend pour afficher l'état actif.

## 6. Tendance récente Batch 41

Les seuils `_MATERIAL_RETURN` du Radar existant restent la source unique de la tendance récente :

```text
5m  = 0.003
15m = 0.005
1h  = 0.010
4h  = 0.020
```

Par horizon : `UP`, `DOWN`, `NEUTRAL` ou `UNKNOWN`. La synthèse globale peut être `MIXED`. `TRENDING` continue d'être normalisé avec cette synthèse. Le Batch 42 ne modifie aucune de ces règles.

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

## 13. Performance réseau

L'enrichissement structurel intervient **après** la sélection de la shortlist et non sur les 120 marchés potentiellement scannés à chaque rotation. Avec les valeurs par défaut :

```text
maximum shortlist : 10 marchés
x 4 timeframes
= 40 lectures history_as_of bornées par refresh
```

Ces lectures passent par le cache canonique. Le sémaphore structure (`fetch_concurrency=8`) borne également la concurrence provider.

## 14. Contrat API et compatibilité

`market-attention-radar-v5` ajoute à chaque entrée de shortlist :

```text
market_structure.observed_at
market_structure.global_state
market_structure.timeframes[]
```

Chaque timeframe expose `state`, `event`, `history_count`, `latest_final_close`, les swing highs/lows confirmés, les swings affichables et la `sequence` HH/HL/LH/LL.

Les routes FastAPI acceptent aussi un `MarketAttentionOverviewV4` injecté. Les tests et consommateurs Batch 41 qui fournissent explicitement un service v4 restent donc sérialisables sans conversion forcée vers v5.

## 15. Cockpit

La ligne principale conserve activité, tendance récente, volume, spread, profondeur L2, déséquilibre, cadence trades et variation de prix. Le détail ajoute :

```text
Structure globale
Structure 5m / 15m / 1h / 4h
Swings HH → HL → ...
Événement BOS/CHOCH éventuel
```

La section OHLCV nomme explicitement `Tendance récente` pour éviter la confusion avec la Market Structure.

## 16. Isolation

Aucun module Batch 42 Market Structure n'importe Agent, Risk, Broker, OpenAI ou outil Web. Le Radar reste read-only vis-à-vis de Kraken et `informative_only=True`.

Le Radar peut observer `SPOT / PERPETUAL / ALL`, mais cette capacité d'observation ne constitue pas une autorisation d'exécuter des trades PERPETUAL. L'exécution du projet reste SPOT.
