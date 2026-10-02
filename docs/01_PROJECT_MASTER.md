# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est un cockpit de contrôle et de visualisation qui peut être fermé sans arrêter le moteur.

Référence GitHub auditée au lancement du Batch 43 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : f5de73270c23c6c4e2a6114ac78b3e57c17c65b1
Commit     : docs: close batch 42 documentation
```

Les Batches 39 à 42 sont intégrés sur `main`. Le Batch 43 est un patch proposé à valider localement avant intégration.

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

Le Batch 42 intégré ajoute une information distincte de la tendance récente. Pour chaque candidat de shortlist, le Radar lit directement les historiques natifs Kraken :

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

Aucun des deux ne constitue une action stratégique. Un `BOS` ou un `CHOCH` reste descriptif et n'est jamais un signal automatique.

## 14. Performance et cache

La Market Structure est enrichie **après** la constitution déterministe de la shortlist. Avec `candidate_limit=10` et quatre timeframes, le nombre de séries demandées par refresh est donc borné à 40. `CandleStreamService` reste le point d'accès canonique et réutilise son cache ; un historique natif déjà à jour n'est pas systématiquement retéléchargé.

## 15. Contrat API Radar

Batch 41 intégré : `market-attention-radar-v4`.

Batch 42 intégré : `market-attention-radar-v5` pour les snapshots réellement enrichis de `market_structure`. Les routes acceptent et sérialisent aussi un service v4 injecté afin de ne pas casser les tests/intégrations Batch 41.

Batch 43 proposé : `market-attention-radar-v6`, ajoutant l'état runtime des filtres ainsi que `volume_24h_usd` et les métadonnées de capitalisation sur les candidats.

`informative_only=True` reste validé côté backend.

## 16. Isolation architecturale

La couche v5 hérite de la couche v4. Le Batch 43 ajoute une couche v6 sans second pipeline candles et sans dépendance Agent/Risk/Broker. L'Agent stratégique reste le seul agent IA de l'application.

## 17. Microstructure

La microstructure reste **SPOT uniquement**. En scope `PERPETUAL`, aucun sous-scan microstructure n'est lancé et les marchés dérivés restent `NOT_APPLICABLE`. En scope `ALL`, seuls les éléments SPOT peuvent être enrichis par `/Depth` et `/Trades`.

L'observation de marchés `PERPETUAL` par le Radar ne modifie pas l'invariant d'exécution : le projet reste SPOT, sans short, levier, margin, future ou perpetual en exécution LIVE.

## 18. Batch 43 — filtres volume et capitalisation

Le Batch 43 proposé ajoute des filtres backend runtime :

```text
market_scope
min_volume_24h_usd
market_cap_categories
min_market_cap_usd
max_market_cap_usd
```

Le filtre de capitalisation intervient dès que les métadonnées sont disponibles, avant le scan OHLCV. Le filtre volume intervient au premier endroit fiable après OHLCV et avant microstructure/Market Structure.

Le volume 24h est calculé causalement à partir des candles Kraken déjà présentes dans le cache. Aucune conversion de devise ou d'unité non prouvée n'est inventée : une valeur non calculable reste `UNKNOWN` et est fail-closed lorsqu'un seuil volume est actif.

La capitalisation est une vraie métadonnée externe read-only :

```text
prix / OHLCV / tendance / structure / microstructure = Kraken
market cap / supply / rank                          = CoinPaprika
trading / Risk / Broker / ordres                    = inchangés
```

CoinPaprika est isolé derrière `MarketMetadataProvider`, sans secret, avec cache long et comportement fail-soft. Une indisponibilité du provider n'arrête jamais le Radar ; la capitalisation reste `UNKNOWN` en l'absence de donnée exploitable.

Catégories applicatives centralisées :

```text
MICRO  < 100 M$
SMALL  100 M$ à < 1 Md$
MID    1 Md$ à < 10 Md$
LARGE  >= 10 Md$
```

Ces catégories sont des conventions de l'application et non une définition universelle du marché.
