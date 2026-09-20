# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité le 20 septembre 2026 : `6415064b0f9bb0ee625cc42e8209cdf4388167e0`
- Commit : `docs: record Batch 07 integration`
- Commit fonctionnel du Batch 07 : `caff3851d8299630f328b955c69eb31eb11baef0` (`feat: add Luna agent provider`).
- Batch 07 intégré sur `main`.

## Validation finale connue du Batch 07

Validation locale Windows confirmée par l'utilisateur :

- `pytest backend` : **168 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 54 source files** ;
- `git diff --check` : aucune erreur ;
- uniquement les warnings habituels LF → CRLF ;
- 2 warnings de dépréciation FastAPI/Starlette sans échec.

## Batch 08 préparé dans cette livraison — non intégré

- Nouveau package `ai_spot_trader.trading` avec `TradingCycleRunner.run_cycle()` et `TradingEngine`.
- Un seul cycle à la fois grâce à un verrou partagé par les appels manuels et la boucle autonome.
- Pipeline explicite : Market -> Portfolio -> Agent -> Risk -> Broker -> snapshot portfolio post-exécution.
- Même `MarketState` pour Agent, Risk et Broker ; même `PortfolioState` pré-cycle pour Agent et Risk ; aucun refresh marché caché.
- `cycle_id`, horloge, cadence et timeouts injectables ; aucune valeur produit de cadence n'est figée.
- HOLD traverse Risk ; REJECT reste un résultat métier normal ; seul Risk produit l'`ExecutionIntent`.
- Erreurs techniques conservées comme résultats `FAILED`, sans conversion silencieuse en HOLD.
- Timeouts explicites sur Market, Agent et Broker ; aucun timeout artificiel sur Risk.
- Start/stop coopératif ; arrêt pendant la cadence immédiat ; aucune seconde loop simultanée.
- `AppRuntime` peut posséder un moteur injecté et l'arrête proprement au shutdown FastAPI, sans démarrage automatique.
- Aucune persistance durable, aucune API de contrôle trading, aucune API Kraken privée et aucun LIVE.

## Validation du Batch 08

Validation réellement exécutée dans l'environnement ChatGPT :

- `pytest -q backend/tests/test_trading_engine.py` : **34 tests passés** ;
- `pytest -q backend/tests/test_health.py backend/tests/test_trading_engine.py` : **37 tests passés** ;
- aucun appel OpenAI ou Kraken réel ;
- `compileall` ciblé : OK ; lignes Python <= 100 et espaces de fin de ligne : OK.

Validation locale Windows confirmée par l'utilisateur avant le correctif Ruff final :

- `pytest backend` : **203 tests passés** ;
- mypy : **Success: no issues found in 57 source files** ;
- `git diff --check` : aucune erreur ;
- 2 warnings de dépréciation FastAPI/Starlette sans échec ;
- Ruff a signalé uniquement deux défauts de style dans le patch Batch 08 : `SIM105` et ordre des imports.

Le correctif de cette livraison traite ces deux défauts Ruff. `ruff check backend` reste à relancer localement après extraction du correctif avant intégration.

## État d'intégration

**Batch 08 — Boucle autonome : préparé mais non encore intégré.**

Ne pas le considérer comme intégré avant validation locale puis commit/push confirmés sur `main`.

## Prochaine étape après validation/intégration

**Batch 09 — Persistance et journal d'audit** : PostgreSQL, migrations et conservation durable des cycles, HOLD, REJECT, MODIFY, ALLOW, intents et fills.

## Points encore à décider

- Capital PAPER initial et devise de référence produit.
- Univers initial de paires Kraken.
- Valeur produit de cadence.
- Valeurs produit des limites Risk.
- Mapping exact de l'agressivité 1–10.
- Valeurs de référence fee/spread/slippage PAPER.
- ORM, migrations, rétention, frontière de journée et reprise après panne.
