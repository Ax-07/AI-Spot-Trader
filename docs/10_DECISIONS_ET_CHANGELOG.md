# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les éléments nécessaires à la reprise.

## Principes actifs

Un seul Agent stratégique, Risk autorité finale, aucune sortie LLM directe vers Broker/Kraken, SPOT sans vente d'actif non détenu, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Market Attention Radar reste strictement observationnel et ne prend aucune décision de trading.

## Référence courante

```text
HEAD GitHub audité : 003dae8dbfdc052edbad5bfde2c23fa24852eace
Commit              : feat: add multi-timeframe market structure
Batch 41            : intégré
Batch 42            : intégré
```

## Changelog — 2026-10-01 — Batch 42 Market Structure multi-timeframe — intégré

Commit intégré : `003dae8dbfdc052edbad5bfde2c23fa24852eace`.

- ajout de `MarketStructureAnalyzer`, déterministe et causal ;
- politique bornée : 100 candles par timeframe par défaut, pivots `2 + 2`, tolérance 2 bps ;
- lecture native Kraken `5m / 15m / 1h / 4h` via `CandleStreamService.history_as_of` ;
- classification `HH / HL / LH / LL` ;
- états `BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN` ;
- événements descriptifs `BOS_UP / BOS_DOWN / CHOCH_UP / CHOCH_DOWN` ;
- synthèse multi-timeframe avec état global `MIXED` lorsque les structures divergent ;
- enrichissement uniquement après constitution de la shortlist scope-éligible ;
- contrat public intégré `market-attention-radar-v5` avec compatibilité v4 des routes ;
- cockpit enrichi sans masquer les métriques Batch 40/41 ;
- aucune modification Agent/Risk/Broker et aucune exécution dérivée de la structure ;
- validations locales avant push : backend `pytest -q` PASS complet, frontend `pnpm test` 54/54 PASS, `pnpm typecheck` PASS.

## Changelog — 2026-10-01 — Batch 41 Scope et tendance — intégré

Commit intégré : `e65940b4c773f0de329648f5f3bb1f8960faa696`.

- ajout d'un scope runtime `SPOT / PERPETUAL / ALL`, `ALL` par défaut ;
- filtrage avant rotation et scan OHLCV ;
- caches frais, compteurs, liquidité, diagnostics et shortlist filtrés au scope ;
- endpoint `PUT /api/v1/market-attention/scope` ;
- ajout de `UP / DOWN / NEUTRAL / MIXED / UNKNOWN` par horizon ;
- ajout d'une synthèse globale multi-timeframe ;
- `TRENDING` dérivé de la même synthèse directionnelle ;
- microstructure explicitement neutralisée en scope `PERPETUAL` ;
- contrat public `market-attention-radar-v4` ;
- cockpit piloté par le scope backend et affichage de tendance global/détaillé.

## ADR-304 — Scope runtime comme couche au-dessus du Radar canonique

**ADOPTÉ — Batch 41 intégré.**

Le scope n'est pas un nouveau `MarketType`. `MarketType` reste le type canonique d'un marché ; `MarketScope` représente uniquement la sélection utilisateur `SPOT / PERPETUAL / ALL`.

La couche `ScopedTrendMarketAttentionRadar` hérite du Radar microstructure existant et filtre la population retournée par le catalogue avant `_next_scan_batch`. Aucun second catalogue ou pipeline candles n'est créé.

## ADR-305 — Cache conservé physiquement, filtré logiquement

**ADOPTÉ — Batch 41 intégré.**

Un changement de scope ne purge pas obligatoirement les snapshots d'une famille exclue. En revanche, `_fresh_activities` et les sorties v4 ne laissent jamais ces snapshots participer au calcul courant. Cela permet un retour à `ALL` sans réintroduire de données hors scope dans le snapshot actif.

## ADR-306 — Synthèse directionnelle unique

**ADOPTÉ — Batch 41 intégré.**

Les seuils `_MATERIAL_RETURN` existants déterminent la direction de chaque horizon. La synthèse globale gère explicitement l'alignement, les conflits et l'insuffisance de preuve. `TRENDING` est ensuite ajouté uniquement pour `UP` ou `DOWN`, puis l'intérêt est recalculé avec la fonction canonique existante.

## ADR-307 — Contrat Radar v4

**ADOPTÉ — Batch 41 intégré.**

L'ajout d'un état runtime global et de champs directionnels imbriqués est une évolution significative du schéma public. Backend et frontend utilisent `market-attention-radar-v4` pour cette couche.

## ADR-308 — Microstructure toujours SPOT uniquement

**RÉAFFIRMÉ — Batch 41 intégré.**

En scope `PERPETUAL`, aucun sous-scan `/Depth` ou `/Trades` n'est déclenché et le cache microstructure exposé est vide. Les marchés PERPETUAL sont représentés avec `NOT_APPLICABLE`.

## ADR-309 — Market Structure basée sur les timeframes Kraken natifs

**ADOPTÉ — Batch 42 intégré.**

La structure H1/H4 ne doit pas être reconstruite arbitrairement depuis les candles 5m. `StructuredMarketAttentionRadar` demande chaque timeframe directement à `CandleStreamService.history_as_of(CandleKey(...))`, ce qui conserve la causalité et le cache canonique.

## ADR-310 — Confirmation causale des pivots

**ADOPTÉ — Batch 42 intégré.**

Un swing n'est confirmé qu'après clôture de `pivot_right_bars` candles postérieures. Les candles futures/non finalisées sont exclues, et `confirmed_at` enregistre la clôture qui rend le pivot connaissable. Les quasi-égalités ne sont pas forcées en HH/LH/HL/LL.

## ADR-311 — Structure enrichie après shortlist

**ADOPTÉ — Batch 42 intégré.**

La structure n'est pas utilisée pour décider quels marchés entrent dans la shortlist. Elle enrichit uniquement les candidats déjà déterminés par le Radar v4. Cela borne le coût réseau et empêche la Market Structure de devenir silencieusement un ranking stratégique.

## ADR-312 — Contrat Radar v5 compatible v4

**ADOPTÉ — Batch 42 intégré.**

Les snapshots enrichis exposent `market-attention-radar-v5` et `market_structure`. Les routes continuent d'accepter explicitement les objets v4 afin de conserver la compatibilité des tests/services Batch 41 injectés.

## Points explicitement non décidés

- utilisation du Radar ou de la Market Structure comme contexte de l'Agent stratégique ;
- filtre de shortlist par direction ou structure ;
- réaction stratégique intra-bougie ;
- streaming WebSocket L2/trades ;
- LIVE.
