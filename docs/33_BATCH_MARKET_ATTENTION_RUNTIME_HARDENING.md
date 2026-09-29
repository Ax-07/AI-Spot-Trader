# Batch 33 — Market Attention Runtime Hardening

Date : 2026-09-29

## 1. Statut et base auditée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 78607ce6ab9f2b9459de2b1e1a7127509475283a
Commit     : docs: finalize batch 32 integration status
HEAD fonctionnel Batch 32 : 5a2d07b3fc5208475c1a136690da6648797efde9
```

Le compare GitHub confirme que `78607ce` est un commit documentaire uniquement. Le comportement fonctionnel de départ du Radar est celui du Batch 32 intégré dans `5a2d07b`.

Le Batch 33 décrit ici un **patch proposé/local**. Il ne devient intégré qu'après validation locale utilisateur, commit et push explicites.

Le fichier local suivant reste strictement hors périmètre :

```text
trades_9h_analysis.json
```

Il ne fait pas partie du ZIP.

## 2. Constat runtime confirmé

Le Batch 32 a corrigé la monopolisation du scan par une seule famille de marchés, mais le snapshot runtime a rendu visibles trois défauts indépendants :

1. chaque historique SPOT rechargeait `AssetPairs` avant son appel OHLC ;
2. l'état `VERY_HIGH / ACCELERATING` pouvait associer le meilleur ratio d'un horizon à la meilleure accélération d'un autre horizon ;
3. le JSON Structured Output de recherche publique acceptait des chaînes plus longues que les modèles Pydantic canoniques.

L'audit a aussi confirmé que la liste `web_search_call.action.sources` peut être plus large que les sources réellement utilisées dans les métriques, observations et catalyseurs structurés.

## 3. Kraken SPOT — registry partagé et borné

### Avant

`KrakenCandleProvider._spot_history()` faisait :

```text
fetch_pair_registry()
normalize(symbol)
fetch_ohlcv_history(...)
```

pour chaque historique SPOT.

Un lot Radar de 100 SPOT pouvait donc déclencher environ 100 appels `AssetPairs` en plus des 100 appels OHLC.

### Après

`KrakenCandleProvider` conserve maintenant un unique cache process-local :

```text
_spot_pair_cache: KrakenPairRegistry | None
_spot_pair_cache_lock: asyncio.Lock
```

Politique :

- chargement initial lazy au premier besoin SPOT ;
- symbole présent : normalisation depuis le cache sans appel `AssetPairs` ;
- symbole absent dans un cache déjà chargé : un seul refresh contrôlé ;
- symbole toujours absent : `UnknownKrakenSymbolError` reste fail-closed ;
- accès concurrents : le lock empêche plusieurs chargements/refreshs identiques ;
- après une erreur fournisseur de `AssetPairs`, une fenêtre fail-fast de **2 secondes** évite qu'un même échec soit immédiatement réémis par chaque marché SPOT en attente. Cette fenêtre n'est pas un TTL de catalogue : le prochain appel réessaie après ce délai.

Le cache reste dans le provider de candles canonique. Aucun second catalogue de marchés et aucun second pipeline OHLCV ne sont créés.

## 4. Diagnostic Kraken borné

Le client REST public distingue maintenant, sans exposer le body fournisseur, l'URL de requête ou une donnée sensible :

```text
KrakenTimeoutError     -> timeout / HTTP 408
KrakenNetworkError     -> erreur réseau/transport
KrakenRateLimitError   -> HTTP 429 ou throttling explicitement déclaré dans payload["error"]
KrakenServerError      -> HTTP 5xx
KrakenHTTPError        -> autre erreur HTTP permanente
KrakenAPIError         -> enveloppe API Kraken valide avec payload["error"] non vide
KrakenPayloadError     -> JSON/structure/valeur impossible à normaliser
UnknownKrakenSymbolError -> mapping absent après refresh contrôlé
```

La classification du throttling dans un payload 200 reste volontairement conservatrice : seuls des libellés explicitement reconnaissables comme rate-limit/throttling sont classés ainsi. Une erreur fournisseur ambiguë reste `KrakenAPIError`.

Le Radar expose ces catégories dans ses compteurs bornés. Aucun payload brut n'est journalisé ou transporté dans l'overview.

## 5. Classification multi-timeframe cohérente

Les seuils numériques sont strictement inchangés :

```text
ELEVATED      : ratio >= 1.40
ACCELERATING : ratio >= 1.75 ET acceleration >= 0.25
VERY_HIGH     : ratio >= 2.50 ET acceleration >= 0.50
```

Le changement porte uniquement sur la cohérence d'horizon.

Avant, le code prenait indépendamment :

```text
max(volume_ratio)
max(volume_acceleration)
```

Après, les séquences ratio/accélération gardent l'index de chaque `ActivityHorizonSnapshot`. Un état `VERY_HIGH` ou `ACCELERATING` n'est produit que si **le même horizon complet** satisfait simultanément les deux seuils.

Conséquences attendues :

- cas type ALGO observé : plus de faux `VERY_HIGH` lorsque ratio et accélération viennent de timeframes différents ;
- cas type AAVE observé : plus de faux `ACCELERATING` pour la même raison ;
- cas type ACE avec ratio et accélération élevés sur 15m : reste légitimement `VERY_HIGH` ;
- horizon incomplet : ignoré pour les couples de classification et ne peut pas fabriquer un état.

## 6. Structured Output web aligné sur Pydantic

Le schéma strict `public_attention_v1` encode désormais les limites de chaînes déjà imposées par les modèles canoniques lorsque le sous-ensemble Structured Outputs le permet :

```text
confidence_context             1..2000
metric.name                    1..128
metric.value                   1..256
metric.unit                    <=64
metric.window                  <=64
source_url                     <=2048
observation.text               1..2000
catalyst.description           1..2000
source.title                   1..1000
source.url                     1..2048
```

Les invariants d'appel restent :

```text
tools = [{"type": "web_search"}]
store = false
include = ["web_search_call.action.sources"]
Structured Output strict
```

La validation Pydantic canonique n'est pas affaiblie. Si une donnée structurée échoue encore à cette frontière, l'adaptateur transforme le `ValidationError` Pydantic en `PublicAttentionResearchError` bornée ; le Radar reste fail-soft et ne remonte pas le détail de validation brut dans son diagnostic.

## 7. Sources publiques exposées

La frontière de confiance existante est conservée :

> une URL présente uniquement dans le JSON structuré n'est jamais une source canonique si elle n'existe pas aussi dans les métadonnées provider.

Le filtrage retenu est déterministe :

1. conserver les URLs provider directement référencées par une métrique, observation ou catalyseur ;
2. conserver également les URLs citées par les annotations provider du message ;
3. en l'absence de référence directe, conserver les sources structurées qui sont aussi provider-backed ;
4. si aucun lien fiable n'est démontrable, conserver les sources provider plutôt que d'appliquer une heuristique de pertinence fragile.

Cette stratégie réduit le bruit lorsque le lien est démontrable sans masquer arbitrairement les seules citations vérifiables.

Sans source provider, le résultat reste `PARTIAL` et aucune URL structurée inventée n'est promue.

## 8. Liquidité et couverture — inchangées

Le Batch 33 ne modifie pas le Batch 31 :

```text
SPOT BASE/USD
-> SPOT_BASE_VOLUME_X_5M_CLOSE_ESTIMATE

SPOT non USD
-> notionnel USD null

PERPETUAL
-> current_notional_usd null
-> baseline_notional_usd null
-> notional_delta_usd null
-> liquidity_regime UNKNOWN
```

Le faible volume absolu reste descriptif et ne devient jamais un filtre d'exclusion.

Le Batch 33 ne modifie pas non plus le Batch 32 :

- `scan_limit = 120` ;
- curseurs SPOT/PERPETUAL indépendants ;
- allocation proportionnelle et absence de starvation ;
- `candidate_limit = 20` ;
- `max_web_searches_per_refresh = 8` ;
- aucune recherche web causée par le scan seul.

## 9. Barrières d'architecture préservées

Le module Radar reste sans dépendance vers :

```text
Agent stratégique
Market Discovery
Risk Engine
Broker / order flow
```

Le Radar ne produit aucun `BUY`, `SELL` ou `HOLD` et aucune donnée Radar n'est injectée dans le trading.

`CandleStreamService` reste la source canonique de candles.

## 10. Fichiers du patch

Backend runtime :

```text
backend/src/ai_spot_trader/integrations/kraken/__init__.py
backend/src/ai_spot_trader/integrations/kraken/errors.py
backend/src/ai_spot_trader/integrations/kraken/rest.py
backend/src/ai_spot_trader/integrations/kraken/candles.py
backend/src/ai_spot_trader/integrations/openai_market_attention.py
backend/src/ai_spot_trader/market/attention.py
```

Tests :

```text
backend/tests/test_kraken_candle_spot_registry_cache.py
backend/tests/test_kraken_rest_runtime_hardening.py
backend/tests/test_market_attention_activity_robustness.py
backend/tests/test_market_attention_batch33_regressions.py
backend/tests/test_openai_market_attention_runtime_hardening.py
```

Frontend :

```text
frontend/src/lib/market-attention.ts
frontend/src/lib/market-attention.test.mjs
```

Documentation :

```text
docs/00_ETAT_ACTUEL.md
docs/09_ROADMAP_DEVELOPPEMENT.md
docs/33_BATCH_MARKET_ATTENTION_RUNTIME_HARDENING.md
```

`docs/10_DECISIONS_ET_CHANGELOG.md` reste volontairement inchangé dans le ZIP proposé : il décrit les décisions intégrées. Les décisions du Batch 33 restent marquées **proposées/locales** dans le présent document tant que le patch n'a pas été validé puis poussé.

## 11. Tests réellement exécutés par ChatGPT

Le repository complet et ses environnements installés ne sont pas montés dans l'environnement de préparation. Les tests backend ci-dessous ont donc été exécutés dans un **harnais minimal** qui charge les fichiers réels modifiés et fournit uniquement les contrats de domaine/imports nécessaires.

Exécuté :

```text
python -m py_compile <fichiers Python modifiés + tests Batch 33>
-> succès

pytest -q <harnais ciblé Batch 33>
-> 32 passed

node --experimental-strip-types --test frontend/src/lib/market-attention.test.mjs
-> 7 passed, 0 failed
```

Le harnais backend couvre notamment :

- réutilisation du registry SPOT ;
- concurrence du chargement initial ;
- anti-stampede en cas d'échec `AssetPairs` ;
- refresh contrôlé sur symbole absent ;
- mapping toujours absent fail-closed ;
- diagnostic API/rate-limit/HTTP/réseau ;
- classification même horizon et frontières exactes ;
- horizons incomplets ;
- limites du Structured Output ;
- source structurée non provider-backed refusée ;
- filtrage des sources utilisées/citées ;
- absence provider -> `PARTIAL` ;
- budget web et absence de recherche causée par le scan ;
- rotation 100/20 ;
- notionnels SPOT/USD, SPOT non USD et PERPETUAL ;
- absence de dépendance Agent/Risk/Broker/Market Discovery.

Ces tests ciblés ne remplacent pas la suite complète locale du repository.

## 12. Validation locale requise avant intégration

Depuis `E:\AI-Spot-Trader` :

```powershell
cd backend
pytest -q

cd ..\frontend
pnpm test
pnpm lint
pnpm typecheck
pnpm build

cd ..
git diff --check
git status --short
```

Après extraction, `git status --short` doit montrer uniquement les fichiers Batch 33 modifiés/créés plus le fichier utilisateur hors périmètre :

```text
?? trades_9h_analysis.json
```

Ce dernier ne doit jamais être ajouté au commit Batch 33.

## 13. Critères de validation runtime recommandés

Après succès des suites locales, lancer le backend/frontend puis observer au moins un refresh complet du Radar.

Attendus :

- lot équilibré selon Batch 32, par exemple ~100 SPOT / 20 PERPETUAL pour la population observée ;
- SPOT ne génère plus un appel `AssetPairs` par marché ;
- disparition de l'avalanche `KrakenPayloadError` provoquée par ce comportement ;
- erreurs restantes distribuées dans des catégories plus précises si le provider permet de les démontrer ;
- liquidité SPOT/USD de nouveau renseignée naturellement sur les marchés exploitables ;
- PERPETUAL reste `UNKNOWN` côté liquidité ;
- ALGO/AAVE ne sont plus surclassés par mélange de timeframes ;
- ACE reste `VERY_HIGH` si un même horizon satisfait réellement les deux seuils ;
- enrichissements web ne produisent plus de `ValidationError` de longueur prévisible ;
- sources affichées plus courtes lorsqu'un usage/citation fiable est disponible.

## 14. Intégration

À ce stade :

```text
Batch 33 : patch proposé/local
GitHub main : inchangé
```

L'intégration doit rester une action explicite de l'opérateur après validation locale complète.
