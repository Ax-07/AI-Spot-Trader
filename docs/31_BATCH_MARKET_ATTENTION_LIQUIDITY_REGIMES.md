# Batch 31 — Market Attention : notionnel USD et régimes de liquidité

## Statut

**Intégré à GitHub `main`.**

Référence intégrée vérifiée lors du Batch 32 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 1850ff8783d0d29a5dd6628bdf1e9bb11a08ca63
Commit     : feat: add robust market attention liquidity context
```

Ce HEAD réunit les travaux Batch 30 + Batch 31. Les anciennes mentions « patch proposé, non intégré » étaient obsolètes.

## Objectif

Conserver le caractère relatif du Radar tout en ajoutant un axe descriptif d'importance économique lorsque le volume peut être normalisé en USD sans ambiguïté.

Le Radar reste observation-only : aucun BUY/SELL/HOLD et aucune donnée fournie à l'Agent, Market Discovery, Risk Engine ou Broker.

## SPOT directement coté USD

Pour un marché canonique `BASE/USD`, le pipeline expose un volume de base et un prix en USD. Le modèle `Candle` ne transporte pas de VWAP ; le notionnel est donc une estimation explicite :

```text
somme(volume_base_5m × close_usd_5m)
```

Méthode exposée :

```text
SPOT_BASE_VOLUME_X_5M_CLOSE_ESTIMATE
```

Champs par horizon :

```text
current_notional_usd
baseline_notional_usd
notional_delta_usd
notional_method
```

## SPOT non USD

Aucune conversion secondaire n'est inventée. `ASSET/EUR`, `ASSET/BTC`, `ASSET/USDT`, etc. conservent les métriques relatives mais les champs notionnels USD restent `null` tant qu'une conversion canonique n'est pas définie.

## PERPETUAL

Le Batch 31 laisse volontairement le notionnel PERPETUAL indisponible.

Le provider Futures utilise bien les candles `trade`, mais `Candle.volume` ne transporte pas l'unité contractuelle et `MarketActivityAnalyzer` reçoit un `ExecutableMarket`, pas les métadonnées `DerivativeInstrument.contract_size` nécessaires pour prouver une conversion économique.

Conséquence intégrée :

```text
PERPETUAL current_notional_usd  = null
PERPETUAL baseline_notional_usd = null
PERPETUAL notional_delta_usd    = null
PERPETUAL liquidity_regime      = UNKNOWN
```

Cette absence explicite est préférable à un faux montant USD.

## Référence de liquidité

Lorsque les baselines notionnelles USD sont disponibles, chaque baseline est ramenée en équivalent horaire :

```text
baseline_hourly_equivalent = baseline_notional_usd × 3600 / horizon_seconds
```

La référence du marché est la médiane des équivalents disponibles sur `5m / 15m / 1h / 4h`.

## Régimes

```text
MICRO
LOW
MEDIUM
HIGH
VERY_HIGH
UNKNOWN
```

La classification est descriptive et relative à la population fraîche observée, séparée par `MarketType`. Elle ne filtre jamais l'éligibilité.

Invariant :

```text
faible liquidité != marché inintéressant
```

Un marché `MICRO` ou `LOW` présentant une anomalie relative forte peut rester candidat.

## Seuils d'activité préservés

```text
ELEVATED      : 1.40
ACCELERATING : 1.75 + accélération 0.25
VERY_HIGH     : 2.50 + accélération 0.50
```

Le régime de liquidité ne remplace ni ces métriques ni le classement relatif d'activité.

## Cockpit

Le cockpit peut afficher :

- régime de liquidité ;
- notionnel USD courant ;
- delta vs baseline ;
- référence de liquidité ;
- méthode notionnelle.

Une valeur non démontrable reste `—`.

Le badge suivant reste obligatoire :

```text
INFORMATIF — N’INFLUENCE PAS LE TRADING
```

## Invariants préservés

- un seul Agent IA stratégique ;
- Radar observation-only ;
- aucune donnée Radar fournie à l'Agent ;
- aucune influence sur Market Discovery, Risk ou Broker ;
- aucun second pipeline OHLCV ;
- `CandleStreamService` canonique ;
- PAPER/LIVE inchangés ;
- seuils relatifs inchangés ;
- faible liquidité non exclue.

## Suite

Le Batch 32 audite à nouveau la chaîne PERPETUAL et confirme que la donnée transportée reste insuffisante pour activer un notionnel USD fiable. Toute activation future devra relier explicitement l'unité de volume de trade à la métadonnée contractuelle canonique avant calcul.
