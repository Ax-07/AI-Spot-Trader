# Batch 47.1 — Fondations Futures ticker du Market Attention Radar

## Statut

**Intégré via `842e6bd7`.**

Référence intégrée :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 842e6bd7f005f1f57bd9b2131d201777020d1d24
Commit     : feat: add futures ticker analytics foundations
```

Le Batch 47.1 est présent dans GitHub `main`. Les mentions antérieures « patch préparé, non intégré » sont obsolètes.

## Objectif

Le Batch 47.1 construit le socle canonique des données Futures instantanées du Radar, sans introduire de série Analytics historique ni de nouveau signal de ranking.

Périmètre :

```text
GET /derivatives/api/v3/tickers
volumeQuote déjà utilisé par le Radar
Open Interest courant
fundingRate courant Kraken
fundingRatePrediction Kraken
markPrice / indexPrice
serverTime
modèle ticker typé commun
contexte PERPETUAL additif
cockpit
```

Le Radar reste `market-attention-radar-v6`, informatif et read-only.

## Audit de l'existant pré-47.1

Avant ce batch, `KrakenAttentionCatalogue.volume_24h_usd_by_market()` appelait directement la méthode privée :

```text
_derivatives._get_json("/tickers", ...)
```

puis parsait uniquement `volumeQuote`.

Le client public canonique `KrakenDerivativesPublicClient` existait déjà. Le Batch 47.1 n'a donc créé aucun second client pour le snapshot bulk : il a ajouté `fetch_tickers()` au client existant et un parser typé.

Le chemin individuel `fetch_ticker()` reste inchangé pour le contexte PAPER et continue de normaliser le `fundingRate` selon la formule historique du projet :

```text
funding_rate_relative = fundingRate / (mark_price * contract_size)
```

Le Batch 47.1 ne modifie pas cette sémantique.

## Snapshot canonique

Le modèle retenu est :

```text
KrakenDerivativesTickerSnapshot
```

Champs :

```text
venue_symbol
observed_at             <- serverTime racine
mark_price              <- markPrice
index_price             <- indexPrice
volume_quote            <- volumeQuote
open_interest           <- openInterest
funding_rate_raw        <- fundingRate
funding_rate_prediction_raw <- fundingRatePrediction
suspended
post_only
funding_rate_relative   <- calcul interne existant, lorsque mark/contractSize le permettent
```

Les champs numériques optionnels restent `None` lorsqu'ils sont absents. `NaN`, `Infinity`, valeurs négatives interdites pour `volumeQuote` / `openInterest`, prix nuls ou négatifs, symboles vides, doublons et formes racine incohérentes échouent explicitement au parsing.

## Source et unités

La documentation Kraken Futures publique de `GET /tickers` démontre la présence, dans le même payload, de `volumeQuote`, `openInterest`, `markPrice`, `indexPrice`, `fundingRate`, `fundingRatePrediction`, `suspended`, `postOnly` et du `serverTime` racine.

Décisions d'unité du Batch 47.1 :

- `volumeQuote` conserve la décision Batch 43.2 : pour un linear perpetual coté directement en USD, il alimente `volume_24h_usd` et la liquidité PERP ;
- `openInterest` est conservé comme valeur Kraken brute : aucun suffixe `USD` n'est inventé ;
- `fundingRate` est conservé comme valeur Kraken brute dans le contexte Radar ;
- le taux relatif normalisé, lorsqu'il est calculable, est stocké séparément dans `funding_rate_relative` ;
- `fundingRatePrediction` est stocké séparément comme prévision Kraken ;
- aucune valeur funding brute ou prédite n'est formatée en `%` dans le cockpit tant que l'unité d'affichage n'est pas explicitement établie par la source utilisée.

## Mutualisation du bulk ticker

Le chemin Radar intégré est :

```text
KrakenDerivativesPublicClient.fetch_tickers()
        ↓ 1 appel public bulk /tickers
KrakenDerivativesTickerSnapshot[]
        ↓
KrakenAttentionCatalogue.perpetual_ticker_snapshot_by_market()
        ↓
FilteredStructuredMarketAttentionRadar._refresh_perpetual_volume_24h()
        ├─ volumeQuote -> volume 24h PERP
        ├─ volumeQuote -> référence liquidité PERP Batch 44
        └─ OI/funding/mark/index -> PerpetualTickerContext
```

Dans un refresh Radar utilisant le catalogue Kraken réel, le filtre volume, la liquidité et le contexte Futures sont alimentés par le même snapshot bulk. Le fallback `volume_24h_usd_by_market()` reste disponible pour compatibilité avec les anciens tests/providers.

## Contexte Radar PERPETUAL

Le modèle additif est :

```text
PerpetualTickerContext
```

Statuts :

```text
AVAILABLE
PARTIAL
NOT_APPLICABLE
TECHNICAL_ERROR
```

Règles :

- SPOT => `NOT_APPLICABLE` ;
- PERPETUAL avec tous les champs instantanés attendus => `AVAILABLE` ;
- PERPETUAL avec snapshot valide mais champs optionnels absents => `PARTIAL` ;
- panne du bulk ticker => `TECHNICAL_ERROR` ;
- ancien provider ne fournissant que le volume Batch 43.2 => volume conservé et contexte Futures `PARTIAL`.

La panne ticker reste fail-soft : sans filtre volume actif, l'activité OHLCV, la Structure et la capitalisation continuent. Avec un filtre volume actif, l'absence de `volumeQuote` conserve le comportement fail-closed Batch 43.2.

## Absence d'impact sur le ranking

Les champs Futures instantanés sont attachés au snapshot candidat mais ne sont consultés par aucune clé de tri, aucun calcul d'intérêt et aucun filtre de shortlist.

Le Batch 47.1 ne modifie pas :

```text
interest_level
interest_reasons
candidate_limit
_activity_sort_key
_v3_sort_key
_structured_candidate_sort_key
ranking Structure Batch 45
baseline MAD Batch 46
```

L'Open Interest et le funding instantanés ne peuvent donc pas introduire un candidat ni modifier son rang dans ce batch.

## Cockpit

Le détail d'un candidat `PERPETUAL` ajoute une section compacte `Futures Kraken` affichant selon disponibilité :

```text
Open Interest
Funding courant · brut Kraken
Funding prévu · prévision Kraken
Mark
Index
Observation
```

La ligne principale reste inchangée. Les candidats SPOT n'affichent pas cette section.

Le texte UI précise que l'Open Interest et les valeurs funding sont affichés bruts lorsque leur unité d'affichage n'est pas démontrée, et que le funding prévu est une prévision Kraken, pas un funding futur réalisé.

## Compatibilité API

Le protocole reste :

```text
market-attention-radar-v6
```

`perpetual_ticker` est un champ additif du candidat v6. Le frontend accepte toujours les anciens payloads qui ne contiennent pas ce champ.

## Tests ajoutés / adaptés

Backend :

```text
backend/tests/test_kraken_derivatives_batch47_1_tickers.py
backend/tests/test_market_attention_batch47_1_perpetual_ticker.py
backend/tests/test_market_attention_batch43_2_perpetual.py
```

Couverture : payload bulk valide, plusieurs tickers, champs instantanés, `serverTime`, valeurs optionnelles absentes, suspension, racine invalide, erreur API, symboles invalides, `NaN`, `Infinity`, prix/volumes/OI invalides, doublons, normalisation relative existante, mutualisation du snapshot, fail-soft/fail-closed, compatibilité provider historique, invariance de l'intérêt, du ranking Structure, de `candidate_limit`, de la Structure et des scores adaptatifs.

Frontend :

```text
frontend/src/lib/market-attention.test.mjs
```

Couverture : payload v6 historique sans Futures, OI, funding courant, prédiction distincte, champs absents, statuts partiel/technique/N/A et absence de faux format `%`.

## Validation connue

Validations exécutées par ChatGPT sur la première préparation 47.1 :

```text
python -m py_compile des sources/tests Python modifiés          : PASS
pytest parser/client bulk avec dépendances stub                : PASS — 23/23
smoke local catalogue partagé / normalisation relative         : PASS
node --test --experimental-strip-types market-attention.test   : PASS — 22/22
tsc --noEmit --strict market-attention.ts                      : PASS
parse/transpile ciblé market-attention-dock.tsx                : PASS
```

Validation locale utilisateur après extraction de la première livraison :

```text
pnpm typecheck   : PASS
pnpm test        : PASS — 68/68
git diff --check : PASS (avertissements LF/CRLF uniquement)
pytest -q        : 3 FAILURES dans le nouveau test Batch 47.1, suite arrivée à 100 %
```

Les trois échecs provenaient des fixtures passant `MarketAttentionFilters` à un Radar dont le contrat Batch 45 attend `StructureAwareMarketAttentionFilters`. Le correctif 47.1.1 aligne les fixtures sans élargir la logique de production. La présence du correctif dans `842e6bd7` est confirmée ; une suite backend complète post-correctif n'est pas documentée comme PASS et n'est pas inventée.

## Suite — Batch 47.2

Le Batch 47.2, préparé après l'intégration de 47.1, ajoute uniquement l'historique Open Interest via la Market Analytics publique et une infrastructure de rotation/cache/coverage séparée.

Il préserve le snapshot bulk 47.1 :

```text
fetch_tickers()
volumeQuote
Open Interest instantané
funding instantané / prédiction
mark / index
```

et n'en remplace aucun usage par des appels individuels inutiles.

Voir `docs/47_2_OPEN_INTEREST_HISTORIQUE.md`.

## Invariants préservés

- un seul Agent IA ;
- Radar informatif uniquement ;
- aucune décision `BUY / SELL / HOLD` issue du Radar ;
- Risk Engine autorité finale ;
- exécution SPOT uniquement ;
- aucune exécution PERPETUAL ;
- aucun short, levier ou margin ajouté ;
- PAPER ;
- aucune clé privée Kraken ;
- aucune modification Agent / Risk Engine / Broker ;
- aucune donnée future ni look-ahead ;
- aucun secret ;
- aucune promesse de rendement.
