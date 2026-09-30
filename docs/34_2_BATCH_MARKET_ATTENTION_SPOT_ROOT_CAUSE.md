# Batch 34.2 — Market Attention SPOT Root Cause

## Objet

Diagnostiquer puis corriger la panne runtime où les 100 marchés SPOT du refresh Market Attention du 29/09/2026 terminaient en `KrakenPayloadError`, sans modifier le trading, les seuils du Radar, le budget web ou Public Attention sans preuve supplémentaire.

## Base et resynchronisation

Au démarrage du batch :

```text
Repository       : Ax-07/AI-Spot-Trader
Branche          : main
HEAD GitHub réel : 4a516fde33853fe84d18bd8c4780753c0db58214
Commit           : fix: harden market attention runtime
HEAD référencé par docs/00 avant mise à jour : 78607ce6ab9f2b9459de2b1e1a7127509475283a
```

Le delta `78607ce6..4a516fde` correspond à l'intégration du Batch 33 Runtime Hardening.

Le working tree utilisateur Batch 34/34.1 n'était pas monté dans l'environnement ChatGPT. Les résultats locaux/runtime fournis par l'utilisateur ont donc été traités comme état courant prioritaire ; aucun test complet sur ce working tree n'est revendiqué.

## Runtime de départ confirmé

Refresh utilisateur du 29/09/2026 :

- catalogue : `1633` ;
- scannés : `120` ;
- SPOT : `100` ;
- PERPETUAL : `20` ;
- SPOT : `0 AVAILABLE / 0 PARTIAL / 100 ERROR` ;
- PERPETUAL : `6 AVAILABLE / 14 PARTIAL / 0 ERROR` ;
- `KrakenPayloadError : 100` ;
- autres erreurs Kraken : `0`.

Le cache partagé/anti-stampede Batch 33 implique qu'une erreur de chargement du registre SPOT peut être répercutée sur tous les marchés SPOT en attente sans créer une rafale `AssetPairs`.

## Confirmé / obsolète / manquant / à décider

### Confirmé

1. Le parseur intégré avant Batch 34.2 imposait `"/" in raw_symbol` pour chaque clé de `AssetPairs.result`.
2. Kraken documente plusieurs versions d'identifiants pour une paire : clé REST interne, `altname`, `wsname`, `base`, `quote`. Les exemples officiels montrent notamment des clés internes avec préfixes historiques et un `wsname` slash-separated distinct.
3. Le projet canonise déjà Bitcoin en `BTC` alors que Kraken conserve `XBT` dans plusieurs interfaces ; Dogecoin présente le même besoin `XDG -> DOGE`.
4. Exiger que la clé de dictionnaire soit elle-même le symbole display rend le registre global vulnérable à une entrée REST interne pourtant exploitable via `wsname`/métadonnées.
5. Une reproduction ciblée avec des clés réalistes telles que `XXBTZUSD` faisait échouer l'ancien contrat de parsing et passe avec le nouveau parseur.
6. L'overview perdait le stage attaché à `KrakenPayloadError` en ne conservant que `type(exc).__name__`.

### Obsolète

- considérer systématiquement la clé `AssetPairs.result` comme symbole canonique display ;
- déduire un préfixe legacy en supprimant aveuglément le premier `X` ou `Z` ; cette méthode casserait des actifs légitimes comme `XTZ` ou `ZRX`.

### Manquant avant Batch 34.2

- compteurs agrégés de stage payload dans `MarketAttentionOverview` ;
- tests avec clés REST internes et aliases display/canoniques ;
- distinction testée des stages payload dans les chemins OHLC.

### À confirmer localement

Le snapshot antérieur ne transportait pas le stage, donc il ne permet pas d'affirmer a posteriori quel stage précis représentait les 100 erreurs du refresh du 29/09. Le défaut `AssetPairs` est reproductible et corrigé ; le refresh post-extraction doit confirmer que les SPOT redeviennent exploitables et, sinon, `activity_payload_stage_counts` identifiera le stage restant sans exposer les données provider.


## Cause runtime finale confirmée — borne OHLC `720/721`

Après le premier correctif, l'utilisateur a exécuté avec succès :

- les tests ciblés Batch 34/34.1/34.2 ;
- la suite backend complète `pytest -q` à 100 % ;
- `git diff --check` sans erreur, hors warnings LF/CRLF.

Un refresh après redémarrage complet du backend conservait néanmoins :

```text
SPOT ERROR                 : 100
KrakenPayloadError         : 100
OHLC_SERIES                : 100
ASSET_PAIRS_*              : 0
OHLC_PAIR_KEY/ROW/etc.     : 0
```

Le test direct du même chemin technique (`httpx` + endpoint public Kraken + mêmes paramètres + `_parse_ohlcv_payload`) a ensuite reproduit exactement :

```text
HTTP: 200
ERROR_COUNT: 0
RESULT_KEYS: ['BTC/USD', 'last']
SERIES_COUNT: 1
SERIES_KEY: BTC/USD
SERIES_TYPE: list
ROW_COUNT: 721
PARSER: KrakenPayloadError
STAGE: OHLC_SERIES
```

La cause est donc démontrée : `_parse_ohlcv_payload` rejetait `len(raw_rows) > 720`. Kraken documente actuellement une limite de 720 entrées et une dernière entrée correspondant à la période courante non finalisée, mais le service public réel a renvoyé 721 lignes sur la fenêtre reproduite le 29/09/2026.

Le correctif est volontairement borné :

- `KRAKEN_SPOT_OHLC_MAX_ROWS = 720` reste la profondeur provider utilisée par le service ;
- `KRAKEN_SPOT_OHLC_MAX_RESPONSE_ROWS = 721` autorise exactement l'overshoot runtime observé ;
- `722+` reste rejeté avec `KrakenPayloadStage.OHLC_SERIES` ;
- aucune donnée brute provider n'est exposée ;
- aucune modification de Market Attention scoring, Public Attention, Agent, Risk, Broker ou PAPER/LIVE.

Un test de régression vérifie explicitement `721` accepté et `722` rejeté.

## Correction `AssetPairs`

Le nouveau parseur :

1. valide strictement l'enveloppe `error/result` ;
2. valide strictement chaque entrée ;
3. traite la clé `result` comme alias provider ;
4. dérive le symbole canonique en priorité depuis `wsname` ;
5. accepte en repli une clé déjà slash-separated ;
6. accepte en dernier repli `base/quote` avec une table **exacte** d'aliases legacy Kraken ;
7. conserve la clé REST interne, `altname` et `wsname` comme aliases de résolution ;
8. déduplique seulement la représentation canonique d'une même paire ;
9. rejette les collisions d'aliases ;
10. vérifie la cohérence entre `wsname`, une éventuelle clé display et `base/quote` lorsqu'ils sont simultanément disponibles ;
11. rejette une entrée sans identité exploitable ou contradictoire avec `ASSET_PAIRS_SYMBOL`.

Aucune entrée invalide n'est ignorée silencieusement. Aucun seuil arbitraire d'entrées à sauter n'est introduit.

## Canonicalisation legacy

La table legacy est explicite et conservative. Elle couvre notamment :

- `XXBT / XBT -> BTC` ;
- `XXDG / XDG -> DOGE` ;
- les anciens identifiants exacts `XETH`, `XLTC`, `XMLN`, `XREP`, `XXLM`, `XXMR`, `XXRP`, `XZEC`, `XETC` ;
- les fiat legacy exacts `ZUSD`, `ZEUR`, `ZGBP`, `ZJPY`, `ZCAD`, `ZAUD`, `ZCHF`.

Il n'existe aucune règle générique « retirer X/Z ».

## Diagnostic payload borné

`MarketAttentionOverview` ajoute :

```text
activity_payload_stage_counts
```

Stages admis :

- `ASSET_PAIRS_PAYLOAD` ;
- `ASSET_PAIRS_ENTRY` ;
- `ASSET_PAIRS_SYMBOL` ;
- `OHLC_RESULT` ;
- `OHLC_SERIES` ;
- `OHLC_PAIR_KEY` ;
- `OHLC_ROW` ;
- `OHLC_TIMESTAMP` ;
- `OHLC_NUMERIC`.

Le Radar mémorise seulement le stage allowlisté associé au marché pendant le refresh. Le snapshot public ne contient pas :

- message d'exception ;
- payload/body Kraken ;
- URL ;
- provider key ;
- symbole provider brut ;
- réponse HTTP complète ;
- secret.

Un stage inconnu ou muté hors allowlist est ignoré dans ces compteurs.

## OHLC

La validation locale complète du premier ZIP 34.2 a démontré une régression : Kraken peut retourner pour l'unique série demandée une clé display/provider équivalente au symbole canonique, notamment `XBT/USD`, `XBTUSD` ou `XXBTZUSD` pour une requête canonique `BTC/USD`.

Le correctif 34.2 accepte ces équivalences uniquement à partir d'aliases exacts dérivés du symbole attendu. Il ne devine pas une paire à partir d'une clé inconnue et continue de rejeter une clé appartenant à un autre marché avec `OHLC_PAIR_KEY`. Les erreurs plus profondes conservent ainsi leurs stages `OHLC_ROW`, `OHLC_TIMESTAMP` et `OHLC_NUMERIC`.

429, 5xx, timeout/network et erreurs API déclarées conservent leurs classes dédiées et ne sont pas reclassés en payload.

## Public Attention

Aucune modification de l'adaptateur Public Attention dans ce batch.

Conservés :

- wire schema OpenAI compatible ;
- contraintes Pydantic canoniques ;
- `strict=true` ;
- `web_search` ;
- `store=false` ;
- sources de confiance ;
- distinction transport / incomplete / HTTP / validation.

Les erreurs ACE/AAVE/2Z/ALGO ne sont pas « corrigées » sans diagnostic reproductible supplémentaire.

## Tests ajoutés

`backend/tests/test_kraken_batch34_2_root_cause.py` couvre :

- clés REST internes réalistes ;
- `wsname`, `altname`, provider key et symbole canonique ;
- aliases `XBT/BTC` ;
- repli `base/quote` ;
- protection contre suppression générique de `X/Z` via `ZRX` ;
- entrée inutilisable fail-closed ;
- stage enveloppe/entrée/symbole ;
- OHLC canonique, display provider, `altname` et clé REST interne legacy ;
- mauvaise clé OHLC appartenant à un autre marché ;
- stages result/series/row/timestamp/numeric, y compris derrière une clé legacy ;
- incohérence `wsname` / `base` / `quote` rejetée avec `ASSET_PAIRS_SYMBOL` ;
- log payload borné à `operation` + `stage`, sans clé/payload provider ;
- 429 / 5xx / network inchangés ;
- absence de contenu provider dans les messages.

`backend/tests/test_market_attention_batch34_2_diagnostics.py` couvre :

- propagation du stage vers le compteur agrégé ;
- maintien de `KrakenPayloadError` dans les compteurs historiques ;
- absence du message d'exception dans le snapshot ;
- suppression du stage mémorisé après retour à un scan sans erreur ;
- rejet défensif d'un stage hors allowlist.

Les tests Batch 33 existants de registre partagé, anti-stampede et cooldown ne sont pas remplacés ; `candles.py` n'est pas modifié par Batch 34.2.

## Tests réellement exécutés par ChatGPT

Dans un harness Python isolé reproduisant les contrats nécessaires après le correctif final `721` :

```text
pytest -q tests/test_kraken_batch34_2_root_cause.py tests/test_market_attention_batch34_2_diagnostics.py
27 passed
```

Également exécuté :

```text
python -m py_compile <4 modules backend modifiés>
```

Résultat : PASS.

Le premier ZIP a révélé 10 régressions Batch 34/34.1, corrigées par le ZIP intermédiaire. L'utilisateur a ensuite validé localement les tests ciblés et la suite complète à 100 %. Le refresh runtime a permis d'isoler puis de reproduire la cause finale `ROW_COUNT: 721`. La suite complète du repository reste à réexécuter localement après extraction du présent correctif final.

## Validations locales requises

Depuis la racine du repository, après extraction du ZIP :

```powershell
cd backend
pytest -q tests/test_kraken_batch34_2_root_cause.py tests/test_market_attention_batch34_2_diagnostics.py tests/test_kraken_rest.py tests/test_kraken_rest_runtime_hardening.py tests/test_kraken_candle_spot_registry_cache.py
pytest -q
cd ..
git diff --check
```

Puis relancer un refresh Market Attention et vérifier en priorité :

```text
activity_market_type_status_counts.SPOT
activity_error_counts
activity_payload_stage_counts
```

Résultat attendu du diagnostic : aucune donnée brute provider ; si `KrakenPayloadError` subsiste, son stage dominant devient immédiatement identifiable.
