# Batch 34 — Market Attention Runtime Recovery

## 1. Base auditée

- repository : `Ax-07/AI-Spot-Trader` ;
- branche : `main` ;
- HEAD GitHub réel audité : `4a516fde33853fe84d18bd8c4780753c0db58214` ;
- commit : `fix: harden market attention runtime` ;
- Batch 33 confirmé intégré ;
- `docs/00_ETAT_ACTUEL.md` et `docs/09_ROADMAP_DEVELOPPEMENT.md` étaient encore restés sur `78607ce` / Batch 33 proposé et sont corrigés dans ce patch.

## 2. Symptômes runtime pris comme faits

Snapshot du 29/09/2026 après intégration Batch 33 :

- scan : `120`, dont `100 SPOT` et `20 PERPETUAL` ;
- SPOT : `100 ERROR`, tous `KrakenPayloadError` ;
- PERPETUAL : `7 AVAILABLE`, `13 PARTIAL`, `0 ERROR` ;
- candidats : `5` ;
- recherches web : `5`, toutes `ERROR / PublicAttentionResearchError`.

La classification activité même-horizon fonctionne et n'est pas modifiée.

## 3. Audit Kraken

### Confirmé

Le catalogue Market Attention a effectivement chargé `1633` marchés. Le catalogue SPOT appelle lui aussi `KrakenPublicRestClient.fetch_pair_registry()` puis `parse_asset_pairs_payload()`. Le parsing `AssetPairs` n'est donc pas un échec structurel déterministe sur toutes les réponses du runtime observé.

Le chemin OHLC SPOT, en revanche, impose au HEAD Batch 33 :

```text
raw result key == expected display symbol
```

avant même de parser les lignes. Cette contrainte est plus stricte que nécessaire pour un endpoint demandé pour **une seule paire** et elle transforme toute clé legacy/internal Kraken sans slash en `KrakenPayloadError`.

La documentation Kraken actuelle conserve `assetVersion=1` comme contrat demandé : la réponse doit normalement utiliser les display names slash-separated. Elle documente aussi le format interne historique (par exemple `XXBTZUSD`) lorsque cette version n'est pas appliquée, et l'écosystème Kraken a déjà connu des réponses REST dont le nom retourné différait du nom demandé alors que la paire était la bonne.

### Limite du diagnostic rétroactif

Le Batch 33 ne conservait que `type(exc).__name__` dans l'overview. Le texte précis du `KrakenPayloadError` et la clé wire reçue n'ont pas été persistés. Il est donc impossible de reconstruire après coup la valeur brute exacte ayant échoué sans inventer une donnée absente.

Le correctif est volontairement conservateur :

- la requête garde `assetVersion=1` ;
- le payload doit toujours contenir exactement une série ;
- une clé display avec `/` doit toujours correspondre exactement au marché demandé ;
- seule une clé non-display/legacy sans `/` est tolérée comme alias de l'unique paire demandée ;
- plusieurs séries, clé vide/invalide, autre paire display ou structure OHLC invalide restent fail-closed.

Cette correction couvre le défaut structurel démontré sans affaiblir les validations de contenu OHLC.

## 4. Audit OpenAI

Le modèle configuré par défaut reste `LLMModel.LUNA`, utilisé par `OpenAIWebAttentionResearcher` via `resolved_settings.llm_model`.

La documentation OpenAI actuelle indique :

- GPT-5.6 Luna supporte Responses API, Structured Outputs et Web Search ;
- Structured Outputs n'accepte qu'un sous-ensemble de JSON Schema ;
- pour les chaînes, les propriétés supportées documentées sont `pattern` et `format` ;
- un schéma strict contenant des mots-clés non supportés provoque une erreur de requête.

Le Batch 33 avait ajouté `minLength` / `maxLength` dans `PUBLIC_ATTENTION_SCHEMA`. Ces contraintes sont retirées **uniquement du schéma wire**.

Les bornes canoniques restent dans les modèles Pydantic `PublicAttention*` et continuent donc à être vérifiées après la sortie structurée.

Contrat de requête conservé :

```text
strict=true
tools=[{"type":"web_search"}]
store=false
include=["web_search_call.action.sources"]
```

## 5. Diagnostic OpenAI borné

`PublicAttentionResearchError` reste la classe de base fail-soft, avec des sous-types ne contenant ni body brut, ni URL de requête, ni secret :

- `PublicAttentionTransportError` ;
- `PublicAttentionContractError` pour HTTP 400 contrat/schema ;
- `PublicAttentionRateLimitError` pour HTTP 429 ;
- `PublicAttentionServerError` pour HTTP 5xx ;
- `PublicAttentionHTTPError` pour les autres HTTP permanents ;
- `PublicAttentionIncompleteError` pour une réponse non complétée/refusée/sans sortie unique ;
- `PublicAttentionValidationError` pour JSON structuré ou validation Pydantic invalide.

Comme le Radar publie déjà `type(exc).__name__`, ce raffinement devient visible sans changer le modèle du Radar ni le frontend.

## 6. Sources publiques

Règle Batch 33 inchangée :

- une URL uniquement présente dans le JSON structuré n'est jamais une source canonique ;
- priorité aux sources/citations effectivement retournées par le provider ;
- une référence structurée peut seulement sélectionner/enrichir une URL déjà provider-backed ;
- fallback conservateur sur métadonnées provider lorsqu'aucun lien plus précis n'est démontrable.

## 7. Tests de régression ajoutés/actualisés

Kraken :

- payload OHLC mono-paire avec clé legacy/internal `XXBTZUSD` accepté pour `BTC/USD` ;
- autre clé display `ETH/USD` refusée pour `BTC/USD` ;
- requête conserve `pair=BTC/USD` et `assetVersion=1` ;
- cache registry, lock async, refresh contrôlé et anti-stampede du Batch 33 non modifiés ;
- tests transport/API/429 existants restent applicables.

OpenAI :

- absence récursive de `minLength` / `maxLength` dans le schéma wire ;
- limites Pydantic maximales toujours acceptées ;
- dépassement Pydantic toujours rejeté après sortie ;
- `web_search / store / include / strict` inchangés ;
- HTTP 400, 429, 5xx, transport et réponse incomplète classifiés séparément ;
- détails de body/transport non exposés ;
- sources structurées non provider-backed toujours exclues.

## 8. Hors périmètre

Aucun changement sur :

- `scan_limit = 120` ;
- allocation SPOT/PERPETUAL et curseurs Batch 32 ;
- `candidate_limit = 20` ;
- `max_web_searches_per_refresh = 8` ;
- seuils activité ;
- classification même-horizon ;
- notionnels/liquidité ;
- Agent / prompts / Market Discovery / Risk / Broker / ordre ;
- PAPER/LIVE.

## 9. État d'intégration

Ce document décrit le **patch Batch 34 proposé/local** livré en ZIP. Il ne doit pas être interprété comme déjà intégré à GitHub tant que l'utilisateur n'a pas extrait, validé, commité et poussé explicitement le patch.
