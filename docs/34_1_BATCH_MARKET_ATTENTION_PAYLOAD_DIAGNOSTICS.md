# Batch 34.1 — Market Attention Payload Diagnostics

Date : 2026-09-29

## 1. Statut et base auditée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 4a516fde33853fe84d18bd8c4780753c0db58214
Commit     : fix: harden market attention runtime
```

Le Batch 33 est intégré dans ce HEAD. Le Batch 34 est appliqué dans le working tree opérateur mais n'est pas intégré à GitHub. Le présent Batch 34.1 est un **patch proposé/local** construit pour se superposer au Batch 34 sans modifier GitHub.

État local communiqué avant le batch :

```text
pytest -q       : 825 passed, 2 warnings
git diff --check: aucune erreur
frontend        : non modifié

Radar refresh :
- catalogue 1633
- scan 120 = 100 SPOT + 20 PERPETUAL
- SPOT : 100 ERROR / 100 KrakenPayloadError
- PERPETUAL : 6 AVAILABLE + 14 PARTIAL / 0 ERROR
```

Le fichier `trades_9h_analysis.json` reste hors périmètre.

## 2. Cause Kraken — preuve et portée

### Défaut confirmé dans le code

Le parser intégré `parse_asset_pairs_payload()` utilisait directement la clé de `AssetPairs.result` comme symbole canonique et rejetait toute clé sans `/`.

Cette hypothèse n'est pas valide pour l'API Kraken : la clé de `result` peut être un identifiant REST/internal tandis que les représentations display sont transportées dans les métadonnées de la paire (`wsname`, ainsi que `base`/`quote`).

Exemple représentatif :

```text
result key : XXBTZUSD
altname    : XBTUSD
wsname     : XBT/USD
base       : XXBT
quote      : ZUSD
```

Le chemin Batch 33 partage désormais un seul `KrakenPairRegistry` lazy. Un échec structurel lors de ce chargement initial est donc propagé en fail-fast aux marchés SPOT concurrents pendant le cooldown. Cela fournit un mécanisme causal cohérent avec le motif runtime `100 SPOT -> 100 KrakenPayloadError` avant même les appels OHLC individuels.

### Ce qui reste à confirmer au runtime

Le payload brut n'est volontairement jamais journalisé. Le Batch 34.1 ajoute donc un stage borné permettant de vérifier que le prochain échec éventuel provient réellement de `ASSET_PAIRS_*` ou d'une étape OHLC précise.

La correction ne dépend pas de cette observation ultérieure : elle supprime une hypothèse de parsing objectivement incompatible avec le contrat provider.

## 3. Correction AssetPairs

`KrakenPairRegistry` reste le composant canonique. Aucun second catalogue n'est créé.

Le parser :

1. accepte une clé `result` display ou REST/internal ;
2. dérive le symbole canonique slash-separated depuis les informations disponibles ;
3. normalise les alias Kraken historiques utiles au projet, notamment `XBT -> BTC`, `XDG -> DOGE` et les préfixes legacy de `base`/`quote` ;
4. exige que les différentes représentations disponibles convergent vers un seul symbole canonique ;
5. conserve la clé provider comme alias de lookup ;
6. échoue fermé avec `ASSET_PAIRS_SYMBOL` si le symbole ne peut pas être normalisé sans ambiguïté.

Ainsi une paire `XXBTZUSD / XBTUSD / XBT/USD` devient canoniquement `BTC/USD`, tout en restant résoluble par ses alias provider.

## 4. Diagnostic Kraken borné

`KrakenPayloadError` conserve sa classe générale pour compatibilité et reçoit un attribut `stage` issu d'une liste fermée :

```text
ASSET_PAIRS_PAYLOAD
ASSET_PAIRS_ENTRY
ASSET_PAIRS_SYMBOL
OHLC_RESULT
OHLC_SERIES
OHLC_PAIR_KEY
OHLC_ROW
OHLC_TIMESTAMP
OHLC_NUMERIC
UNKNOWN
```

Le client REST journalise uniquement :

```text
Kraken payload rejected operation=<AssetPairs|OHLC> stage=<CODE>
```

Ne sont jamais inclus :

- payload Kraken brut ;
- body HTTP brut ;
- URL de requête ;
- valeur de paire rejetée ;
- secret.

Les classifications réseau/API existantes restent séparées : timeout/408, réseau, 429, 5xx, HTTP permanent et erreur API Kraken.

## 5. OHLC — comportement Batch 34 préservé

Le correctif Batch 34 qui tolère une clé REST/internal pour la série OHLC est conservé selon une règle bornée :

- la réponse doit contenir exactement une série non-`last` ;
- une clé sans `/` peut être traitée comme l'identifiant interne de cette unique série ;
- une clé display contenant `/` est normalisée puis doit correspondre au marché demandé ;
- une mauvaise clé display explicite reste rejetée avec `OHLC_PAIR_KEY`.

Les validations de rows, timestamps, chronologie, nombre de séries, valeurs numériques, prix et volume restent fail-closed.

## 6. Public Attention — schema wire et contrat canonique

Le Batch 34 a démontré que le schema wire Structured Outputs ne doit pas transporter les mots-clés `minLength/maxLength` non supportés dans ce chemin. Le Batch 34.1 conserve donc :

```text
strict = true
tools = [{"type": "web_search"}]
store = false
include = ["web_search_call.action.sources"]
```

Le schema wire conserve types, enum, champs requis et `additionalProperties=false`, mais pas les contraintes de longueur.

Les limites restent intégralement appliquées par les modèles Pydantic canoniques :

```text
confidence_context      1..2000
metric.name             1..128
metric.value            1..256
metric.unit/window      <=64
source_url              <=2048
observation.text        1..2000
catalyst.description    1..2000
source.title            1..1000
source.url              1..2048
```

Aucune relaxation de ces modèles n'est introduite.

## 7. PublicAttentionValidationError bornée

Lorsqu'une construction Pydantic échoue, l'adaptateur lève `PublicAttentionValidationError` avec uniquement :

```text
validation_path
validation_code
validation_error_count (borné à 8)
```

Exemple de diagnostic sûr :

```text
path=quantitative_metrics[0].name
code=string_too_long
errors=1
```

La valeur rejetée, le message Pydantic détaillé, son `input` et le JSON structuré brut ne sont pas journalisés.

Les erreurs manuelles de contrat `attention_direction` / `confidence_context` utilisent la même frontière bornée.

### APE / 2Z

Le runtime Batch 34 ne conservait que le nom `PublicAttentionValidationError`. La violation exacte d'APE et 2Z n'est donc **pas confirmée** avant Batch 34.1.

Décision : ne pas tronquer, normaliser ou assouplir silencieusement un champ au hasard. Le prochain runtime indiquera le chemin/code exact ; une correction sémantique ne sera ajoutée que si cette observation la justifie.

## 8. Erreurs OpenAI transport / HTTP

Le Batch 34.1 garde les erreurs de transport distinctes des erreurs de validation :

```text
PublicAttentionTransportError -> réseau / timeout final
PublicAttentionRateLimitError -> HTTP 429 final
PublicAttentionServerError    -> HTTP 5xx final
PublicAttentionHTTPError      -> autre HTTP >= 400, notamment 400/schema
PublicAttentionValidationError-> contrat canonique Pydantic
```

`PublicAttentionTransportError` observé sur AAVE reste donc une dégradation contrôlée et n'est pas confondu avec le contrat structuré.

## 9. Frontière de confiance des sources

La politique Batch 33/34 est inchangée :

- une URL présente uniquement dans le JSON structuré n'est jamais promue comme source canonique ;
- elle doit être provider-backed via les métadonnées/citations de `web_search` ;
- sans source provider vérifiable, le résultat reste `PARTIAL`.

## 10. Invariants non modifiés

```text
scan_limit = 120
candidate_limit = 20
max_web_searches_per_refresh = 8
seuils = 1.40 / 1.75+0.25 / 2.50+0.50
```

Sont également inchangés :

- allocation/cursors SPOT/PERPETUAL Batch 32 ;
- classification same-horizon Batch 33 ;
- notionnel USD SPOT ;
- SPOT non-USD -> notionnel null ;
- PERPETUAL -> notionnel null / liquidité UNKNOWN ;
- faible liquidité non filtrante ;
- Agent prompts ;
- Market Discovery ;
- Risk Engine ;
- Broker / ordres ;
- PAPER/LIVE ;
- caractère observationnel du Market Attention Radar.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## 11. Fichiers du patch

Runtime :

```text
backend/src/ai_spot_trader/integrations/kraken/errors.py
backend/src/ai_spot_trader/integrations/kraken/symbols.py
backend/src/ai_spot_trader/integrations/kraken/rest.py
backend/src/ai_spot_trader/integrations/openai_market_attention.py
```

Tests :

```text
backend/tests/test_market_attention_batch34_1_payload_diagnostics.py
```

Documentation :

```text
docs/00_ETAT_ACTUEL.md
docs/09_ROADMAP_DEVELOPPEMENT.md
docs/34_1_BATCH_MARKET_ATTENTION_PAYLOAD_DIAGNOSTICS.md
```

`docs/10_DECISIONS_ET_CHANGELOG.md` reste volontairement inchangé : Batch 34 et Batch 34.1 ne sont pas encore intégrés à GitHub et le document de décisions intégrées ne doit pas présenter le patch comme adopté.

Le frontend n'est pas modifié.

## 12. Validation attendue dans le repository opérateur

Depuis la racine :

```powershell
cd backend
pytest -q
cd ..
git diff --check
git status --short
```

Le frontend n'a pas besoin d'être revalidé spécifiquement pour ce patch puisqu'aucun fichier frontend n'est livré.

## 13. Validation runtime recommandée

Après réussite des tests locaux et redémarrage backend, observer au moins un refresh complet.

Attendus principaux :

- les SPOT ne doivent plus échouer collectivement au chargement du registry pour une clé `AssetPairs.result` interne ;
- si un `KrakenPayloadError` subsiste, le log doit contenir uniquement son stage ;
- `KrakenPayloadError` reste la catégorie générale du Radar ;
- APE/2Z, s'ils échouent encore, doivent produire un `path/code/count` exploitable sans valeur rejetée ;
- AAVE transport reste classé transport si l'incident réseau se reproduit ;
- les recherches ALGO/ACE/ADA et autres résultats valides ne doivent pas régresser ;
- aucune donnée Radar ne doit entrer dans le chemin de trading.

## 14. Intégration

À la livraison :

```text
GitHub main : 4a516fde — inchangé
Batch 34    : local, non intégré
Batch 34.1  : patch proposé/local
```

Commit/push restent des actions explicites de l'opérateur après validation complète.
