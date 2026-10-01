# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est un cockpit de contrôle et de visualisation qui peut être fermé sans arrêter le moteur.

Référence GitHub auditée au lancement du Batch 40 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 2aaff09b01300008e63eaadbca242817bcb4ce28
Commit     : docs: mark batch 39 as integrated
```

Le Batch 39 est intégré. Le Batch 40 reste un patch local tant qu'il n'a pas été validé puis intégré par l'utilisateur.

## 2. Invariants fonctionnels

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- premières versions en PAPER ;
- SPOT comme invariant d'exécution cible ;
- actions stratégiques `BUY`, `SELL`, `HOLD` ;
- Luna par défaut pour les premiers tests, Sol sélectionnable par configuration ;
- Risk Engine déterministe comme autorité finale ;
- aucune sortie LLM directement transmise au Broker/Kraken ;
- frais, spread et slippage pris en compte dans la chaîne d'exécution concernée ;
- décisions, `HOLD`, sélections, évaluations Risk et exécutions auditables ;
- aucun look-ahead ;
- aucun secret dans prompts, logs, frontend ou fichiers versionnés ;
- frontend non nécessaire au fonctionnement du moteur ;
- Market Attention strictement informatif.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

La cible expérimentale `+4 %/jour` reste un objectif de recherche non garanti, jamais une promesse de rendement.

## 3. Persistance et sessions

`Session` reste une façade sur les objets canoniques :

```text
Session UX
-> Strategy
-> StrategyRevision(s)
-> Campaign(s) immuables
-> paper_run(s)
```

Une modification de configuration crée un nouveau snapshot Campaign sans réécrire l'historique.

## 4. Market Discovery

Market Discovery et Market Attention sont deux frontières distinctes. Market Discovery prépare l'univers stratégique ; Market Attention observe l'activité Kraken. Une shortlist Radar n'est ni une watchlist d'exécution, ni un signal de trading.

## 5. Multi-timeframes stratégiques

Le mapping canonique `trading-style-map-v1` reste :

- SCALP : `1m`, `5m`, `15m`, `30m` ;
- SWING : `1h`, `4h`, `1d`.

`StrategicMultiTimeframeContextService` réutilise le `CandleStreamService` partagé. `history_as_of(...)` protège la causalité et empêche tout look-ahead.

## 6. Cycle stratégique

Un cycle produit un plan ordonné et borné via l'Agent stratégique unique :

```text
contexte causal
-> Agent IA unique
-> plan [D1, D2, ... Dn]
-> chaque décision : Risk -> exécution éventuelle -> portefeuille courant
```

`HOLD` et `REJECT` ne sont pas des erreurs techniques.

## 7. Cadences distinctes

L'application distingue le monitoring déterministe, la cadence du cycle stratégique IA, Market Discovery, le streaming/cache candles et le Market Attention Radar. Le Radar Batch 40 conserve une cadence propre et un cache microstructure court ; il n'impose jamais la cadence de l'Agent.

## 8. Transparence des appels IA

Les appels de l'Agent stratégique et, lorsqu'elle existe, la logique IA de Market Discovery doivent rester distinguables. **Le Market Attention Radar v3 ne produit aucun appel IA ni aucune recherche Web.**

## 9. Risk, coûts et exécution

Le Radar ne modifie ni Risk, ni Broker. Le slippage Batch 40 est une **simulation théorique read-only** obtenue en parcourant le snapshot L2 ; aucun ordre réel ou PAPER n'est construit.

## 10. Market Attention Radar v3 — Kraken déterministe

```text
Kraken
├── catalogue
├── CandleStreamService / OHLCV 5m canonique finalisé
├── trades SPOT récents REST bornés
└── carnet SPOT L2 REST borné
        ↓
facts 5m / 15m / 1h / 4h + microstructure
        ↓
caractéristiques déterministes
        ↓
intérêt LOW / MEDIUM / HIGH / VERY_HIGH
        ↓
shortlist diversifiée
        ↓
API/cockpit read-only
```

Les caractéristiques OHLCV du Batch 39 sont conservées. Le Batch 40 ajoute, uniquement lorsqu'elles sont supportées par les données, des caractéristiques descriptives de spread, profondeur, déséquilibre, activité des trades, pression fournisseur et risque de slippage.

## 11. Contrat API Radar

Le protocole proposé est `market-attention-radar-v3`. Il ajoute au contrat v2 : état/qualité/fraîcheur microstructure, spread, profondeur base/quote, profondeur par bandes, déséquilibre L2, métriques de trades récents et slippage théorique par taille notionnelle en devise cotée.

`informative_only=True` reste validé côté backend.

## 12. Isolation architecturale

Le module Radar ne dépend pas d'Agent, Risk, Broker ou Market Discovery. L'Agent stratégique reste le seul agent IA de l'application. Le Batch 40 réutilise le calcul OHLCV du Batch 39 et n'introduit aucun second pipeline candles.

## 13. Bornage microstructure

Par défaut : carnet L2 limité à 100 niveaux par côté, trades récents limités à 1 000 lignes, 24 marchés SPOT microstructure par refresh, concurrence 4, refresh 300 s, cache 900 s. Ces valeurs sont centralisées dans `MicrostructurePolicy`.

Les tailles de slippage `100 / 500 / 1 000 / 5 000` sont exprimées dans la **devise cotée** du marché ; pour `*/USD`, elles correspondent exactement à des USD. Aucun FX implicite n'est créé.

## 14. Hors périmètre du Batch 40

Décision stratégique automatique par carnet, déclenchement intra-bougie de l'Agent, smart order routing, exécution VWAP/TWAP réelle, market making, arbitrage, LIVE, clés privées Kraken supplémentaires, refonte Risk et Rust restent hors périmètre.
