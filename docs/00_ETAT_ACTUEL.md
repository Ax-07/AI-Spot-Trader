# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 9fc6a4a15f1c44c8ff7b43a342ab8d74bbedb892
Commit     : ux: simplify financial terminology
```

État revérifié le 30/09/2026 au démarrage du Batch 37. Le Batch 36 est **intégré** dans ce HEAD. Les références documentaires précédentes à `58b59ba...` et au Batch 36 « local/non intégré » sont obsolètes.

## Batch 37 — cadence stratégique IA synchronisée aux bougies

**État : patch proposé/local non intégré.**

Le patch ajoute un scheduling stratégique unique avec deux modes :

- `CANDLE_CLOSE` : cycle autonome aligné sur une clôture de bougie canonique ;
- `INTERVAL` : comportement historique conservé (`cycle -> attente X secondes -> cycle`).

Nouvelles Sessions :

- SCALP : recommandation UX `CANDLE_CLOSE` sur `5m` ;
- SWING : recommandation UX `CANDLE_CLOSE` sur `4h`.

Les Campaigns historiques sans nouveau champ restent exactement en mode `INTERVAL`; leur payload canonique et leur digest ne sont pas réécrits. Aucune migration DB n'est ajoutée.

Le scheduler réutilise `CandleStreamService` pour vérifier la finalité d'une bougie et ne crée aucun second pipeline OHLC. Le contexte stratégique multi-timeframes reste distinct du timeframe de déclenchement et conserve les garanties `history_as_of(...)` sans look-ahead.

Le monitoring/mark-to-market continue indépendamment. Market Discovery garde sa cadence propre, évaluée lors du passage d'un cycle stratégique par Discovery. Market Attention reste strictement informatif.

Voir `docs/37_BATCH_CADENCE_IA_BOUGIES.md`.
