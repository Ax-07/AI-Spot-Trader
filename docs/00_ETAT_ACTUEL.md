# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub intégré : `74c168180716e484ea2ec76f461620f595cb1b91` (`fix: finalize Batch 16.1 perpetual paper smoke`).
- Commit fonctionnel Batch 16 : `06e3185c8a8c638263427842ab6591a2397810e0` (`feat: add Kraken derivatives paper trading`).
- Batch 16.1 intégré sur GitHub `main` le 21 septembre 2026 au commit `74c168180716e484ea2ec76f461620f595cb1b91`.

## Batch 16.1 — Smoke Kraken PERPETUAL PAPER

Le Batch 16.1 corrige le parsing Kraken Derivatives de `contractValueTradePrecision` afin d'accepter les précisions entières négatives réellement renvoyées par l'API publique.

Exemples observés sur Kraken :

- `PF_PEPEUSD`, `PF_SHIBUSD`, `PF_BONKUSD` : `contractValueTradePrecision = -3` ;
- `PF_XBTUSD` : `contractValueTradePrecision = 4`.

La conversion reste `min_order_quantity = 10^-precision` : une précision `-3` donne donc une quantité minimale de `1000`, tandis que `4` donne `0.0001`.

Le correctif reste local au parseur Kraken Derivatives et un test de non-régression couvre simultanément une précision négative et le cas historique positif.

## Validation locale confirmée

Validation fournie depuis le dépôt local utilisateur :

```text
pytest            : 339 passés
ruff check .       : OK
mypy .             : OK
git diff --check   : aucune erreur, warnings LF -> CRLF uniquement
```

Smoke réel Kraken PERPETUAL PAPER :

- paire canonique : `BTC/USD` ;
- instrument Kraken : `PF_XBTUSD` ;
- cycle : `COMPLETED` ;
- Agent : `HOLD` ;
- Risk : `ALLOW` / `HOLD_NO_EXECUTION` ;
- analytics `paper-analytics-v2` validés sur une base PostgreSQL isolée ;
- `initial_equity = 1000` ;
- `ending_equity = 1000` ;
- `trade_count = 0` ;
- `hold_count = 1`.

## Ce que le smoke ne valide pas

Le smoke s'est terminé en `HOLD`. Il **ne valide donc pas en réel** :

- l'ouverture `LONG` ou `SHORT` ;
- les fills dérivés ;
- l'accumulation effective du funding sur une position ouverte ;
- le P&L de position réalisé/non réalisé après exécution ;
- `reduce_only`, réduction et fermeture de position.

Ces chemins restent couverts par les tests existants, mais pas encore par un smoke Kraken réel avec exécution PAPER.

## Dette découverte — isolation des runs PAPER

Les analytics PAPER actuels agrègent les cycles présents dans une même base PostgreSQL. Plusieurs essais PAPER indépendants utilisant la même base peuvent donc être mélangés dans les métriques.

Il n'existe pas encore de `paper_run_id` durable permettant d'isoler explicitement un run expérimental de bout en bout.

Le smoke Batch 16.1 a utilisé une base PostgreSQL isolée pour éviter ce mélange. Cette limite est documentée mais **n'est pas corrigée dans le Batch 16.1**.

## Prochaine étape proposée

Traiter dans un batch séparé l'isolation durable des runs PAPER (`paper_run_id` ou mécanisme équivalent), puis seulement ensuite poursuivre les smokes d'exécution dérivés contrôlés avec ouverture/réduction/fermeture.
