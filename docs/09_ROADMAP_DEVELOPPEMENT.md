# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel          : 2aaff09b01300008e63eaadbca242817bcb4ce28
Commit                    : docs: mark batch 39 as integrated
Batch 39                  : intégré
Batch 40                  : patch proposé/local non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve un seul Agent IA stratégique, Kraken comme exchange initial, Risk Engine comme autorité finale, backend indépendant du frontend, mode PAPER avant tout LIVE, aucune sortie LLM directement exécutable et Market Attention strictement informatif.

## Cadences distinctes

1. monitoring / mark-to-market : déterministe ;
2. cycle stratégique IA : `INTERVAL` ou `CANDLE_CLOSE` ;
3. Market Discovery : cadence distincte ;
4. streaming/caches marché : technique et déterministe ;
5. Market Attention Radar : observation déterministe Kraken, avec cadence microstructure bornée distincte.

## État intégré jusqu'au Batch 39

Les Batches 28 à 35 ont construit et durci Market Attention. Le Batch 36 a amélioré la terminologie financière. Le Batch 37 a aligné la cadence stratégique sur les clôtures de bougies. Le Batch 38 a ajouté le préfiltrage Kraken et les caractéristiques structurelles. Le Batch 39, intégré dans `5bff583` puis marqué intégré par `2aaff09`, a supprimé la couche Web/IA du Radar.

## Batch 40 — microstructure Kraken

**État : patch proposé.**

Objectif : enrichir le Radar avec trades publics SPOT récents et carnet L2 Kraken, puis calculer spread, profondeur, déséquilibre, intensité, pression fournisseur descriptive et slippage théorique, sans ordre et sans IA/Web.

Architecture proposée :

```text
OHLCV Batch 39
+
Depth/Trades Kraken SPOT bornés
=
Market Attention Radar v3
```

Invariants : cache court, sous-scan SPOT rotatif, fail-soft, aucune nouvelle clé privée, PERPETUAL historique non étendu, isolation Agent/Risk/Broker et `informative_only=True`.

## Périmètres ultérieurs possibles

- métriques de retard `scheduled_close -> cycle_start` ;
- cadence stratégique adaptée aux positions ouvertes ;
- éventuelle utilisation explicite de données Radar comme contexte Agent, uniquement après décision architecturale ;
- LIVE, séparé et ultérieur.

Aucun ranking déterministe stratégique, quota de trades ou promesse de rendement ne doit être introduit silencieusement.
