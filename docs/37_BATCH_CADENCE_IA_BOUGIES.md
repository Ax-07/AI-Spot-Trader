# 37 — Batch cadence stratégique IA synchronisée aux bougies

## 1. Base auditée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 9fc6a4a15f1c44c8ff7b43a342ab8d74bbedb892
Commit     : ux: simplify financial terminology
```

Le Batch 36 est intégré. `docs/00_ETAT_ACTUEL.md` et `docs/09_ROADMAP_DEVELOPPEMENT.md` étaient obsolètes au démarrage du batch car ils pointaient encore sur `58b59ba...` et décrivaient le Batch 36 comme local.

## 2. Audit de l'existant

### Confirmé

- `CampaignConfiguration.trading_cadence_seconds` est persisté dans le snapshot Campaign.
- `campaign_composition.py` transmet cette valeur au `TradingEngine`.
- `TradingEngine` exécute un cycle puis attend `cadence_seconds` : la cadence historique est glissante et dépend donc de la durée du cycle.
- le chemin multi-marchés courant produit un plan stratégique borné via le même Agent puis passe chaque décision séquentiellement dans Risk/Broker ;
- Market Discovery appelle `refresh_if_due()` depuis le chemin du cycle dynamique lorsque nécessaire ; `watchlist_refresh_seconds` n'est pas un scheduler autonome ;
- mark-to-market/monitoring est une boucle backend séparée et ne doit pas être ralentie ;
- `CandleTimeframe` est déjà canonique ;
- `CandleStreamService.history_as_of(...)` et `StrategicMultiTimeframeContextService` imposent déjà la causalité/no-look-ahead.

### Obsolète

- le HEAD documentaire `58b59ba...` ;
- le statut « Batch 36 local/non intégré » ;
- l'affirmation du prompt de lancement « moteur SPOT uniquement » : le HEAD intégré supporte aussi PERPETUAL PAPER via le pipeline canonique. Le Batch 37 ne régresse donc pas cette capacité. FUTURE daté reste interdit.

### Manquant avant le batch

- une représentation explicite de la stratégie de scheduling ;
- un alignement sur les frontières de candles ;
- un garde de finalité avant déclenchement autonome ;
- une UX lisible minutes/heures pour ce réglage ;
- des tests dédiés à la non-dérive et à l'absence de catch-up.

### À décider ultérieurement

- cadence spéciale lorsqu'une position est ouverte ;
- réaction événementielle intra-bougie ;
- observabilité dédiée du retard entre clôture planifiée et démarrage effectif ;
- politique de retry/alerte opérateur après indisponibilité très longue de candles.

## 3. Architecture retenue

Aucun second moteur n'est ajouté.

```text
CampaignConfiguration
  trading_cadence_seconds
  strategic_schedule?         # extension optionnelle

ScheduledTradingEngine
  ├─ INTERVAL      -> boucle historique TradingEngine
  └─ CANDLE_CLOSE  -> CandleCloseSchedule
                      -> CandleCloseReadinessGate
                      -> runner canonique
```

### `strategic_schedule`

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

Le champ est optionnel. Son absence conserve le comportement historique.

Aucune migration DB et aucun changement de `paper-control-plane-config-v1` ne sont nécessaires, car les Campaigns stockent déjà le payload de configuration JSON.

## 4. Compatibilité historique

Pour une ancienne Campaign :

```text
strategic_schedule absent
=> effective_trading_cadence_mode = INTERVAL
=> trading_cadence_seconds inchangé
=> canonical_payload sans nouveau champ
=> digest historique inchangé
```

Une Session historique rouverte par le cockpit garde ce champ absent tant que l'utilisateur ne choisit pas explicitement un nouveau mode. L'édition ne transforme donc pas silencieusement une ancienne Campaign.

## 5. Scheduling CANDLE_CLOSE

`CandleCloseSchedule` utilise la durée du `CandleTimeframe` canonique et une grille UTC.

Exemple 5m :

```text
12:00
12:05
12:10
12:15
```

Au démarrage, la prochaine frontière est strictement postérieure à l'heure courante. Après un cycle, la prochaine cible est recalculée depuis l'horloge, pas depuis `fin_du_cycle + timeframe`.

Conséquences :

- pas de dérive cumulative ;
- pas de double cycle pour la même clôture ;
- pas de replay de toutes les frontières manquées ;
- après un cycle long, reprise sur la prochaine frontière future ;
- après une indisponibilité de donnée, l'ancienne clôture peut être sautée plutôt que rejouée en rafale.

## 6. Finalité et causalité

La frontière théorique ne suffit pas. `CandleCloseReadinessGate` demande au `CandleStreamService` canonique une lecture `history_as_of(...)` et vérifie une candle :

- `is_final == true` ;
- `close_time == target_close` ;
- `updated_at <= observed_at`.

Une candle non finale ou une révision disponible seulement dans le futur ne peut pas débloquer le cycle.

Le garde ne calcule aucun signal et n'appelle aucun LLM.

Le contexte Agent reste construit séparément par `StrategicMultiTimeframeContextService`. La bougie de décision sert uniquement de trigger temporel.

## 7. Timeframes autorisés

La v1 du contrat de scheduling expose uniquement les timeframes stratégiques déjà canoniques :

```text
1m, 5m, 15m, 30m, 1h, 4h, 1d
```

Validation par style :

```text
SCALP -> 1m / 5m / 15m / 30m
SWING -> 1h / 4h / 1d
```

Defaults UX :

```text
SCALP -> CANDLE_CLOSE 5m
SWING -> CANDLE_CLOSE 4h
```

Ces defaults ne sont pas des règles Risk ou stratégie.

## 8. Run manuel et arrêt

`ScheduledTradingEngine` hérite de `run_cycle()` sans modifier la primitive de cycle et expose explicitement `allows_manual_cycle_while_running = True`. Le runtime peut donc demander un cycle manuel pendant que le scheduler autonome attend une frontière.

Le runner canonique conserve son verrou de sérialisation : si un cycle automatique est déjà en cours, le cycle manuel attend ce verrou au lieu de s'exécuter en concurrence. Les moteurs qui n'optent pas pour cette capacité conservent le refus historique pendant RUNNING.

La boucle autonome attend sur l'Event de stop. `stop()` réveille aussi bien l'attente avant frontière que l'attente de finalité.

## 9. Market Discovery, monitoring et Market Attention

Le batch ne fusionne aucune cadence :

- mark-to-market : continue indépendamment ;
- cycle stratégique : INTERVAL ou CANDLE_CLOSE ;
- Discovery : `refresh_if_due()` garde `watchlist_refresh_seconds` et est évalué dans le cycle dynamique ;
- Market Attention : reste indépendant et informatif.

Un cycle déclenché sur clôture peut donc comporter un appel Agent de planification et, si Discovery est due, un appel Agent supplémentaire de sélection de watchlist. Les tool loops peuvent également produire plusieurs appels fournisseur. L'UX ne promet donc pas « un appel OpenAI exact par bougie ».

## 10. UX

Le configurateur simple expose :

```text
Déclenchement des décisions IA
- À la clôture d'une bougie
- À intervalle fixe
```

En CANDLE_CLOSE :

```text
Bougie de décision : 5 minutes / 4 heures / ...
Timeframes analysées : mapping du style
Fréquence effective : après chaque clôture cible validée
```

En INTERVAL, la saisie simple utilise secondes/minutes/heures puis convertit vers `trading_cadence_seconds` pour le contrat backend.

La configuration avancée conserve la valeur technique en secondes et explique qu'elle n'est pas utilisée pour cadencer le scheduler CANDLE_CLOSE.

Changer seulement SCALP/SWING ne réécrit pas automatiquement le schedule. `Réappliquer les valeurs conseillées` est l'action explicite qui applique le default du style.

## 11. Fichiers du batch

Backend :

```text
backend/src/ai_spot_trader/domain/enums.py
backend/src/ai_spot_trader/control_plane.py
backend/src/ai_spot_trader/core/runtime.py
backend/src/ai_spot_trader/trading/cadence.py
backend/src/ai_spot_trader/trading/__init__.py
backend/src/ai_spot_trader/campaign_composition.py
backend/tests/test_trading_cadence.py
backend/tests/test_control_plane_campaign_config.py
```

Frontend :

```text
frontend/src/lib/api/types.ts
frontend/src/lib/session-config.ts
frontend/src/lib/session-config.test.mjs
frontend/src/components/cockpit/simple-configurator.tsx
```

Documentation :

```text
docs/00_ETAT_ACTUEL.md
docs/01_PROJECT_MASTER.md
docs/09_ROADMAP_DEVELOPPEMENT.md
docs/10_DECISIONS_ET_CHANGELOG.md
docs/37_BATCH_CADENCE_IA_BOUGIES.md
```

## 12. Tests dédiés ajoutés

Backend :

- alignements 1m, 5m, 15m, 30m, 1h, 4h, 1d ;
- frontière strictement future au démarrage ;
- cycle long sans dérive/catch-up ;
- finalité exacte de la candle ;
- rejet non-final/future revision ;
- `run_cycle()` manuel immédiat ;
- stop pendant l'attente ;
- INTERVAL historique ;
- cohérence des composants selon le mode ;
- Campaign legacy sans schedule ;
- roundtrip CANDLE_CLOSE/INTERVAL ;
- validation timeframe/style ;
- refus des champs inconnus.

Frontend :

- CANDLE_CLOSE 5m ;
- INTERVAL explicite ;
- omission legacy ;
- compatibilité style/timeframe ;
- default SCALP 5m ;
- reconstruction d'une personnalisation ;
- default/recommandation SWING 4h ;
- non-régression des profils Risk/Discovery existants.

## 13. Hors périmètre

LIVE, ordres Kraken réels, cadence accélérée position ouverte, réaction intra-bougie, stop-loss/take-profit déterministes, signal Radar vers Agent, ranking technique, second Agent, second pipeline OHLC, HFT et modification de politique Risk restent hors périmètre.
