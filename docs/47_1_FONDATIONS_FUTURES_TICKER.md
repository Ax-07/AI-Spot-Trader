# Batch 47.1 — Fondations Futures ticker du Market Attention Radar

## Statut

**Patch préparé, non intégré.**

Base auditée :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : b2193654ed3ba9db890c6129545acd90e238b0f1
Commit     : feat: add adaptive statistical radar baseline
```

Le HEAD a été revérifié avant modification. Le commit `b219365` contient bien le Batch 46 et son plancher de compatibilité H4 à 6 périodes ; les statuts documentaires qui le présentaient encore comme proposé étaient donc obsolètes.

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

## Audit de l'existant

Avant ce batch, `KrakenAttentionCatalogue.volume_24h_usd_by_market()` appelait directement la méthode privée :

```text
_derivatives._get_json("/tickers", ...)
```

puis parsait uniquement `volumeQuote`.

Le client public canonique `KrakenDerivativesPublicClient` existait déjà. Le Batch 47.1 ne crée donc aucun second client : il ajoute une méthode publique `fetch_tickers()` au client existant et un parser bulk typé.

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

La documentation historique Kraken distingue d'ailleurs `fundingRate` et `relativeFundingRate`, ce qui justifie de ne pas conflater la valeur brute avec le taux relatif interne existant.

## Mutualisation du bulk ticker

Le chemin Radar devient :

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

Dans un refresh Radar utilisant le catalogue Kraken réel, le filtre volume, la liquidité et le contexte Futures sont donc alimentés par le même snapshot bulk. Le fallback `volume_24h_usd_by_market()` reste disponible pour compatibilité avec les anciens tests/providers, mais le Radar préfère la nouvelle méthode partagée lorsqu'elle existe.

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

La panne ticker reste fail-soft : sans filtre volume actif, l'activité OHLCV, la Structure et la capitalisation continuent. Avec un filtre volume actif, l'absence de `volumeQuote` conserve le comportement fail-closed Batch 43.2 via `UNKNOWN_TECHNICAL_ERROR` / `UNKNOWN_MISSING_QUOTE_VOLUME`.

## Absence d'impact sur le ranking

Les champs Futures sont attachés au snapshot candidat mais ne sont consultés par aucune clé de tri, aucun calcul d'intérêt et aucun filtre de shortlist.

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

L'Open Interest et le funding ne peuvent donc pas introduire un candidat ni modifier son rang dans ce batch.

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

Couverture ajoutée : payload bulk valide, plusieurs tickers, champs instantanés, `serverTime`, valeurs optionnelles absentes, suspension, racine invalide, erreur API, symboles invalides, `NaN`, `Infinity`, prix/volumes/OI invalides, doublons, normalisation relative existante, mutualisation du snapshot, fail-soft/fail-closed, compatibilité provider historique, invariance de l'intérêt, du ranking Structure, de `candidate_limit`, de la Structure et des scores adaptatifs.

Frontend :

```text
frontend/src/lib/market-attention.test.mjs
```

Couverture : payload v6 historique sans Futures, OI, funding courant, prédiction distincte, champs absents, statuts partiel/technique/N/A et absence de faux format `%`.

## Validation exécutée par ChatGPT

Le repository complet n'était pas disponible dans le conteneur et l'accès réseau GitHub depuis le shell était indisponible. Les validations suivantes ont réellement été exécutées :

```text
python -m py_compile des sources/tests Python modifiés        : PASS
pytest parser/client bulk sur le vrai derivatives.py avec stubs : PASS — 23/23
smoke local catalogue partagé / normalisation relative       : PASS
node --test --experimental-strip-types market-attention.test : PASS — 22/22
tsc --noEmit --strict market-attention.ts                    : PASS
parse/transpile ciblé market-attention-dock.tsx              : PASS
```

Le harnais `pytest` du parser injecte uniquement les dépendances de package absentes du checkout partiel ; le fichier `derivatives.py` et le test Batch 47.1 exécutés sont ceux du patch.

Validation locale utilisateur après extraction de la première livraison :

```text
pnpm typecheck   : PASS
pnpm test        : PASS — 68/68
git diff --check : PASS (avertissements LF/CRLF uniquement)
pytest -q        : 3 FAILURES dans le nouveau test Batch 47.1, suite arrivée à 100 %
```

Les trois échecs ne provenaient ni du parser bulk ni du chemin Radar Futures : les scénarios appelaient le Radar Batch 45 avec un `MarketAttentionFilters` générique. `StructureAwareFilteredMarketAttentionRadar.set_filters()` attend un `StructureAwareMarketAttentionFilters`; Pydantic 2.13 refuse de convertir implicitement une autre instance `BaseModel` via `model_validate`. Le correctif 47.1.1 utilise donc directement le modèle structure-aware dans ces scénarios, avec tous les filtres Structure laissés à leur valeur par défaut. Aucune logique de production n'est modifiée pour contourner un défaut de fixture.

La suite backend complète doit être relancée après extraction du correctif ; elle n'est pas déclarée PASS ici.

Un smoke HTTP public réel sur `https://futures.kraken.com/derivatives/api/v3/tickers` a été tenté depuis l'environnement, mais l'accès direct à cet endpoint était bloqué ; aucun résultat live n'est donc revendiqué.

## Validation locale requise

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

## Hors périmètre 47.2+

```text
endpoint Market Analytics historique
open-interest historique
funding historique
liquidation-volume
CVD
aggressor-differential
rotation/cache/coverage Analytics historique
score MAD OI/funding historique
ranking avancé basé sur Futures
```

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
