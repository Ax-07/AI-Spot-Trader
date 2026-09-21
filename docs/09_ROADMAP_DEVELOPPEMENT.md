# 09 — Roadmap de développement

## Règle de lecture

Un batch n'est **intégré** qu'après validation locale, commit et push confirmés sur `main`.

## Batches 00 à 15.3 — intégrés

Les étapes historiques suivantes sont intégrées : documentation/bootstrap, contrats domaine, Kraken Spot public, Market State, Portfolio/Paper Broker, Risk Engine, Agent Luna/Sol, boucle autonome, persistance PostgreSQL, API FastAPI, cockpit Next.js, analytics, expérimentation agressivité, comparaison Luna/Sol, chat opérateur, composition runtime PAPER, contexte marché multi-horizon et découplage contexte/cadence.

Référence fonctionnelle Batch 15.3 : `d0f6d46b9adb37117051a7a497a8d55075c41d32`.

## Batch 16 — Kraken Derivatives PAPER

**État : intégré sur `main` au commit fonctionnel `06e3185c8a8c638263427842ab6591a2397810e0` (`feat: add Kraken derivatives paper trading`).**

Le support intégré couvre le domaine `SPOT | PERPETUAL | FUTURE`, l'exécution PAPER des perpetuals linéaires en marge ISOLATED, LONG/SHORT, levier déterministe, P&L, funding, reduce-only, protections Risk, API/analytics étendus, sans API Kraken privée ni LIVE.

## Batch 16.1 — Smoke test PERPETUAL PAPER

**État : validé localement le 21 septembre 2026 ; non intégré à GitHub tant que le commit/push utilisateur n'est pas effectué.**

### Correctif inclus

- accepter les valeurs entières négatives de `contractValueTradePrecision` dans le parser Kraken Derivatives ;
- exemples réels observés : `PF_PEPEUSD`, `PF_SHIBUSD`, `PF_BONKUSD` à `-3` ;
- non-régression conservée pour `PF_XBTUSD` à `4` ;
- test dédié ajouté.

### Validation locale

```text
pytest            : 339 passés
ruff check .       : OK
mypy .             : OK
git diff --check   : aucune erreur, warnings LF -> CRLF uniquement
```

### Smoke réel validé

- `BTC/USD` / `PF_XBTUSD` ;
- cycle `COMPLETED` ;
- Agent `HOLD` ;
- Risk `ALLOW` / `HOLD_NO_EXECUTION` ;
- analytics `paper-analytics-v2` validés sur base PostgreSQL isolée ;
- equity `1000 -> 1000` ;
- `trade_count=0`, `hold_count=1`.

### Non validé en réel

Le smoke n'ayant produit aucun ordre, il ne valide pas encore : ouverture LONG/SHORT, fills dérivés, funding accumulé, P&L de position, réduction/fermeture ni `reduce_only`.

## Batch 16.2 — Isolation durable des runs PAPER

**Proposé — sujet séparé découvert pendant le Batch 16.1.**

Objectif : empêcher les analytics de mélanger plusieurs expériences PAPER indépendantes stockées dans la même base.

Périmètre à auditer avant implémentation :

- notion durable de run (`paper_run_id` ou mécanisme équivalent) ;
- création et reprise d'un run ;
- propagation vers cycles, décisions, risk results, fills et snapshots utiles ;
- filtrage des endpoints analytics ;
- compatibilité avec les données historiques sans identifiant de run ;
- stratégie de migration PostgreSQL ;
- comportement cockpit/API ;
- tests d'isolation de deux runs dans une même base.

Aucune solution n'est considérée comme intégrée avant audit et décision explicite.

## Batch 17 — Robustesse Derivatives

**Proposé.** Validation live des schémas publics Kraken sur davantage d'instruments, tiers de marge par taille, liquidation PAPER plus fidèle, cockpit dédié dérivés, reprise/reconciliation du ledger mémoire, scénarios multi-position/multi-instrument et smokes contrôlés d'ouverture/réduction/fermeture.

## LIVE — toujours séparé

Le LIVE n'est pas une suite automatique. Il nécessitera une décision explicite et un batch séparé couvrant : adaptateur privé Kraken, permissions minimales sans retrait, idempotence, réconciliation, recovery, limites renforcées, activation opérateur et observabilité.
