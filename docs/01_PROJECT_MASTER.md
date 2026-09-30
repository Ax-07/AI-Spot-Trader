# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading **PAPER** pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est un cockpit de contrôle et de visualisation qui peut être fermé sans arrêter le moteur.

Référence GitHub auditée pour le Batch 37 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 9fc6a4a15f1c44c8ff7b43a342ab8d74bbedb892
Commit     : ux: simplify financial terminology
```

Le Batch 36 de simplification de terminologie financière est intégré dans cette base. Le Batch 37 est un patch proposé/local tant qu'il n'a pas été validé puis intégré par l'utilisateur.

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

La cible expérimentale `+4 %/jour` est un objectif de recherche non garanti et ne doit pas être transformée en contrainte de prompt ou en promesse de rendement.

## 3. Modèle utilisateur et persistence

`Session` reste une façade sur les objets canoniques :

```text
Session UX
-> Strategy
-> StrategyRevision(s)
-> Campaign(s) immuables
-> paper_run(s)
```

Une modification de configuration crée un nouveau snapshot Campaign sans réécrire l'historique. `CampaignConfiguration` reste versionnée par `paper-control-plane-config-v1` et son digest est calculé sur son payload canonique exact.

Les extensions optionnelles utilisent `exclude_if=None` afin qu'une Campaign historique dépourvue d'un nouveau champ garde exactement son payload et son digest historiques.

## 4. Univers de marchés et Market Discovery

En mode automatique :

```text
catalogue Kraken
-> admissibilité déterministe
-> candidats
-> même Agent choisit une watchlist
-> même Agent produit le plan stratégique du cycle
```

En mode manuel, l'univers est explicitement limité par l'opérateur. Dans les deux cas, Risk reste final.

Market Discovery possède sa propre politique (`catalog_refresh_seconds`, `watchlist_refresh_seconds`, etc.). Son refresh est évalué lorsque le runner dynamique est traversé par un cycle stratégique ; le Batch 37 ne crée pas de scheduler Discovery indépendant.

Market Discovery et Market Attention restent distincts. La shortlist Radar ne devient ni watchlist d'exécution ni signal de trading.

## 5. Trading Style et multi-timeframes

Le mapping canonique reste `trading-style-map-v1` :

- SCALP : `1m`, `5m`, `15m`, `30m` ;
- SWING : `1h`, `4h`, `1d`.

`StrategicMultiTimeframeContextService` réutilise le `CandleStreamService` partagé. `history_as_of(...)` ne retourne que des observations causalement disponibles au timestamp demandé ; aucune révision future n'est injectée et les gaps restent explicites.

Le style guide l'Agent mais ne devient ni un signal algorithmique, ni une politique Risk, ni un timer de sortie.

## 6. Cycle stratégique multi-marchés

Un cycle courant produit un plan ordonné et borné via un seul appel stratégique de planification :

```text
contexte causal
-> Agent IA unique
-> plan [D1, D2, ... Dn]
-> D1 : Risk -> exécution éventuelle -> portefeuille courant
-> D2 : Risk -> exécution éventuelle -> portefeuille courant
-> ...
```

`max_decisions_per_cycle` vaut 6 par défaut et possède une limite dure de 20. Risk évalue chaque décision sur le portefeuille courant, après les éventuelles mutations précédentes du même cycle. Une erreur technique peut provoquer le rollback PAPER prévu par le pipeline canonique ; `HOLD` et `REJECT` ne sont pas des erreurs techniques.

## 7. Cadences distinctes

L'application distingue plusieurs horloges qui ne doivent pas être confondues :

1. monitoring / mark-to-market déterministe, sans appel Agent stratégique ;
2. cadence du cycle stratégique IA ;
3. Market Discovery, évalué dans le chemin dynamique selon sa politique propre ;
4. streaming / cache candles, technique ;
5. Market Attention Radar, informatif avec sa propre cadence/cache.

Le Batch 37 ne ralentit ni le mark-to-market, ni les flux candles, ni le Radar.

## 8. Scheduling stratégique — Batch 37

`CampaignConfiguration` conserve obligatoirement `trading_cadence_seconds` pour la compatibilité. Elle peut désormais porter un champ optionnel `strategic_schedule` :

```text
strategic_schedule:
  mode: INTERVAL | CANDLE_CLOSE
  decision_timeframe: 5m   # requis uniquement pour CANDLE_CLOSE
```

### 8.1 Compatibilité historique

Si `strategic_schedule` est absent :

```text
mode effectif = INTERVAL
intervalle    = trading_cadence_seconds
```

Le comportement historique est inchangé : un cycle est lancé, puis le moteur attend l'intervalle configuré après sa fin. Le champ optionnel absent n'apparaît pas dans le payload canonique, donc les anciennes Campaigns gardent leur digest exact.

### 8.2 Mode CANDLE_CLOSE

Le moteur autonome attend une clôture UTC alignée sur le timeframe configuré. Il ne décale pas la grille à cause de la durée d'un cycle.

Exemple `5m` :

```text
12:05 -> cycle
12:10 -> cycle
12:15 -> cycle
```

Si le cycle de 12:05 se termine à 12:05:18, la prochaine cible reste 12:10. Si un cycle long dépasse une ou plusieurs frontières, les frontières manquées ne sont pas rejouées en rafale : le scheduler repart vers la prochaine clôture pertinente de la grille.

Au démarrage/restart, la première cible est une frontière strictement future ; le moteur ne rejoue pas une décision historique uniquement parce qu'une ancienne bougie a déjà clôturé.

### 8.3 Finalité des candles

Une frontière temporelle théorique ne suffit pas. `CandleCloseReadinessGate` vérifie via le `CandleStreamService` canonique qu'une bougie cible est explicitement finale et causalement disponible avant de lancer le cycle autonome.

Aucune bougie n'est inventée. Si une clôture reste indisponible jusqu'à être supplantée par la frontière suivante, l'ancienne décision est sautée plutôt que rejouée plus tard en rafale.

La vérification de disponibilité n'est pas un nouveau pipeline OHLC et n'appelle pas le LLM.

### 8.4 Timeframe de décision vs contexte analysé

Le timeframe de décision est un **trigger temporel**, distinct du contexte multi-timeframes transmis à l'Agent.

Exemples UX recommandés :

```text
SCALP
trigger : 5m
contexte Agent : 1m + 5m + 15m + 30m

SWING
trigger : 4h
contexte Agent : 1h + 4h + 1d
```

La configuration CANDLE_CLOSE exige un style explicite et un `decision_timeframe` appartenant au mapping canonique de ce style.

### 8.5 Run manuel et concurrence

`run-cycle` conserve la primitive immédiate héritée : il ne doit pas attendre une clôture. Le nouveau moteur schedulé autorise explicitement un cycle manuel même pendant que sa boucle autonome attend une frontière ; le runner canonique sérialise toujours les cycles, donc une commande manuelle ne peut pas chevaucher un cycle automatique déjà en cours. Les autres moteurs gardent le refus historique pendant RUNNING.

## 9. Defaults UX du Batch 37

Pour une nouvelle Session :

- SCALP -> `CANDLE_CLOSE` / `5m` ;
- SWING -> `CANDLE_CLOSE` / `4h`.

Ce sont des recommandations UX, pas des règles de stratégie. Changer simplement le style n'écrase pas silencieusement une personnalisation existante. L'action explicite `Réappliquer les valeurs conseillées` peut appliquer le mode et le timeframe recommandés.

Une Session historique sans `strategic_schedule` se rouvre en comportement legacy INTERVAL, sans transformation silencieuse.

Le cockpit présente l'intervalle fixe en unités lisibles secondes/minutes/heures et conserve le champ technique en secondes dans la configuration avancée.

## 10. Transparence des appels IA

Le cockpit doit distinguer :

- le cycle stratégique IA ;
- l'éventuel appel Market Discovery/watchlist si son refresh est dû ;
- le monitoring/mark-to-market sans Agent stratégique ;
- Market Attention indépendant.

Il ne faut donc pas promettre « exactement un appel OpenAI toutes les 5 minutes ». Une clôture peut déclencher un cycle stratégique et, selon l'état de Discovery et les tool loops de l'Agent, d'autres appels fournisseur peuvent exister.

## 11. Risk, coûts et exécution

Le Batch 37 ne modifie ni la politique Risk, ni le pricing PAPER, ni les frais/spread/slippage, ni le mapping BUY/SELL/HOLD, ni la logique Broker. Le scheduler décide seulement **quand** le cycle autonome peut démarrer.

Sur SPOT, aucune vente d'un actif non détenu n'est autorisée. Sur PERPETUAL, les contrôles de levier, marge, exposition, liquidation et `reduce_only` restent ceux du pipeline canonique.

## 12. Market Attention

Market Attention Radar reste strictement observationnel. Il possède ses propres horizons descriptifs et sa propre orchestration. Le Batch 37 ne l'utilise pas comme trigger et ne fournit pas ses snapshots à l'Agent stratégique.

## 13. Hors périmètre du Batch 37

- LIVE ;
- ordres Kraken réels ;
- cadence accélérée spéciale position ouverte ;
- réaction événementielle intra-bougie ;
- stop-loss/take-profit déterministes automatiques ;
- signal Market Attention vers l'Agent ;
- ranking technique stratégique ;
- second Agent ou second pipeline OHLC ;
- HFT ;
- scheduler Discovery indépendant ;
- modification de la politique Risk ;
- promesse de rendement.

## 14. Validation

Les tests dédiés du Batch 37 couvrent la grille 1m/5m/15m/30m/1h/4h/1d, la finalité des candles, la compatibilité Campaign legacy, les modes CANDLE_CLOSE/INTERVAL, le stop, le run manuel et l'absence de catch-up en rafale.

La suite complète backend/frontend doit être exécutée dans le repository local utilisateur après extraction du ZIP.
