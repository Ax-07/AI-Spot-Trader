# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les éléments nécessaires à la reprise.

## Principes actifs

Un seul Agent stratégique, Risk Engine autorité finale, aucune sortie LLM directe vers Broker/Kraken, exécution SPOT sans vente d'actif non détenu, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Market Attention Radar reste strictement observationnel et ne prend aucune décision de trading.

## Référence courante

```text
HEAD GitHub observé : 45d41b7
Commit HEAD         : feat: move market structure before radar shortlist
Batch 43.2          : intégré
Batch 44            : intégré
Batch 45            : intégré via 45d41b7
Batch 46            : patch proposé, non intégré
```

## Changelog — 2026-10-04 — Correctif Batch 46.1 compatibilité baseline H4 — proposé

Validation locale de la première livraison Batch 46 : `pytest -q` a révélé 7 échecs de non-régression, tandis que `pnpm typecheck`, `pnpm test` (65/65) et `git diff --check` étaient corrects.

Cause : `baseline_periods = 12` était appliqué comme exigence rigide à chaque horizon. Les fixtures historiques de 404–420 candles M5 ne fournissent que 6 périodes historiques H4 après exclusion de `previous` et `current`, alors qu'elles étaient valides avant Batch 46. H4 devenait `INSUFFICIENT_HISTORY`, le snapshot `PARTIAL`, puis les candidats disparaissaient avant Structure.

Correctif :

- cible statistique par défaut maintenue à `12` périodes ;
- plancher de compatibilité centralisé à `6` périodes ;
- `_horizon()` choisit le plus grand nombre causal de périodes complètes disponible entre le plancher et la cible ;
- avec 720 candles M5 : H4 utilise 12 périodes ;
- avec 420 candles M5 : H4 utilise 6 périodes ;
- sous le plancher : `INSUFFICIENT_HISTORY` reste explicite ;
- `baseline_period_count` continue d'exposer le nombre réellement utilisé ;
- aucune modification du scoring MAD, des filtres, de Structure, des sources volume 24h ou de la liquidité PERP.

Tests Batch 46 ajoutés pour couvrir explicitement les fenêtres 720/420/sous-plancher. La suite backend complète doit être relancée localement après application du correctif.

## ADR-330 — La baseline adaptative distingue cible statistique et plancher de compatibilité

**PROPOSÉ — Correctif Batch 46.1, non intégré.**

`baseline_periods` reste la cible maximale de l'analyse robuste. Le Radar peut utiliser moins de périodes uniquement lorsque l'historique causal disponible est insuffisant pour la cible mais atteint le plancher déterministe de 6 périodes. Cette dégradation est bornée, observable via `baseline_period_count` et ne réintroduit aucune donnée future.

## Changelog — 2026-10-04 — Batch 46 baseline statistique adaptative — patch proposé

Base auditée : GitHub `main` au HEAD `45d41b7`.

- audit confirmé : `MarketActivityAnalyzer` est le composant canonique unique de l'activité ; aucun analyseur parallèle n'est créé ;
- baseline cible d'activité portée de `6` à `12` périodes historiques ; H4 utilise 12 périodes lorsque l'historique le permet et le correctif 46.1 conserve un plancher compatible à 6 périodes ;
- adoption d'une baseline robuste par marché et timeframe : médiane, MAD, dispersion `1.4826 * MAD`, score signé ;
- ajout des méthodes explicites `ROBUST_MAD`, `LEGACY_RATIO_FALLBACK`, `UNAVAILABLE` ;
- aucun score artificiel lorsque `MAD == 0` ; le ratio historique reste diagnostic et fallback déterministe ;
- ajout des scores volume, range et volatilité ainsi que du score volume précédent et du delta de score ;
- `MarketActivityState` utilise le score robuste en priorité et la logique ratio historique uniquement en fallback ;
- seuils adaptatifs centralisés : `2.0`, `3.5 + delta 1.0`, `5.0`, confirmation `1.5`, contraction `-2.0`, divergence volume forte `3.0` ;
- `VOLUME_ANOMALY`, `VOLATILITY_EXPANSION`, `CONSOLIDATING`, les confirmations `BREAKOUT_WATCH` / `REVERSAL_WATCH` et `PRICE_VOLUME_DIVERGENCE` deviennent adaptatifs lorsque le MAD est exploitable ;
- `_MATERIAL_RETURN`, `TrendDirection`, Market Structure, HH/HL/LH/LL, BOS/CHOCH, rotation/cache Structure et filtres Batch 45 ne sont pas modifiés ;
- les tris canoniques réutilisent l'intensité adaptative disponible et restent déterministes ; le ranking Structure reste additif et symétrique hausse/baisse ;
- `SubthresholdActivitySnapshot` conserve `peak_volume_ratio` et ajoute `peak_anomaly_score` / méthode ;
- contrat `market-attention-radar-v6` conservé avec champs additifs ;
- cockpit : détails OHLCV enrichis avec ratio historique, score adaptatif et méthode sans alourdir la ligne principale ;
- aucune modification des sources volume 24h SPOT/PERP ni de la liquidité Batch 44 ; aucune notionnalisation artificielle des chart candles PERP ;
- aucune modification Agent / Risk Engine / Broker et aucune capacité LIVE ou PERP exécutable.

Validations exécutées par ChatGPT sur le patch préparé :

```text
Python py_compile backend ciblé                 : PASS
exécution helpers robustes extraits du code       : PASS
frontend market-attention.test.mjs ciblé       : PASS — 19/19
typecheck TypeScript ciblé market-attention.ts : PASS
parse TypeScript/TSX ciblé cockpit              : PASS
```

Validation locale utilisateur de la première livraison : `pnpm typecheck` PASS, `pnpm test` PASS 65/65, `git diff --check` sans erreur ; `pytest -q` a révélé 7 régressions de shortlist, traitées par le correctif 46.1 ci-dessus. La suite backend complète doit être relancée après application du correctif.

## ADR-328 — L'anomalie d'activité utilise une médiane et un MAD normalisé

**PROPOSÉ — Batch 46, non intégré.**

Formule :

```text
baseline          = median(history)
MAD               = median(abs(x - baseline))
robust_dispersion = 1.4826 * MAD
adaptive_score    = (current - baseline) / robust_dispersion
```

La constante `1.4826` est centralisée et nommée. Elle normalise le MAD sur une échelle comparable à un écart-type sous une référence gaussienne sans abandonner la robustesse médiane.

Le score est signé : positif = expansion par rapport au régime historique du marché/horizon ; négatif = contraction.

Si `MAD == 0`, le Radar ne divise pas par zéro et ne fabrique pas de score extrême. Il bascule explicitement vers `LEGACY_RATIO_FALLBACK` si le ratio est valide, sinon `UNAVAILABLE`.

Les seuils du Batch 46 constituent une policy déterministe expérimentale et explicable. Ils ne sont pas présentés comme un optimum universel et ne sont jamais auto-optimisés à partir du P&L.

## ADR-329 — Le ratio historique reste observable et le contrat v6 reste additif

**PROPOSÉ — Batch 46, non intégré.**

Les champs historiques `volume_ratio`, `range_expansion_ratio`, `volatility_expansion_ratio`, `volume_change` et `volume_acceleration` restent exposés pour diagnostic, compatibilité et fallback.

Les nouveaux champs robustes sont additifs. Aucun bump mécanique du protocole v6 n'est introduit tant que les routes et la sémantique générale restent compatibles.

## Changelog — 2026-10-03 — Batch 45 Structure en amont et filtres — intégré

Commit intégré : `45d41b7` (`feat: move market structure before radar shortlist`).

- déplacement de la Structure avant la shortlist finale sans scan Structure illimité ;
- rotation/cache Structure séparés des curseurs OHLCV ;
- cache causal : aucun snapshot futur réutilisé ;
- événements `BOS / CHOCH` confirmés capables de compléter l'attention ;
- régimes persistants non transformés en anomalies permanentes ;
- filtres tendance/Structure avec `OR` intra-champ et `AND` inter-familles/timeframes ;
- `UNKNOWN` fail-closed ;
- diagnostic de couverture Structure séparé ;
- protocole v6 conservé ;
- aucune modification Agent/Risk/Broker.

Les validations connues du patch avant intégration restent : Python `py_compile` PASS, test frontend ciblé 16/16 PASS, typecheck ciblé lib PASS, typecheck cockpit ciblé avec stubs PASS. Aucune validation complète supplémentaire n'est inventée.

## ADR-325 — Géométrie Structure et policy de scan séparées

**ADOPTÉ — Batch 45.**

`MarketStructurePolicy` porte la causalité/géométrie. `MarketStructureScanPolicy` porte `market_limit_per_refresh` et `cache_ttl_seconds`. Le curseur Structure est indépendant des curseurs OHLCV.

## ADR-326 — Attention structurelle par événements confirmés

**ADOPTÉ — Batch 45.**

Par défaut, un régime `BULLISH / BEARISH / RANGE / TRANSITION` sans événement ne force pas la shortlist. Un `BOS_UP / BOS_DOWN / CHOCH_UP / CHOCH_DOWN` confirmé peut compléter l'attention. Le ranking reste directionnellement symétrique.

## ADR-327 — Filtres Structure fail-closed et zéro résultat explicable

**ADOPTÉ — Batch 45.**

`UNKNOWN`, absence, expiration ou non-couverture échouent à un filtre Structure actif. Le cockpit distingue une couverture incomplète d'une couverture complète sans correspondance.

## Changelog — 2026-10-03 — Batch 44 liquidité PERPETUAL et couverture — intégré

Commit fonctionnel intégré : `c262d54` (`feat: add perpetual liquidity and radar coverage diagnostics`).

- référence SPOT/USD canonique conservée ;
- linear perpetual/USD : liquidité fondée uniquement sur `volumeQuote` 24h public déjà validé ;
- percentiles SPOT/PERP séparés ;
- `UNKNOWN` lorsque la donnée fiable manque ;
- diagnostic de couverture/rotation OHLCV sans auto-correction silencieuse.

## ADR-323 — Liquidité PERPETUAL via `volumeQuote` USD validé

**ADOPTÉ — Batch 44.**

Le Radar ne notionnalise jamais les chart candles PERP par `candle.volume * close`. Une donnée non démontrée reste `LiquidityRegime.UNKNOWN`.

## ADR-324 — La couverture est observée, pas auto-corrigée

**ADOPTÉ — Batch 44.**

Les diagnostics exposent la capacité théorique de rotation avant expiration du cache, mais le Radar n'augmente pas automatiquement cadence, limites ou concurrence réseau.

## Changelog — 2026-10-03 — Batch 43.2 correctif Radar PERPETUAL — intégré

Commit intégré : `25dcb5c` (`fix: repair perpetual market attention radar`).

- `PERPETUAL + Volume Tous` conservé ;
- `volumeQuote` bulk Kraken Futures pour les linear perpetuals cotés USD ;
- aucune requête par marché ;
- aucune formule inventée sur `candle.volume` ;
- diagnostics `UNKNOWN_*` explicites ;
- aucune capacité d'exécution PERP.

## ADR-321 — Volume PERPETUAL USD via turnover quote public Kraken

**ADOPTÉ — Batch 43.2.**

Pour les linear perpetuals cotés directement en USD, `volumeQuote` constitue le volume 24h USD. Les quotes non USD ne sont pas converties implicitement.

## ADR-322 — Une shortlist PERPETUAL vide n'est pas réparée en abaissant le scoring

**ADOPTÉ — Batch 43.2.**

Si le catalogue et les données sont valides mais qu'aucune activité n'est assez inhabituelle, une shortlist vide est un résultat normal et explicable.
