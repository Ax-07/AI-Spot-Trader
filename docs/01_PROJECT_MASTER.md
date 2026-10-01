# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est un cockpit de contrôle et de visualisation qui peut être fermé sans arrêter le moteur.

Référence GitHub auditée au lancement du Batch 41 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 2a368c76f30373a6b9003324a1a14d8192cc0ad8
Commit     : docs: mark batch 40 as integrated
```

Les Batches 39 et 40 sont intégrés. Le Batch 41 décrit dans ce document est un patch proposé localement, non intégré tant qu'aucun commit utilisateur n'a été poussé.

## 2. Invariants fonctionnels

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- premières versions en PAPER ;
- SPOT comme invariant d'exécution cible ;
- actions stratégiques `BUY`, `SELL`, `HOLD` ;
- Luna par défaut pour les premiers tests, Sol sélectionnable par configuration ;
- Risk Engine déterministe comme autorité finale ;
- aucune sortie LLM directement transmise au Broker/Kraken ;
- frais, spread et slippage pris en compte dans la chaîne d'exécution concernée ;
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

L'application distingue le monitoring déterministe, la cadence du cycle stratégique IA, Market Discovery, le streaming/cache candles et le Market Attention Radar. Le Radar conserve sa cadence propre et son cache microstructure court ; il n'impose jamais la cadence de l'Agent.

## 8. Transparence des appels IA

Les appels de l'Agent stratégique et, lorsqu'elle existe, la logique IA de Market Discovery doivent rester distinguables. **Le Market Attention Radar ne produit aucun appel IA ni aucune recherche Web.**

## 9. Risk, coûts et exécution

Le Radar ne modifie ni Risk, ni Broker. Le slippage microstructure est une **simulation théorique read-only** obtenue en parcourant le snapshot L2 ; aucun ordre réel ou PAPER n'est construit.

## 10. Market Attention Radar v4 — Kraken déterministe

Le patch Batch 41 conserve le Radar v3 comme socle et ajoute une couche v4 de scope runtime et de direction de tendance :

```text
catalogue Kraken complet
        ↓
scope runtime SPOT / PERPETUAL / ALL
        ↓
population réellement éligible
        ↓
rotation / scan_limit
        ↓
CandleStreamService / OHLCV 5m canonique finalisé
        ↓
facts 5m / 15m / 1h / 4h
        ↓
direction par horizon + synthèse globale
        ↓
caractéristiques / intérêt / shortlist
        ↓
microstructure SPOT uniquement lorsque applicable
        ↓
API/cockpit informatif
```

Le scope par défaut est `ALL`, afin de préserver le comportement historique si l'utilisateur ne modifie aucun réglage.

## 11. Direction de tendance

La direction réutilise les seuils matériels `_MATERIAL_RETURN` existants. Par horizon :

- `UP` si `price_return >= +seuil` ;
- `DOWN` si `price_return <= -seuil` ;
- `NEUTRAL` si le rendement reste strictement entre les deux seuils ;
- `UNKNOWN` si l'horizon est incomplet ou non exploitable.

La synthèse globale est multi-timeframe : conflit matériel positif/négatif => `MIXED`; au moins deux horizons matériels alignés sans conflit => `UP` ou `DOWN`; aucun mouvement matériel avec au moins deux horizons exploitables => `NEUTRAL`; sinon => `UNKNOWN`.

`TRENDING` est dérivé de la même synthèse et n'est présent que pour une synthèse globale `UP` ou `DOWN`.

## 12. Contrat API Radar

Le patch propose `market-attention-radar-v4`. Il ajoute :

- `market_scope` au snapshot global ;
- `trend_direction` au `MarketActivitySnapshot` ;
- `trend_direction` à chaque horizon ;
- `PUT /api/v1/market-attention/scope` pour modifier le scope runtime et obtenir immédiatement un snapshot rafraîchi.

`informative_only=True` reste validé côté backend.

## 13. Isolation architecturale

La couche v4 hérite du Radar microstructure existant. Elle ne crée ni second catalogue, ni second pipeline candles, ni nouveau client Kraken privé. L'Agent stratégique reste le seul agent IA de l'application.

## 14. Microstructure

La microstructure reste **SPOT uniquement**. En scope `PERPETUAL`, aucun sous-scan microstructure n'est lancé et les marchés dérivés restent `NOT_APPLICABLE`. En scope `ALL`, seuls les éléments SPOT peuvent être enrichis par `/Depth` et `/Trades`.

## 15. Hors périmètre du Batch 41

Aucune décision automatique basée sur la tendance, aucun BUY/SELL depuis le Radar, aucun passage automatique vers l'Agent, aucun ordre Kraken, aucun short/levier/margin/future dans le moteur d'exécution, aucun nouvel indicateur technique décoratif et aucune refonte générale ne sont introduits.
