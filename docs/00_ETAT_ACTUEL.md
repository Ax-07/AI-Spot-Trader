# 00 — État actuel

## Référence fonctionnelle intégrée

```text
Repository                : Ax-07/AI-Spot-Trader
Branche                   : main
Dernier commit fonctionnel: c262d54
Commit                    : feat: add perpetual liquidity and radar coverage diagnostics
```

Le Batch 44 est validé localement et intégré fonctionnellement via `c262d54`. Une clôture documentaire distincte peut suivre sans modifier ce SHA fonctionnel de référence.

## État intégré — Batch 44

Le Market Attention Radar reste `market-attention-radar-v6`, strictement informatif, déterministe, causal et read-only.

Éléments intégrés :

- scope runtime `SPOT / PERPETUAL / ALL` ;
- activité OHLCV, tendances et Market Structure native `5m / 15m / 1h / 4h` ;
- microstructure SPOT ;
- filtres runtime volume 24h et capitalisation ;
- volume 24h `SPOT/USD` calculé causalement sur les candles Kraken 5m finalisées ;
- volume 24h des linear perpetuals cotés USD via le `volumeQuote` public Kraken Futures bulk ;
- diagnostics explicites du filtre volume ;
- aucune capacité d'exécution PERP, aucune modification Agent / Risk Engine / Broker.

## Batch 44 — intégré fonctionnellement

Le Batch 44 corrige deux limites du Radar v6 sans modifier son rôle :

- liquidité PERPETUAL : `liquidity_reference_usd` utilise uniquement le `volumeQuote` 24h USD déjà validé pour les linear perpetuals/USD, avec percentiles séparés de la population SPOT ;
- couverture : le contrat v6 expose l'univers éligible, les marchés frais/expirés/non vus, le ratio de couverture, la rotation théorique, le TTL et un diagnostic explicite lorsque la configuration ne peut pas revisiter l'univers avant expiration.

La rotation existante par curseurs SPOT/PERP et le scoring canonique sont conservés. Aucun seuil n'est modifié.

Voir `docs/44_LIQUIDITE_PERPETUAL_ET_COUVERTURE_RADAR.md`.

## Validation connue

Batch 43.2 intégré :

```text
backend pytest -q       : PASS local avant intégration
frontend pnpm typecheck : PASS local avant intégration
frontend pnpm test      : PASS — 57/57 local avant intégration
git diff --check        : PASS local avant intégration
```

Batch 44 validé localement avant intégration :

```text
backend pytest -q       : PASS
frontend pnpm typecheck : PASS
frontend pnpm test      : PASS — 59/59
git diff --check        : PASS (avertissements LF/CRLF uniquement)
git status --short      : propre après commit fonctionnel
```
