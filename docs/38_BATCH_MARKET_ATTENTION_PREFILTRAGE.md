# Batch 38 — Market Attention Radar : préfiltrage Kraken et maîtrise du coût IA

## Référence

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD audité: c699e7ce9fc4f9f43f005d7e8c19199a30befdf1
Commit     : feat: align AI decisions with candle closes
```

Le document `docs/00_ETAT_ACTUEL.md` était obsolète au début du batch : il pointait encore sur `9fc6a4a` et décrivait le Batch 37 comme non intégré.

## 1. Audit confirmé

Le Radar intégré avant Batch 38 possédait déjà :

- un catalogue Kraken ;
- un scan canonique en candles 5m ;
- les horizons 5m / 15m / 1h / 4h ;
- volume relatif, accélération, prix, volatilité et liquidité ;
- une shortlist d'activité inhabituelle ;
- un cache Public Attention ;
- un enrichissement OpenAI Responses + `web_search` ;
- un plafond de recherches par refresh.

Valeurs intégrées avant patch :

```text
refresh radar                  = 300 s
scan_limit                     = 120
candidate_limit                = 20
max_web_searches_per_refresh   = 8
public_attention_ttl_seconds   = 1800 s
```

La dépense principale vient donc du nombre de recherches publiques, pas de la longueur du prompt. L'existant est suffisamment canonique pour évoluer sans second pipeline OHLC.

## 2. Architecture retenue

```text
catalogue Kraken
        ↓
scan OHLCV 5m canonique
        ↓
activité + liquidité
        ↓
structure déterministe descriptive
        ↓
niveau d'intérêt déterministe
        ↓
shortlist réduite
        ↓
recherche publique seulement si HIGH / VERY_HIGH
et seulement si cache/événement le justifie
```

Le Radar reste **INFORMATIF — N'INFLUENCE PAS LE TRADING**.

## 3. Faits structurels ajoutés

Les horizons réutilisent les groupes de candles déjà construits par `MarketActivityAnalyzer` et ajoutent :

- retour de la fenêtre précédente ;
- range médian de baseline ;
- ratio d'expansion du range ;
- volatilité réalisée médiane de baseline ;
- ratio d'expansion de volatilité ;
- distance descriptive au plus haut/bas historique de la fenêtre de référence.

Aucun RSI/MACD ou collection d'indicateurs redondants n'est ajouté.

## 4. Caractéristiques descriptives

```text
TRENDING
VOLUME_ANOMALY
VOLATILITY_EXPANSION
BREAKOUT_WATCH
REVERSAL_WATCH
CONSOLIDATING
PRICE_VOLUME_DIVERGENCE
```

Un marché peut porter plusieurs caractéristiques. Les seuils sont déterministes et décrivent uniquement l'état observé.

## 5. Niveau d'intérêt Radar

```text
LOW
MEDIUM
HIGH
VERY_HIGH
```

Le score interne agrège des faits descriptifs :

- anomalie de volume ;
- expansion de volatilité/range ;
- tendance cohérente sur plusieurs horizons ;
- breakout/reversal descriptif ;
- divergence prix/volume ;
- état d'activité ACCELERATING / VERY_HIGH ;
- régime de liquidité relatif.

`MICRO` peut réduire l'intérêt d'un cran. `CONSOLIDATING` reste une information descriptive sans poids positif à elle seule.

Le résultat ne prédit pas le futur et ne code aucune direction de trade.

## 6. Politique de recherche publique

Valeurs Batch 38 :

```text
candidate_limit                       = 10
max_web_searches_per_refresh          = 2 (limite dure 3)
public_attention_ttl_seconds          = 7200
public_attention_event_cooldown       = 900
```

Règles :

- `LOW` / `MEDIUM` : aucune nouvelle recherche ;
- `HIGH` / `VERY_HIGH` : éligible ;
- cache frais : réutilisé ;
- cache expiré : recherche possible ;
- événement significatif après cooldown : refresh anticipé possible ;
- budget épuisé : aucune recherche supplémentaire ;
- aucun appel n'est effectué pour « remplir » le quota.

Événements reconnus :

```text
NEW_HIGH_INTEREST
CACHE_EXPIRED
RETRY_AFTER_ERROR
INTEREST_ESCALATION
BREAKOUT_EVENT
REVERSAL_EVENT
NEW_TOP_MARKET
```

Raisons explicites de non-recherche :

```text
INTEREST_BELOW_HIGH
RESEARCHER_NOT_CONFIGURED
CACHE_FRESH
EVENT_COOLDOWN
BUDGET_EXHAUSTED
```

## 7. Absence de burst

La boucle de recherche reste séquentielle et le compteur est vérifié avant chaque appel. Le plafond est donc respecté au niveau du refresh et aucune vague parallèle de `web_search` n'est introduite.

## 8. Observabilité

`MarketAttentionOverview` expose en plus :

- candidats éligibles à une recherche publique ;
- recherches réellement lancées ;
- candidats servis par cache ;
- refresh événementiels ;
- recherches évitées/skippées.

Chaque `MarketAttentionSnapshot` expose `public_research` avec l'éligibilité, l'appel effectué ou non, l'utilisation du cache, le trigger et la raison éventuelle du skip.

Les compteurs sont calculés par actif afin d'éviter de compter deux fois un même asset présent en SPOT et PERPETUAL.

## 9. Prompt OpenAI

Audit : le prompt actuel est déjà observationnel, structuré et sourcé. Il interdit BUY/SELL/HOLD, direction et probabilités. Il ne demande pas au modèle de recalculer le volume Kraken.

Aucune réduction agressive de prompt n'est appliquée dans ce batch : le levier économique principal est la raréfaction des recherches.

## 10. Modèle OpenAI du Radar

Audit confirmé : `main.py` passe actuellement `resolved_settings.llm_model` au `OpenAIWebAttentionResearcher`.

Option recommandée pour un batch suivant :

```text
Agent stratégique    -> modèle Campaign/configurable
Market Attention     -> modèle auxiliaire distinct, Luna par défaut
```

Cette séparation n'est pas intégrée dans Batch 38 afin de ne pas modifier en même temps le contrat de configuration process. Le point reste explicitement à décider.

## 11. Invariants préservés

- un seul Agent stratégique ;
- Risk Engine final ;
- PAPER ;
- aucune sortie LLM vers un ordre ;
- aucun second pipeline OHLC ;
- aucun look-ahead ;
- aucun secret ;
- aucune dépendance Radar vers Agent/Risk/Broker/Discovery ;
- aucune recommandation LONG/SHORT ;
- Market Attention reste `informative_only=True`.

## 12. Tests du batch

Le fichier `backend/tests/test_market_attention_batch38_prefilter.py` couvre :

1. marché normal -> LOW ;
2. anomalie de volume isolée insuffisante ;
3. tendance + breakout -> intérêt élevé ;
4. reversal -> intérêt élevé sans signal directionnel ;
5. cache frais -> pas de répétition ;
6. événement significatif -> refresh anticipé après cooldown ;
7. budget par défaut 2 et limite dure 3 ;
8. aucun burst au-dessus du budget ;
9. ranking déterministe stable ;
10. historique insuffisant -> fail-soft ;
11. candle future exclue ;
12. `informative_only=True` ;
13. isolation vis-à-vis des composants de trading;
14. préservation de la diversification historique par régime de liquidité, y compris lorsque `candidate_limit` est inférieur au nombre de régimes représentés.

## 13. État de validation ChatGPT

Après la validation locale utilisateur, un correctif a été appliqué : le premier patch utilisait le nouveau tri `interest/liquidity` pour choisir les leaders de régime. Avec un `candidate_limit` inférieur au nombre de régimes, ce tri pouvait écarter `MICRO` avant même que la diversification historique ne joue.

Le correctif conserve `_activity_sort_key` pour sélectionner les leaders de régimes, puis applique le tri déterministe Batch 38 uniquement à la shortlist déjà diversifiée. La liquidité reste donc un contexte descriptif et un facteur d'intérêt, sans devenir un filtre qui supprime mécaniquement les petites capitalisations/liquidités.

Exécuté dans un harness local minimal reproduisant les contrats de domaine nécessaires, y compris une reproduction du test `test_small_liquidity_market_remains_candidate_and_shortlist_is_regime_diversified` :

```text
19 passed
```

`py_compile` a également été exécuté sur :

```text
backend/src/ai_spot_trader/market/attention.py
backend/tests/test_market_attention_batch38_prefilter.py
```

La suite complète du repository ne peut pas être déclarée réussie ici car le checkout GitHub complet n'était pas disponible dans l'environnement d'exécution local. Elle doit être exécutée après extraction dans le repo utilisateur.
