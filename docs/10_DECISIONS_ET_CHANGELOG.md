# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les éléments nécessaires à la reprise.

## Principes actifs

Un seul Agent stratégique, Risk autorité finale, aucune sortie LLM directe vers Broker/Kraken, SPOT sans vente d'actif non détenu, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Market Attention Radar reste strictement observationnel et ne prend aucune décision de trading.

## Référence courante

```text
HEAD GitHub audité : 2a368c76f30373a6b9003324a1a14d8192cc0ad8
Commit              : docs: mark batch 40 as integrated
Batch 40            : intégré
Batch 41            : patch proposé, non intégré
```

## Changelog — 2026-10-01 — Batch 41 Scope et tendance

- ajout d'un scope runtime `SPOT / PERPETUAL / ALL`, `ALL` par défaut ;
- filtrage avant rotation et scan OHLCV ;
- caches frais, compteurs, liquidité, diagnostics et shortlist filtrés au scope ;
- nouvel endpoint `PUT /api/v1/market-attention/scope` ;
- ajout de `UP / DOWN / NEUTRAL / MIXED / UNKNOWN` par horizon ;
- ajout d'une synthèse globale multi-timeframe ;
- `TRENDING` dérivé de la même synthèse directionnelle ;
- microstructure explicitement neutralisée en scope `PERPETUAL` ;
- contrat public proposé `market-attention-radar-v4` ;
- cockpit piloté par le scope backend et affichage de tendance global/détaillé ;
- aucune modification Agent/Risk/Broker et aucune exécution dérivée du Radar.

## ADR-304 — Scope runtime comme couche au-dessus du Radar canonique

**PROPOSÉ Batch 41.**

Le scope n'est pas un nouveau `MarketType`. `MarketType` reste le type canonique d'un marché ; `MarketScope` représente uniquement la sélection utilisateur `SPOT / PERPETUAL / ALL`.

La couche `ScopedTrendMarketAttentionRadar` hérite du Radar microstructure existant et filtre la population retournée par le catalogue avant `_next_scan_batch`. Aucun second catalogue ou pipeline candles n'est créé.

## ADR-305 — Cache conservé physiquement, filtré logiquement

**PROPOSÉ Batch 41.**

Un changement de scope ne purge pas obligatoirement les snapshots d'une famille exclue. En revanche, `_fresh_activities` et les sorties v4 ne laissent jamais ces snapshots participer au calcul courant. Cela permet un retour à `ALL` sans réintroduire de données hors scope dans le snapshot actif.

## ADR-306 — Synthèse directionnelle unique

**PROPOSÉ Batch 41.**

Les seuils `_MATERIAL_RETURN` existants déterminent la direction de chaque horizon. La synthèse globale gère explicitement l'alignement, les conflits et l'insuffisance de preuve. `TRENDING` est ensuite ajouté uniquement pour `UP` ou `DOWN`, puis l'intérêt est recalculé avec la fonction canonique existante.

## ADR-307 — Contrat Radar v4

**PROPOSÉ Batch 41.**

L'ajout d'un état runtime global et de champs directionnels imbriqués est considéré comme une évolution significative du schéma public. Backend et frontend passent donc ensemble à `market-attention-radar-v4`.

## ADR-308 — Microstructure toujours SPOT uniquement

**RÉAFFIRMÉ Batch 41.**

En scope `PERPETUAL`, aucun sous-scan `/Depth` ou `/Trades` n'est déclenché et le cache microstructure exposé est vide. Les marchés PERPETUAL sont représentés avec `NOT_APPLICABLE`.

## Points explicitement non décidés

- utilisation du Radar comme contexte de l'Agent stratégique ;
- filtre de shortlist par direction ;
- réaction stratégique intra-bougie ;
- streaming WebSocket L2/trades ;
- LIVE.
