# 37 — Cadence stratégique IA synchronisée aux bougies

## 1. Historique et référence courante

Le Batch 37 a introduit `CANDLE_CLOSE` sur une grille UTC avec `CandleCloseSchedule` et un garde de finalité pré-cycle. Son audit initial avait été réalisé sur `9fc6a4a15f1c44c8ff7b43a342ab8d74bbedb892`.

Le diagnostic ayant conduit au Batch 51.4 a été réalisé sur le HEAD pré-51.4 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 5d24185ac1eefe9be3c21e31e62831228c73fea9
Commit     : feat: add live Ollama agent observability
```

Le Batch 51.4 est désormais intégré sur `main` :

```text
HEAD       : 566e0ca1a2170a18a06d1bd531ac3b2d118f6849
Commit     : fix: restore automatic candle-close agent cycles
```

Cette intégration corrige la sémantique de readiness du scheduler sans créer de second moteur.

## 2. Invariants

- un seul `ScheduledTradingEngine` ;
- le run manuel utilise toujours la même primitive `run_cycle()` ;
- le runner canonique reste sérialisé ;
- Market Discovery/Radar reste résolu dans `DynamicMarketTradingCycleRunner` ;
- le scheduler ne décide jamais BUY/SELL/HOLD ;
- Risk conserve l'autorité finale ;
- PAPER uniquement ;
- aucune donnée future n'est admise par les lectures causales ;
- aucun replay en rafale de frontières manquées.

## 3. Modes de cadence

`CampaignConfiguration.strategic_schedule` reste optionnel :

```json
{
  "mode": "CANDLE_CLOSE",
  "decision_timeframe": "5m"
}
```

ou :

```json
{
  "mode": "INTERVAL"
}
```

Une Campaign historique sans ce champ conserve le comportement `INTERVAL` historique et son payload canonique.

## 4. Architecture CANDLE_CLOSE après 51.4

Architecture retenue :

```text
CampaignConfiguration
  strategic_schedule=CANDLE_CLOSE
  decision_timeframe
        |
        v
CandleCloseSchedule              # grille UTC, trigger temporel
        |
        v
ScheduledTradingEngine
        |
        v
runner canonique unique
  ├─ DynamicMarketTradingCycleRunner -> Radar/Discovery si dynamique
  └─ MultiMarketTradingCycleRunner   -> univers statique
        |
        v
services de contexte causaux
  -> history_as_of(as_of=...)
        |
        v
Agent -> Risk -> Broker PAPER
```

`CandleCloseReadinessGate` n'est plus composé dans ce chemin. Il reste un helper de diagnostic/test capable de vérifier une candle finale exacte sur un ensemble de marchés explicitement connu.

## 5. Pourquoi le gate pré-cycle a été retiré du scheduler

### Option 1 — readiness strict sur tous les bootstrap markets

Rejetée. En Campaign dynamique, `paper_executable_markets` représente le bootstrap autorisé, pas nécessairement l'univers qui sera utilisé après Radar, positions existantes et capacity. Un seul marché bootstrap avec une erreur provider peut donc supprimer tout le cycle sans rapport avec l'univers stratégique réel.

### Option 2 — readiness adapté à l'univers Radar

Rejetée pour le scheduler. Connaître l'univers exact avant le cycle demanderait de répliquer ou déplacer hors du runner des responsabilités de Discovery, positions et capacity. Cela créerait deux résolutions d'univers et un risque de split-brain.

### Option 3 — frontière temporelle comme trigger, données causales dans le cycle

Adoptée. Le scheduler sait uniquement **quand** un cycle doit être tenté. Les services qui savent **quelles données** sont nécessaires vérifient leur disponibilité au moment où elles sont consommées.

Cette séparation respecte l'architecture : Radar/déterministe fournit le contexte, le même Agent décide, Risk tranche.

## 6. Causalité / no-look-ahead

Retirer le gate pré-cycle ne retire aucune protection de causalité.

`CandleStreamService.history_as_of()` :

- ne retourne que les observations disponibles à `as_of` ;
- filtre `open_time`, `close_time` et `updated_at` ;
- n'admet une candle finale que si `close_time <= as_of` ;
- rejette toute révision dont `updated_at > as_of` ;
- backfill avec `before=as_of` puis applique les mêmes filtres avant merge.

Les services consommateurs conservent leur contrat existant : le contexte multi-timeframe peut déclarer une série `AVAILABLE`, `PARTIAL` ou `MISSING`, tandis qu'une erreur technique provider remonte dans le chemin d'échec du cycle. Le scheduler ne remplace jamais une donnée, n'invente pas une candle et ne fait aucun fallback vers un autre marché/provider.

## 7. Scheduling et absence de catch-up

`CandleCloseSchedule.next_close_after()` retourne toujours une frontière strictement future.

Pour 5 minutes :

```text
12:00
12:05
12:10
12:15
```

Règles :

- démarrage à 12:00 -> première cible 12:05 ;
- une frontière atteinte déclenche au maximum un cycle ;
- après le cycle, la prochaine cible est recalculée depuis l'horloge murale ;
- si un cycle long traverse une ou plusieurs frontières, elles sont sautées ;
- si la boucle se réveille alors que la cible est déjà superseded par la frontière suivante, elle saute la cible obsolète au lieu de lancer une rafale ;
- aucune dérive `fin_cycle + timeframe` ;
- aucun replay historique au restart.

## 8. Erreurs temporaires de candles/provider

Avant 51.4, une exception `history_as_of()` dans le gate était convertie en `False`. La boucle pouvait repoller puis abandonner la frontière lorsque la suivante arrivait, sans jamais appeler le runner ; `last_error_type` n'était pas exposé par le scheduler.

Après 51.4, aucune requête candle/provider n'est effectuée par le scheduler. Si le cycle a besoin d'une donnée et rencontre une erreur Kraken/OHLC :

1. le cycle est réellement démarré ;
2. la partialité légitime reste explicitement représentée par les services de contexte, tandis qu'une erreur technique suit le chemin d'échec canonique/audit du cycle ;
3. le scheduler journalise la fin `FAILED` et le type d'erreur disponible ;
4. la prochaine tentative reste la prochaine frontière future ;
5. aucun polling infini ni catch-up burst n'est créé.

## 9. Radar dynamique

Le chemin `RADAR_SHORTLIST` reste inchangé dans son ownership :

```text
cycle -> discovery.refresh_if_due()
      -> shortlist Radar causale
      -> positions existantes
      -> capacity
      -> univers effectif
      -> contexte Radar + multi-timeframe + thèses
      -> même Agent stratégique
```

Le bootstrap n'est jamais promu silencieusement en univers stratégique de substitution lorsque Radar doit décider l'univers.

## 10. SPOT et PERPETUAL

Le scheduler est indépendant du type de marché. Les providers de candles gardent leurs contrats canoniques :

- SPOT : finalité fournie par les lignes OHLC Kraken après validation ;
- PERPETUAL : finalité dérivée causalement par rapport à `before/as_of` dans le provider charts.

Le warning `Kraken payload validation failed operation=OHLC stage=OHLC_NUMERIC` reste un WARNING provider et n'est ni masqué ni converti en readiness silencieuse.

## 11. Run manuel et arrêt

`ScheduledTradingEngine.allows_manual_cycle_while_running = True` reste inchangé. Le run manuel n'attend jamais une frontière CANDLE_CLOSE ; le runner canonique sérialise les cycles.

L'attente jusqu'à la prochaine frontière utilise l'Event de stop. `stop()` interrompt donc toujours la boucle sans lancer de cycle.

## 12. Observabilité scheduler 51.4

Événements INFO/WARNING attendus, une seule fois par événement :

```text
scheduler_next_close ...
scheduler_boundary_reached ...
scheduler_readiness_validated mode=TEMPORAL_ONLY ... causal_data=DELEGATED_TO_CYCLE
scheduler_cycle_started trigger=AUTO_CANDLE_CLOSE ...
scheduler_cycle_completed ... status=...
scheduler_boundary_skipped ... reason=SCHEDULER_LATE|CYCLE_ELAPSED
```

Aucun log n'est émis toutes les 0,5 s. Aucun payload Kraken brut, prompt, réponse LLM brute, secret ou thinking/CoT n'est journalisé.

## 13. Timeframes autorisés

La v1 conserve :

```text
1m, 5m, 15m, 30m, 1h, 4h, 1d
```

Mapping UX :

```text
SCALP -> 1m / 5m / 15m / 30m ; recommandation 5m
SWING -> 1h / 4h / 1d          ; recommandation 4h
```

Ces valeurs restent des recommandations UX, pas des règles Risk.

## 14. Tests de non-régression

Le Batch 51.4 ajoute une couverture ciblée pour :

- grille UTC ;
- frontière prête -> exactement un cycle ;
- run manuel immédiat ;
- arrêt pendant attente ;
- erreur temporaire de donnée dans le cycle -> FAILED visible puis prochaine frontière ;
- Radar dynamique non pré-gaté par bootstrap ;
- SPOT/PERPETUAL au niveau des contrats candles ;
- aucune double exécution ;
- aucun catch-up burst ;
- logs de scheduler bornés/non spammés ;
- causalité `history_as_of()` inchangée.

Dans l'environnement de livraison pré-intégration, le harness isolé du scheduler passait 26/26 et les tests ciblés de logging passaient 2/2. Cette mention est conservée comme historique de validation de la livraison 51.4.

## 15. Hors périmètre

LIVE, second scheduler, second Agent, réaction intra-bougie, HFT, stop-loss/take-profit algorithmique, changement de Risk Policy et fallback de provider restent hors périmètre.
