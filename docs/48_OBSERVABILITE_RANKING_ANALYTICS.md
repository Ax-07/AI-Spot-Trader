# 48 — Observabilité et validation causale du ranking Analytics

## Statut de la livraison

```text
Repository GitHub audité : Ax-07/AI-Spot-Trader
Branche                    : main
HEAD GitHub de départ       : 4278a5c732b9636b06144ff58e8485b3350a2c0d
Commit HEAD                 : docs: mark batch 47.5 integrated
Batch 48                    : patch proposé, non intégré à GitHub au moment de la livraison
```

Le Batch 48 est strictement un batch d'**observabilité**. Il ne modifie ni le score Analytics `0..4`, ni ses seuils, ni la population de candidats, ni `interest_level`, ni `candidate_limit`.

## 1. Audit préalable

### Confirmé

- Le Radar produit un snapshot à chaque refresh et conserve déjà un historique process-local borné par `MarketAttentionPolicy.history_limit`.
- La valeur par défaut est `history_limit=96` et `refresh_seconds=300`, soit environ huit heures de profondeur nominale lorsque le processus reste actif et que la cadence nominale est tenue.
- `PerpetualAnalyticsMarketAttentionRadar` réutilise cette limite via sa propre `deque(maxlen=self._policy.history_limit)` et expose `history(limit=...)`.
- Le contrat API possède déjà `/api/v1/market-attention/history`, borné à 96 éléments.
- Le diagnostic `analytics_ranking` du Batch 47.5 contient déjà les faits nécessaires à l'observation : score, composantes, diagnostics des cinq séries, déduplication/conflit order-flow, application au ranking, rang avant/après et `rank_change`.
- CVD et Aggressor Differential sont déjà regroupés dans une seule famille `ORDER_FLOW` et peuvent donc être observés sans recréer un calcul concurrent.
- La persistence SQL canonique existe, mais elle est orientée faits économiques et audit des cycles PAPER. Le writer d'audit trading est une frontière durable fail-closed ; ce n'est pas un store générique de télémétrie Radar.
- Le cockpit expose déjà les diagnostics candidat du ranking 47.5 et la santé instantanée des cinq séries.
- L'exécution reste SPOT uniquement ; les PERP observés n'ont aucune voie vers Broker.

### Obsolète

- Une instrumentation basée uniquement sur le snapshot courant est insuffisante pour mesurer fréquence, stabilité temporelle, distribution du score ou fréquence de reranking.
- Réutiliser la persistence PAPER comme si elle constituait une télémétrie générique du Radar serait une interprétation incorrecte de son rôle actuel.

### Manquant avant Batch 48

- distribution temporelle du score `0..4` ;
- fréquence de contribution des quatre familles ;
- distribution des statuts des cinq séries sur les candidats réellement observés ;
- fréquence d'application et d'effet réel du reranking ;
- amplitude des changements de rang ;
- distinction explicite entre `rank_change=0`, ranking non applicable et rang manquant ;
- fréquence de déduplication et de conflit CVD/Aggressor ;
- proportion de PERP sans aucune série `AVAILABLE` ;
- vue agrégée par scope et par marché ;
- endpoint compact dédié au diagnostic agrégé.

### À décider ultérieurement

- nécessité d'une conservation durable au-delà de la durée de vie du processus ;
- durée cible d'une éventuelle fenêtre durable ;
- export offline pour recherche statistique ;
- toute modification des poids ou des seuils du score ;
- toute utilisation par l'Agent.

## 2. Options comparées

### Option 1 — diagnostics uniquement dans le snapshot courant

Simple, mais ne répond pas aux questions de fréquence ou de stabilité. Rejetée comme solution principale.

### Option 2 — agrégation en mémoire glissante séparée

Permet les fréquences récentes, mais créerait un second buffer alors que le Radar conserve déjà les snapshots nécessaires. Rejetée pour éviter une infrastructure parallèle inutile.

### Option 3 — journalisation/persistence durable dédiée

Reproductibilité inter-redémarrage supérieure, mais nécessite un nouveau contrat de persistence, un schéma, une politique de rétention et des migrations. Trop lourd pour un premier batch d'observabilité ; non justifié avant d'avoir prouvé le besoin.

### Option 4 — agrégation courte + journal durable existant

La persistence durable existante est canonique pour les cycles PAPER, pas pour la télémétrie Radar. La réutiliser couplerait l'observation du marché à l'audit économique et à ses propriétés fail-closed. Rejetée dans l'état actuel.

## 3. Décision Batch 48

**Retenue : agrégation à la demande sur l'historique Radar déjà canonique et borné.**

```text
Radar refresh
    ↓
historique Market Attention existant (max 96 exposé par l'API)
    ↓
GET /api/v1/market-attention/observability?limit=96
    ↓
agrégation déterministe, read-only, causale
    ↓
cockpit compact
```

Il n'existe :

- aucune nouvelle base ;
- aucune nouvelle table ;
- aucun second `deque` ;
- aucun nouveau scanner ;
- aucun nouveau cache Analytics ;
- aucune écriture de télémétrie ;
- aucun calcul dépendant d'un prix futur ou d'un P&L futur.

La contrepartie est explicite : **un redémarrage backend remet l'historique Radar process-local à zéro**. Le Batch 48 ne prétend donc pas fournir une archive longue durée.

## 4. Contrat d'observabilité

Nouveau schéma :

```text
analytics-ranking-observability-v1
```

Nouvelle route additive :

```text
GET /api/v1/market-attention/observability?limit=96
```

Le payload historique et le payload `/market-attention` existants ne sont pas modifiés par cette agrégation.

### Fenêtre

Le diagnostic expose :

- `requested_history_limit` ;
- `source_snapshot_count` ;
- `snapshots_observed` ;
- `legacy_snapshots_ignored` ;
- `window_started_at` ;
- `window_ended_at`.

L'agrégateur se reborde lui-même à `96` même si un appelant lui transmet accidentellement davantage d'éléments.

## 5. Métriques descriptives

### Scores

Distribution exacte :

```text
score_0
score_1
score_2
score_3
score_4
```

Seuls les candidats PERPETUAL portant un diagnostic `analytics_ranking` sont inclus dans cette distribution.

### Contributions

Compteurs séparés :

```text
OPEN_INTEREST
FUNDING
LIQUIDATION_VOLUME
ORDER_FLOW
```

Une même famille n'est comptée qu'une fois par candidat, même en présence d'un payload anormalement dupliqué.

### Santé des séries

Les cinq séries sont suivies séparément :

```text
open-interest
funding
liquidation-volume
cvd
aggressor-differential
```

Statuts comptés :

```text
AVAILABLE
PARTIAL
INSUFFICIENT_HISTORY
STALE
TECHNICAL_ERROR
NOT_APPLICABLE
UNAVAILABLE
```

Le diagnostic expose aussi les ratios `AVAILABLE`, `PARTIAL`, `INSUFFICIENT_HISTORY`, `STALE` et `TECHNICAL_ERROR` par série, ainsi que les totaux globaux.

### Reranking

Le Batch 48 distingue explicitement :

- snapshot où le ranking est applicable ;
- snapshot applicable avec au moins un changement de rang ;
- snapshot applicable sans aucun changement de rang ;
- candidat monté ;
- candidat descendu ;
- candidat inchangé avec `rank_change=0` ;
- candidat applicable dont `rank_change` est absent ;
- distribution exacte de `rank_change` ;
- moyenne et maximum de `abs(rank_change)`.

Ainsi `rank_change=0` n'est jamais assimilé à une absence de donnée.

### Order flow

Le diagnostic mesure :

- nombre et ratio de déduplications CVD/Aggressor ;
- nombre et ratio de conflits CVD/Aggressor.

Ces compteurs observent le comportement de la règle 47.5 ; ils ne rajoutent aucun poids.

### Analytics exploitable

Un candidat PERP est classé « sans Analytics exploitable » lorsqu'aucune des cinq séries diagnostiquées n'est `AVAILABLE`, ou lorsque le contexte de ranking est absent.

Ce compteur est distinct du score `0` : un candidat peut avoir cinq séries `AVAILABLE` et un score nul simplement parce qu'aucune anomalie validée n'est active.

### Marchés et scopes

Le diagnostic expose :

- une ventilation `SPOT / PERPETUAL / ALL` ;
- score moyen descriptif par scope lorsqu'il existe des candidats classés ;
- snapshots applicables/effectifs par scope ;
- couverture déterministe triée par marché ;
- nombre d'observations, disponibilité Analytics, score moyen et changements de rang effectifs par marché.

Aucune comparaison de P&L n'est effectuée.

## 6. Cockpit

Un dock compact séparé est ajouté au cockpit afin de ne pas surcharger le dock Radar principal.

Il affiche :

- distribution récente `0..4` ;
- taux de reranking effectif ;
- contributions des quatre familles ;
- santé des cinq séries ;
- candidats sans série `AVAILABLE` ;
- mouvements de rang moyen/max ;
- conflits/déduplications order-flow ;
- différences descriptives par scope ;
- couverture compacte par marché.

Le frontend ne conserve pas l'historique de référence : il ne fait que lire l'agrégat backend. Fermer le frontend n'affecte donc ni le Radar ni l'observation backend.

## 7. Compatibilité et invariants

Le Batch 48 ne modifie pas :

- le score `0..4` ;
- les caractéristiques 47.2–47.4 ;
- `interest_level` ;
- `candidate_limit` ;
- l'ordre canonique de ranking ;
- l'admission ou la suppression des candidats ;
- les positions SPOT en scope `ALL` ;
- Agent ;
- Risk Engine ;
- Broker ;
- les ordres Kraken ;
- le mode PAPER ;
- l'exécution SPOT-only.

Les snapshots antérieurs sans contrat Analytics 47.5 sont ignorés explicitement et comptés dans `legacy_snapshots_ignored` au lieu d'être interprétés rétroactivement.

## 8. Validation préparée

Tests Batch 48 ajoutés pour couvrir notamment :

- distribution `0..4` ;
- composantes comptées une seule fois ;
- séries comptées une seule fois ;
- déduplications/conflits order-flow ;
- statuts dégradés ;
- score nul versus Analytics indisponible ;
- `rank_change=0` versus ranking non applicable/manquant ;
- amplitude/direction des changements de rang ;
- scopes SPOT/PERPETUAL/ALL ;
- couverture par marché et fenêtre temporelle ;
- legacy ;
- borne interne 96 ;
- non-mutation de la population et de `interest_level` ;
- absence de dépendance Agent/Risk/Broker/P&L futur ;
- route API additive et validation du `limit`.

La validation complète du repository doit rester :

```powershell
python -m pytest -q
cd frontend
pnpm typecheck
pnpm test
cd ..
git diff --check
```

Aucune réussite de ces commandes complètes ne doit être déclarée tant qu'elles n'ont pas été réellement exécutées sur le repository complet.

## 9. Interprétation des observations

Ces métriques répondent à la question « comment le ranking Analytics se comporte-t-il réellement ? », pas à la question « est-il rentable ? ».

Une corrélation observée ultérieurement avec des mouvements de prix ne constitue pas à elle seule une justification pour modifier les poids, les seuils ou la stratégie. Toute calibration future devra faire l'objet d'un batch séparé avec protocole causal explicite, sans look-ahead ni optimisation post-hoc.
