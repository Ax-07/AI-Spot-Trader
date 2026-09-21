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

**État : intégré.**

Le correctif accepte les valeurs négatives de `contractValueTradePrecision`. Le smoke réel `BTC/USD / PF_XBTUSD` a terminé `COMPLETED`, Agent `HOLD`, Risk `ALLOW / HOLD_NO_EXECUTION`, analytics `1000 -> 1000`, `trade_count=0`, `hold_count=1`.

Ce smoke initial ne validait pas encore les branches d'exécution LONG/SHORT.

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
- filtres run-scoped disponibles pour audit ;
- endpoints de découverte/sélection des runs ;
- aucun changement frontend requis.

## Batch 16.3 — Smokes d'exécution Derivatives contrôlés

**État : intégré sur GitHub `main` au commit fonctionnel `520b016eb501f1a208bcb6d0e90eb1df947e1d0b` (`test: add controlled perpetual paper smoke harness`).**

Le harness de validation est séparé du runtime normal et ne force jamais l'Agent de production.

Validation locale :

```text
pytest               : suite complète OK, 2 warnings externes FastAPI/Starlette
ruff check .          : All checks passed
mypy .                : Success: no issues found in 109 source files
git diff --check      : aucune erreur
```

Smokes réels contrôlés `BTC/USD / PF_XBTUSD`, levier `1x`, `ISOLATED` :

- LONG : ouverture, HOLD/mark, funding, réduction `reduce_only`, fermeture oversize bornée par Risk, position finale vide ;
- SHORT : scénario symétrique validé ;
- 4 cycles `COMPLETED` et 3 exécutions par run ;
- aucun cycle `FAILED` ;
- P&L, marge, frais/spread/slippage et funding valorisés ;
- aucune inversion accidentelle ;
- deux `paper_run_id` distincts fermés proprement ;
- contrôle `verify-isolation` : `isolation_verified=true`.

## Prochain jalon — Premier run Agent réel PERPETUAL PAPER

**Proposé comme prochaine étape immédiate.**

Objectif : lancer GPT-5.6 Luna dans la composition normale PERPETUAL PAPER, sans décision forcée, avec Risk conservant l'autorité finale.

Le run doit mesurer honnêtement décisions `BUY/SELL/HOLD`, fills éventuels, coûts, funding, exposition, P&L et drawdown. Un `HOLD` naturel est un résultat valide et ne doit pas être modifié post-hoc.

## Batch 17 — Robustesse Derivatives

**Proposé après les premiers essais Agent PERPETUAL PAPER.**

Pistes : validation des schémas publics Kraken sur davantage d'instruments, tiers de marge par taille, liquidation PAPER plus fidèle, cockpit dédié dérivés, reprise/réconciliation du ledger mémoire, scénarios multi-position/multi-instrument.

## LIVE — toujours séparé

Le LIVE n'est pas une suite automatique. Il nécessitera une décision explicite et un batch séparé couvrant : adaptateur privé Kraken, permissions minimales sans retrait, idempotence, réconciliation, recovery, limites renforcées, activation opérateur et observabilité.
