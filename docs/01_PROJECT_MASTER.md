# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est un cockpit de contrôle et de visualisation qui peut être fermé sans arrêter le moteur.

Référence GitHub auditée au lancement du Batch 39 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 2776fc68fb0ff8c094148a246d22de844ee868c7
Commit     : feat: prefilter market attention web research
```

Le Batch 38 est intégré. Le Batch 39 reste un patch local tant qu'il n'a pas été validé puis intégré par l'utilisateur.

## 2. Invariants fonctionnels

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- premières versions en PAPER ;
- SPOT comme invariant d'exécution cible ;
- actions stratégiques `BUY`, `SELL`, `HOLD` ;
- Luna par défaut pour les premiers tests, Sol sélectionnable par configuration ;
- Risk Engine déterministe comme autorité finale ;
- aucune sortie LLM directement transmise au Broker/Kraken ;
- frais, spread et slippage pris en compte ;
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

L'application distingue le monitoring déterministe, la cadence du cycle stratégique IA, Market Discovery, le streaming/cache candles et le Market Attention Radar. Le cycle stratégique peut être aligné sur les clôtures de bougies sans rendre le Radar décisionnel.

## 8. Transparence des appels IA

Les appels de l'Agent stratégique et, lorsqu'elle existe, la logique IA de Market Discovery doivent rester distinguables. **Le Market Attention Radar v2 ne produit plus aucun appel IA ni aucune recherche Web.**

## 9. Risk, coûts et exécution

Le Radar ne modifie ni Risk, ni le pricing PAPER, ni frais/spread/slippage, ni Broker. Il ne possède aucune interface d'exécution.

## 10. Market Attention Radar v2 — déterministe Kraken

À partir du Batch 39 proposé :

```text
Kraken
-> catalogue
-> CandleStreamService / OHLCV 5m canonique
-> bougies finalisées uniquement
-> agrégations 5m / 15m / 1h / 4h
-> faits volume / prix / range / volatilité / liquidité
-> caractéristiques déterministes
-> intérêt LOW / MEDIUM / HIGH / VERY_HIGH
-> shortlist diversifiée par régime de liquidité
-> API/cockpit read-only
```

Caractéristiques conservées :

- `TRENDING` ;
- `VOLUME_ANOMALY` ;
- `VOLATILITY_EXPANSION` ;
- `BREAKOUT_WATCH` ;
- `REVERSAL_WATCH` ;
- `CONSOLIDATING` ;
- `PRICE_VOLUME_DIVERGENCE`.

Le niveau d'intérêt exprime uniquement une priorité d'observation. Il n'est ni une probabilité, ni un signal directionnel, ni un `BUY/SELL/HOLD`.

Les anciennes notions `PublicAttentionSnapshot`, `PublicResearchDecision`, budget/TTL/cooldown Web, cache de recherche publique et compteurs de `web_search` ne font plus partie du contrat courant.

## 11. Contrat API Radar

Le protocole courant proposé est `market-attention-radar-v2`. L'API expose notamment : état Radar, nombre de marchés scannés/frais, candidats, état d'activité, caractéristiques, niveau et raisons d'intérêt, régime de liquidité, fraîcheur/qualité, diagnostics Kraken et shortlist.

`informative_only=True` est validé côté backend.

## 12. Isolation architecturale

Le module Radar ne dépend pas d'Agent, Risk, Broker ou Market Discovery. L'Agent stratégique reste le seul agent IA de l'application. Les systèmes déterministes calculent des faits et contraintes ; l'Agent conserve la décision stratégique.

## 13. Hors périmètre du Batch 39

- carnet d'ordres L2 ;
- trades Kraken ;
- spread/profondeur/déséquilibre ;
- intensité des trades ;
- slippage théorique issu du carnet ;
- LIVE ;
- utilisation de la shortlist Radar comme signal ou décision automatique.

Ces données microstructurelles sont réservées au Batch 40.
