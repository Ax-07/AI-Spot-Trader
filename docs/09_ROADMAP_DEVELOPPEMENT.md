# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel       : 003dae8dbfdc052edbad5bfde2c23fa24852eace
Commit                 : feat: add multi-timeframe market structure
Batch 39               : intégré
Batch 40               : intégré
Batch 41               : intégré
Batch 42               : intégré
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

## État intégré jusqu'au Batch 42

Les Batches 28 à 35 ont construit et durci Market Attention. Le Batch 36 a amélioré la terminologie financière. Le Batch 37 a aligné la cadence stratégique sur les clôtures de bougies. Le Batch 38 a ajouté le préfiltrage Kraken et des caractéristiques descriptives. Le Batch 39 a supprimé la couche Web/IA du Radar. Le Batch 40 a ajouté la microstructure Kraken SPOT et le contrat Radar v3. Le Batch 41, intégré à `e65940b4...`, a ajouté le scope `SPOT / PERPETUAL / ALL`, les directions récentes par horizon et le contrat Radar v4. Le Batch 42, intégré à `003dae8d...`, ajoute la Market Structure multi-timeframe et le contrat Radar v5.

## Batch 42 — Market Structure multi-timeframe

**État : intégré sur `main` au commit `003dae8dbfdc052edbad5bfde2c23fa24852eace`.**

Éléments intégrés :

- lecture directe `5m / 15m / 1h / 4h` via `CandleStreamService.history_as_of` ;
- analyse de 100 candles finalisées par timeframe par défaut, avec politique bornée ;
- confirmation causale des pivots avec fenêtre droite explicite ;
- classification des swing highs/lows `HH / HL / LH / LL` ;
- états `BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN` ;
- événements descriptifs `BOS / CHOCH` lorsqu'ils sont confirmés ;
- synthèse multi-timeframe descriptive, pouvant être `MIXED` ;
- calcul uniquement sur la shortlist déjà filtrée par scope ;
- affichage cockpit sans masquer tendance récente, prix, volume, volatilité, liquidité ou microstructure ;
- séparation totale avec Agent/Risk/Broker.

`recent_trend` et `market_structure` restent deux notions indépendantes : la première décrit la direction récente, la seconde la géométrie des swings confirmés.

Le Radar demeure déterministe, Kraken-only et `informative_only=True`. Un `BOS` ou `CHOCH` n'est jamais un signal de trading automatique. Le scope d'observation `SPOT / PERPETUAL / ALL` ne modifie pas l'invariant d'exécution SPOT du projet.

## Validation Batch 42

Avant le push, l'utilisateur a validé localement :

```text
backend pytest -q       : PASS complet — 100 %
frontend pnpm test      : 54/54 PASS
frontend pnpm typecheck : PASS
```

Ces validations sont celles réalisées avant intégration ; elles ne sont pas réattribuées à la clôture documentaire.

## Périmètres ultérieurs possibles

- filtres d'affichage explicites par structure/tendance, dans un batch séparé ;
- métriques de retard `scheduled_close -> cycle_start` ;
- cadence stratégique adaptée aux positions ouvertes ;
- éventuelle utilisation explicite de données Radar comme contexte Agent, uniquement après décision architecturale ;
- LIVE, séparé et ultérieur.

Aucun ranking déterministe stratégique, quota de trades ou promesse de rendement ne doit être introduit silencieusement.
