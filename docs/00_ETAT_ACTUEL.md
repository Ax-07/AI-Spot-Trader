# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` observé au démarrage du Batch 19.6A :
  `07050faea54bbed89cf250b34f8e97bd10d94bd3`
  (`feat: add operator AI and risk explainability`).
- Batch 19.5 : **intégré sur GitHub `main`** à cette référence.
- Validation automatisée 19.5 communiquée par l'opérateur : 8 tests ciblés ; suite backend complète 586 tests passés avec 2 warnings de dépréciation ; frontend `pnpm lint`, `pnpm typecheck`, `pnpm build` passés.
- La revue visuelle 19.5 light/dark + desktop/mobile reste une validation opérateur distincte si elle n'a pas encore été réalisée.

## État fonctionnel intégré

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- `NORMAL` / `MANAGEMENT`, discovery dynamique et watchlist auditée sont intégrés ;
- l'explicabilité 19.5 expose séparément contexte/discovery, sélection de marché, Agent, Risk et exécution PAPER depuis les faits persistés ;
- frontend toujours sans autorité trading ni calcul financier parallèle.

## Batch 19.6A — patch proposé, non intégré

Le patch 19.6A ajoute la couche backend canonique pour les futurs charts :

```text
Kraken REST / charts -> historique initial
Kraken WebSocket -> updates temps réel
backend -> normalisation OHLCV + cache borné + recovery
FastAPI -> historique + WebSocket cockpit
```

Principes : cache process-local sans nouvelle table SQL ; clé `(symbol, market_type, timeframe)` ; ordre/déduplication/candle courante ; backfill sans invention de données ; un stream backend partagé par plusieurs consommateurs ; lifecycle backend indépendant du frontend ; aucune IA, stratégie ou logique Risk dans ce pipeline.

Limites fournisseur retenues : historique Spot borné à 720 rows par l'endpoint OHLC ; PERPETUAL via Kraken Futures charts avec cible jusqu'à 1000 rows, sans supposer que le fournisseur renvoie toujours cette profondeur.

Validation exécutée par ChatGPT dans le workspace reconstruit du patch : `pytest -q tests/test_candle_streaming.py` = **18 tests passés** ; `py_compile` des fichiers modifiés = **passé**. La suite complète du repository n'a pas pu être exécutée dans cet environnement et reste à valider localement.

## Prochaine priorité

1. extraire le patch 19.6A à la racine du repository et exécuter les tests ciblés puis `pytest` sur le repository complet ;
2. après validation opérateur, commit/push du 19.6A puis mise à jour de son état en « intégré » ;
3. Batch 19.6B — vue Marchés, charts et markers ;
4. conserver séparément la revue visuelle 19.5 si elle reste à faire.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, puis distinguer clairement état intégré, modifications locales et patch proposé.
