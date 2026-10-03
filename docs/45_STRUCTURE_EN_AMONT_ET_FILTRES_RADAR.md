# Batch 45 — Market Structure en amont et filtres tendance/structure

## Statut

**Patch proposé, non intégré.**

Base auditée :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : c4f474ccd8882014eb48a9c98c70ab94b9ab353d
Commit     : docs: close batch 44
```

Dernier commit fonctionnel intégré du Radar :

```text
c262d54fc902ac062c5d6f7404bfcb637448a8b6
feat: add perpetual liquidity and radar coverage diagnostics
```

## Objectif

Rendre la Market Structure utilisable comme source descriptive d'attention **avant la shortlist finale**, afin qu'une dégradation ou un retournement structurel confirmé puisse devenir visible même lorsque `MarketActivityState = NORMAL`.

Le Radar reste strictement informatif. Une structure n'est jamais traduite en `BUY`, `SELL` ou `HOLD` et n'a aucune autorité sur Agent, Risk Engine ou Broker.

## Audit

### Confirmé

Au HEAD de départ, `StructuredMarketAttentionRadar` reçoit un `MarketAttentionOverviewV4` dont `shortlist` a déjà été constituée par le pipeline activité + microstructure, puis appelle `_market_structure_for_market()` uniquement pour les éléments de cette shortlist.

Pipeline ancien :

```text
catalogue
-> scope
-> capitalisation
-> rotation OHLCV
-> volume
-> activité / tendance / liquidité
-> microstructure SPOT
-> shortlist canonique
-> Market Structure 5m / 15m / 1h / 4h uniquement sur cette shortlist
```

Un marché peut donc avoir :

```text
activité NORMAL
H4 TRANSITION + CHOCH_DOWN
H1 BEARISH
```

sans jamais obtenir de structure si l'ancien sélecteur ne l'a pas retenu.

### Obsolète

- considérer que la Structure est nécessairement un enrichissement post-shortlist ;
- considérer qu'une couverture Structure peut être déduite du diagnostic OHLCV du Batch 44 ;
- utiliser un simple état permanent `BULLISH`/`BEARISH` comme anomalie par défaut.

### Manquant avant Batch 45

- rotation Structure autonome et bornée ;
- cache Structure avec TTL explicite ;
- diagnostic Structure distinct ;
- critère d'attention structurelle avant shortlist ;
- filtres tendance et structure backend ;
- filtres par timeframe et événements BOS/CHOCH ;
- distinction cockpit entre zéro résultat réel et rotation Structure incomplète.

### À décider ultérieurement

- Open Interest, Funding, Liquidations, CVD ;
- baseline statistique adaptative ;
- microstructure Futures ;
- utilisation du Radar comme contexte Agent ;
- LIVE.

## Nouveau pipeline

Le runtime Batch 45 proposé utilise le pipeline suivant :

```text
catalogue Kraken
-> scope SPOT / PERPETUAL / ALL
-> metadata / filtre capitalisation
-> rotation et cache OHLCV existants
-> volume 24h / filtre volume
-> activité / tendance / liquidité
-> microstructure SPOT canonique
-> pool Market Structure éligible
-> rotation Market Structure bornée
-> cache Market Structure frais
-> filtres tendance / structure
-> shortlist finale bornée par candidate_limit
-> cockpit
```

Le runtime Batch 45 appelle directement le niveau v4 après microstructure afin de **bypasser l'ancien enrichissement Structure post-shortlist**. Il ne déclenche donc pas deux pipelines Structure concurrents.

Les hooks Batch 43/44 restent dynamiquement utilisés pour :

- scope ;
- capitalisation ;
- volume ;
- liquidité PERPETUAL ;
- microstructure SPOT ;
- couverture OHLCV.

## Pool Structure

Un marché peut entrer dans le pool Structure uniquement s'il possède déjà une activité fraîche après les filtres moins coûteux.

Conceptuellement :

```text
scope accepté
ET capitalisation acceptée si filtre actif
ET OHLCV frais/exploitable
ET volume accepté si filtre actif
=> éligible Structure
```

Un marché rejeté par capitalisation ou volume ne provoque donc pas quatre lectures natives de Structure.

## Policy de scan Structure

La responsabilité est séparée en deux policies.

`MarketStructurePolicy` reste la policy géométrique et causale existante :

```text
history_limit
min_history_candles
pivot_left_bars
pivot_right_bars
equality_tolerance_bps
swing_display_limit
fetch_concurrency
```

Le Batch 45 ajoute `MarketStructureScanPolicy` :

```text
market_limit_per_refresh = 20
cache_ttl_seconds        = 3600
```

Les valeurs sont centralisées et validées par Pydantic.

`fetch_concurrency` reste appliqué par le composant Structure canonique. Une analyse de marché conserve les quatre timeframes natives :

```text
5m
15m
1h
4h
```

## Rotation

La rotation Structure utilise un curseur distinct de `_scan_cursors` OHLCV.

Ordre déterministe :

```text
market_type
puis symbol
```

Le curseur Structure n'écrit jamais dans les curseurs SPOT/PERP de la rotation OHLCV.

La shortlist finale reste bornée par `MarketAttentionPolicy.candidate_limit`.

## Cache et causalité

Le cache est indexé par `ExecutableMarket` et stocke directement :

```text
MultiTimeframeMarketStructure
```

Le `observed_at` contenu dans le modèle est conservé.

Réutilisation autorisée uniquement si :

```text
cached.observed_at <= as_of
ET as_of - cached.observed_at <= cache_ttl
```

Un snapshot calculé à un instant futur par rapport à un `as_of` demandé n'est donc jamais réutilisé.

Les analyses natives conservent les garanties Batch 42 :

```text
history_as_of(observed_at)
candles finalisées uniquement
close_time <= observed_at
updated_at <= observed_at
pivot visible seulement après pivot_right_bars clôturées
```

## Diagnostic de couverture Structure

Le payload v6 expose désormais `structure_coverage`, distinct du `coverage` OHLCV.

Champs :

```text
eligible_market_count
fresh_market_count
expired_market_count
unseen_market_count
scanned_market_count
coverage_ratio
effective_market_limit
estimated_refreshes_per_full_rotation
estimated_full_rotation_seconds
cache_ttl_seconds
oldest_structure_age_seconds
rotation_within_cache_ttl
status
```

Statuts :

```text
NO_MARKETS
COVERED
ROTATING
TTL_EXPIRED
CONFIGURATION_TOO_SLOW
```

La durée théorique d'une rotation est :

```text
ceil(eligible_market_count / effective_market_limit)
* MarketAttentionPolicy.refresh_seconds
```

Le Radar n'augmente aucune limite automatiquement lorsque la configuration est trop lente.

## Attention structurelle par défaut

Le Batch 45 ne transforme pas les régimes de Structure persistants en anomalies permanentes.

Règle par défaut :

```text
BULLISH / BEARISH / RANGE / TRANSITION sans événement
=> ne force pas un candidat

BOS_UP / BOS_DOWN / CHOCH_UP / CHOCH_DOWN confirmé
=> peut compléter la shortlist canonique
```

Le sens haussier/baissier est symétrique :

```text
BOS_UP   == BOS_DOWN   en importance
CHOCH_UP == CHOCH_DOWN en importance
```

Le classement canonique conserve d'abord le niveau d'intérêt existant. À niveau d'intérêt identique, la priorité Structure agit comme un complément lisible, sans créer un second ranking concurrent :

1. timeframe : `4h > 1h > 15m > 5m` ;
2. nature : `CHOCH > BOS` à timeframe identique ;
3. les critères microstructure/activité canoniques départagent ensuite les éléments restants.

La Structure peut donc rendre un marché `NORMAL` éligible sans écraser systématiquement un candidat déjà mieux classé par le Radar canonique.

Le niveau `interest_level` existant n'est pas artificiellement transformé en recommandation stratégique. Un candidat peut donc être visible pour un événement Structure tout en conservant un niveau d'intérêt activité/microstructure faible.

## Filtres runtime

Le modèle backend devient `StructureAwareMarketAttentionFilters`, extension additive des filtres Batch 43.

### Tendance

```text
trend_directions = []
=> aucun filtre

UP / DOWN / NEUTRAL / MIXED
=> valeurs sélectionnables
```

`UNKNOWN` est interdit dans la configuration d'un filtre tendance.

Plusieurs valeurs : `OR`.

### Structure globale

```text
structure_global_states = []
=> aucun filtre

BULLISH
BEARISH
RANGE
TRANSITION
MIXED
=> sélectionnables
```

`UNKNOWN` est interdit dans la configuration.

### Structure par timeframe

Chaque timeframe possède :

```text
states: []
events: []
```

Timeframes :

```text
structure_5m
structure_15m
structure_1h
structure_4h
```

États autorisés :

```text
BULLISH
BEARISH
RANGE
TRANSITION
```

Événements :

```text
BOS_UP
BOS_DOWN
CHOCH_UP
CHOCH_DOWN
```

### Sémantique

```text
plusieurs valeurs dans states/events => OR
plusieurs timeframes configurées      => AND
plusieurs familles de filtres         => AND
state + event sur même timeframe      => AND
champ vide                             => aucune contrainte
```

Exemple :

```text
trend_directions = [DOWN]
structure_1h.states = [BEARISH]
structure_4h.states = [TRANSITION]
structure_4h.events = [CHOCH_DOWN]
```

signifie :

```text
trend DOWN
ET H1 BEARISH
ET H4 TRANSITION
ET H4 CHOCH_DOWN
```

Une structure `UNKNOWN`, absente, expirée ou pas encore couverte échoue au filtre Structure actif.

## Effet d'un filtre explicite sur l'éligibilité

Sans filtre tendance/Structure :

```text
candidats canoniques activité/microstructure
OU événement Structure confirmé
=> pool final
```

Avec au moins un filtre tendance/Structure explicite :

```text
tout marché du pool couvert qui satisfait les filtres
=> éligible à la shortlist finale
```

Cette distinction permet de rechercher volontairement un régime persistant `BULLISH` ou `BEARISH` sans le transformer en anomalie permanente lorsque les filtres sont désactivés.

## Contrat API

Le protocole reste :

```text
market-attention-radar-v6
```

Le changement est additif, comme les extensions diagnostiques des Batches 43.1 et 44.

Routes conservées :

```text
GET /api/v1/market-attention
GET /api/v1/market-attention/filters
PUT /api/v1/market-attention/filters
PUT /api/v1/market-attention/scope
GET /api/v1/market-attention/history
```

Aucune route parallèle v7 n'est introduite.

## Cockpit

Le cockpit ajoute une section repliable :

```text
Filtres Tendance & Market Structure
```

Elle expose :

- tendance `UP / DOWN / NEUTRAL / MIXED` ;
- structure globale ;
- états `5m / 15m / 1h / 4h` ;
- événements BOS/CHOCH par timeframe ;
- contrôles réellement pilotés par le backend.

Le détail candidat conserve l'affichage Structure par timeframe déjà présent depuis le Batch 42.

Un bloc séparé affiche la couverture Structure.

Lorsqu'un filtre Structure donne zéro résultat, le message distingue :

```text
couverture encore incomplète
```

et :

```text
couverture complète mais aucun marché ne correspond
```

## Cas PENDLE synthétique

Le test Batch 45 représente conceptuellement :

```text
activité NORMAL
trend DOWN
H1 BEARISH / BOS_DOWN
H4 TRANSITION / CHOCH_DOWN
```

Le marché peut entrer dans la shortlist même sans ancien candidat activité/microstructure.

Le test symétrique :

```text
activité NORMAL
trend UP
H1 BULLISH / BOS_UP
H4 TRANSITION / CHOCH_UP
```

obtient la même priorité directionnelle.

Aucun code n'est spécifique à PENDLE.

## Tests ajoutés

Backend :

```text
backend/tests/test_market_attention_batch45_structure_prefilter.py
```

Couvre notamment :

- defaults = aucun filtre tendance/Structure ;
- validation des doublons ;
- `UNKNOWN` interdit dans les filtres actifs ;
- OR dans une famille ;
- AND entre timeframes ;
- AND state/event ;
- fail-closed Structure inconnue ;
- symétrie CHOCH_UP / CHOCH_DOWN ;
- priorité timeframe supérieure ;
- `NORMAL + CHOCH` éligible ;
- simple état persistant non éligible par défaut ;
- état persistant recherchable avec filtre explicite ;
- `candidate_limit` respecté ;
- rotation Structure déterministe ;
- curseurs OHLCV non modifiés ;
- quatre timeframes appelées ;
- cache frais réutilisé ;
- cache expiré rafraîchi ;
- cache futur jamais réutilisé ;
- diagnostic de couverture.

Frontend :

```text
frontend/src/lib/market-attention.test.mjs
```

Couvre notamment :

- valeurs par défaut ;
- libellés tendance/Structure/BOS/CHOCH ;
- diagnostic couverture Structure ;
- détection d'un filtre Structure actif ;
- distinction rotation incomplète / aucun match ;
- sérialisation du payload complet de filtres.

Les tests historiques Batch 42/43/43.1/43.2/44 restent nécessaires pour la non-régression globale.

## Validation exécutée par ChatGPT

Dans l'environnement de génération du patch :

```text
python -m py_compile <fichiers Python modifiés> : PASS
node --test --experimental-strip-types frontend/src/lib/market-attention.test.mjs : PASS — 16/16
tsc ciblé frontend/src/lib/market-attention.ts : PASS
tsc ciblé cockpit avec stubs des dépendances UI : PASS
```

Le repository complet et ses dépendances n'étaient pas présents dans le conteneur de génération. ChatGPT n'a donc pas exécuté la suite complète `pytest -q` ni le `pnpm typecheck/test` du projet entier.

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

## Invariants préservés

- un seul Agent IA ;
- Radar informatif uniquement ;
- aucune décision stratégique par la Structure ;
- aucun `BUY`, `SELL`, `HOLD` produit par le Radar ;
- aucune sortie Radar directement vers Kraken ;
- Risk Engine autorité finale ;
- aucune modification Agent / Risk Engine / Broker ;
- aucune capacité d'exécution PERP ;
- aucun short, levier, margin, future ou perpetual exécutable ;
- PAPER ;
- aucune donnée future ;
- candles finalisées uniquement ;
- pivots causaux uniquement ;
- Kraken derrière ses interfaces existantes ;
- capitalisation externe read-only ;
- aucun secret ;
- aucune promesse de rendement.
