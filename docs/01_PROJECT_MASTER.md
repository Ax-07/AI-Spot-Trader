# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est un cockpit de contrôle et de visualisation qui peut être fermé sans arrêter le moteur.

Référence GitHub auditée au lancement du Batch 42 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : e65940b4c773f0de329648f5f3bb1f8960faa696
Commit     : feat: add market attention scope and trend direction
```

Les Batches 39 à 41 sont intégrés. Le Batch 42 décrit dans ce document est un patch proposé localement, non intégré tant qu'aucun commit utilisateur n'a été poussé.

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

La Market Structure du Radar Batch 42 est une autre consommation read-only du même pipeline candles. Elle n'altère pas le contexte stratégique de l'Agent et ne choisit aucune action.

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

L'application distingue le monitoring déterministe, la cadence du cycle stratégique IA, Market Discovery, le streaming/cache candles et le Market Attention Radar. Le Radar conserve sa cadence propre et ses caches ; il n'impose jamais la cadence de l'Agent.

## 8. Transparence des appels IA

Les appels de l'Agent stratégique et, lorsqu'elle existe, la logique IA de Market Discovery doivent rester distinguables. **Le Market Attention Radar ne produit aucun appel IA ni aucune recherche Web.**

## 9. Risk, coûts et exécution

Le Radar ne modifie ni Risk, ni Broker. Le slippage microstructure est une **simulation théorique read-only** obtenue en parcourant le snapshot L2 ; aucun ordre réel ou PAPER n'est construit.

## 10. Market Attention Radar v4 — scope et tendance récente

Le Batch 41 intégré conserve le Radar v3 comme socle et ajoute une couche v4 de scope runtime et de direction de tendance :

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
facts récents 5m / 15m / 1h / 4h
        ↓
direction récente par horizon + synthèse globale
        ↓
caractéristiques / intérêt / shortlist
        ↓
microstructure SPOT uniquement lorsque applicable
```

Le scope par défaut est `ALL`, afin de préserver le comportement historique si l'utilisateur ne modifie aucun réglage.

## 11. Direction de tendance récente

La direction Batch 41 réutilise les seuils matériels `_MATERIAL_RETURN` existants. Par horizon :

- `UP` si `price_return >= +seuil` ;
- `DOWN` si `price_return <= -seuil` ;
- `NEUTRAL` si le rendement reste strictement entre les deux seuils ;
- `UNKNOWN` si l'horizon est incomplet ou non exploitable.

La synthèse globale est multi-timeframe : conflit matériel positif/négatif => `MIXED`; au moins deux horizons matériels alignés sans conflit => `UP` ou `DOWN`; aucun mouvement matériel avec au moins deux horizons exploitables => `NEUTRAL`; sinon => `UNKNOWN`.

`TRENDING` est dérivé de la même synthèse et n'est présent que pour une synthèse globale `UP` ou `DOWN`.

## 12. Market Structure v5 — géométrie des swings

Le Batch 42 proposé ajoute une information distincte de la tendance récente. Pour chaque candidat de shortlist, le Radar lit directement les historiques natifs Kraken :

```text
CandleStreamService.history_as_of(...)
  ├─ CandleKey(market, 5m)
  ├─ CandleKey(market, 15m)
  ├─ CandleKey(market, 1h)
  └─ CandleKey(market, 4h)
```

Par défaut, environ 100 candles finalisées sont analysées par timeframe. Aucun timeframe supérieur n'est reconstruit artificiellement à partir du 5m.

Les pivots sont confirmés causalement après un nombre explicite de candles situées à droite du pivot. Les swing highs sont classés `HH/LH`, les swing lows `HL/LL`, avec une tolérance explicite pour les quasi-égalités. Une seule rupture isolée ne suffit pas à déclarer une structure complète.

États exposés :

```text
BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN
```

La synthèse multi-timeframe peut exposer `MIXED`. Des événements descriptifs `BOS_UP`, `BOS_DOWN`, `CHOCH_UP`, `CHOCH_DOWN` peuvent être ajoutés uniquement lorsque la séquence de pivots confirmés le justifie.

## 13. Séparation tendance récente / structure

Les deux concepts restent indépendants :

```text
recent_trend      = mouvement récent mesuré par les horizons Batch 41
market_structure  = géométrie des pivots confirmés sur historique natif plus long
```

Exemple valide :

```text
Tendance récente H4 : DOWN
Structure H4         : TRANSITION
Swings               : HH → HL → LH → LL
```

Aucun des deux ne constitue une action stratégique.

## 14. Performance et cache

La Market Structure est enrichie **après** la constitution déterministe de la shortlist. Avec `candidate_limit=10` et quatre timeframes, le nombre de séries demandées par refresh est donc borné à 40. `CandleStreamService` reste le point d'accès canonique et réutilise son cache ; un historique natif déjà à jour n'est pas systématiquement retéléchargé.

## 15. Contrat API Radar

Batch 41 intégré : `market-attention-radar-v4`.

Batch 42 proposé : `market-attention-radar-v5` pour les snapshots réellement enrichis de `market_structure`. Les routes acceptent et sérialisent aussi un service v4 injecté afin de ne pas casser les tests/intégrations Batch 41.

`informative_only=True` reste validé côté backend.

## 16. Isolation architecturale

La couche v5 hérite de la couche v4. Elle ne crée ni second catalogue, ni second client privé Kraken, ni pipeline candles parallèle. Elle n'importe aucun composant Agent, Risk ou Broker. L'Agent stratégique reste le seul agent IA de l'application.

## 17. Microstructure

La microstructure reste **SPOT uniquement**. En scope `PERPETUAL`, aucun sous-scan microstructure n'est lancé et les marchés dérivés restent `NOT_APPLICABLE`. En scope `ALL`, seuls les éléments SPOT peuvent être enrichis par `/Depth` et `/Trades`.

## 18. Hors périmètre du Batch 42

Aucune décision automatique basée sur la structure, aucun BUY/SELL/LONG/SHORT/HOLD depuis le Radar, aucun passage automatique vers l'Agent, aucun ordre Kraken, aucune modification Risk/Broker, aucune agrégation artificielle 5m -> H1/H4 et aucune refonte générale ne sont introduits.
