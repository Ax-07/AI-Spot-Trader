# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- Référence fonctionnelle intégrée du Batch 19.6A :
  `3c53af3bdb1ef53c574e26afe9b6178a374d9f06`
  (`feat: add backend candle cache and streaming`).
- Batch 19.5 : **intégré** au commit `07050faea54bbed89cf250b34f8e97bd10d94bd3`.
- Batch 19.6A : **intégré sur GitHub `main`** ; la référence fonctionnelle ci-dessus reste le commit de code du batch.
- Validation automatisée 19.5 communiquée par l'opérateur : 8 tests ciblés ; suite backend complète 586 tests passés avec 2 warnings de dépréciation ; frontend `pnpm lint`, `pnpm typecheck`, `pnpm build` passés.
- La revue visuelle 19.5 light/dark + desktop/mobile reste une validation opérateur distincte si elle n'a pas encore été réalisée.

## État fonctionnel intégré

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- `NORMAL` / `MANAGEMENT`, discovery dynamique et watchlist auditée sont intégrés ;
- l'explicabilité 19.5 expose séparément contexte/discovery, sélection de marché, Agent, Risk et exécution PAPER depuis les faits persistés ;
- frontend toujours sans autorité trading ni calcul financier parallèle.

## Batch 19.6A — intégré

Le Batch 19.6A ajoute la couche backend canonique pour les futurs charts :

```text
Kraken REST / charts -> historique initial
Kraken WebSocket -> updates temps réel
backend -> normalisation OHLCV + cache borné + recovery
FastAPI -> historique + WebSocket cockpit
```

Principes : cache process-local sans nouvelle table SQL ; clé `(symbol, market_type, timeframe)` ; ordre/déduplication/candle courante ; backfill sans invention de données ; un stream backend partagé par plusieurs consommateurs ; lifecycle backend indépendant du frontend ; aucune IA, stratégie ou logique Risk dans ce pipeline.

Limites fournisseur retenues : historique Spot borné à 720 rows par l'endpoint OHLC ; PERPETUAL via Kraken Futures charts avec cible jusqu'à 1000 rows, sans supposer que le fournisseur renvoie toujours cette profondeur.

Validation opérateur locale avant intégration : tests ciblés candles/Kraken = **53 passés**, 2 warnings de dépréciation ; suite backend complète = **604 passés**, 2 warnings de dépréciation ; `git diff --check` sans erreur de whitespace, uniquement les avertissements LF -> CRLF. Validation ChatGPT préalable : 18 tests 19.6A ciblés + `py_compile` passés.

## Prochaine priorité

1. Batch 19.6B — vue Marchés, charts et markers consommant exclusivement les contrats backend 19.6A ;
2. conserver séparément la revue visuelle 19.5 si elle reste à faire.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, puis distinguer clairement état intégré, modifications locales et patch proposé.
