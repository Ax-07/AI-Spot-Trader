# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence auditée au démarrage du batch contexte marché

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub intégré : `97d529647179c6769a6bdc528b9d9f5e7c85c119` (`feat: add multi-horizon market context`).
- Le document précédent référençait encore `59e3bc26c7b4d6acca25bc7d21c85c3c14eeb336` ; `4b9701f` a intégré la composition PAPER exécutable du Batch 15.1.

## État confirmé avant ce patch

Le premier essai PAPER réel sur `BTC/USDC` a validé PostgreSQL, Alembic, FastAPI, audit/analytics, chat Luna, Kraken public, un cycle manuel et un smoke run autonome. Le cycle restait toutefois limité à un prix instantané : `market_state.context = null`.

Cause racine confirmée : `KrakenMarketDataSource.snapshot()` construisait directement un `MarketState` minimal à partir du ticker WebSocket et contournait le `MarketStateBuilder` déjà canonique.

## Batch — contexte marché multi-horizon PAPER

Patch livré pour rendre le contexte marché exploitable sans architecture parallèle :

- `MarketStateBuilder` devient la voie canonique de construction du snapshot Kraken PAPER ;
- les horizons existants **5 min / 30 min** restent inchangés ;
- bootstrap historique via l'endpoint public Kraken OHLC en granularité technique **1 minute** ;
- la dernière bougie OHLC Kraken, non clôturée par contrat fournisseur, est toujours exclue ;
- chaque clôture historique est horodatée à `started_at + interval`, c'est-à-dire à son instant causal de disponibilité ;
- le ticker WebSocket courant reste la source du `last_price` courant ;
- les observations strictement futures ou postérieures au ticker courant ne sont jamais injectées ;
- la fraîcheur est contrôlée avant puis après la récupération historique afin qu'un appel OHLC lent ne masque pas une donnée devenue stale ;
- erreurs/timeout Market restent des erreurs techniques du cycle, jamais des HOLD synthétiques ;
- aucun signal, score ou décision déterministe BUY/SELL/HOLD n'est ajouté à la couche marché ;
- aucun changement frontend, aucune API Kraken privée et aucun LIVE.

## Validation

Exécuté par ChatGPT sur les fichiers livrés :

- `py_compile` des fichiers Python ajoutés/modifiés : réussi ;
- tests isolés REST Kraken : 7/7 ;
- tests isolés source marché Kraken : 15/15.

Validation locale confirmée le 21 septembre 2026 :

- tests ciblés Market State/Kraken/cycle : **71 passés** ;
- suite complète : **306 passés**, 2 warnings externes ;
- Ruff : **All checks passed** ;
- mypy : **94 fichiers sans erreur** ;
- `git diff --check` : aucune erreur, warnings LF -> CRLF uniquement ;
- cycle PAPER réel `BTC/USDC` : **COMPLETED**, `market_state.context` non nul, fenêtres 300 s / 1800 s complètes, respect du no-look-ahead, HOLD Agent fondé explicitement sur les horizons 5 min / 30 min.
- contrôle des chemins ZIP et absence de secrets/caches avant livraison.

La validation locale complète est terminée : `pytest`, Ruff, mypy et `git diff --check` sont tous validés.

## Limites conservées

- PAPER/SPOT uniquement ; aucun LIVE, aucune API Kraken privée.
- Chat opérateur strictement conversationnel et non mutant.
- Ledger PAPER toujours mémoire ; recovery/réconciliation après crash différés.
- Aucun exactly-once global ledger/PostgreSQL.
- La granularité OHLC 1 minute est un mécanisme de bootstrap descriptif ; les horizons stratégiques/descriptifs canoniques restent ceux du `MarketStateBuilder`.

## Prochaine étape

Le Batch 15.2 est intégré sur `main` et validé localement. La suite consiste à poursuivre les essais PAPER contrôlés avec le contexte multi-horizon désormais présent. Le LIVE reste séparé et hors périmètre.
