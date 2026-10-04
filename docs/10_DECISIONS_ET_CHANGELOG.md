# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les éléments nécessaires à la reprise.

## Principes actifs

Un seul Agent stratégique, Risk Engine autorité finale, aucune sortie LLM directe vers Broker/Kraken, exécution SPOT sans vente d'actif non détenu, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Le Market Attention Radar reste strictement observationnel et ne prend aucune décision de trading.

## Référence courante

```text
HEAD GitHub observé : c09dd14cab31233f635ff535cbf0298ba3f2bd51
Commit HEAD         : feat: add historical open interest analytics
Batch 45            : intégré via 45d41b7
Batch 46 / 46.1     : intégré via b219365
Batch 47.1          : intégré via 842e6bd7
Batch 47.2          : intégré via c09dd14
Batch 47.3          : patch préparé, non intégré
```

## Changelog — 2026-10-04 — Batch 47.3 Funding historique + Liquidation Volume — proposé

Base auditée : GitHub `main` au HEAD `c09dd14`.

Audit de reprise :

- **confirmé** : Batch 47.2 est intégré via `c09dd14` ;
- **obsolète** : les statuts documentaires présentant 47.2 et ADR-333..336 comme proposés/non intégrés ;
- **confirmé** : `PerpetualAnalyticsScanner` est l'infrastructure historique canonique et doit être étendue, pas dupliquée ;
- **confirmé** : la shortlist et le ranking canoniques sont calculés avant l'enrichissement Analytics ;
- **confirmé par contrat public Kraken** : `funding` expose `rate` et `relativeRate`, chacun en OHLC ;
- **confirmé par documentation Kraken** : le signe du funding relatif distingue le sens du paiement, sans en faire une décision de trading ;
- **confirmé par documentation Kraken** : `liquidation-volume` est un total agrégé de positions forcées à la clôture par intervalle ; aucun split LONG/SHORT n'est démontré ;
- **confirmé par schéma public** : la famille Analytics générique accepte scalaire ou OHLC ;
- **confirmé par smoke live local utilisateur** : `PF_XBTUSD/funding` renvoie `data.rate[]` et `data.relativeRate[]` en OHLC, `timestamp[]` en millisecondes epoch, `more=false`, `errors=[]` ;
- **confirmé par smoke live local utilisateur** : `PF_XBTUSD/liquidation-volume` renvoie `data[]` scalaire non négatif, `timestamp[]` en secondes epoch, `more=false`, `errors=[]`.

Patch 47.3 :

- extension de `KrakenDerivativesAnalyticsClient` avec `fetch_funding_history()` et `fetch_liquidation_volume_history()` ;
- parser Funding strict : objet `data` contenant exactement `rate` et `relativeRate`, longueurs alignées sur `timestamp`, buckets OHLC signés cohérents, timestamps millisecondes normalisés explicitement, ordre temporel strict et `more=false` ;
- conservation séparée de l'absolu/raw et du relatif ; aucune confusion avec la prédiction ticker ;
- parser Liquidation Volume strict : scalaire ou OHLC générique, valeurs finies/non négatives ; aucune dimension directionnelle inventée ;
- réutilisation du même catalogue Futures, sans second transport HTTP ;
- extension provider canonique avec `funding_history()` et `liquidation_volume_history()` ;
- un seul curseur/cache Analytics pour OI, Funding et Liquidation Volume ;
- concurrence globale bornée par `fetch_concurrency` ;
- plafond théorique par défaut : 10 marchés × 3 séries = 30 appels Analytics par refresh ;
- causalité conservatrice 47.2 conservée : un point n'est analysé qu'après `timestamp + interval <= as_of` ;
- Funding : baseline médiane/MAD sur `relativeRate`, score robuste signé, pas de fallback ratio lorsque le MAD est nul afin de ne pas fabriquer une sémantique de ratio sur une série signée ;
- Liquidation Volume : baseline médiane/MAD, caractéristique de spike uniquement ; fallback ratio uniquement si la baseline est non nulle ;
- ajout d'une couverture par série dans `perpetual_analytics_coverage` ;
- cockpit : Funding historique, Liquidation Volume agrégé, caractéristiques et couverture par série ;
- aucun filtre utilisateur Funding/Liquidation ;
- aucune modification Agent / Risk Engine / Broker, aucune exécution PERP.

Validations exécutées dans l'environnement ChatGPT :

```text
python -m py_compile production + tests ciblés                   : PASS
pytest ciblé Batch 47.3 avec stubs du checkout partiel           : PASS — 23/23 après correctif timestamp Funding
smoke logique compatibilité parser/analyse OI Batch 47.2         : PASS
tsc --noEmit --strict market-attention.ts                       : PASS
typecheck ciblé cockpit avec stubs React/UI                     : PASS
node --test market-attention-batch47_3.test.mjs                 : PASS — 4/4
smoke HTTP Kraken Funding                                       : PASS local utilisateur — OHLC + timestamps ms
smoke HTTP Kraken Liquidation Volume                            : PASS local utilisateur — scalaires + timestamps s
backend suite complète avant correctif timestamp Funding         : PASS local utilisateur — 100 %
```

## ADR-337 — OI, Funding et Liquidation Volume partagent une seule rotation/cache Analytics

**PROPOSÉ — Batch 47.3, non intégré.**

Le Batch 47.3 étend `PerpetualAnalyticsScanner` au lieu de créer un scanner Funding et un scanner Liquidation séparés. Un même marché sélectionné par la rotation peut déclencher les trois séries, sous un sémaphore global. Cette décision conserve un coût explicable et évite des populations de couverture divergentes.

Avec la policy actuelle, le budget théorique maximal devient 30 appels par refresh. La limite de marchés et la concurrence restent inchangées ; aucun auto-tuning n'est introduit.

## ADR-338 — Le Funding historique conserve séparément rate, relativeRate et prédiction ticker

**PROPOSÉ — Batch 47.3, non intégré.**

`rate` et `relativeRate` du flux historique Kraken sont stockés séparément. La statistique adaptative porte sur `relativeRate`, tandis que le `rate` absolu/raw reste observable. `fundingRatePrediction` du snapshot ticker reste une prévision Kraken distincte et n'est jamais mélangée à l'historique.

La série étant signée, le Batch 47.3 n'applique pas le fallback de ratio MAD nul utilisé pour des métriques strictement positives. Sans dispersion robuste exploitable, la méthode Funding devient `UNAVAILABLE` plutôt que de fabriquer un score extrême.

## ADR-339 — Liquidation Volume reste agrégé, non directionnel et sans autorité de ranking

**PROPOSÉ — Batch 47.3, non intégré.**

Kraken décrit `liquidation-volume` comme un total par intervalle sans démontrer une composante LONG/SHORT. Le modèle conserve donc une métrique agrégée et ne crée aucun champ `long_liquidations` ou `short_liquidations`.

`LIQUIDATION_VOLUME_SPIKE`, `FUNDING_POSITIVE_EXTREME` et `FUNDING_NEGATIVE_EXTREME` peuvent seulement enrichir un candidat déjà retenu. Elles ne modifient ni `interest_level`, ni `candidate_limit`, ni la clé de tri. Toute influence multi-analytics reste réservée au Batch 47.5.

## Changelog — 2026-10-04 — Batch 47.2 historique Open Interest — intégré

Commit intégré : `c09dd14` (`feat: add historical open interest analytics`).

- extension Market Analytics du client Futures public canonique ;
- parser `open-interest` strict sur buckets OHLC `[open, high, low, close]` ;
- utilisation exclusive du `close` comme valeur historique du bucket ;
- `more=true` rejeté ;
- rotation/cache Analytics séparés de l'OHLCV et de Structure ;
- cache causal, concurrence bornée et diagnostic de couverture ;
- baseline médiane/MAD réutilisant les primitives Batch 46 ;
- caractéristiques `OPEN_INTEREST_EXPANSION` et `OPEN_INTEREST_CONTRACTION` ;
- aucune conversion USD inventée ;
- aucune influence sur le ranking ou la shortlist canonique ;
- contrat v6 additif et cockpit enrichi ;
- aucune capacité d'exécution PERP.

Validation locale observée avant intégration :

```text
pytest -q        : PASS — suite arrivée à 100 %
pnpm typecheck   : PASS
pnpm test        : PASS — 72/72
git diff --check : PASS hors avertissements LF/CRLF
smoke PF_XBTUSD  : PASS — OHLC confirmé, more=false
```

## ADR-333 — Les Analytics Futures historiques utilisent une rotation/cache séparée

**ADOPTÉ — Batch 47.2 intégré via `c09dd14`.**

`PerpetualAnalyticsScanner` possède un curseur déterministe, un cache causal, une concurrence bornée et un diagnostic de couverture séparé des rotations OHLCV et Structure. Les séries suivantes doivent réutiliser cette infrastructure.

## ADR-334 — L'Open Interest est analysé relativement à son propre historique sans unité économique inventée

**ADOPTÉ — Batch 47.2 intégré via `c09dd14`.**

`openInterest` reste une valeur Kraken brute. Aucun `open_interest_usd` n'est créé. L'analyse compare le point courant à une baseline médiane propre au marché et réutilise le MAD normalisé Batch 46.

## ADR-335 — La causalité Analytics applique un délai conservateur d'un intervalle

**ADOPTÉ — Batch 47.2 intégré via `c09dd14`.**

Un point Analytics n'est consommé qu'après `timestamp + interval <= as_of`. Cette règle s'applique aux extensions 47.3 tant qu'une sémantique fournisseur plus précise n'est pas démontrée et testée.

## ADR-336 — L'OI historique n'a pas d'autorité de ranking

**ADOPTÉ — Batch 47.2 intégré via `c09dd14`.**

Le ranking canonique et la shortlist finale sont construits avant l'enrichissement Analytics. Une influence multi-analytics éventuelle est réservée au Batch 47.5.

## Changelog — Batch 47.1 fondations Futures ticker — intégré

Commit : `842e6bd7`.

Décisions actives : un snapshot bulk `/tickers` partagé ; `volumeQuote` conserve sa sémantique ; OI/funding instantanés restent descriptifs ; raw/relatif/prédiction sont séparés ; aucun ranking ou filtre stratégique.

## ADR-331 — Le Radar réutilise un snapshot Futures bulk canonique

**ADOPTÉ — Batch 47.1 intégré via `842e6bd7`.**

Aucun second client Kraken Futures n'est créé pour le contexte ticker.

## ADR-332 — OI/funding instantanés restent descriptifs et leurs unités restent explicites

**ADOPTÉ — Batch 47.1 intégré via `842e6bd7`.**

Aucun suffixe économique ni pourcentage n'est inventé pour les valeurs brutes/prédites dont l'unité d'affichage n'est pas démontrée.

## Décisions antérieures toujours actives

- **ADR-330 — ADOPTÉ via `b219365`** : cible baseline adaptative 12 périodes, plancher 6.
- **ADR-328 — ADOPTÉ via `b219365`** : anomalie robuste = médiane + MAD normalisé.
- **ADR-329 — ADOPTÉ via `b219365`** : ratios historiques observables, contrat v6 additif.
- **ADR-325 — ADOPTÉ via `45d41b7`** : policy Structure et scan Structure séparés.
- **ADR-326 — ADOPTÉ via `45d41b7`** : événements BOS/CHOCH descriptifs, symétriques.
- **ADR-327 — ADOPTÉ via `45d41b7`** : filtres Structure fail-closed sur UNKNOWN.
- **ADR-323 — ADOPTÉ via `c262d54`** : liquidité PERP via `volumeQuote` USD validé.
- **ADR-324 — ADOPTÉ via `c262d54`** : couverture observée, pas auto-corrigée.
- **ADR-321 — ADOPTÉ via `25dcb5c`** : volume PERP USD via turnover quote public Kraken.
- **ADR-322 — ADOPTÉ via `25dcb5c`** : une shortlist PERP vide n'est pas réparée en abaissant le scoring.
