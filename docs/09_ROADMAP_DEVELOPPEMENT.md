# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel          : 2776fc68fb0ff8c094148a246d22de844ee868c7
Commit                    : feat: prefilter market attention web research
Batch 38                  : intégré
Batch 39                  : patch proposé/local non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve un seul Agent IA stratégique, Kraken comme exchange initial, Risk Engine comme autorité finale, backend indépendant du frontend, mode PAPER avant tout LIVE, aucune sortie LLM directement exécutable et Market Attention strictement informatif.

## Cadences distinctes

1. monitoring / mark-to-market : déterministe ;
2. cycle stratégique IA : `INTERVAL` ou `CANDLE_CLOSE` ;
3. Market Discovery : cadence distincte ;
4. streaming/caches marché : technique et déterministe ;
5. Market Attention Radar : observation déterministe Kraken.

## État intégré jusqu'au Batch 38

Les Batches 28 à 35 ont construit et durci Market Attention. Le Batch 36 a amélioré la terminologie financière. Le Batch 37 a aligné la cadence stratégique sur les clôtures de bougies. Le Batch 38, intégré dans `2776fc6`, a ajouté le préfiltrage Kraken, les caractéristiques structurelles et `LOW/MEDIUM/HIGH/VERY_HIGH`, tout en conservant encore une couche Web auxiliaire.

## Batch 39 — Radar 100 % Kraken, zéro IA/Web

**État : patch proposé/local non intégré.**

Objectif : supprimer la couche auxiliaire de recherche publique au lieu de seulement en réduire le coût.

```text
Kraken
-> OHLCV 5m canonique finalisé
-> analyse 5m / 15m / 1h / 4h
-> caractéristiques déterministes
-> intérêt déterministe
-> shortlist diversifiée
-> observabilité
```

Décisions :

- suppression du wiring `OpenAIWebAttentionResearcher` du Radar ;
- suppression du cache, TTL, cooldown, budget et décisions de recherche publique ;
- suppression des champs API/UI correspondants ;
- protocole API `market-attention-radar-v2` ;
- maintien de `informative_only=True` ;
- maintien du pipeline OHLC canonique et des calculs sur bougies finalisées ;
- maintien du ranking et de la diversification par régime de liquidité ;
- aucune dépendance Radar vers Agent/Risk/Broker/Discovery ;
- zéro coût token du Radar.

## Batch 40 — microstructure Kraken

Batch dédié, volontairement séparé : trades Kraken, carnet L2, spread, profondeur, déséquilibre bid/ask, intensité des trades et slippage théorique. Ces éléments ne doivent pas être introduits dans Batch 39.

## Périmètres ultérieurs possibles

- métriques de retard `scheduled_close -> cycle_start` ;
- cadence stratégique adaptée aux positions ouvertes ;
- éventuelle utilisation explicite de données Radar comme contexte Agent, uniquement après décision architecturale ;
- LIVE, séparé et ultérieur.

Aucun ranking déterministe stratégique, quota de trades ou promesse de rendement ne doit être introduit silencieusement.
