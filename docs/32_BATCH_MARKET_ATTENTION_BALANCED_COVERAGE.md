# Batch 32 — Market Attention : couverture équilibrée SPOT/PERPETUAL

Date : 2026-09-28

## 1. Statut et base auditée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 1850ff8783d0d29a5dd6628bdf1e9bb11a08ca63
Commit     : feat: add robust market attention liquidity context
```

Batch 30 et Batch 31 sont intégrés dans cette base.

Le Batch 32 décrit ici un **patch proposé/local**. Il ne devient intégré qu'après validation, commit et push explicites par l'opérateur.

Le fichier local `trades_9h_analysis.json` est hors périmètre et ne fait pas partie de la livraison.

## 2. Constat confirmé

Le catalogue Market Attention intégré est trié par :

```text
(market_type.value, symbol)
```

La rotation précédente utilisait un unique `_scan_cursor` puis prélevait une tranche séquentielle de taille `scan_limit`.

Comme les marchés d'un même type sont contigus dans le catalogue, un refresh pouvait être composé exclusivement de PERPETUAL ou exclusivement de SPOT.

Avec un catalogue nettement plus grand que `scan_limit`, la couverture fraîche simultanée pouvait donc être techniquement valide mais peu représentative des deux familles.

## 3. Décision de rotation

La rotation devient **stratifiée et déterministe par `MarketType`**.

État interne :

```text
_scan_cursors[SPOT]
_scan_cursors[PERPETUAL]
```

Chaque famille progresse indépendamment dans sa propre séquence triée. Le wrap-around d'une famille ne réinitialise pas le curseur de l'autre.

Aucun résultat du Radar, ratio d'activité, régime de liquidité ou résultat web n'entre dans la rotation.

## 4. Allocation de `scan_limit`

La capacité est allouée à partir de :

```text
population SPOT
population PERPETUAL
scan_limit
```

Règle :

1. `target = min(scan_limit, population_totale)` ;
2. part exacte proportionnelle à chaque population ;
3. minimum d'une place pour chaque famille non vide lorsque `target` le permet ;
4. floor déterministe de la part proportionnelle ;
5. redistribution des places restantes selon le plus grand reliquat proportionnel, puis capacité restante et ordre fixe de type comme tie-breaker ;
6. aucune allocation ne dépasse la population de sa famille.

Exemples :

```text
100 SPOT / 100 PERPETUAL, scan_limit 120 -> 60 / 60
1000 SPOT / 1 PERPETUAL, scan_limit 120 -> 119 / 1
7 SPOT / 0 PERPETUAL, scan_limit 120 -> 7 / 0
3 SPOT / 4 PERPETUAL, scan_limit 120 -> 3 / 4
```

Cette formule évite un quota arbitraire 50/50 tout en garantissant qu'une petite famille disponible n'est pas systématiquement invisible.

## 5. Absence de starvation

Les marchés sélectionnés pour chaque famille sont pris à partir de son curseur propre, avec wrap-around modulo la taille de la famille.

Un refresh avance chaque curseur exactement du nombre de marchés alloué à cette famille. Après suffisamment de refreshs, tous les marchés de chaque famille non vide sont donc visités.

Le catalogue peut être rafraîchi sans perdre cette progression : chaque curseur est simplement ramené modulo la nouvelle taille de sa propre famille.

## 6. Diagnostics de couverture

`MarketAttentionOverview` ajoute deux compteurs structurés :

```text
scanned_market_type_counts
  SPOT
  PERPETUAL

fresh_market_type_counts
  SPOT
  PERPETUAL
```

Le premier décrit uniquement le batch scanné pendant le refresh courant.

Le second décrit le cache d'activité encore frais selon le TTL canonique ; il peut donc être supérieur au scan du refresh courant.

Le cockpit affiche ces informations sous forme compacte, sans transformer le dock en écran de debug.

## 7. PARTIAL vs qualité structurelle

L'audit confirme qu'il ne s'agit pas d'une contradiction.

- `data_quality = COMPLETE` : les observations OHLC/trades reçues sont structurellement cohérentes selon les règles du pipeline ;
- `status = PARTIAL` : un ou plusieurs horizons ne fournissent pas encore toutes les métriques nécessaires/exploitables.

Les statuts backend ne sont pas changés pour des raisons cosmétiques.

Le cockpit renomme simplement le bloc en **Qualité structurelle** et précise cette distinction.

## 8. Audit notionnel PERPETUAL

Chaîne auditée :

```text
Kraken Futures candles trade
-> volume provider
-> Candle.volume canonique
-> MarketActivityAnalyzer
-> notionnel éventuel
```

Constats :

- `KrakenCandleProvider` utilise bien les candles Futures `trade` ;
- le parser place la valeur provider `volume` directement dans `Candle.volume` ;
- le modèle `Candle` ne transporte ni unité de volume, ni `contract_size`, ni notionnel fournisseur ;
- les métadonnées d'instrument Kraken comportent un `contract_size` dans `DerivativeInstrument` ;
- le catalogue Market Attention convertit cependant ces instruments en `ExecutableMarket`, qui ne transporte pas cette métadonnée ;
- `MarketActivityAnalyzer` ne reçoit donc pas les éléments suffisants pour démontrer une formule canonique.

Conclusion du Batch 32 : **aucune conversion PERPETUAL n'est activée**.

```text
current_notional_usd  = null
baseline_notional_usd = null
notional_delta_usd    = null
liquidity_regime      = UNKNOWN
```

Aucune formule `candle.volume × close` ni conversion via `contract_size` n'est inventée.

## 9. SPOT et régimes de liquidité

Le comportement Batch 31 est conservé :

```text
SPOT BASE/USD
-> SPOT_BASE_VOLUME_X_5M_CLOSE_ESTIMATE

SPOT non USD
-> notionnel USD null
```

Les régimes restent :

```text
MICRO
LOW
MEDIUM
HIGH
VERY_HIGH
UNKNOWN
```

Ils restent descriptifs et non filtrants. Un petit marché peut toujours devenir candidat sur anomalie relative.

## 10. Seuils et budget web

Inchangés :

```text
ELEVATED      : 1.40
ACCELERATING : 1.75 + 0.25
VERY_HIGH     : 2.50 + 0.50

candidate_limit                  = 20
max_web_searches_per_refresh     = 8
```

La recherche web intervient toujours après la construction des candidats. Le seul fait d'être inclus dans le scan stratifié ne déclenche aucune recherche.

## 11. Barrières d'architecture

Préservées :

- un seul Agent IA stratégique ;
- Radar observation-only ;
- aucune donnée Radar envoyée à l'Agent ;
- aucune influence sur Market Discovery ;
- aucune influence sur Risk Engine ;
- aucune influence sur Broker/order flow ;
- aucun BUY/SELL/HOLD produit par le Radar ;
- `CandleStreamService` reste canonique ;
- aucun second pipeline OHLCV ;
- stratégie, prompts Agent, sizing et PAPER/LIVE inchangés.

## 12. Tests du batch

Nouveaux tests backend ciblent :

- allocation proportionnelle équilibrée ;
- population fortement déséquilibrée ;
- `scan_limit` respecté ;
- catalogue plus petit que la capacité ;
- SPOT-only et PERPETUAL-only ;
- présence des deux familles quand disponibles ;
- absence de starvation ;
- curseurs indépendants ;
- wrap-around indépendant ;
- indépendance vis-à-vis du cache/ratios d'activité ;
- compteurs `scanned` et `fresh` par type ;
- absence de recherche web causée par le scan seul.

Les tests Batch 30/31 existants restent responsables des contrats suivants : seuils inchangés, petit marché éligible, notionnel SPOT/USD, SPOT non USD `null`, PERPETUAL `null`, régimes stables et absence de dépendance Agent/Risk/Broker/Market Discovery.

Frontend : le fixture `MarketAttentionOverview` couvre les deux nouveaux compteurs, et les tests de formatage de liquidité restent inchangés.

## 13. Validation ChatGPT

Exécuté dans l'environnement de préparation :

```text
python -m py_compile backend/src/ai_spot_trader/market/attention.py
python -m py_compile backend/tests/test_market_attention_balanced_coverage.py
```

Succès.

Un harnais fonctionnel minimal du module patché a également validé :

```text
100/100, limite 120 -> 60/60
1000/1, limite 120 -> 119/1
single-family -> capacité disponible utilisée
4 refreshs sur 23 SPOT + 7 PERPETUAL -> tous les marchés vus
```

Frontend ciblé exécuté :

```text
node --test --experimental-strip-types \
  src/lib/market-attention.test.mjs \
  src/lib/market-attention-liquidity.test.mjs
```

Résultat : `9 passed, 0 failed`.

Le repository complet, son environnement Python et `pnpm` ne sont pas présents dans l'environnement ChatGPT ; la suite complète reste donc à exécuter localement.

## 14. Validation locale requise

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

Le fichier `trades_9h_analysis.json` doit rester non suivi et hors commit.
