# 09 — Roadmap de développement

## Règle de lecture

Un batch n'est **intégré** qu'après validation locale, commit et push confirmés sur `main`.

## Batches 00 à 15.3 — intégrés

Les étapes historiques suivantes sont intégrées : documentation/bootstrap, contrats domaine, Kraken Spot public, Market State, Portfolio/Paper Broker, Risk Engine, Agent Luna/Sol, boucle autonome, persistance PostgreSQL, API FastAPI, cockpit Next.js, analytics, expérimentation agressivité, comparaison Luna/Sol, chat opérateur, composition runtime PAPER, contexte marché multi-horizon et découplage contexte/cadence.

Référence fonctionnelle Batch 15.3 : `d0f6d46b9adb37117051a7a497a8d55075c41d32`.

HEAD GitHub vérifié avant Batch 16 : `c2e21f9b5b47086ea8dad336cc80ff15afa27ba0`.

## Batch 16 — Kraken Derivatives PAPER

**État : patch local proposé, non intégré tant que la validation utilisateur n'est pas terminée.**

### Objectif

Étendre l'architecture canonique existante de SPOT-only vers **SPOT + Kraken Derivatives** sans créer de second moteur ou second agent.

### Périmètre

- `MarketType`: SPOT / PERPETUAL / FUTURE ;
- métadonnées instruments Kraken Derivatives publiques ;
- normalisation symboles Kraken Futures ;
- positions LONG/SHORT séparées des holdings SPOT ;
- perpetuals linéaires PAPER exécutables ;
- contrats inverses et futures datés découverts mais non exécutables ;
- marge ISOLATED ;
- levier Risk-configuré, défaut 1x ;
- P&L réalisé/non réalisé ;
- funding perpetual ;
- notionnel, maintenance margin et liquidation price estimé ;
- ouvertures/augmentations/réductions/fermetures ;
- reduce-only et anti-retournement ;
- caps Risk de levier/notionnel/exposition/marge/liquidation ;
- API/analytics étendus sans migration DB ;
- aucune API Kraken privée ;
- aucun LIVE.

### Validation minimale attendue

```powershell
git diff --check
pytest
ruff check .
mypy .
git status --short
```

Tests ciblés exécutés par ChatGPT sur le patch reconstruit : **23 passés**. `compileall` : **réussi**. Ruff/mypy et suite complète restent à exécuter localement.

## Batch 16.1 — Smoke test PERPETUAL PAPER

**À faire après intégration du Batch 16.**

- sélectionner une paire Kraken Derivatives réellement disponible ;
- démarrer avec levier `1x` ;
- caps de notionnel/exposition faibles ;
- vérifier un cycle HOLD puis un scénario contrôlé d'ouverture/réduction/fermeture ;
- confirmer journal, portfolio, analytics, funding et absence de route LIVE/private ;
- comparer les faits API avec les logs locaux sans look-ahead.

## Batch 17 — Robustesse Derivatives

**Proposé.**

- validation live des schémas publics Kraken sur davantage d'instruments ;
- tiers de marge par taille plutôt qu'un taux conservateur unique ;
- liquidation PAPER plus fidèle/simulée explicitement ;
- affichage cockpit dédié positions dérivés/exposition/funding ;
- reprise/reconciliation du ledger mémoire après crash ;
- scénarios multi-position/multi-instrument si décidés.

## LIVE — toujours séparé

Le LIVE n'est pas une suite automatique du Batch 16. Il nécessitera une décision explicite et un batch séparé couvrant : adaptateur privé Kraken, permissions minimales sans retrait, idempotence, réconciliation, recovery, limites renforcées, activation opérateur et observabilité.

## Décisions encore ouvertes

- politique exacte CROSS margin ;
- support des contrats inverses ;
- exécution des futures datés ;
- liquidation PAPER détaillée ;
- exposition combinée multi-symboles plus avancée ;
- reconstruction durable du ledger ;
- auth/déploiement ;
- éventuel LIVE.
