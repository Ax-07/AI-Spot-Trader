# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence auditée au démarrage du Batch 15.1

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité : `59e3bc26c7b4d6acca25bc7d21c85c3c14eeb336` (`fix(docs): restore Batch 15 state encoding`).
- HEAD fonctionnel Batch 15 sous-jacent : `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6` (`feat: add operator agent chat`).
- Les trois commits entre ces deux références sont documentaires ; le code fonctionnel Batch 15 reste celui de `1c182b8`.

## Batch 15.1 — composition runtime PAPER

Patch livré pour rendre le premier essai PAPER réellement exécutable sans ajouter de voie parallèle :

- composition canonique `Kraken public -> TradingCycleRunner -> Agent Luna/Sol -> Risk -> PaperBroker -> PaperPortfolioLedger -> audit PostgreSQL` ;
- même `PaperExecutionCostModel` injecté à Risk et au Paper Broker ;
- même ledger PAPER exposé au moteur, à FastAPI et au Chat en lecture seule ;
- même PostgreSQL utilisé par le writer d'audit et les lecteurs/analytics ;
- même `LLMModel` configuré transmis à l'Agent stratégique et au Chat opérateur ;
- configuration du premier run explicitement requise, sans defaults produit pour capital, paire, cadence, agressivité, Risk ou coûts ;
- `main:app` compose le runtime PAPER au lifespan mais ne démarre jamais automatiquement le moteur ;
- `POST /api/v1/engine/run-cycle` demande exactement un `TradingEngine.run_cycle()` et refuse si la boucle autonome tourne ;
- fermeture backend : moteur, ressources Kraken possédées, puis DB ;
- préflight PostgreSQL du writer avant chaque cycle ; une DB indisponible bloque le cycle avant Market/Agent/Risk/Broker ;
- aucune API Kraken privée et aucun LIVE.

## Fail-safe audit

La limite connue reste inchangée : il n'existe pas d'exactly-once global entre mutation du ledger mémoire et commit PostgreSQL.

Pour le premier essai, `AuditedTradingCycleRunner` vérifie d’abord la disponibilité du writer PostgreSQL avant d’appeler le runner canonique. Une erreur de préflight ou d’écriture est propagée et verrouille ensuite le wrapper en état **fail-closed** : tout cycle ultérieur est refusé avant Market/Agent/Risk/Broker jusqu’au redémarrage. Ce verrou ne constitue ni recovery ni réconciliation.

## Validation du patch

Exécuté par ChatGPT sur le patch isolé :

- compilation Python des fichiers ajoutés/modifiés ;
- validations dynamiques ciblées de la configuration fail-closed, du verrou mono-cycle/lifecycle et du latch d'audit ;
- contrôles statiques du composition root : Kraken public uniquement, absence de chemin BUY/SELL direct et partage explicite du cost model/ledger/runtime.

La suite backend complète, Ruff et mypy restent à exécuter localement après extraction du ZIP dans le repository, car l'environnement de génération ne dispose pas du clone Git local complet.

## Limites conservées

- PAPER/SPOT uniquement ; aucun LIVE, aucune API Kraken privée.
- Chat opérateur strictement conversationnel et non mutant.
- Ledger PAPER toujours mémoire ; recovery/reconciliation après crash différés.
- Aucun exactly-once global ledger/PostgreSQL.

## Prochaine étape

Valider localement le Batch 15.1, puis reprendre le protocole du premier essai PAPER : migrations PostgreSQL, backend démarré et moteur arrêté, inspection des surfaces, un cycle manuel, inspection complète, puis seulement un petit run autonome contrôlé. Le futur LIVE reste séparé au Batch 16 éventuel.
