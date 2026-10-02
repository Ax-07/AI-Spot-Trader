# 42 — Market Structure multi-timeframe

## Statut

**INTÉGRÉ** sur `main` au commit :

```text
003dae8dbfdc052edbad5bfde2c23fa24852eace
feat: add multi-timeframe market structure
```

Référence de départ auditée avant développement :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : e65940b4c773f0de329648f5f3bb1f8960faa696
Commit     : feat: add market attention scope and trend direction
```

## Objectif

Ajouter au Market Attention Radar une lecture déterministe de la géométrie des swings sur chaque timeframe natif Kraken :

```text
5m / 15m / 1h / 4h
```

La Market Structure est un **contexte descriptif**. Elle ne produit aucune action, ne modifie pas le Risk Engine et ne déclenche aucun ordre.

## Relation avec le Batch 41

Le Batch 41 reste inchangé conceptuellement :

```text
recent_trend = UP / DOWN / NEUTRAL / MIXED / UNKNOWN
```

Le Batch 42 ajoute séparément :

```text
market_structure = géométrie des pivots confirmés
```

Une tendance récente `DOWN` peut donc coexister avec une structure `TRANSITION`, par exemple après `HH → HL → LH → LL`.

## Source des candles

Aucune reconstruction H1/H4 depuis le 5m n'est utilisée. Pour chaque marché et timeframe :

```python
CandleStreamService.history_as_of(
    CandleKey(symbol=market.symbol, market_type=market.market_type, timeframe=timeframe),
    as_of=observed_at,
    limit=100,
)
```

La profondeur est configurable via `MarketStructurePolicy.history_limit`, par défaut 100 et bornée entre 40 et 300.

## Politique par défaut

```text
history_limit          = 100
min_history_candles    = 20
pivot_left_bars        = 2
pivot_right_bars       = 2
equality_tolerance_bps = 2
swing_display_limit    = 8
fetch_concurrency      = 8
```

## Causalité

Un pivot à l'indice `i` n'est détectable que lorsque les `pivot_right_bars` situées après lui sont finalisées. `confirmed_at` correspond à la clôture de la dernière candle de confirmation.

L'analyseur rejette localement toute candle :

- non finalisée ;
- fermée après `observed_at` ;
- mise à jour après `observed_at` ;
- appartenant à un autre timeframe.

`history_as_of(...)` apporte en plus la barrière causale canonique du cache/provider.

## Pivots et classifications

Swing high :

```text
nouveau high > high précédent + tolérance -> HH
nouveau high < high précédent - tolérance -> LH
```

Swing low :

```text
nouveau low > low précédent + tolérance -> HL
nouveau low < low précédent - tolérance -> LL
```

Dans la zone de quasi-égalité, le pivot est conservé mais sa classification directionnelle reste absente. Le Radar n'invente donc pas une direction sur du bruit sub-tolérance.

## États

```text
BULLISH
BEARISH
RANGE
TRANSITION
UNKNOWN
```

Règles principales :

- `BULLISH` exige plusieurs `HH` et `HL` récents ;
- `BEARISH` exige plusieurs `LH` et `LL` récents ;
- `TRANSITION` décrit un changement confirmé de géométrie ou des derniers high/low contradictoires ;
- `RANGE` décrit plusieurs pivots confirmés sans progression directionnelle au-delà de la tolérance ;
- `UNKNOWN` est utilisé si la preuve est insuffisante.

## Événements descriptifs

Le Batch 42 peut exposer :

```text
BOS_UP
BOS_DOWN
CHOCH_UP
CHOCH_DOWN
```

Ils servent uniquement à expliquer la géométrie observée. Aucun événement ne devient `BUY`, `SELL`, `LONG`, `SHORT` ou `HOLD` et aucun `BOS`/`CHOCH` ne constitue un signal de trading automatique.

## Synthèse multi-timeframe

Chaque timeframe conserve son résultat complet. La synthèse globale est :

- identique à l'état lorsque tous les timeframes connus sont alignés ;
- `MIXED` lorsque plusieurs états connus divergent ;
- `UNKNOWN` lorsque moins de deux timeframes fournissent une structure connue.

## Coût réseau et rotation

L'analyse structurelle est appliquée après le classement v4, uniquement aux marchés de `shortlist`. Avec `candidate_limit=10`, le plafond logique est :

```text
10 marchés × 4 timeframes = 40 lectures history_as_of / refresh
```

Ces lectures utilisent `CandleStreamService`, donc son cache process-local, ses verrous par `CandleKey` et son backfill causal. La concurrence structurelle est en plus bornée à 8 par défaut.

## Scope

Le scope `SPOT / PERPETUAL / ALL` est toujours appliqué avant la shortlist. Puisque la Market Structure n'enrichit que cette shortlist, elle ne demande aucune série pour un marché qui n'est pas éligible au scope actif.

Cette capacité d'observation de marchés PERPETUAL ne modifie pas l'invariant d'exécution du projet : le trading reste SPOT, sans short, levier, margin, future ou perpetual en exécution LIVE.

## API

Le Batch 42 introduit :

```text
market-attention-radar-v5
```

Chaque candidat possède :

```yaml
market_structure:
  observed_at: ...
  global_state: MIXED
  timeframes:
    - timeframe: 4h
      state: TRANSITION
      event: CHOCH_DOWN
      history_count: 100
      sequence: [HH, HL, LH, LL]
      confirmed_swing_highs: [...]
      confirmed_swing_lows: [...]
```

La route accepte aussi les snapshots v4 lorsqu'un service Batch 41 est injecté, afin de ne pas casser les tests/intégrations existants.

## Cockpit

Le détail marché affiche séparément :

```text
Tendance récente 5m/15m/1h/4h
Structure globale
Structure 5m/15m/1h/4h
Séquence des swings
Événement structurel éventuel
```

Les métriques préexistantes restent visibles : variation de prix, volume relatif, volatilité, liquidité et microstructure.

## Fichiers principaux

```text
backend/src/ai_spot_trader/market/structure.py
backend/src/ai_spot_trader/market/attention_structure.py
backend/src/ai_spot_trader/api/routes/market_attention.py
backend/src/ai_spot_trader/main.py
backend/tests/test_market_structure.py
frontend/src/lib/market-structure.ts
frontend/src/lib/market-structure.test.mjs
frontend/src/components/cockpit/market-attention-dock.tsx
```

## Validations réalisées avant intégration

Validations locales réalisées par l'utilisateur avant le commit et le push du Batch 42 :

```text
backend pytest -q          : PASS complet — 100 %
frontend pnpm test         : 54/54 PASS
frontend pnpm typecheck    : PASS (tsc --noEmit)
```

Le branchement production a également été contrôlé dans `backend/src/ai_spot_trader/main.py` avec `StructuredMarketAttentionRadar` et `MarketStructurePolicy` avant l'intégration.

Ces validations sont historiques ; elles ne sont pas présentées comme ayant été réexécutées lors de cette clôture documentaire.

## Couverture fonctionnelle validée avant intégration

Les tests dédiés couvrent notamment :

- swing highs / swing lows ;
- `HH / HL / LH / LL` ;
- `BULLISH / BEARISH / TRANSITION / RANGE / UNKNOWN` ;
- exclusion des candles non finalisées/futures ;
- confirmation causale à droite ;
- stabilité d'un pivot déjà confirmé ;
- indépendance 5m/15m/1h/4h ;
- appel natif `history_as_of` pour chacun des quatre timeframes ;
- contrat API v5 et compatibilité v4 ;
- helpers frontend de projection/labels de structure.

## Hors périmètre

- aucun appel OpenAI ;
- aucune recherche Web ;
- aucun nouvel Agent ;
- aucune recommandation d'achat/vente ;
- aucun ordre Kraken ;
- aucune connexion Risk/Broker ;
- aucune promotion automatique d'un BOS/CHOCH en signal stratégique ;
- aucune agrégation artificielle 5m vers H1/H4.
