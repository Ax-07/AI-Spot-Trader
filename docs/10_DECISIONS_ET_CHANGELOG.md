# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les éléments nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers Broker/Kraken, SPOT sans short, PERPETUAL derrière les contrôles dérivés déterministes, FUTURE daté interdit, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Market Attention Radar reste strictement observationnel et n'est pas un input de l'Agent stratégique.

## Référence courante

```text
HEAD GitHub audité     : c699e7ce9fc4f9f43f005d7e8c19199a30befdf1
HEAD                   : feat: align AI decisions with candle closes
Batch 37               : intégré
Batch 38               : patch Market Attention préfiltrage proposé localement
```

## Changelog — 2026-10-01 — Batch 38 Market Attention préfiltrage Kraken

- base GitHub auditée : `c699e7ce9fc4f9f43f005d7e8c19199a30befdf1` ;
- correction de la documentation qui décrivait encore le Batch 37 comme local ;
- conservation du pipeline canonique `CandleStreamService` / OHLCV 5m ;
- enrichissement déterministe des horizons avec retours précédent/courant, range de référence, expansion range/volatilité et distance de breakout ;
- caractéristiques descriptives : tendance, anomalie de volume, expansion de volatilité, breakout/reversal watch, consolidation, divergence prix/volume ;
- nouveau niveau d'intérêt Radar `LOW/MEDIUM/HIGH/VERY_HIGH`, déterministe et non directionnel ;
- shortlist déterministe réduite ;
- aucune nouvelle recherche publique pour `LOW` / `MEDIUM` ;
- `max_web_searches_per_refresh` passe à 2 par défaut avec limite dure 3 ;
- Public Attention TTL passe à 2 h ;
- refresh anticipé possible après 15 min en cas d'escalade d'intérêt, nouveau breakout/reversal descriptif ou nouvelle entrée en tête ;
- cache réutilisé lorsque l'événement ne justifie pas un refresh ;
- recherches toujours séquentielles et bornées ;
- exposition de la décision de recherche par candidat et de compteurs d'éligibilité/cache/refresh/skip ;
- aucun changement Risk, Broker, Campaign, exécution PAPER, frais, spread, slippage ou Agent stratégique ;
- le couplage de modèle du Radar à `resolved_settings.llm_model` est confirmé mais non modifié dans ce batch.

## ADR-240 à ADR-279 — décisions antérieures actives

Les décisions Session/lifecycle, Trading Style, coûts, multi-timeframes, gestion des positions, cycle multi-décisions, contrats Agent, reasoning et causalité restent actives. Les détails historiques demeurent dans Git.

## ADR-280 à ADR-286 — Market Attention Radar v1

Market Attention Radar v1, son observabilité, sa robustesse, ses régimes de liquidité et son runtime hardening restent intégrés. Il ne produit aucun ordre, aucun score stratégique et aucune préférence LONG/SHORT.

## ADR-287 à ADR-290 — scheduling stratégique Batch 37

**INTÉGRÉS dans `c699e7c`.**

- `strategic_schedule` optionnel dans Campaign ; absence = `INTERVAL` historique exact ;
- un seul `ScheduledTradingEngine` gère INTERVAL et CANDLE_CLOSE ;
- le timeframe de décision est un trigger, pas un nouveau contexte stratégique ;
- Discovery conserve sa cadence et son orchestration propres ;
- aucune migration DB, aucun second pipeline OHLC, aucun catch-up en rafale.

## ADR-291 — Market Attention devient un entonnoir déterministe avant le Web

**ADOPTÉ DANS LE PATCH BATCH 38 — À INTÉGRER.**

Le scan Kraken reste fréquent et bon marché. Les données OHLCV servent à calculer des faits descriptifs auditables avant toute recherche publique. Le Web n'est plus alloué simplement parce qu'un actif fait partie des premiers candidats.

Le niveau `LOW/MEDIUM/HIGH/VERY_HIGH` exprime uniquement une priorité d'observation. Il ne constitue ni un score de trading, ni une probabilité de hausse/baisse, ni une préférence directionnelle.

## ADR-292 — Les recherches publiques sont événementielles, cachées et fortement bornées

**ADOPTÉ DANS LE PATCH BATCH 38 — À INTÉGRER.**

Politique :

```text
LOW / MEDIUM     -> aucune nouvelle recherche
HIGH / VERY_HIGH -> recherche possible
TTL              -> 2 h
cooldown événementiel -> 15 min
budget default   -> 2 / refresh
limite dure      -> 3 / refresh
```

Un cache frais est réutilisé, sauf changement significatif après cooldown. Les événements reconnus sont l'escalade d'intérêt, l'apparition de `BREAKOUT_WATCH` / `REVERSAL_WATCH` et une nouvelle entrée parmi les marchés de tête. Les recherches restent séquentielles afin d'éviter les bursts.

## ADR-293 — Le Radar reste hors du chemin de trading

**ADOPTÉ DANS LE PATCH BATCH 38 — À INTÉGRER.**

Le module Market Attention ne dépend pas d'Agent, Risk, Broker ou Market Discovery. `informative_only=True` reste un invariant de modèle. Les nouvelles caractéristiques servent exclusivement au préfiltrage du Radar et à son observabilité.

## ADR-294 — Séparation du modèle auxiliaire Market Attention reportée

**À DÉCIDER.**

L'audit confirme que `main.py` construit encore `OpenAIWebAttentionResearcher` avec `resolved_settings.llm_model`. Une option préférée est d'introduire un réglage auxiliaire distinct, Luna par défaut, afin qu'une future sélection Sol pour la stratégie n'augmente pas automatiquement le coût du Radar.

Cette modification touche la configuration process et ses tests ; elle est volontairement reportée afin de garder le Batch 38 centré sur le levier de coût principal : le nombre de recherches Web.

## Points explicitement non décidés

- modèle auxiliaire Radar configurable séparément ;
- utilisation de Market Attention comme contexte Agent ;
- réaction stratégique intra-bougie ;
- LIVE.
