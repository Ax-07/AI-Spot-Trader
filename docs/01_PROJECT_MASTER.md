# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading **PAPER** pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est un cockpit de contrôle et de visualisation qui peut être fermé sans arrêter le moteur.

Référence GitHub auditée pour le Batch 38 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : c699e7ce9fc4f9f43f005d7e8c19199a30befdf1
Commit     : feat: align AI decisions with candle closes
```

Le Batch 37 de cadence stratégique alignée sur les clôtures de bougies est intégré. Le Batch 38 reste un patch local tant qu'il n'a pas été validé puis intégré par l'utilisateur.

## 2. Invariants fonctionnels

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- PAPER uniquement dans les versions actuelles ;
- SPOT et PERPETUAL linéaire selon les capacités canoniques intégrées ;
- FUTURE daté interdit à l'exécution ;
- actions `BUY`, `SELL`, `HOLD` ;
- Luna par défaut, Sol sélectionnable ;
- Risk Engine déterministe comme autorité finale ;
- aucune sortie LLM/tool directement transmise au Broker/Kraken ;
- frais, spread et slippage pris en compte ;
- décisions, `HOLD`, sélections, évaluations Risk et exécutions auditables ;
- aucun look-ahead ;
- aucun secret dans prompts, logs, frontend ou fichiers versionnés ;
- frontend non nécessaire au fonctionnement du moteur ;
- Market Attention strictement informatif et non injecté dans l'Agent stratégique.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

La cible expérimentale `+4 %/jour` est un objectif de recherche non garanti et ne doit pas devenir une contrainte de prompt ou une promesse de rendement.

## 3. Modèle utilisateur et persistance

`Session` reste une façade sur les objets canoniques :

```text
Session UX
-> Strategy
-> StrategyRevision(s)
-> Campaign(s) immuables
-> paper_run(s)
```

Une modification de configuration crée un nouveau snapshot Campaign sans réécrire l'historique. Les extensions optionnelles doivent préserver exactement les payloads et digests historiques lorsqu'elles sont absentes.

## 4. Univers de marchés et Market Discovery

En mode automatique :

```text
catalogue Kraken
-> admissibilité déterministe
-> candidats
-> même Agent choisit une watchlist
-> même Agent produit le plan stratégique du cycle
```

En mode manuel, l'univers est limité par l'opérateur. Dans les deux cas, Risk reste final.

Market Discovery possède sa propre politique et reste distinct de Market Attention. Une shortlist Radar n'est ni une watchlist d'exécution ni un signal de trading.

## 5. Trading Style et multi-timeframes

Le mapping canonique `trading-style-map-v1` reste :

- SCALP : `1m`, `5m`, `15m`, `30m` ;
- SWING : `1h`, `4h`, `1d`.

`StrategicMultiTimeframeContextService` réutilise le `CandleStreamService` partagé. `history_as_of(...)` protège la causalité ; aucune révision future n'est injectée.

## 6. Cycle stratégique multi-marchés

Un cycle courant produit un plan ordonné et borné via un seul appel stratégique de planification :

```text
contexte causal
-> Agent IA unique
-> plan [D1, D2, ... Dn]
-> chaque décision : Risk -> exécution éventuelle -> portefeuille courant
```

`max_decisions_per_cycle` vaut 6 par défaut et possède une limite dure de 20. `HOLD` et `REJECT` ne sont pas des erreurs techniques.

## 7. Cadences distinctes

L'application distingue :

1. monitoring / mark-to-market déterministe ;
2. cadence du cycle stratégique IA ;
3. Market Discovery ;
4. streaming / cache candles ;
5. Market Attention Radar avec cadence/cache propres.

Le cycle stratégique supporte `INTERVAL` historique ou `CANDLE_CLOSE`. En `CANDLE_CLOSE`, le scheduler attend une frontière UTC et la finalité explicite de la candle canonique, sans replay en rafale. Le timeframe de déclenchement reste distinct du contexte multi-timeframes transmis à l'Agent.

Defaults UX intégrés : SCALP `5m`, SWING `4h`.

## 8. Transparence des appels IA

Le cockpit doit distinguer les appels du cycle stratégique, les appels éventuels de Market Discovery et les recherches auxiliaires du Market Attention Radar. Le monitoring et le traitement déterministe Kraken ne sont pas des appels Agent stratégique.

## 9. Risk, coûts et exécution

Les schedulers et le Radar ne modifient ni la politique Risk, ni le pricing PAPER, ni frais/spread/slippage, ni la logique Broker. Sur SPOT, aucune vente d'un actif non détenu n'est autorisée.

## 10. Market Attention — entonnoir déterministe Batch 38

Market Attention reste un service **observationnel**. Il réutilise exclusivement le pipeline OHLCV canonique et n'appelle jamais Risk, Broker, l'Agent stratégique ou Market Discovery.

Le Radar suit désormais l'entonnoir :

```text
Kraken catalogue
-> scan OHLCV 5m canonique
-> activité / liquidité
-> structure déterministe descriptive
-> niveau d'intérêt LOW / MEDIUM / HIGH / VERY_HIGH
-> shortlist déterministe bornée
-> recherche publique uniquement pour HIGH / VERY_HIGH si nécessaire
```

Caractéristiques possibles :

- `TRENDING` ;
- `VOLUME_ANOMALY` ;
- `VOLATILITY_EXPANSION` ;
- `BREAKOUT_WATCH` ;
- `REVERSAL_WATCH` ;
- `CONSOLIDATING` ;
- `PRICE_VOLUME_DIVERGENCE`.

Ces libellés signifient uniquement « mérite davantage d'attention ». Ils ne contiennent aucune préférence LONG/SHORT et ne produisent aucun `BUY`, `SELL` ou `HOLD`.

Le niveau d'intérêt est calculé à partir de faits auditables : volume relatif/accélération, retours descriptifs sur plusieurs horizons, expansion du range ou de volatilité, franchissement de la zone historique, cohérence ou divergence prix/volume et liquidité relative. Il ne prédit pas le sens futur.

Politique Web du Batch 38 :

- `LOW` / `MEDIUM` : aucune nouvelle recherche publique ;
- `HIGH` / `VERY_HIGH` : recherche possible ;
- budget par refresh : 2 par défaut, maximum 3 ;
- TTL Public Attention : 2 h ;
- refresh anticipé possible après un cooldown de 15 min lorsqu'un événement déterministe significatif survient : escalade d'intérêt, apparition d'un breakout/reversal descriptif ou nouvelle entrée en tête ;
- cache frais réutilisé sinon ;
- aucun quota n'est rempli artificiellement.

L'API expose la décision de recherche et les compteurs nécessaires pour expliquer les appels évités.

## 11. Modèle OpenAI auxiliaire du Radar

L'audit Batch 38 confirme que `OpenAIWebAttentionResearcher` reçoit encore `resolved_settings.llm_model`, donc le même modèle process que d'autres usages. Le prompt n'est pas la cause principale du coût : le nombre de recherches `web_search` domine le levier de réduction.

La séparation de configuration en un modèle auxiliaire Market Attention, Luna par défaut, est jugée pertinente mais reste **à décider** séparément afin de ne pas étendre silencieusement le contrat de configuration global dans ce batch.

## 12. Hors périmètre

- LIVE et ordres Kraken réels ;
- signal Market Attention vers l'Agent ;
- ranking technique stratégique ;
- second Agent ou second pipeline OHLC ;
- HFT ;
- modification de la politique Risk ;
- promesse de rendement.

## 13. Validation

Le Batch 38 ajoute des tests dédiés pour les marchés normaux, anomalies insuffisantes, tendances/breakouts, retournements, cache, refresh événementiel, budget Web, absence de burst, ranking déterministe, fail-soft, no-look-ahead, `informative_only` et isolation vis-à-vis du trading.

La suite complète backend/frontend doit être exécutée dans le repository local utilisateur après extraction du ZIP.
