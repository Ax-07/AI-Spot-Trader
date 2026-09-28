# Batch 28 — Market Attention Radar v1

## 1. Référence de départ

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD GitHub vérifié : d011faa98e7e347875186f12cb24b5e7041aa25c
Commit              : feat: add trading reasoning doctrine
Parent direct        : b46f463c474e25a38da7ddcaebf588753922031b
```

Lors de l'audit, `docs/00_ETAT_ACTUEL.md` mentionnait encore `b46f463c` et décrivait la Trading Reasoning Doctrine v1 comme patch local. Cette dérive documentaire est corrigée dans ce batch.

## 2. Objectif

Ajouter un radar observationnel répondant à :

> « Sur quels marchés crypto quelque chose d'inhabituel semble-t-il commencer à se produire ? »

Le système croise deux axes indépendants :

```text
MARKET ACTIVITY
volume / prix / volatilité Kraken
        +
PUBLIC WEB ATTENTION
recherche publique OpenAI web_search
        ↓
MARKET ATTENTION
        ↓
shortlist indicative
        ↓
cockpit
```

**Market Attention Radar v1 = observationnel uniquement. Aucune donnée du radar n'est actuellement fournie à l'Agent stratégique.**

## 3. Audit de l'existant

### Confirmé

- `CandleStreamService` est le service backend canonique de candles et expose déjà le volume Kraken ;
- `KrakenCandleProvider` supporte SPOT + PERPETUAL et fournit l'historique public sans clé privée ;
- le domaine `Candle` conserve OHLCV, finalisation et timestamps ;
- le client stratégique `OpenAIResponsesClient` utilise déjà Responses API et Structured Outputs ;
- Market Discovery est un sous-système distinct où **le même Agent stratégique** sélectionne une watchlist ;
- le lifecycle FastAPI possède le `CandleStreamService` partagé ;
- le cockpit reste un consommateur backend sans autorité de trading.

### Obsolète

- la référence HEAD dans `docs/00_ETAT_ACTUEL.md` (`b46f463c`) ;
- la qualification de Trading Reasoning Doctrine comme patch local alors qu'elle est intégrée dans `d011faa`.

### Manquant avant le batch

- mesure multi-horizon du volume relatif pour détecter une accélération d'activité ;
- présélection observationnelle indépendante de Market Discovery ;
- contrat de recherche publique OpenAI `web_search` ;
- modèle structuré de Public Attention ;
- croisement Market/Public Attention ;
- API read-only dédiée ;
- UI Radar avec sources cliquables ;
- cache/TTL et bornes de coût dédiées.

### À décider ultérieurement

- persistence PostgreSQL durable des snapshots Radar ;
- exposition éventuelle d'un contexte Radar à l'Agent stratégique après observation de données réelles ;
- calibration empirique des seuils descriptifs d'activité et des cadences selon charge/coût réel.

## 4. Architecture retenue

```text
Kraken public catalogue
        ↓
SPOT + PERPETUAL linéaire
        ↓
scan borné / rotation
        ↓
CandleStreamService.history(5m)
        ↓
MarketActivityAnalyzer
5m / 15m / 1h / 4h
        ↓
candidats activité inhabituelle (max borné)
        ↓
déduplication par actif
        ↓
OpenAIWebAttentionResearcher
Responses API + hosted web_search
        ↓
PublicAttentionSnapshot
        ↓
MarketAttentionSnapshot
        ↓
shortlist informative + historique mémoire
        ↓
GET /api/v1/market-attention
GET /api/v1/market-attention/history
        ↓
Market Attention cockpit dock
```

Le Radar ne possède aucune interface Agent, Risk, Broker ou ordre.

## 5. Market Activity Radar

### Horizons v1

Après audit des timeframes disponibles, la v1 retient :

```text
5m
15m
1h
4h
```

La source de base est la candle `5m` canonique. Les horizons supérieurs sont construits à partir de groupes de candles finalisées, sans seconde récupération OHLCV ni interpolation.

### Facts calculés

Pour chaque horizon :

- `current_volume` ;
- `previous_comparable_volume` ;
- `baseline_volume` ;
- `volume_ratio` ;
- `volume_change` ;
- `volume_acceleration` ;
- `price_return` ;
- `price_range` ;
- `realized_volatility` ;
- `observation_count` ;
- `baseline_period_count` ;
- `complete`.

Le `baseline_volume` est la médiane de fenêtres comparables précédentes. Le volume relatif est le cœur de l'observation ; le volume absolu n'est pas utilisé comme raccourci d'intérêt.

### États descriptifs

```text
UNKNOWN
NORMAL
ELEVATED
ACCELERATING
VERY_HIGH
```

Ces labels décrivent l'ampleur/accélération des ratios observés. Ils ne sont pas un signal BUY/SELL et ne représentent aucun rendement attendu.

### Données insuffisantes et stale

Une fenêtre qui ne possède pas assez de candles/baselines reste `complete=false` et ne reçoit pas de métriques inventées. Un snapshot trop ancien est `STALE`.

SPOT et PERPETUAL sont toujours adressés par le couple canonique `symbol + market_type`.

## 6. Présélection et coût Kraken

Le catalogue public peut être important. La v1 ne déclenche pas un historique complet sur tous les marchés simultanément :

- `scan_limit` borné, défaut `120`, hard limit `500` ;
- rotation déterministe du curseur entre refreshes ;
- cache d'activité avec TTL ;
- présélection `candidate_limit`, défaut `20`, hard limit `30`.

Les activités fraîches déjà en cache restent comparables avec le nouveau batch scanné. Le compteur `catalogue_market_count / cached_activity_market_count / scanned_market_count` rend cette couverture visible.

## 7. Public Web Attention

### API OpenAI

L'audit de l'API actuelle confirme l'utilisation canonique de Responses API avec :

```json
"tools": [{"type": "web_search"}],
"include": ["web_search_call.action.sources"],
"text": {
  "format": {
    "type": "json_schema",
    "name": "public_attention_v1",
    "strict": true
  }
}
```

`store=false` reste explicite.

Le client est volontairement séparé de `OpenAIResponsesClient` stratégique afin de ne pas modifier son contrat, ses tool loops ou ses audits.

### Contrat de recherche

Le prompt auxiliaire exige :

- attention publique récente et son évolution ;
- métriques publiques uniquement lorsqu'elles sont réellement disponibles ;
- observations qualitatives conservées comme telles ;
- catalyseurs récents possibles ;
- sources publiques ;
- absence d'hypothèse d'exhaustivité X/Reddit/LunarCrush ;
- distinction des fenêtres glissantes, par exemple `mentions_24h` != nouveaux posts dans la dernière heure.

Il interdit :

```text
BUY / SELL / HOLD
recommandation de position
LONG / SHORT preference
position size
probabilité de hausse/baisse
métrique inventée
```

### Sources canoniques

Une URL n'est retenue comme source canonique que si elle apparaît dans les métadonnées/citations de la recherche web Responses API. Le JSON structuré peut décrire une source mais ne peut pas créer à lui seul une URL canonique.

Le modèle conserve :

- titre ;
- URL ;
- domaine ;
- heure d'observation ;
- heure de publication si disponible.

Le système ne persiste ni pages web complètes ni posts sociaux.

### LunarCrush / Reddit / X

Aucune API dédiée n'est utilisée. Ces domaines peuvent apparaître uniquement si une page est publiquement accessible et trouvée par `web_search`. Leur absence ne fait jamais échouer la recherche.

## 8. Cache, TTL, retry et fail-soft

Defaults v1 :

```text
refresh_seconds                 = 300
catalogue_ttl_seconds           = 1800
activity_ttl_seconds            = 900
public_attention_ttl_seconds    = 1800
candidate_limit                 = 20
max_web_searches_per_refresh    = 8
history_limit                   = 96
```

Les bornes sont portées par `MarketAttentionPolicy` et validées par Pydantic.

La recherche web est dédupliquée par actif : par exemple `QNT/USD SPOT` et `QNT/USD PERPETUAL` n'entraînent pas automatiquement deux recherches publiques.

Le client OpenAI possède un retry très borné sur transport/timeout/429/5xx. Toute erreur finale devient un `PublicAttentionSnapshot` dégradé ; elle ne remonte pas dans le cycle de trading.

## 9. Croisement Market + Public

La v1 conserve les deux axes séparés et expose un état croisé :

```text
NORMAL
MARKET_ONLY
PUBLIC_ONLY
CONVERGING
```

Puis un niveau d'attention :

```text
NORMAL
MEDIUM
HIGH
```

Le tri porte uniquement sur convergence/caractère inhabituel, puis ratios/accélération de volume. Aucun champ `expected_return`, `probability_up`, `probability_down`, `long_preference`, `short_preference` ou `position_size` n'existe.

## 10. Historisation / persistence

### Décision v1

Aucune migration SQL.

Le Radar maintient un `deque` borné de `MarketAttentionOverview`. Cela permet l'inspection des derniers snapshots pendant la durée du process sans introduire une seconde base d'observabilité ni recopier les données sources.

### Limite explicite

L'historique Radar est perdu au redémarrage backend.

Cette limite est acceptée en v1 : l'objectif est d'abord de collecter de l'expérience réelle sur utilité, fréquence et coût. Une persistence durable doit être conçue ensuite si le besoin est démontré.

## 11. API

Lecture uniquement :

```text
GET /api/v1/market-attention
GET /api/v1/market-attention/history?limit=<1..96>
```

Il n'existe aucun endpoint de trade, d'ordre ou de modification de la stratégie.

Lorsque le Radar n'est pas composé, l'API expose `NOT_CONFIGURED` plutôt que d'inventer des données.

## 12. Cockpit

Un `MarketAttentionDock` global est rendu depuis `frontend/src/app/page.tsx`.

Il affiche :

- état global ;
- taille catalogue / cache / batch scanné ;
- nombre de candidats ;
- nombre de recherches web ;
- market + type ;
- attention level / cross state ;
- Market Activity ;
- Public Attention ;
- ratios 5m / 15m / 1h ;
- mouvement de prix ;
- nombre de sources ;
- fraîcheur ;
- contexte/catalyseur ;
- métriques publiques ;
- sources publiques cliquables.

Le badge `INFORMATIF — N’INFLUENCE PAS LE TRADING` est visible dans l'en-tête du panneau.

## 13. Invariants prouvés par architecture

- `market/attention.py` n'importe aucun module Agent, Risk, Broker ou Market Discovery ;
- aucun fichier Agent n'est modifié ;
- aucun fichier Risk n'est modifié ;
- aucun fichier Broker n'est modifié ;
- aucun fichier `market/discovery.py` n'est modifié ;
- l'intégration `main.py` se limite à construire/démarrer/arrêter le Radar et enregistrer son router ;
- l'API est GET-only ;
- le frontend ne publie aucune action vers le moteur.

Donc :

```text
radar web failure != trading cycle failure
radar result != Agent input
radar shortlist != Market Discovery watchlist
```

## 14. Fichiers du batch

### Backend

```text
backend/src/ai_spot_trader/market/attention.py
backend/src/ai_spot_trader/integrations/kraken/attention.py
backend/src/ai_spot_trader/integrations/openai_market_attention.py
backend/src/ai_spot_trader/api/routes/market_attention.py
backend/src/ai_spot_trader/main.py
backend/tests/test_market_attention.py
backend/tests/test_openai_market_attention.py
```

### Frontend

```text
frontend/src/app/page.tsx
frontend/src/components/cockpit/market-attention-dock.tsx
frontend/src/lib/market-attention.ts
frontend/src/lib/market-attention.test.mjs
frontend/package.json
```

### Documentation

```text
README.md
docs/00_ETAT_ACTUEL.md
docs/01_PROJECT_MASTER.md
docs/02_ARCHITECTURE_TECHNIQUE.md
docs/09_ROADMAP_DEVELOPPEMENT.md
docs/10_DECISIONS_ET_CHANGELOG.md
docs/28_BATCH_MARKET_ATTENTION_RADAR_V1.md
```

## 15. Tests réellement exécutés par ChatGPT

### Compilation Python

```text
python -m py_compile
  market/attention.py
  integrations/kraken/attention.py
  integrations/openai_market_attention.py
  api/routes/market_attention.py
  main.py
  tests/test_market_attention.py
  tests/test_openai_market_attention.py
```

Résultat : **succès**.

### Harness backend isolé

Cas exécutés :

- baseline / volume ratio ;
- volume acceleration ;
- gaps de candles non interpolés ;
- marché `NORMAL` non envoyé à la recherche web ;
- état `VERY_HIGH` ;
- refresh Radar ;
- timeout public web -> snapshot public `ERROR` mais activité marché `AVAILABLE` ;
- Responses API request avec `web_search` ;
- `include=web_search_call.action.sources` ;
- `store=false` ;
- parsing Structured Output ;
- parsing source/domain.

Résultat : **PASS**.

### Frontend isolé

```text
node --test --experimental-strip-types src/lib/market-attention.test.mjs
```

Résultat : **3/3 passés**.

## 16. Validation locale initiale et correctif

Après extraction du premier ZIP, la validation locale utilisateur a donné :

- suite backend complète : un seul échec dans `test_market_activity_reports_insufficient_and_stale_data_without_fake_statistics` ;
- frontend `pnpm test` : `42/42` passés ;
- frontend `pnpm lint` : un seul échec `react-hooks/set-state-in-effect` dans `market-attention-dock.tsx` ;
- frontend `pnpm typecheck` : succès ;
- frontend `pnpm build` : succès ;
- `git diff --check` : aucune erreur de whitespace, seulement les avertissements LF -> CRLF du checkout Windows.

Le ZIP correctif applique deux corrections ciblées :

1. `MarketActivitySnapshot.status` devient `AVAILABLE` uniquement lorsque **tous** les horizons v1 sont complets ; une couverture incomplète reste `PARTIAL`, et `STALE` qualifie un snapshot complet devenu ancien. Le test d'insuffisance utilise les 20 candles les plus récentes afin de ne pas mélanger insuffisance et vieillissement.
2. le premier refresh du dock est déclenché depuis l'événement d'ouverture utilisateur ; l'`useEffect` ne fait plus de mise à jour d'état synchrone et conserve uniquement l'abonnement périodique avec cleanup.

Aucune interface Agent/Risk/Broker/Market Discovery n'est modifiée par ce correctif.

Revalidation du correctif dans l'environnement ChatGPT :

- `py_compile` des sept fichiers Python du batch : succès ;
- harness Radar isolé avec `PARTIAL` frais et `STALE` complet : PASS ;
- test frontend isolé `market-attention.test.mjs` : `3/3` passés.

`pnpm lint`, `pnpm typecheck`, `pnpm build` et la suite `pytest -q` complète restent à rejouer localement sur le repository complet.

## 17. Tests restant à exécuter localement

L'environnement ChatGPT ne possède pas un checkout complet du repository ni ses dépendances installées. Les suites complètes suivantes n'ont donc pas été déclarées réussies :

```powershell
cd backend
pytest -q

cd ..\frontend
pnpm test
pnpm lint
pnpm typecheck
pnpm build
```

Les nouveaux tests backend couvrent en particulier :

- volume/baseline/ratio/accélération ;
- données insuffisantes ;
- stale ;
- séparation SPOT/PERPETUAL ;
- présélection inhabituelle / bornes / déduplication web ;
- panne web fail-soft ;
- mode sans web ;
- API read-only ;
- absence de dépendance Agent/Risk/Broker/Discovery ;
- contrat OpenAI web_search/Structured Output/sources ;
- retry borné ;
- interdiction de recommandations de trading.

## 18. Migration

Aucune.

## 19. Extraction

Le ZIP du batch est **root-relative** : extraire directement à la racine `E:\AI-Spot-Trader` (ou toute autre racine locale du repository). Il ne contient aucun dossier parent `AI-Spot-Trader`, aucun `.git`, `.env`, secret, venv, cache ou dépendance installée.

## 20. Validation PowerShell minimale

```powershell
git status --short
cd backend
pytest -q
cd ..\frontend
pnpm test
pnpm lint
pnpm typecheck
pnpm build
cd ..
git diff --check
```

Ne pousser `main` qu'après validation locale et décision explicite de l'opérateur.
