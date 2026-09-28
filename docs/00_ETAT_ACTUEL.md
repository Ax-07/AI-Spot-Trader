# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 5a2d07b3fc5208475c1a136690da6648797efde9
Commit     : feat: balance market attention spot perpetual coverage
```

État vérifié le 28/09/2026 après intégration du Batch 32.

## État des batches Market Attention

- Batch 28 — Radar v1 : intégré ;
- Batch 29 — observabilité : intégré ;
- Batch 30 — robustesse activité : intégré ;
- Batch 31 — notionnel USD SPOT et régimes de liquidité : intégré dans `1850ff8` ;
- Batch 32 — couverture équilibrée SPOT/PERPETUAL : intégré dans `5a2d07b`.

## État intégré confirmé

Le Radar reste strictement informatif et n'alimente ni l'Agent, ni Market Discovery, ni le Risk Engine, ni le Broker/order flow.

Le pipeline intégré conserve :

- `CandleStreamService` comme source canonique de candles ;
- seuils d'activité `1.40 / 1.75 + 0.25 / 2.50 + 0.50` ;
- `candidate_limit = 20` ;
- `max_web_searches_per_refresh = 8` ;
- notionnel SPOT directement coté USD via `SPOT_BASE_VOLUME_X_5M_CLOSE_ESTIMATE` ;
- notionnel SPOT non USD à `null` ;
- notionnel PERPETUAL à `null` tant que l'unité économique de `Candle.volume` n'est pas reliée canoniquement aux métadonnées du contrat ;
- régimes `MICRO / LOW / MEDIUM / HIGH / VERY_HIGH / UNKNOWN`, descriptifs et non filtrants.

## Batch 32 intégré

Le Batch 32 remplace le curseur global du Radar par une rotation déterministe stratifiée :

- curseur SPOT indépendant ;
- curseur PERPETUAL indépendant ;
- allocation proportionnelle à la taille des familles ;
- au moins une place par famille disponible quand la capacité le permet ;
- redistribution déterministe des places inutilisées ;
- diagnostics `scanned` et `fresh` par type de marché dans l'overview et le cockpit.

Le Batch 32 ne modifie ni la stratégie, ni les prompts Agent, ni le Risk Engine, ni le sizing, ni PAPER/LIVE.

## Validation locale et intégration

Validation utilisateur exécutée avant intégration :

- backend `pytest -q` : suite complète passée à `100 %`, sans échec ;
- frontend `pnpm test` : `46/46` tests passés ;
- frontend `pnpm lint` : passé ;
- frontend `pnpm typecheck` : passé ;
- build Next.js de production : passé ;
- `git diff --check` : passé, avec uniquement des avertissements LF -> CRLF non bloquants.

Intégration GitHub :

```text
Commit : 5a2d07b3fc5208475c1a136690da6648797efde9
Push   : 1850ff8..5a2d07b  main -> main
```

Après le push, le working tree utilisateur connu contient uniquement :

```text
?? trades_9h_analysis.json
```

Ce fichier reste hors périmètre et non versionné.
