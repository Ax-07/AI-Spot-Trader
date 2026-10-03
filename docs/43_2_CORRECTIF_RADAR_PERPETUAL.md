# Batch 43.2 — Correctif Radar PERPETUAL

## Statut

Patch proposé à partir du HEAD GitHub `main` :

```text
85cbd01be40680a099bc1a251dc919ef3bbc7212
fix: correct market attention volume filter
```

Ce document décrit le patch fourni ; il ne prétend pas que celui-ci est déjà intégré à GitHub.

## Audit

### Confirmé

- `KrakenAttentionCatalogue.list_markets()` construit déjà un catalogue mixte SPOT + linear perpetuals à partir des instruments publics Kraken.
- Le scope `PERPETUAL` est filtré avant le scan OHLCV.
- `KrakenCandleProvider` utilise les chart candles Futures `trade/{venue_symbol}/{resolution}` et conserve le volume tradé.
- L'activité du Radar est déterminée à partir de l'OHLCV. La microstructure est SPOT-only ; les PERP sont `NOT_APPLICABLE` et ne doivent pas être rejetés pour cette raison.
- Lorsque `min_volume_24h_usd` vaut `None`, `attention_filters` ne rejette pas un PERP sur son volume.
- Au HEAD `85cbd01`, lorsqu'un seuil volume est actif, `_volume_24h_measurement()` renvoie systématiquement `UNKNOWN_UNSUPPORTED_MARKET_TYPE` pour un PERP. Le fail-closed supprime donc tous les PERP avant la shortlist.

### Cause racine du filtre volume PERP

Kraken Futures expose dans le ticker public bulk un champ `volumeQuote` correspondant au turnover dans l'actif de cotation sur la fenêtre 24h du ticker. Pour un linear perpetual coté directement en USD, cette valeur est déjà un notionnel USD exploitable.

Le patch utilise donc :

```text
PERPETUAL linear + quote USD
=> /tickers public bulk
=> volumeQuote
=> volume_24h_usd
```

Il n'utilise pas :

```text
candle.volume * close
```

pour les PERP, car l'unité contractuelle du volume de candle ne doit pas être supposée.

### Pourquoi `PERPETUAL + Volume Tous` peut rester vide

`Volume Tous` n'est pas le même défaut. Sans seuil volume :

```text
catalogue PERP
→ scope PERPETUAL
→ scan OHLCV
→ qualité/fraîcheur
→ critères d'activité
→ shortlist
```

Une shortlist vide est légitime si les marchés valides sont `NORMAL` / sous les critères d'intérêt. Elle peut aussi provenir d'erreurs Kraken, d'un historique insuffisant ou discontinu. Le patch ne réduit donc aucun seuil d'intérêt pour « forcer » des résultats.

Le cockpit possède déjà les compteurs catalogue/scannés/frais/statuts/erreurs/activité. Le patch complète son message de statut avec les compteurs `volume_24h_status_counts` lorsqu'un filtre volume actif explique un résultat vide.

## Implémentation

### `integrations/kraken/attention.py`

- mémorise le mapping canonique des linear perpetuals découvert lors du catalogue ;
- effectue un seul GET public bulk `/tickers` via le client Futures canonique ;
- parse `volumeQuote` de façon stricte et non négative ;
- ignore les tickers suspendus et ceux qui ne publient pas `volumeQuote` ;
- mappe seulement les instruments PERPETUAL/LINEAR cotés USD vers `ExecutableMarket`.

### `market/attention_filters.py`

- détecte si le catalogue sait fournir `volume_24h_usd_by_market()` ;
- rafraîchit le snapshot de volume PERP avant l'application du filtre ;
- conserve le calcul SPOT/USD causal existant ;
- PERP/USD connu : `AVAILABLE` ;
- provider absent : `UNKNOWN_UNSUPPORTED_MARKET_TYPE` pour compatibilité des providers de test/non-Kraken ;
- provider Kraken ayant répondu mais sans valeur pour le marché : `UNKNOWN_MISSING_QUOTE_VOLUME` ;
- provider Kraken en erreur : `UNKNOWN_TECHNICAL_ERROR` ;
- quote non USD : `UNKNOWN_UNSUPPORTED_QUOTE` ;
- seuil inclusif : `value >= minimum`.

### Frontend

`frontend/src/lib/market-attention.ts` connaît désormais `volume_24h_status_counts` et explique explicitement, lorsque le filtre volume actif laisse zéro candidat :

- combien de marchés n'ont pas de volume 24h USD exploitable ; ou
- combien de marchés connus sont sous le seuil.

## Invariants préservés

- Radar informatif uniquement ;
- déterministe ;
- causal ;
- Kraken public/read-only ;
- aucune clé privée ;
- aucune microstructure Futures ajoutée ;
- aucun LLM ;
- aucun ordre ;
- aucune modification Agent / Risk Engine / Broker ;
- aucun short, levier, margin, future ou perpetual n'est rendu exécutable par ce patch ;
- aucune baisse artificielle des critères d'intérêt.

## Tests ajoutés

`backend/tests/test_market_attention_batch43_2_perpetual.py` couvre :

- découverte d’un linear perpetual dans le catalogue et mapping du ticker bulk ;
- parsing strict du `volumeQuote` public bulk ;
- ticker suspendu / valeur absente ;
- volume négatif rejeté ;
- `PERPETUAL + Volume Tous` : catalogue, scan, données fraîches et candidat actif ;
- volume PERP supérieur au seuil ;
- volume PERP égal au seuil ;
- volume PERP sous le seuil ;
- panne du provider volume : `UNKNOWN_TECHNICAL_ERROR` explicite ;
- scope `ALL` mélangeant SPOT connu, PERP connu et PERP non mesurable sans suppression croisée.

Les tests historiques existants couvrent déjà le chart endpoint Futures, le venue symbol, `from/to/count`, le volume candle, les payloads invalides et les erreurs de transport. La couverture de causalité/finalisation existante est conservée.

## Validation locale attendue

```powershell
cd E:\AI-Spot-Trader\backend
pytest -q

cd E:\AI-Spot-Trader\frontend
pnpm typecheck
pnpm test

cd E:\AI-Spot-Trader
git diff --check
git status --short
```

Un smoke read-only réel Kraken reste recommandé localement pour observer :

```text
nombre de linear perpetuals
BTC/USD -> PF_XBTUSD
ETH/USD -> PF_ETHUSD
volumeQuote de quelques PERP USD
nombre / première / dernière candle trade 5m
```
