# Batch 19.9B — Données stratégiques multi-timeframes SCALP / SWING

## Objectif

Fournir au même Agent IA stratégique un contexte candles multi-timeframes causal, borné, stable et auditable, sans introduire de second pipeline OHLC ni de ranking stratégique déterministe.

## Source canonique des timeframes

Le mapping reste exclusivement porté par `trading-style-map-v1` / `TradingStyleContext.preferred_timeframes` :

- SCALP : `1m`, `5m`, `15m`, `30m` ;
- SWING : `1h`, `4h`, `1d`.

Le service 19.9B consomme ce mapping ; il ne redéfinit pas un mapping SCALP/SWING parallèle.

## Contrat `strategic-mtf-v1`

Le contexte est ajouté de façon optionnelle et backward-compatible à `MarketSelectionInput` et `AgentInput`.

Pour chaque marché/timeframe, il expose : timeframe demandée, statut `AVAILABLE` / `PARTIAL` / `MISSING`, profondeur demandée et nombre réel de candles, couverture, nombre de gaps, stale, dernière candle et son statut final/non final, ainsi qu'un résumé OHLCV descriptif de la fenêtre et son rendement brut. Aucune règle BUY/SELL n'est dérivée de ces statistiques.

Le payload LLM ne transporte pas tout l'historique brut. L'historique borné sert à construire ce résumé compact.

Bornes v1 :

- marchés : 32 maximum ;
- taille JSON : 128 KiB maximum ;
- concurrence de lecture : 4 ;
- profondeurs : `1m=12`, `5m=12`, `15m=10`, `30m=8`, `1h=16`, `4h=12`, `1d=10`.

## Causalité

`CandleStreamService.history_as_of()` complète le pipeline canonique :

- cache : une candle n'est visible que si `open_time <= as_of` et `updated_at <= as_of` ; une finale exige également `close_time <= as_of` ; une non-finalisée exige `open_time <= as_of < close_time` ;
- backfill demandé après coup pour un `as_of` historique : seules les candles finalisées déjà clôturées et disponibles à `as_of` sont fusionnées ; la candle courante retournée par un REST appelé aujourd'hui n'est jamais utilisée pour reconstruire artificiellement son état passé ;
- aucune interpolation des trous ; un gap reste explicitement signalé ;
- si une révision plus récente d'une candle active a remplacé une révision ancienne dans le cache, elle est exclue pour un `as_of` antérieur plutôt que rétro-projetée.

## Snapshot de cycle

`MultiTimeframeDecisionProvider` décore l'Agent stratégique :

1. à Market Selection, il construit le contexte au `MarketSelectionInput.created_at` ;
2. il attache ce contexte à l'input réellement envoyé au LLM ;
3. il conserve exactement le même objet pour le cycle ;
4. à la décision BUY/SELL/HOLD, il réattache le même snapshot à l'`AgentInput` final.

En legacy single-market avec un style explicite mais sans phase de sélection, un snapshot d'un seul marché est construit au `AgentInput.created_at`.

## Discovery

Discovery ne reçoit pas le contexte candles riche v1. Il conserve ses candidats factuels bornés et `TradingStyleContext` / `ExecutionCostContext`. L'enrichissement multi-timeframes se fait après la présélection Discovery, sur l'univers effectif remis à Market Selection. Cela évite l'explosion `marchés × timeframes × historique` sans déplacer la décision stratégique vers du code déterministe.

## Partage du pipeline candles

Le `CandleStreamService` créé par le backend FastAPI est injecté dans `CampaignRuntimeManager`, puis `build_campaign_runtime`. Le cockpit et le moteur stratégique utilisent donc la même instance, le même cache et le même provider. Le Campaign runtime n'en devient pas propriétaire et ne le ferme pas ; le backend le ferme après le runtime Campaign.

## Compatibilité et audit

- `agent-contract-v1` conservé : champs multi-timeframes optionnels, schémas de sortie Agent inchangés ;
- anciennes Campaigns sans `trading_style` : comportement inchangé et aucun chargement multi-timeframes ;
- persistence : les payloads complets `MarketSelectionInput` et `AgentInput` existants embarquent automatiquement le nouveau contexte ;
- analytics/replay : `AgentInput` connaît officiellement le champ optionnel, donc les payloads 19.9B restent validables et les anciens payloads restent acceptés ;
- `ExecutionCostContext` reste une responsabilité distincte ;
- aucun changement Risk Engine, broker, règle indicateur→action ou timer de liquidation.

## Validation attendue avant intégration

```powershell
cd E:\AI-Spot-Trader
git status --short
git diff --check
pytest backend/tests/test_strategic_multi_timeframe.py
pytest
```

Le frontend n'est pas modifié par ce batch.
