# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel          : 9fc6a4a15f1c44c8ff7b43a342ab8d74bbedb892
Commit                    : ux: simplify financial terminology
Batches 28 à 35           : intégrés
Batch 36 terminologie UX  : intégré dans 9fc6a4a
Batch 37 cadence bougies  : patch proposé/local non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve :

- un seul Agent IA stratégique ;
- backend Python/FastAPI comme application de trading ;
- frontend comme cockpit uniquement ;
- Risk Engine déterministe comme autorité finale ;
- PAPER comme mode actuel ;
- Kraken comme exchange initial ;
- SPOT + PERPETUAL selon les capacités canoniques intégrées, FUTURE daté interdit ;
- aucune sortie LLM directement exécutable sur Kraken ;
- aucun secret versionné ;
- LIVE séparé et ultérieur ;
- Market Attention strictement informatif.

## Cadences distinctes

1. monitoring / mark-to-market : déterministe, sans LLM stratégique ;
2. cycle stratégique IA : `INTERVAL` historique ou `CANDLE_CLOSE` ;
3. Market Discovery : cadence distincte, refresh évalué dans le chemin du cycle dynamique ;
4. streaming marché / candles : technique et déterministe ;
5. Market Attention Radar : observation avec cadence/cache/TTL propres.

## État Market Attention et UX

Les Batches 28 à 35 restent intégrés : Radar v1, observabilité, robustesse, liquidité, couverture, runtime hardening, diagnostic/récupération SPOT Kraken et distinction erreur courante/historique.

Le Batch 36 est désormais **intégré** dans `9fc6a4a15f1c44c8ff7b43a342ab8d74bbedb892`. Les libellés utilisateurs ont été simplifiés (`Montant max par ordre`, `Valeur de la position`, etc.) sans modifier les identifiants techniques, calculs, API, Risk ou trading.

## Batch 37 — cadence stratégique alignée sur les bougies

**État : patch proposé/local non intégré.**

Objectif : séparer clairement la cadence stratégique IA du monitoring et permettre un déclenchement autonome sur une clôture de bougie canonique.

Architecture retenue :

```text
CampaignConfiguration
  trading_cadence_seconds      # historique, toujours conservé
  strategic_schedule?          # extension optionnelle
    mode = INTERVAL | CANDLE_CLOSE
    decision_timeframe?        # seulement CANDLE_CLOSE

ScheduledTradingEngine unique
  INTERVAL -> boucle historique
  CANDLE_CLOSE -> grille UTC + finalité CandleStreamService -> cycle
```

Defaults UX proposés :

- SCALP -> clôture `5m` ;
- SWING -> clôture `4h`.

Garanties :

- aucune migration DB ;
- ancienne Campaign sans schedule => INTERVAL exact ;
- aucun replay/catch-up en rafale ;
- aucune dérive liée à la durée du cycle ;
- stop réveille l'attente ;
- `run-cycle` manuel reste immédiat hors moteur autonome ;
- finalité de la candle vérifiée sans inventer de donnée ;
- contexte MTF et trigger restent séparés ;
- Risk/Broker/coûts inchangés ;
- Discovery ne reçoit pas un second scheduler.

Voir `docs/37_BATCH_CADENCE_IA_BOUGIES.md`.

## Périmètres ultérieurs possibles

À décider seulement sur besoin mesuré :

- cadence stratégique différente lorsqu'une position est ouverte ;
- réaction événementielle intra-bougie ;
- métriques d'observabilité du retard `scheduled_close -> cycle_start` ;
- politique explicite de tolérance aux indisponibilités longues de candles ;
- éventuelle exposition de Market Attention à l'Agent : non décidée ;
- LIVE : séparé et ultérieur.

Aucun ranking déterministe, quota de trades ou promesse de rendement ne doit être introduit silencieusement.
