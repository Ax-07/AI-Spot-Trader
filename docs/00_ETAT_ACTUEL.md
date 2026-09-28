# 00 — État actuel

## Référence GitHub vérifiée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD GitHub vérifié : 3c609c7499dbef37a917046d6e70ae5112e0ad4c
HEAD                : feat: add market attention radar v1
Vérifié              : 2026-09-28
```

Le HEAD `3c609c7` intègre désormais **Market Attention Radar v1**. La version précédente de ce document était en retard : elle mentionnait encore `d011faa` et présentait le Radar comme patch proposé.

## État fonctionnel intégré à préserver

- un seul Agent IA stratégique ;
- PAPER uniquement à ce stade ;
- Kraken ;
- SPOT + PERPETUAL linéaire ; FUTURE daté interdit ;
- BUY / SELL / HOLD ; SPOT sans short ; PERPETUAL LONG/SHORT selon l'état intégré ;
- plan multi-marchés / multi-décisions ordonné ;
- Risk Engine déterministe = autorité finale ;
- aucune sortie LLM -> ordre direct ;
- `HOLD` journalisé ; `management_mode` conservé ;
- objectif stratégique courant = progression de l'equity nette après coûts, sans obligation de turnover ;
- `trading-reasoning-doctrine-v1` intégrée aux prompts stratégiques courants, pas à Market Discovery ;
- frontend = cockpit uniquement ; fermer le frontend n'arrête pas le backend ;
- Market Attention Radar v1 = observation uniquement et aucune donnée Radar n'est fournie à l'Agent.

## Market Attention Radar v1 — intégré

Architecture intégrée :

```text
catalogue Kraken public
        ↓
rotation / scan borné
        ↓
CandleStreamService canonique 5m
        ↓
activité relative 5m / 15m / 1h / 4h
        ↓
candidats inhabituels bornés
        ↓
OpenAI Responses API + hosted web_search
        ↓
attention publique structurée + sources
        ↓
shortlist informative + API read-only + cockpit
```

Garanties intégrées :

- aucun second pipeline OHLCV ;
- aucun seuil Radar fourni à l'Agent ;
- aucune influence sur Market Discovery, Risk, Broker, sizing ou ordres ;
- aucune API dédiée X/Reddit/LunarCrush ;
- recherche publique uniquement pour les candidats d'activité inhabituelle ;
- erreurs Radar fail-soft ;
- historique Radar v1 borné en mémoire, sans migration SQL ;
- badge cockpit `INFORMATIF — N’INFLUENCE PAS LE TRADING`.

Voir `docs/28_BATCH_MARKET_ATTENTION_RADAR_V1.md`.

## Patch proposé — observabilité Market Attention

Le batch courant améliore uniquement le diagnostic du Radar sans toucher aux seuils `1.40 / 1.75 / 2.50` ni au chemin de trading.

Il ajoute :

- compteurs des snapshots frais par statut `AVAILABLE / PARTIAL / STALE / ERROR` ;
- compteurs par état `UNKNOWN / NORMAL / ELEVATED / ACCELERATING / VERY_HIGH` ;
- top borné des marchés `AVAILABLE + NORMAL` les plus proches du seuil, calculé à partir des snapshots canoniques ;
- statut global cohérent lorsqu'aucun candidat n'est détecté mais que le Radar possède des données exploitables ;
- rendu cockpit compact des compteurs et du diagnostic sous seuil.

Les marchés « sous seuil » restent strictement diagnostiques : aucun candidat, aucune recherche web, aucune donnée Agent, aucune modification Market Discovery/Risk/Broker.

Voir `docs/29_BATCH_MARKET_ATTENTION_OBSERVABILITY.md`.

## Validation connue

Le commit intégré `3c609c7` correspond au Radar v1 livré et validé localement lors du batch précédent selon `docs/28_BATCH_MARKET_ATTENTION_RADAR_V1.md`.

Pour le patch observabilité courant, les validations exécutées dans l'environnement ChatGPT sont documentées dans `docs/29_BATCH_MARKET_ATTENTION_OBSERVABILITY.md`. Les suites complètes du repository doivent être rejouées localement après extraction du ZIP avant tout commit/push.
