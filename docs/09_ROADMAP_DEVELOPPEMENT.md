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

**État : intégré sur GitHub `main` le 21 septembre 2026 ; HEAD documentaire actuel vérifié : `08926e98dda3fe9ad7b68b4ddb5c582cbe49529c`.**

Le correctif accepte les valeurs négatives de `contractValueTradePrecision`. Le smoke réel `BTC/USD / PF_XBTUSD` a terminé `COMPLETED`, Agent `HOLD`, Risk `ALLOW / HOLD_NO_EXECUTION`, analytics `1000 -> 1000`, `trade_count=0`, `hold_count=1`.

Le smoke ne valide pas encore en réel l'ouverture LONG/SHORT, les fills dérivés, le funding accumulé sur position, le P&L de position, la réduction/fermeture ni `reduce_only`.

## Batch 16.2 — Isolation durable des runs PAPER

**État : intégré sur GitHub `main` au commit fonctionnel `003bbadd7ae2f8288ccde049433832046f066957` (`feat: add durable paper run isolation`).**

Implémentation intégrée :

- table durable `paper_runs` ;
- FK nullable `audit_cycles.paper_run_id` ;
- décisions, Risk, intents et fills rattachés indirectement par leur cycle ;
- migration PostgreSQL `0002_paper_runs` sans backfill trompeur ;
- anciennes lignes conservées à `NULL` et exclues des analytics run-scoped ;
- même mécanisme pour SPOT et PERPETUAL ;
- analytics d'un run strictement filtrés par `paper_run_id` ;
- filtres run-scoped disponibles pour cycles/décisions/Risk/exécutions/erreurs/market ;
- endpoints `GET /api/v1/paper-runs`, `/paper-runs/current`, `/paper-runs/{id}` ;
- `GET /api/v1/analytics?paper_run_id=<uuid>` pour sélection explicite ;
- aucun changement frontend requis : la composition PAPER garde le run courant comme défaut.

Sémantique du cycle de vie : `engine stop/start` conserve le run ; arrêt backend propre clôt le run ; redémarrage backend crée un nouveau run car le ledger reste en mémoire et est réinitialisé. Aucun resume automatique d'un ancien run n'est autorisé tant que la reprise durable du portefeuille n'existe pas.

Validation locale confirmée avant intégration :

```text
alembic upgrade head : 0001_audit_journal -> 0002_paper_runs
alembic current      : 0002_paper_runs (head)
pytest               : 344 passed, 2 warnings externes
ruff check .          : All checks passed
mypy .                : Success: no issues found in 106 source files
git diff --check      : aucune erreur, warnings LF -> CRLF uniquement
```

## Batch 16.3 — Smokes d'exécution Derivatives contrôlés

**Proposé comme prochain batch fonctionnel après l'intégration du Batch 16.2.**

Objectif : valider séparément un chemin PAPER réel contrôlé couvrant ouverture LONG/SHORT, fill, mark/funding, réduction/fermeture et `reduce_only`, sans mélanger les métriques entre expériences.

## Batch 17 — Robustesse Derivatives

**Proposé.** Validation des schémas publics Kraken sur davantage d'instruments, tiers de marge par taille, liquidation PAPER plus fidèle, cockpit dédié dérivés, reprise/réconciliation du ledger mémoire, scénarios multi-position/multi-instrument.

## LIVE — toujours séparé

Le LIVE n'est pas une suite automatique. Il nécessitera une décision explicite et un batch séparé couvrant : adaptateur privé Kraken, permissions minimales sans retrait, idempotence, réconciliation, recovery, limites renforcées, activation opérateur et observabilité.
