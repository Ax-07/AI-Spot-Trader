# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- Commit fonctionnel Batch 08 audité le 20 septembre 2026 : `8deb72faeeaa1ac065189480c64ba16410c0d451`
- Commit : `feat: add autonomous trading loop`
- Batch 08 — Boucle autonome : **intégré sur `main`**.
- Le push `6415064..8deb72f` a été confirmé et le `git status --short` local était vide après intégration.

## État backend intégré

- Données publiques Kraken SPOT et `MarketState` déterministe, sans look-ahead.
- `PaperPortfolioLedger` et `PaperBroker` avec frais, spread et slippage injectables.
- Agent Luna/Sol derrière `LLMProvider`, sortie limitée à BUY/SELL/HOLD + quantité stratégique.
- Risk Engine déterministe avec ALLOW/MODIFY/REJECT ; seul Risk crée l'`ExecutionIntent`.
- `TradingCycleRunner.run_cycle()` orchestre un cycle PAPER cohérent avec un unique `MarketState` partagé Agent/Risk/Broker.
- `TradingEngine` répète les cycles séquentiellement, sans chevauchement ni rattrapage concurrent.
- HOLD traverse Risk et n'appelle pas Broker ; REJECT reste une issue métier normale.
- Erreurs techniques et timeouts Market/Agent/Broker restent distincts d'un HOLD.
- `AppRuntime` peut arrêter proprement un moteur injecté au shutdown FastAPI ; aucun trading ne démarre automatiquement.
- Aucune persistance durable, aucune API Kraken privée et aucun LIVE.

## Validation finale du Batch 08

Validation locale Windows confirmée par l'utilisateur avant intégration :

- `ruff check backend` : **All checks passed** ;
- `pytest backend` : **203 tests passés**, 2 warnings de dépréciation FastAPI/Starlette sans échec ;
- mypy : **Success: no issues found in 57 source files** ;
- `git diff --check` : aucune erreur, uniquement les warnings habituels LF → CRLF ;
- `git status --short` : vide après commit/push ;
- commit/push confirmé sur `main` : `8deb72f`.

Tests complémentaires réellement exécutés dans l'environnement ChatGPT pendant le Batch 08 : suite ciblée Health + Trading **37/37**, `compileall` ciblé et contrôles statiques de cohérence. Aucun appel OpenAI ou Kraken réel.

## Prochaine étape

**Batch 09 — Persistance et journal d'audit** : PostgreSQL, migrations et conservation durable des cycles, décisions, HOLD, REJECT, MODIFY, ALLOW, erreurs techniques, intents et fills, avec reprise/réconciliation/idempotence à cadrer.

## Points encore à décider

- Capital PAPER initial et devise de référence produit.
- Univers initial de paires Kraken.
- Valeur produit de cadence.
- Valeurs produit des limites Risk.
- Mapping exact de l'agressivité 1–10.
- Valeurs de référence fee/spread/slippage PAPER.
- ORM, migrations, rétention, frontière de journée et stratégie de reprise après panne.
