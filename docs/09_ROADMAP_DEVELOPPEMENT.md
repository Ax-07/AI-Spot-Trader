# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel       : e65940b4c773f0de329648f5f3bb1f8960faa696
Commit                 : feat: add market attention scope and trend direction
Batch 39               : intégré
Batch 40               : intégré
Batch 41               : intégré
Batch 42               : patch proposé, non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve un seul Agent IA stratégique, Kraken comme exchange initial, Risk Engine comme autorité finale, backend indépendant du frontend, mode PAPER avant tout LIVE, aucune sortie LLM directement exécutable et Market Attention strictement informatif.

## Cadences distinctes

1. monitoring / mark-to-market : déterministe ;
2. cycle stratégique IA : `INTERVAL` ou `CANDLE_CLOSE` ;
3. Market Discovery : cadence distincte ;
4. streaming/caches marché : technique et déterministe ;
5. Market Attention Radar : observation déterministe Kraken, avec cadence propre et lectures structurelles bornées.

## État intégré jusqu'au Batch 41

Les Batches 28 à 35 ont construit et durci Market Attention. Le Batch 36 a amélioré la terminologie financière. Le Batch 37 a aligné la cadence stratégique sur les clôtures de bougies. Le Batch 38 a ajouté le préfiltrage Kraken et des caractéristiques descriptives. Le Batch 39 a supprimé la couche Web/IA du Radar. Le Batch 40 a ajouté la microstructure Kraken SPOT et le contrat Radar v3. Le Batch 41, intégré à `e65940b4...`, a ajouté le scope `SPOT / PERPETUAL / ALL`, les directions récentes par horizon et le contrat Radar v4.

## Batch 42 — Market Structure multi-timeframe

**État : patch proposé localement, non intégré.**

Objectifs réalisés dans le patch :

- lire directement `5m / 15m / 1h / 4h` via `CandleStreamService.history_as_of` ;
- analyser environ 100 candles finalisées par timeframe avec une politique bornée ;
- confirmer les pivots causalement avec une fenêtre droite explicite ;
- classer les swing highs/lows `HH / HL / LH / LL` ;
- exposer `BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN` ;
- ajouter des événements descriptifs `BOS / CHOCH` lorsqu'ils sont confirmés ;
- conserver une synthèse multi-timeframe descriptive, pouvant être `MIXED` ;
- ne calculer la structure que sur la shortlist déjà filtrée par scope ;
- exposer la structure dans le cockpit sans masquer tendance récente, prix, volume, volatilité, liquidité ou microstructure ;
- conserver une séparation totale avec Agent/Risk/Broker.

## Validation Batch 42

Le patch contient des tests dédiés pour pivots, classifications, états, causalité, indépendance multi-timeframe, appel `history_as_of` natif et contrat API, ainsi que des tests frontend des labels/structures. Le `pytest` complet du repository et le typecheck Next.js doivent être rejoués dans le checkout utilisateur après extraction.

## Périmètres ultérieurs possibles

- filtres d'affichage explicites par structure/tendance, dans un batch séparé ;
- métriques de retard `scheduled_close -> cycle_start` ;
- cadence stratégique adaptée aux positions ouvertes ;
- éventuelle utilisation explicite de données Radar comme contexte Agent, uniquement après décision architecturale ;
- LIVE, séparé et ultérieur.

Aucun ranking déterministe stratégique, quota de trades ou promesse de rendement ne doit être introduit silencieusement.
