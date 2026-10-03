# 00 — État actuel

## Référence intégrée GitHub

```text
Repository          : Ax-07/AI-Spot-Trader
Branche             : main
HEAD GitHub observé : c4f474c
Commit              : docs: close batch 44
```

Le dernier commit **fonctionnel** du Radar reste `c262d54` (`feat: add perpetual liquidity and radar coverage diagnostics`). Le commit `c4f474c` clôt uniquement la documentation du Batch 44.

## État intégré — Batch 44

Le Market Attention Radar reste `market-attention-radar-v6`, strictement informatif, déterministe, causal et read-only.

Éléments intégrés :

- scope runtime `SPOT / PERPETUAL / ALL` ;
- activité OHLCV, tendances et Market Structure native `5m / 15m / 1h / 4h` ;
- microstructure SPOT ;
- filtres runtime volume 24h et capitalisation ;
- volume 24h `SPOT/USD` calculé causalement sur les candles Kraken 5m finalisées ;
- volume 24h des linear perpetuals cotés USD via le `volumeQuote` public Kraken Futures bulk ;
- liquidité PERPETUAL basée sur ce `volumeQuote` validé ;
- diagnostics de couverture/rotation OHLCV ;
- aucune capacité d'exécution PERP, aucune modification Agent / Risk Engine / Broker.

## Batch 45 — patch proposé, non intégré

Le patch Batch 45 préparé à partir du HEAD `c4f474c` déplace la Market Structure **avant la shortlist finale** sans la calculer sur tout le catalogue :

```text
catalogue
-> scope
-> capitalisation
-> rotation OHLCV
-> volume
-> activité / tendance / liquidité / microstructure canonique
-> pool Structure borné et rotatif
-> cache Structure frais
-> filtres tendance / Structure
-> shortlist finale bornée
```

Le patch ajoute :

- une rotation/cache Market Structure séparée de la rotation OHLCV ;
- un diagnostic de couverture Structure distinct ;
- une attention structurelle basée sur événements confirmés `BOS / CHOCH`, symétrique haussier/baissier ;
- des filtres runtime de tendance, structure globale, états et événements par `5m / 15m / 1h / 4h` ;
- `UNKNOWN` fail-closed lorsqu'un filtre correspondant est actif ;
- cockpit repliable pour ces filtres et diagnostics ;
- conservation additive du protocole public `market-attention-radar-v6`.

Un état persistant `BULLISH` ou `BEARISH` ne force pas à lui seul un marché dans la shortlist par défaut. Il reste néanmoins recherchable lorsqu'un filtre Structure explicite est activé.

Voir `docs/45_STRUCTURE_EN_AMONT_ET_FILTRES_RADAR.md`.

## Validation connue

Batch 44 validé localement avant intégration :

```text
backend pytest -q       : PASS
frontend pnpm typecheck : PASS
frontend pnpm test      : PASS — 59/59
git diff --check        : PASS (avertissements LF/CRLF uniquement)
```

Batch 45 — validations exécutées par ChatGPT sur le patch préparé :

```text
Python py_compile des fichiers Python modifiés : PASS
frontend market-attention.test.mjs ciblé           : PASS — 16/16
typecheck TypeScript ciblé market-attention.ts     : PASS
typecheck ciblé cockpit avec stubs de dépendances  : PASS
```

La suite complète backend/frontend et `git diff --check` restent à exécuter localement après extraction du ZIP.
