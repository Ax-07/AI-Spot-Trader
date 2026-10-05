# Batch 47.5 — Influence multi-analytics bornée sur le ranking

## Statut

**INTÉGRÉ sur GitHub `main` via `d988de42dd684b597a78a6ce1d6d32a86147bf37` (`feat: add bounded multi-analytics radar ranking`).**

Base auditée au démarrage du batch :

```text
Repository               : Ax-07/AI-Spot-Trader
Branche                  : main
HEAD initial             : e972fd9112363b268a53658fe5ce88facbfa7dd7
Commit fonctionnel 47.4 : 472f3adca1d19822289af47b52b03afab3cda0fb
Clôture documentaire 47.4: e972fd9
Commit fonctionnel 47.5 : d988de42dd684b597a78a6ce1d6d32a86147bf37
```

Le contrat reste `market-attention-radar-v6`, additif, déterministe, causal et informatif. L'exécution reste SPOT uniquement.

## Objectif

Décider explicitement si les cinq séries Futures Analytics intégrées jusqu'au Batch 47.4 doivent influencer le classement du Market Attention Radar, tout en évitant :

- double comptage CVD/Aggressor ;
- avantage mécanique lié au nombre de métriques disponibles ;
- pénalité liée à une panne technique ;
- modification de `interest_level` ou de l'admission ;
- création d'un candidat uniquement grâce aux Analytics ;
- transformation du Radar en bot algorithmique traditionnel.

## Audit

### Confirmé

- `interest_level` est calculé avant Analytics ;
- `_deterministic_radar_sort_key()` place le niveau d'intérêt en premier ;
- la sélection Structure finale préserve intérêt puis Structure avant le reste de la clé ;
- `candidate_limit` appartient à `MarketAttentionPolicy` (`10` par défaut, `1..30`) ;
- le scan Analytics alimente le cache avant Structure, mais l'enrichissement 47.4 intervenait après admission dans la shortlist ;
- les cinq séries partagent un scanner, un curseur, un cache et un sémaphore uniques ;
- CVD et Aggressor Differential décrivent deux vues du même order flow agressif ;
- OI/Funding/Liquidation/CVD/Aggressor exposent déjà les caractéristiques nécessaires ;
- les statuts dégradés sont explicites ;
- CVD/Aggressor avec MAD nul restent `UNAVAILABLE` sans score extrême artificiel.

### Obsolète après intégration

La règle 47.4 « aucun impact Analytics sur le ranking » reste historiquement vraie pour 47.4 mais n'est plus l'état courant depuis `d988de4`.

### Manquant avant 47.5

- politique multi-analytics bornée ;
- déduplication CVD/Aggressor ;
- diagnostics d'influence ;
- règle SPOT/PERPETUAL/ALL ;
- tests garantissant l'absence d'impact Agent/Risk/Broker.

## Options comparées

### 1. Aucun impact

Très sûr, mais les cinq séries resteraient purement descriptives.

### 2. Tie-break strict

Influence trop faible et rarement observable à cause des clés existantes déjà fortement discriminantes.

### 3. Bonus/malus sur le score existant

Rejeté : cela aurait pu modifier `interest_level`, franchir un seuil d'admission ou introduire une fausse sémantique directionnelle.

### 4. Score multi-analytics séparé et plafonné

**Retenu et intégré.**

Cette solution conserve `interest_level` intact, borne l'influence, permet la déduplication order-flow et expose un diagnostic autonome.

## Politique intégrée

### Score `0..4`

```text
OPEN_INTEREST       : +1 max
FUNDING             : +1 max
LIQUIDATION_VOLUME  : +1 max
ORDER_FLOW          : +1 max
TOTAL               : 0..4
```

Une famille contribue uniquement lorsqu'une caractéristique 47.2–47.4 est active et que la série correspondante est `AVAILABLE`.

La disponibilité seule vaut 0.

### Symétrie des séries signées

Les extrêmes positifs et négatifs sont symétriques pour **l'attention**.

Ils ne constituent jamais une instruction BUY/SELL et ne modifient pas l'Agent stratégique.

### Déduplication CVD / Aggressor

CVD et Aggressor Differential partagent une seule composante `ORDER_FLOW` :

```text
un seul signal actif          -> +1
deux signaux concordants      -> +1 total
deux signaux opposés          -> 0
aucun signal exploitable      -> 0
```

Le diagnostic expose `order_flow_deduplicated` et `order_flow_conflict`.

### Données dégradées

Les statuts suivants sont neutres et ne produisent aucun malus :

```text
UNAVAILABLE
PARTIAL
INSUFFICIENT_HISTORY
STALE
TECHNICAL_ERROR
NOT_APPLICABLE
```

Une panne fournisseur ne devient jamais une information de marché.

## Place dans le ranking

Le score Analytics ne peut agir qu'après admission du candidat.

Il ne modifie jamais :

- `interest_level` ;
- `candidate_limit` ;
- les filtres utilisateur ;
- les conditions d'éligibilité ;
- la population de candidats.

Hiérarchie PERP :

```text
interest_level
-> événement Structure confirmé
-> analytics_ranking.score
-> reste de la clé microstructure / activité / liquidité
-> symbole déterministe
```

Un score Analytics élevé ne peut donc pas dépasser un niveau d'intérêt supérieur ou une priorité Structure supérieure.

## Compatibilité des scopes

### SPOT

Aucun reranking Analytics. Aucun contexte Futures requis.

### PERPETUAL

Les PERP déjà présents peuvent être réordonnés entre eux.

### ALL

Les positions SPOT restent fixes. Seuls les PERP peuvent échanger leurs propres slots.

Cette règle évite de favoriser PERPETUAL par rapport à SPOT uniquement parce que les Futures Analytics n'ont pas d'équivalent SPOT.

## API et cockpit

`market-attention-radar-v6` est conservé.

Extension additive optionnelle :

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

Le cockpit expose :

- score `0..4` ;
- composantes ;
- caractéristiques retenues ;
- état de chaque série ;
- déduplication/conflit order-flow ;
- rang avant/après ;
- variation réelle de rang ;
- rappel explicite de l'absence d'impact direct Agent/Risk/Broker.

Les payloads antérieurs restent compatibles car `analytics_ranking` est optionnel.

## Invariants préservés

- un seul Agent IA stratégique ;
- Kraken exchange initial ;
- Risk Engine déterministe avec autorité finale ;
- aucune sortie LLM directement exécutable ;
- PAPER ;
- exécution SPOT uniquement ;
- aucun short, levier, margin, future ou perpetual exécuté ;
- un seul scanner/cache/cursor Analytics ;
- policy réseau inchangée ;
- statistiques 47.2–47.4 inchangées ;
- aucun look-ahead ;
- aucun ajustement post-hoc d'une décision ;
- aucune optimisation sur le P&L.

## Tests ciblés ajoutés

Backend :

- symétrie des séries signées ;
- score plafonné à 4 ;
- déduplication CVD/Aggressor ;
- conflit order-flow ;
- données absentes/insuffisantes/stale/technical/partial neutres ;
- disponibilité sans anomalie = 0 ;
- MAD nul CVD = 0 influence ;
- compatibilité snapshots historiques ;
- ordre intérêt -> Structure -> Analytics ;
- scope `ALL` avec slots SPOT immuables ;
- scope `SPOT` inchangé ;
- égalités déterministes ;
- aucune création/suppression de candidat ;
- aucune dépendance Agent/Risk/Broker.

Frontend :

- score/composantes/déduplication ;
- rang avant/après et variation ;
- compatibilité payload legacy ;
- libellés explicites ;
- séries indisponibles sans contribution négative.

## Validation finale

Validations de préparation ChatGPT :

```text
python -m py_compile production + test backend 47.5 : PASS
harnais backend isolé ranking 47.5                  : PASS — 15/15
tsc strict ciblé market-attention.ts                : PASS
tsc syntaxe lib + cockpit                           : PASS
test frontend 47.5                                  : PASS — 4/4
```

Validation complète locale utilisateur :

```text
git diff --check       : PASS — warnings LF -> CRLF uniquement
python -m pytest -q    : PASS — suite backend complète à 100 %
pnpm typecheck         : PASS
pnpm test              : PASS — 86/86
git push origin main   : PASS — e972fd9..d988de4
git status --short     : propre
```

Warnings connus et non bloquants :

- dépréciations FastAPI/Starlette dans les dépendances de test ;
- warning Node `MODULE_TYPELESS_PACKAGE_JSON`.

Ces warnings n'ont provoqué aucun échec et n'ont pas été mélangés au périmètre fonctionnel 47.5.

## Décisions

Les ADR suivantes sont **ADOPTÉES via `d988de4`** :

- ADR-345 — score Analytics séparé et plafonné à quatre familles ;
- ADR-346 — CVD + Aggressor = une seule composante order-flow ;
- ADR-347 — Analytics ne crée aucun candidat et ne modifie pas `interest_level` ;
- ADR-348 — une série Analytics indisponible est neutre.

## Conclusion

Le Batch 47.5 introduit une influence Analytics volontairement limitée : elle **priorise uniquement l'attention entre PERP déjà sélectionnés**.

Le Radar reste déterministe, causal, informatif et indépendant de la décision stratégique de trading.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**
