# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les éléments nécessaires à la reprise.

## Principes actifs

Un seul Agent stratégique, Risk autorité finale, aucune sortie LLM directe vers Broker/Kraken, SPOT sans vente d'actif non détenu, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Market Attention Radar reste strictement observationnel et ne prend aucune décision de trading.

## Référence courante

```text
HEAD GitHub audité : 32320e268722c6e431ae722924bca487ae45d004
Commit              : feat: add market attention volume and market cap filters
Batch 42            : intégré
Batch 43            : intégré
```

## Changelog — 2026-10-02 — Batch 43 filtres volume/capitalisation — intégré

- ajout d'un état runtime unique `MarketAttentionFilters` ;
- ajout d'un filtre minimum `volume_24h_usd` ;
- ajout de filtres de capitalisation par catégories applicatives et/ou bornes min/max ;
- catégories centralisées : `MICRO < 100 M$`, `SMALL < 1 Md$`, `MID < 10 Md$`, `LARGE >= 10 Md$` ;
- volume 24h SPOT/USD dérivé causalement du cache Kraken 5m existant, sans nouvel appel REST par marché ;
- absence de conversion implicite pour les marchés dont le notionnel USD n'est pas prouvé ;
- interface `MarketMetadataProvider` isolant les métadonnées externes ;
- provider initial `CoinPaprikaMarketMetadataProvider`, read-only, sans clé, cache long et fail-soft ;
- filtre capitalisation appliqué avant le scan OHLCV ;
- filtre volume appliqué avant microstructure et avant Market Structure ;
- contrat intégré `market-attention-radar-v6` ;
- endpoints `GET /api/v1/market-attention/filters` et `PUT /api/v1/market-attention/filters` ;
- `/scope` conservé pour compatibilité ;
- cockpit enrichi avec contrôles Volume 24h et Capitalisation, pilotés par l'état backend ;
- aucune modification Agent/Risk/Broker et aucune autorité stratégique pour les métadonnées externes.

Commit fonctionnel intégré : `32320e268722c6e431ae722924bca487ae45d004`.

## ADR-313 — Une vraie capitalisation utilise une source de métadonnées externe

**ADOPTÉ — Batch 43.**

Kraken fournit les données de marché nécessaires au Radar mais pas une supply circulante universelle permettant de calculer une vraie capitalisation pour tous les actifs. Un proxy de liquidité Kraken ne doit donc pas être nommé `market_cap`.

Le Batch 43 introduit `MarketMetadataProvider`. L'implémentation initiale CoinPaprika fournit uniquement des métadonnées descriptives read-only : `circulating_supply`, `market_cap_usd`, `market_cap_rank`, `observed_at`, `provider`.

Cette source n'importe ni Agent, ni Risk, ni Broker et n'a aucune autorité de décision.

## ADR-314 — Cache long et fail-soft des métadonnées de capitalisation

**ADOPTÉ — Batch 43.**

Le provider de métadonnées conserve un cache de six heures. Une indisponibilité externe ne fait jamais tomber le Radar complet. Sans donnée exploitable, la capitalisation reste `UNKNOWN`. Si un filtre de capitalisation est actif, un actif `UNKNOWN` n'est pas prétendu éligible.

## ADR-315 — Volume 24h calculé à partir du pipeline candles canonique

**ADOPTÉ — Batch 43.**

Le Radar dispose déjà d'un historique 5m suffisamment profond. Pour les marchés SPOT cotés directement en USD, le volume notionnel 24h est calculé causalement comme somme `volume_base × close` sur les candles finalisées connues à l'instant du snapshot.

Aucun endpoint `/Ticker` additionnel par marché n'est introduit. Pour les marchés où l'unité USD n'est pas prouvée, `volume_24h_usd` reste `UNKNOWN` au lieu d'inventer une conversion.

## ADR-316 — Les filtres doivent précéder les enrichissements coûteux

**ADOPTÉ — Batch 43.**

Ordre effectif :

```text
catalogue Kraken
-> scope SPOT / PERPETUAL / ALL
-> market cap metadata
-> filtre capitalisation
-> rotation / scan OHLCV
-> calcul volume 24h
-> filtre volume
-> activité / tendance / shortlist
-> microstructure SPOT
-> Market Structure 5m / 15m / 1h / 4h
```

Le filtre volume ne peut raisonnablement précéder l'OHLCV sans dupliquer une source déjà disponible. Il est néanmoins placé avant L2/trades et avant les quatre lectures structurelles.

## ADR-317 — Contrat Radar v6 et cohérence runtime

**ADOPTÉ — Batch 43.**

`market-attention-radar-v6` expose les filtres actifs au niveau global et, sur chaque candidat, les métadonnées disponibles de volume/capitalisation. Le changement de filtre est sérialisé par le verrou runtime existant. Avant le refresh complet, `latest` bascule sur un snapshot `PARTIAL` vide associé aux nouveaux filtres afin de ne jamais présenter une shortlist calculée avec l'ancien réglage comme actuelle.

Les routes v4/v5 restent sérialisables pour préserver les tests/intégrations injectés existants.

## ADR-318 — Formulation précise des sources du Radar

**ADOPTÉ — Batch 43.**

Depuis l'intégration du Batch 43, ne plus écrire sans nuance « Radar Kraken-only ». Utiliser :

```text
prix / OHLCV / tendance / structure / microstructure = Kraken
market cap / circulating supply / rank               = provider metadata externe read-only
trading / ordres                                     = Kraken uniquement
```

## Rappel — Batch 42 intégré

Commit fonctionnel : `003dae8dbfdc052edbad5bfde2c23fa24852eace`.

- Market Structure native `5m / 15m / 1h / 4h` ;
- pivots causaux `HH / HL / LH / LL` ;
- états `BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN` ;
- événements descriptifs `BOS / CHOCH` ;
- contrat intégré `market-attention-radar-v5` ;
- aucune modification Agent/Risk/Broker.

## Points explicitement non décidés

- utilisation du Radar ou de la Market Structure comme contexte de l'Agent stratégique ;
- filtre de shortlist par direction ou structure ;
- conversion FX implicite pour le filtre de volume ;
- réaction stratégique intra-bougie ;
- streaming WebSocket L2/trades ;
- LIVE.
