# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel       : 2a368c76f30373a6b9003324a1a14d8192cc0ad8
Commit                 : docs: mark batch 40 as integrated
Batch 39               : intégré
Batch 40               : intégré
Batch 41               : patch proposé, non intégré
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

## État intégré jusqu'au Batch 40

Les Batches 28 à 35 ont construit et durci Market Attention. Le Batch 36 a amélioré la terminologie financière. Le Batch 37 a aligné la cadence stratégique sur les clôtures de bougies. Le Batch 38 a ajouté le préfiltrage Kraken et les caractéristiques structurelles. Le Batch 39 a supprimé la couche Web/IA du Radar. Le Batch 40 a ajouté la microstructure Kraken SPOT et le contrat Radar v3.

## Batch 41 — scope de marché et direction de tendance

**État : patch proposé localement, non intégré.**

Objectifs :

- sélectionner `SPOT`, `PERPETUAL` ou `ALL` avant le scan ;
- conserver `ALL` par défaut ;
- empêcher toute fuite de cache ou compteur hors scope ;
- conserver la microstructure SPOT uniquement ;
- exposer `UP / DOWN / NEUTRAL / MIXED / UNKNOWN` par horizon et globalement ;
- faire dériver `TRENDING` de la même synthèse ;
- exposer le contrat `market-attention-radar-v4` et le contrôle cockpit associé.

## Périmètres ultérieurs possibles

- filtre d'affichage ou de recherche par direction, dans un batch séparé ;
- métriques de retard `scheduled_close -> cycle_start` ;
- cadence stratégique adaptée aux positions ouvertes ;
- éventuelle utilisation explicite de données Radar comme contexte Agent, uniquement après décision architecturale ;
- LIVE, séparé et ultérieur.

Aucun ranking déterministe stratégique, quota de trades ou promesse de rendement ne doit être introduit silencieusement.
