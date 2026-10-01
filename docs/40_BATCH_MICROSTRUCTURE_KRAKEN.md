# Batch 40 — Microstructure Kraken pour Market Attention

## Référence et état d'intégration

Audit initial réalisé le 01/10/2026 sur GitHub `main` au HEAD :

```text
2aaff09b01300008e63eaadbca242817bcb4ce28
 docs: mark batch 39 as integrated
```

Le Batch 40 est désormais intégré sur GitHub `main` au HEAD :

```text
6d263be5edb589723101c32065ad68434b0b64f1
 feat: enrich market attention with kraken microstructure
```

Le commit applicatif Batch 39 est `5bff583b47acf2b3a2a112611c40e0046c78cc3e`.

Audit confirmé : le Radar v2 réutilise `CandleStreamService`, est Kraken-only et déterministe, mais aucune abstraction canonique pour les trades publics récents ou le carnet L2 SPOT n'existait dans `KrakenPublicRestClient`.

## Objectif

Enrichir l'attention marché avec des faits microstructurels Kraken sans modifier la frontière stratégique :

```text
OHLCV structurel Batch 39
+
trades récents SPOT
+
carnet L2 SPOT
=
Market Attention Radar v3
```

Le Radar reste strictement informatif.

## Architecture

Nouveaux composants :

- `market/microstructure.py` : modèles, politique bornée, normalisation analytique et calculs purs ;
- `integrations/kraken/microstructure.py` : lecture publique `/Depth` et `/Trades` ;
- `market/attention_microstructure.py` : enrichissement du Radar Batch 39, cache, sous-scan, scoring descriptif et contrat v3.

`MarketAttentionRadar` Batch 39 reste la source canonique des faits OHLCV. Il n'existe aucun second pipeline candles.

## Données Kraken utilisées

### Carnet L2

Endpoint public `GET /0/public/Depth`, `assetVersion=1`, `count=100` par défaut. Le nombre de niveaux est configurable dans `MicrostructurePolicy` et borné à la limite publique Kraken.

### Trades récents

Endpoint public `GET /0/public/Trades`, `assetVersion=1`, `count=1000` par défaut. Les lignes sont bornées ; aucune accumulation historique infinie n'est conservée.

Aucune clé Kraken privée n'est nécessaire.

## Métriques carnet

- `best_bid`, `best_ask` ;
- `mid_price` ;
- `spread_absolute`, `spread_bps` ;
- `bid_depth_base`, `ask_depth_base` ;
- `bid_depth_quote`, `ask_depth_quote`, `total_depth_quote` ;
- `book_imbalance = (bid_quote - ask_quote) / total_quote` ;
- profondeur bid/ask dans `±5`, `±10`, `±25`, `±50 bps` autour du mid.

Les niveaux reçus dans un ordre inattendu sont triés. Les niveaux dupliqués au même prix sont agrégés. Les nombres négatifs/non finis sont rejetés.

## Métriques trades

Sur les trades reçus et causaux (`occurred_at <= observed_at`) :

- `trade_count` ;
- volume base et quote ;
- taille moyenne et médiane en base ;
- cadence courante en trades/minute ;
- cadence de référence ;
- ratio et variation d'activité.

Fenêtres par défaut :

```text
courant : 60 s
baseline précédente : 240 s
fenêtre totale comparée : 300 s
```

Le côté fournisseur Kraken est conservé uniquement pour les marqueurs connus. Les volumes acheteur/vendeur et le déséquilibre correspondant ne sont calculés que si la couverture du côté est de 100 % sur la fenêtre courante. Aucun côté n'est inventé.

## Slippage théorique

Tailles centralisées par défaut :

```text
100
500
1000
5000
```

Unité : **devise cotée du marché**. Pour `BTC/USD`, il s'agit d'USD ; pour `BTC/EUR`, d'EUR.

Pour chaque taille et chaque sens hypothétique, le calcul parcourt le carnet et retourne :

- VWAP estimé ;
- prix de référence best bid/ask ;
- slippage absolu ;
- slippage en bps ;
- volume base consommé ;
- profondeur quote disponible ;
- `insufficient_depth`.

Si la profondeur est insuffisante, aucun faux VWAP complet n'est publié.

## Caractéristiques descriptives

La couche peut produire :

```text
TIGHT_SPREAD
WIDE_SPREAD
DEEP_LIQUIDITY
THIN_LIQUIDITY
ORDER_BOOK_IMBALANCE
TRADE_ACTIVITY_SURGE
TRADE_ACTIVITY_FADE
BUY_PRESSURE
SELL_PRESSURE
SLIPPAGE_RISK
```

Elles décrivent des faits. Elles ne sont jamais des actions de trading.

## Intégration au niveau d'intérêt

Le niveau Batch 39 reste la base. Les règles Batch 40 sont bornées :

- hausse d'intensité : renforcement ;
- déséquilibre L2 : renforcement ;
- pression transactionnelle complète : renforcement ;
- spread large / profondeur faible / slippage élevé : réduction d'un cran maximum ;
- profondeur confortable : raison descriptive sans forcer le niveau.

Un marché OHLCV modéré peut donc entrer dans la shortlist si sa microstructure est objectivement inhabituelle, tandis qu'un mouvement apparent très coûteux peut être dépriorisé.

## Coût et cadence

Valeurs par défaut :

```text
book_levels                 = 100
trade_count                 = 1000
market_limit_per_refresh    = 24 SPOT
concurrency                 = 4
refresh_seconds             = 300
cache_ttl_seconds           = 900
stale_after_seconds         = 420
```

Le sous-scan est rotatif parmi les marchés SPOT du scan OHLCV courant. À cadence nominale, le maximum théorique est 48 lectures REST publiques pour 24 marchés lorsqu'aucune entrée de cache n'est réutilisable, puis le cache évite les duplications trop rapprochées.

## Fail-soft

- une source microstructure valide suffit à conserver un snapshot `PARTIAL` ;
- deux sources en erreur donnent un statut microstructure `ERROR`, sans supprimer l'activité OHLCV ;
- cache ancien : `STALE` ;
- PERPETUAL : `NOT_APPLICABLE` pour cette couche ;
- donnée non scannée : `PARTIAL / MicrostructureNotScannedYet` ;
- aucune absence de donnée ne devient arbitrairement un bonus ou un malus.

## API et cockpit

Le protocole intégré est `market-attention-radar-v3`.

Le cockpit ajoute : spread, profondeur L2, déséquilibre, cadence/ratio des trades, slippage théorique, fraîcheur et diagnostics microstructure. Les formulations restent descriptives et un rappel explicite indique qu'aucun ordre n'est construit.

## Isolation et sécurité

Les modules Batch 40 Market Attention n'importent ni Agent, ni Risk, ni Broker, ni OpenAI, ni outil Web. `informative_only=True` reste obligatoire. Aucun secret n'est loggé ou versionné.

## Tests ajoutés

- calculs carnet : bid/ask, mid, spread, profondeur, déséquilibre, bandes ;
- niveaux non ordonnés/dupliqués ;
- carnet vide fail-soft ;
- trades : compte, volumes, moyenne, médiane, cadence, hausse/baisse ;
- absence d'invention du côté ;
- slippage acquisition/cession et profondeur insuffisante ;
- données périmées et erreurs partielles ;
- parsing Kraken `/Depth` et `/Trades` ;
- isolation statique Agent/Risk/Broker/OpenAI/Web ;
- enrichissement du niveau d'intérêt.

## Fichiers créés/modifiés

Créés :

```text
backend/src/ai_spot_trader/market/microstructure.py
backend/src/ai_spot_trader/market/attention_microstructure.py
backend/src/ai_spot_trader/integrations/kraken/microstructure.py
backend/tests/test_market_microstructure.py
backend/tests/test_kraken_microstructure.py
backend/tests/test_market_attention_batch40_microstructure.py
docs/40_BATCH_MICROSTRUCTURE_KRAKEN.md
```

Modifiés :

```text
backend/src/ai_spot_trader/main.py
backend/src/ai_spot_trader/api/routes/market_attention.py
frontend/src/lib/market-attention.ts
frontend/src/components/cockpit/market-attention-dock.tsx
docs/00_ETAT_ACTUEL.md
docs/01_PROJECT_MASTER.md
docs/02_ARCHITECTURE_TECHNIQUE.md
docs/09_ROADMAP_DEVELOPPEMENT.md
docs/10_DECISIONS_ET_CHANGELOG.md
```

Aucun fichier n'est supprimé par le Batch 40.

## Validation d'intégration

Le Batch 40 a été validé localement puis poussé sur `main`. Validations communiquées lors de la clôture documentaire :

```text
backend pytest -q       : PASS, suite complète
frontend pnpm typecheck : PASS
frontend pnpm test      : 49/49 PASS
```

## Hors périmètre

Agent intra-bougie, exécution algorithmique, smart order routing, ordre iceberg, VWAP/TWAP réel, market making, arbitrage, LIVE, nouvelles clés privées Kraken, refonte Risk, optimisation prématurée et Rust restent hors périmètre.
