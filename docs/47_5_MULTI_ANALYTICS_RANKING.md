# Batch 47.5 — Influence multi-analytics bornée sur le ranking

## Objet

Le Batch 47.5 décide explicitement si les cinq séries Futures Analytics intégrées jusqu'au Batch 47.4 doivent influencer le classement du Market Attention Radar, sans transformer le Radar en moteur de trading.

Base auditée au démarrage :

```text
Repository            : Ax-07/AI-Spot-Trader
Branche               : main
HEAD GitHub réel      : e972fd9112363b268a53658fe5ce88facbfa7dd7
Commit fonctionnel 47.4: 472f3adca1d19822289af47b52b03afab3cda0fb
Clôture documentaire  : e972fd9 — docs: mark batch 47.4 integrated
```

Le contrat reste `market-attention-radar-v6`, additif, déterministe, causal et informatif. L'exécution reste SPOT uniquement.

## Audit avant modification

### Confirmé

- `interest_level` est calculé dans `market/attention.py` à partir des caractéristiques OHLCV, de l'état d'activité et du régime de liquidité ; les seuils restent LOW/MEDIUM/HIGH/VERY_HIGH.
- la clé canonique `_deterministic_radar_sort_key()` trie par niveau d'intérêt, priorité des caractéristiques, liquidité puis intensité/accélération/mouvement ; le symbole ferme l'ordre déterministe ;
- la microstructure enrichit ensuite le niveau d'intérêt et `_v3_sort_key()` conserve ce niveau comme premier critère ;
- `candidate_limit` n'est pas calculé dynamiquement par Analytics : il provient de `MarketAttentionPolicy` (`10` par défaut, borné `1..30`) et est appliqué avant l'enrichissement Analytics, dans les sélections canoniques activité/microstructure puis dans la sélection finale Structure ;
- la sélection finale Structure utilise `_structured_candidate_sort_key()` : niveau d'intérêt d'abord, puis événement Structure confirmé, puis le reste de la clé canonique ;
- le scan Analytics est déclenché avant le scan Structure afin d'alimenter le cache, mais `perpetual_analytics` n'était ajouté aux candidats qu'après la shortlist finale ;
- en 47.4, `_snapshot_with_analytics()` ajoutait `perpetual_analytics`, les caractéristiques Analytics dans `combined_characteristics` et leurs libellés dans `interest_reasons` **après** la shortlist finale ; ces raisons descriptives étaient plafonnées à huit mais ne recalculaient pas `interest_level` ;
- les cinq séries utilisent un seul `PerpetualAnalyticsScanner`, un seul `_perpetual_analytics_cursor`, un seul `_cache`, un sémaphore global et la même policy réseau ;
- CVD et Aggressor Differential décrivent tous deux l'order flow agressif ; les traiter comme deux preuves indépendantes créerait une double pondération ;
- OI, Funding et Liquidation Volume exposent déjà des caractéristiques robustes et testées ; aucune nouvelle statistique n'est nécessaire pour le ranking ;
- `INSUFFICIENT_HISTORY`, `STALE`, `TECHNICAL_ERROR` et l'absence d'une série sont déjà distingués au niveau des snapshots ;
- pour CVD/Aggressor signés, MAD nul produit `UNAVAILABLE` sans fallback ratio ni score extrême artificiel.

### Obsolète

- `docs/00_ETAT_ACTUEL.md`, `docs/09_ROADMAP_DEVELOPPEMENT.md` et `docs/10_DECISIONS_ET_CHANGELOG.md` citaient encore `472f3ad` comme HEAD audité alors que le HEAD réel est la clôture documentaire `e972fd9` ;
- la règle Batch 47.4 « aucun impact ranking Analytics » devient historique à partir de 47.5. Elle reste vraie pour 47.4 mais n'est plus l'état courant après application de ce batch.

### Manquant avant 47.5

- une politique multi-analytics explicite et plafonnée ;
- une séparation visible entre les raisons qui expliquent `interest_level` et les diagnostics qui expliquent le reranking Analytics ; le patch conserve la compatibilité de `interest_reasons` mais ajoute `analytics_ranking` comme diagnostic dédié ;
- une déduplication CVD/Aggressor ;
- des diagnostics montrant les composantes retenues et ignorées ;
- une règle claire pour `SPOT`, `PERPETUAL` et `ALL` ;
- des tests prouvant qu'Analytics ne peut pas créer un candidat ni modifier Agent/Risk/Broker.

### À décider

- niveau d'autorité exact des Analytics sur le ranking ;
- traitement des métriques signées : direction de trading ou simple intensité d'attention ;
- comportement lorsqu'une série est indisponible ;
- place exacte du score dans la clé de tri.

## Options comparées

### 1. Aucun impact Analytics

Avantage : risque architectural minimal. Inconvénient : les cinq séries resteraient purement descriptives alors qu'elles possèdent désormais des caractéristiques causales, reproductibles et testées. Cette option est sûre mais n'exploite pas la valeur d'attention démontrée par les batches 47.2–47.4.

### 2. Analytics comme tie-breaker strict

Avantage : influence très faible. Inconvénient : le tie-break strict serait presque inerte car les clés canoniques contiennent déjà de nombreux critères puis le symbole, rendant les égalités complètes rares. La politique serait difficile à observer et à tester utilement.

### 3. Bonus/malus sur le score existant

Rejeté. Modifier le score qui détermine `interest_level` pourrait faire franchir un seuil LOW/MEDIUM/HIGH/VERY_HIGH et donc modifier l'admission dans la population de candidats. Cela mélangerait détection d'activité, Analytics Futures et sémantique de direction. Un funding négatif ou une impulsion CVD négative n'est pas intrinsèquement un « malus » d'attention.

### 4. Score multi-analytics séparé, plafonné, injecté ensuite

**Retenu.** Cette solution sépare explicitement l'attention Analytics du niveau d'intérêt existant, permet la déduplication sémantique, expose des diagnostics clairs et peut être insérée après l'admission dans la shortlist.

## Politique retenue

### Score d'attention Analytics `0..4`

Quatre familles sémantiques indépendantes valent chacune au maximum `+1` :

```text
OPEN_INTEREST       : +1 si expansion OU contraction active et série AVAILABLE
FUNDING             : +1 si extrême positif OU négatif actif et série AVAILABLE
LIQUIDATION_VOLUME  : +1 si spike actif et série AVAILABLE
ORDER_FLOW          : +1 max pour CVD + Aggressor Differential
```

La simple disponibilité d'une série ne donne aucun point. Le score ne dépend pas de la magnitude brute du z-score/MADσ ; il consomme uniquement les caractéristiques déjà validées par les batches 47.2–47.4.

Les anomalies signées sont symétriques pour l'attention : positif et négatif valent la même contribution lorsqu'ils sont statistiquement actifs. Ce score n'exprime donc jamais BUY/SELL.

### Déduplication CVD / Aggressor

CVD et Aggressor Differential constituent une seule famille `ORDER_FLOW` :

- un seul signal actif : `+1` ;
- deux signaux actifs concordants : `+1`, `order_flow_deduplicated=true` ;
- deux signaux actifs opposés : `0`, `order_flow_conflict=true` ;
- aucune série exploitable : `0`.

Il est donc impossible d'obtenir `+2` avec CVD + Aggressor.

### Données manquantes ou dégradées

Une série ne peut contribuer que si son statut est `AVAILABLE`. Les statuts suivants sont neutres :

```text
UNAVAILABLE
PARTIAL
INSUFFICIENT_HISTORY
STALE
TECHNICAL_ERROR
NOT_APPLICABLE
```

Ils n'ajoutent aucun point mais ne soustraient rien non plus. Une panne fournisseur ne devient jamais un malus de marché.

### Place dans le ranking

Le score n'est calculé qu'après la shortlist finale déjà construite par le pipeline canonique. Il ne modifie jamais :

- `interest_level` ;
- `candidate_limit` ;
- les conditions d'éligibilité ;
- les filtres utilisateur ;
- la population de candidats.

Pour les PERP déjà retenus, la hiérarchie devient :

```text
interest_level
-> événement Structure confirmé (timeframe puis type)
-> analytics_ranking.score (0..4)
-> reste de la clé microstructure / activité / liquidité
-> symbole déterministe
```

Analytics ne peut donc pas dépasser un candidat d'un niveau d'intérêt supérieur ni un événement Structure confirmé prioritaire.

### Compatibilité des scopes

- `SPOT` : classement inchangé, aucun contexte `analytics_ranking` ;
- `PERPETUAL` : les candidats PERP déjà présents peuvent être réordonnés ;
- `ALL` : les positions SPOT sont figées ; seuls les PERP peuvent échanger leurs propres emplacements entre eux.

Cette règle empêche de favoriser mécaniquement PERPETUAL face à SPOT simplement parce que SPOT n'a pas de Futures Analytics comparable.

## Contrat API additif

`market-attention-radar-v6` est conservé. Chaque candidat PERP peut exposer :

```text
analytics_ranking.score
analytics_ranking.max_score
analytics_ranking.components[]
analytics_ranking.order_flow_deduplicated
analytics_ranking.order_flow_conflict
analytics_ranking.applied_to_ranking
analytics_ranking.rank_before_analytics
analytics_ranking.rank_after_analytics
analytics_ranking.rank_change
analytics_ranking.ranking_policy
```

Chaque composante indique sa contribution, ses caractéristiques utilisées et l'état des séries sous-jacentes. Les rangs avant/après et `rank_change` rendent l'impact réellement observé explicite, y compris lorsqu'il vaut zéro. Le champ est optionnel afin de conserver la compatibilité des payloads legacy.

## Invariants préservés

- un seul Agent IA stratégique ;
- Risk Engine déterministe avec autorité finale ;
- aucun ordre direct issu du Radar ;
- aucune exécution PERPETUAL ;
- PAPER ;
- aucun short, levier, margin, future ou perpetual exécuté ;
- aucun nouveau scanner/cache/cursor Analytics ;
- policy réseau 47.4 inchangée : 10 marchés, 5 séries, 50 appels max/refresh, concurrence 4 ;
- aucun changement statistique 47.2–47.4 ;
- aucun look-ahead ni optimisation post-hoc sur le P&L.

## Tests ciblés ajoutés

Backend :

- symétrie des anomalies signées ;
- score plafonné à 4 ;
- déduplication CVD/Aggressor ;
- conflit order-flow ;
- séries absentes, insuffisantes, stale, technical error et partial neutres ;
- disponibilité sans anomalie = zéro ;
- MAD nul CVD = zéro influence ;
- compatibilité payload historique sans CVD/Aggressor ;
- insertion du score après intérêt + Structure ;
- scope ALL : slots SPOT immuables ;
- scope SPOT inchangé ;
- égalités déterministes ;
- aucune création/suppression de candidat ;
- aucune dépendance Agent/Risk/Broker et aucune modification directe d'`interest_level`.

Frontend :

- diagnostics score/composantes/déduplication et rang avant/après ;
- compatibilité payload legacy sans `analytics_ranking` ;
- libellés explicites ;
- séries indisponibles représentées sans contribution négative.

## Validation

Les résultats réellement exécutés dans l'environnement ChatGPT sont consignés dans `docs/00_ETAT_ACTUEL.md` et `docs/10_DECISIONS_ET_CHANGELOG.md`. La validation complète du repository doit être relancée localement après extraction du ZIP.
