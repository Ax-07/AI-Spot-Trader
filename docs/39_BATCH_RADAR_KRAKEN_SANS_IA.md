# Batch 39 — Market Attention Radar 100 % Kraken, zéro IA/Web

## Référence

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD audité: 2776fc68fb0ff8c094148a246d22de844ee868c7
Commit     : feat: prefilter market attention web research
```

Au démarrage du batch, `docs/00_ETAT_ACTUEL.md` était obsolète : il pointait encore vers `c699e7c` et indiquait à tort que le Batch 38 n'était pas intégré.

## 1. Objectif

Transformer Market Attention en composant entièrement déterministe basé sur les données Kraken :

```text
Market Attention Radar
= données Kraken
+ calculs déterministes
+ score d'intérêt
+ shortlist diversifiée
+ observabilité

0 appel OpenAI
0 recherche Web
0 token LLM
```

Le Radar répond à : « quels marchés présentent un comportement assez inhabituel pour mériter l'attention ? ». Il ne cherche plus à expliquer le mouvement par des news.

## 2. Audit du HEAD intégré

L'audit de `2776fc6` confirme :

- `main.py` instancie `OpenAIWebAttentionResearcher` pour le Radar lorsque `OPENAI_API_KEY` est présent ;
- `market/attention.py` contient le protocole Public Attention, le cache, TTL/cooldown, budget et décisions de recherche ;
- `integrations/openai_market_attention.py` est dédié à cette fonctionnalité ;
- l'API et le frontend exposent encore les résultats et compteurs Web ;
- `core/config.py` ne contient pas de réglage spécifique nécessaire au Radar après retrait de la couche Web ;
- le calcul déterministe Batch 38 est déjà présent et réutilisable ;
- l'analyseur filtre déjà `is_final=True` et `close_time <= observed_at` ;
- la shortlist possède déjà un ranking stable et une diversification par régime de liquidité.

## 3. Architecture retenue

```text
Kraken
  ↓
OHLCV canonique 5m
  ↓
5m / 15m / 1h / 4h
  ↓
volume / prix / volatilité / range / liquidité
  ↓
caractéristiques déterministes
  ↓
LOW / MEDIUM / HIGH / VERY_HIGH
  ↓
shortlist diversifiée
  ↓
observabilité read-only
```

Aucun chemin du Radar ne possède un client OpenAI ou un outil Web.

## 4. Contrat runtime

`MarketAttentionPolicy` ne contient plus de TTL Public Attention, cooldown événementiel ou budget Web.

`MarketAttentionSnapshot` ne contient plus que le snapshot déterministe d'activité. Les types Public Attention et décisions de recherche sont supprimés.

`MarketAttentionOverview` ne conserve aucun compteur toujours à zéro. Le protocole devient :

```text
market-attention-radar-v2
```

Le statut global est dérivé uniquement de la disponibilité/fraîcheur/erreur des données Kraken.

## 5. Scoring et caractéristiques

Les caractéristiques Batch 38 sont conservées sans changement de sémantique :

- `TRENDING` ;
- `VOLUME_ANOMALY` ;
- `VOLATILITY_EXPANSION` ;
- `BREAKOUT_WATCH` ;
- `REVERSAL_WATCH` ;
- `CONSOLIDATING` ;
- `PRICE_VOLUME_DIVERGENCE`.

Le score d'intérêt agrège des faits observables et produit `LOW/MEDIUM/HIGH/VERY_HIGH`. Il reste non directionnel. Aucune caractéristique ne devient `BUY`, `SELL` ou `HOLD`.

## 6. Diversification et liquidité

La logique de shortlist conserve l'invariant corrigé en Batch 38 : les leaders de régimes de liquidité sont d'abord préservés selon l'activité inhabituelle, puis la shortlist finale est triée avec la clé déterministe. Un marché `MICRO` intéressant n'est donc pas éliminé mécaniquement par les marchés les plus liquides.

## 7. Fail-soft et causalité

- données insuffisantes : `PARTIAL`, sans métrique inventée ;
- données périmées : `STALE` ;
- erreurs Kraken : agrégées avec catégories bornées ;
- étapes de payload Kraken : allowlist bornée ;
- contenu d'exception fournisseur : non exposé dans le snapshot ;
- bougies non finalisées ou futures : ignorées ;
- aucune interpolation de prix ;
- aucun second pipeline OHLC.

## 8. Wiring FastAPI

`build_market_attention()` construit uniquement :

- le `CandleStreamService` partagé ;
- `KrakenAttentionCatalogue` ;
- `MarketAttentionPolicy` ;
- `MarketAttentionRadar`.

La clé OpenAI et `resolved_settings.llm_model` ne sont plus consultés pour construire le Radar. Les usages OpenAI de l'Agent stratégique/chat restent séparés et inchangés.

## 9. API et frontend

Le cockpit conserve :

- état du Radar ;
- catalogue, marchés scannés et marchés frais ;
- candidats ;
- état d'activité ;
- niveau d'intérêt ;
- caractéristiques ;
- raisons du niveau ;
- liquidité ;
- fraîcheur et qualité ;
- ratios volume/range/volatilité ;
- diagnostics Kraken.

Sont retirés : sources publiques, catalyseurs Web, statut de recherche, date de recherche, compteurs Web, cache/budget/recherche IA.

## 10. Suppressions

Après audit de références, les composants dédiés à l'ancien chemin Public Attention n'ont plus d'usage runtime :

```text
backend/src/ai_spot_trader/integrations/openai_market_attention.py
backend/tests/test_openai_market_attention.py
backend/tests/test_openai_market_attention_runtime_hardening.py
```

Ils doivent être supprimés du checkout lors de l'application du batch.

## 11. Tests attendus

La couverture adaptée vérifie : marché normal, volume anormal, tendance multi-horizons, expansion de volatilité, breakout, retournement, consolidation, divergence prix/volume, diversification `MICRO`, données insuffisantes, données périmées, erreur Kraken fail-soft, exclusion des bougies futures/non finalisées, ranking stable, isolation Agent/Risk/Broker/Discovery, `informative_only=True`, absence de chemin OpenAI/Web, contrat API v2 et frontend.

La suite backend complète et le typecheck frontend doivent être exécutés dans le checkout utilisateur après extraction.

## 12. Hors périmètre

Aucun trade Kraken, carnet d'ordres L2, spread, profondeur, déséquilibre bid/ask, intensité de trades ou slippage théorique n'est ajouté. Ces éléments sont réservés au Batch 40.
