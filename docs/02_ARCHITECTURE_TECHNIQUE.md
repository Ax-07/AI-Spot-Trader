# 02 — Architecture technique

## 1. Référence

```text
Repository            : Ax-07/AI-Spot-Trader
Branche               : main
HEAD GitHub audité    : 2a368c76f30373a6b9003324a1a14d8192cc0ad8
Batch 40              : intégré
Batch 41              : patch proposé, non intégré
Contrat Radar proposé : market-attention-radar-v4
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

     -> ScopedTrendMarketAttentionRadar (v4, observation uniquement)
        -> MicrostructureMarketAttentionRadar (v3)
           -> MarketAttentionRadar canonique
              -> catalogue Kraken
              -> CandleStreamService partagé / OHLCV 5m canoniques
           -> couche microstructure SPOT
              -> GET /0/public/Depth
              -> GET /0/public/Trades
        -> scope runtime SPOT / PERPETUAL / ALL
        -> direction déterministe multi-timeframe
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

Le scope vaut `ALL` par défaut. Les curseurs de rotation par famille existants sont conservés.

## 4. Caches et compteurs

Les snapshots peuvent rester physiquement dans les caches historiques, mais `_fresh_activities(...)` filtre toujours selon le scope courant. Les compteurs, la classification de liquidité, les diagnostics et la shortlist sont donc construits uniquement sur la population active.

Le `catalogue_market_count` v4 est recalculé sur la population éligible du scope, y compris après un changement runtime.

## 5. Changement runtime

`PUT /api/v1/market-attention/scope` reçoit :

```json
{"market_scope":"SPOT"}
```

Le service :

1. sérialise le changement avec un verrou v4 couvrant le refresh OHLCV + microstructure complet ;
2. remplace immédiatement le `latest` v4 par un snapshot `PARTIAL` vide du nouveau scope ;
3. lance un refresh du Radar ;
4. renvoie le nouveau snapshot cohérent.

Le frontend utilise uniquement `market_scope` renvoyé par le backend pour afficher l'état actif.

## 6. Direction de tendance

Les seuils `_MATERIAL_RETURN` du Radar existant restent la source unique :

```text
5m  = 0.003
15m = 0.005
1h  = 0.010
4h  = 0.020
```

Par horizon :

- `UP` : rendement >= seuil ;
- `DOWN` : rendement <= -seuil ;
- `NEUTRAL` : mouvement non matériel ;
- `UNKNOWN` : horizon incomplet, valeur absente/non finie ou timeframe sans seuil.

Synthèse globale :

- moins de deux horizons exploitables => `UNKNOWN` ;
- au moins un `UP` et un `DOWN` matériels => `MIXED` ;
- au moins deux `UP`, aucun `DOWN` => `UP` ;
- au moins deux `DOWN`, aucun `UP` => `DOWN` ;
- zéro mouvement matériel avec données suffisantes => `NEUTRAL` ;
- un seul mouvement matériel isolé => `UNKNOWN`.

## 7. Cohérence TRENDING

Après la classification structurelle v3, la couche v4 normalise uniquement `TRENDING` :

- synthèse `UP` ou `DOWN` => `TRENDING` présent ;
- `MIXED`, `NEUTRAL` ou `UNKNOWN` => `TRENDING` absent.

Le niveau d'intérêt et ses raisons sont ensuite recalculés avec les mêmes fonctions canoniques du Radar. Il n'existe donc pas deux définitions divergentes de la tendance directionnelle.

## 8. Causalité

La direction ne lit pas les candles directement. Elle s'appuie sur les `ActivityHorizonSnapshot` produits par `MarketActivityAnalyzer`, qui ne retient déjà que les candles `is_final == True`, de bon marché/timeframe et `close_time <= observed_at`. Le Batch 41 ne crée aucun nouveau chemin OHLCV et n'ajoute aucun look-ahead.

## 9. Microstructure

Les invariants Batch 40 restent inchangés :

- `SPOT` : microstructure possible ;
- `PERPETUAL` : `NOT_APPLICABLE` ;
- scope `PERPETUAL` : `_next_micro_batch(...)` retourne vide et le cache microstructure visible est vide ;
- scope `ALL` : seuls les marchés SPOT peuvent appeler `/Depth` et `/Trades`.

## 10. Contrat et cockpit

`market-attention-radar-v4` expose `market_scope`, la tendance globale et les tendances par timeframe. Le cockpit affiche `SPOT / PERP / TOUS`, la direction globale dans la ligne principale et chaque direction dans le détail OHLCV, sans masquer les variations numériques.

## 11. Isolation

Aucun module Batch 41 Market Attention n'importe Agent, Risk, Broker, OpenAI ou outil Web. Le Radar reste read-only vis-à-vis de Kraken et `informative_only=True`.
