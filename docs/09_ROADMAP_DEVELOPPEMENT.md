# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub vérifié                    : 321ce2d19105046af1f11295d67130402c09f2c5
Référence fonctionnelle Batch 19.6A  : 3c53af3bdb1ef53c574e26afe9b6178a374d9f06
Batch 19.5                            : intégré sur GitHub main
Batch 19.6A                           : intégré sur GitHub main
Batch 19.6B                           : patch proposé, non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch. Le document détaillé des améliorations est `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Jalons intégrés

- 18.1 à 18.8 : tools Agent read-only, sélection multi-marchés, expérimentation, recovery et résilience réseau ;
- 18.9A à 18.9C : Control Plane backend/frontend et validation comportementale ;
- 18.10 à 18.13 : refonte UX, guide opérateur, simplification, dark mode et modernisation ;
- Batch 19.1 : comptabilité SPOT canonique ;
- Batch 19.2 : mark-to-market canonique, equity/exposition backend et monitors SPOT/PERPETUAL sans LLM ;
- Batch 19.3 : `CapacityEvaluator`, modes `NORMAL` / `MANAGEMENT`, économie IA et barrière Risk contre l'augmentation d'exposition en MANAGEMENT ;
- Batch 19.4 : découverte dynamique Kraken, watchlist multi-marchés auditée, même Agent stratégique, fallback/recovery et configurateur simplifié ;
- Batch 19.5 : projection d'explicabilité opérateur Agent/Risk/exécution depuis les faits persistés ;
- Batch 19.6A : backend candles OHLCV, cache borné, recovery et streaming cockpit partagé.

## Batch 19.5 — Explicabilité opérateur

**État : intégré sur GitHub `main`.**

Référence : `07050faea54bbed89cf250b34f8e97bd10d94bd3` (`feat: add operator AI and risk explainability`).

Résultat : projection défensive depuis les faits persistés ; séparation contexte/discovery, sélection marché, Agent, Risk et exécution PAPER ; distinction HOLD/MODIFY/REJECT/FAILED ; aucune causalité inventée.

Validation opérateur communiquée : 8 tests ciblés, 586 tests backend avec 2 warnings, `pnpm lint`, `pnpm typecheck` et `pnpm build` passés. La revue visuelle light/dark + responsive reste distincte si elle n'a pas été réalisée.

## Batch 19.6A — Backend candles, cache et streaming cockpit

**État : intégré sur GitHub `main`.**

Référence : `3c53af3bdb1ef53c574e26afe9b6178a374d9f06` (`feat: add backend candle cache and streaming`).

Architecture intégrée :

```text
SPOT      : Kraken REST OHLC + WebSocket v2 OHLC
PERPETUAL : Kraken Futures charts + WebSocket public trade agrégé
                         |
                         v
              Candle canonique OHLCV
                         |
              cache process-local borné
                         |
             hub partagé par market key
                  /               \
        API historique       WebSocket cockpit
```

Choix actifs : clé `symbol + market_type + timeframe`, aucune persistence SQL candles, déduplication et candle courante causale, aucun trou inventé, backfill après reconnexion/gap, un stream backend partagé, timeframes fermés, aucune IA/Risk dans ce pipeline.

Validation opérateur 19.6A : 53 tests ciblés passés ; suite backend 604 tests passés avec 2 warnings ; `git diff --check` sans erreur de whitespace. Validation ChatGPT préalable : 18 tests 19.6A et `py_compile` passés.

## Batch 19.6B — Vue Marchés, Lightweight Charts et markers

**État : patch proposé, non intégré.**

Périmètre implémenté dans le patch :

- navigation visible `Accueil | Marchés | Positions | Historique | Réglages` sans créer une seconde navigation ;
- marchés = watchlist effective backend lorsqu'elle existe, sinon univers de campagne actif comme bootstrap, puis ajout des positions ouvertes ; aucune sélection/ranking stratégique TypeScript ;
- onglets marché responsive, un seul marché/timeframe chargé à la demande ;
- `lightweight-charts` pour chandeliers OHLC et volume ;
- historique initial par `GET /api/v1/markets/candles`, puis WebSocket `/api/v1/markets/candles/stream` via le proxy cockpit `/backend` ;
- reconnexion frontend bornée et cleanup lors du changement de marché/timeframe ou démontage ;
- petit cache client process-local ; aucune nouvelle persistence ;
- timeframes centralisés et strictement alignés sur 19.6A ;
- contexte de position affiché depuis `/portfolio`, sans recalcul depuis les candles ;
- markers BUY/SELL créés uniquement depuis les fills persistés `/executions` ; `reduce_only` peut annoter une réduction ; aucune clôture n'est déduite lorsqu'aucun fait canonique ne l'atteste ;
- sélection d'un marker -> `/cycles/{cycle_id}` pour réutiliser l'explicabilité 19.5 ;
- aucune connexion frontend directe à Kraken, aucun P&L/Risk parallèle, aucune candle/fill/causalité inventée.

Validation ChatGPT réellement exécutée sur le patch :

- `node --test --experimental-strip-types src/lib/market-candles.test.mjs` : **6 tests passés** ;
- parsing/transpilation TypeScript des six fichiers `.ts/.tsx` nouveaux/modifiés : **passé**.

Restent à valider localement avant intégration :

- mise à jour `pnpm-lock.yaml` après installation de `lightweight-charts` ;
- `pnpm test` ;
- `pnpm lint` ;
- `pnpm typecheck` ;
- `pnpm build` ;
- runtime avec backend 19.6A réel : historique, snapshot WS, update, reconnexion/stale/error ;
- revue visuelle light/dark, desktop/mobile, nombreuses paires/symbole long, position/sans position, rationale longue, raisons Risk multiples et markers rapprochés.

Le Batch 19.6B ne devient « intégré » qu'après validation opérateur réelle puis commit/push.

## Cadences à maintenir distinctes

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY / SELL / HOLD ;
3. **discovery / watchlist IA** : lente, même Agent ;
4. **streaming marché / candles** : technique, déterministe, sans LLM et indépendant des trois précédentes.

## Périmètres ultérieurs

- LIVE reste séparé et ultérieur ;
- FUTURE daté reste hors exécution/streaming 19.6A/19.6B ;
- multi-quote/FX reste à traiter explicitement ;
- persistence durable des candles uniquement sur besoin démontré ;
- aucun ranking algorithmique stratégique ne doit être introduit silencieusement.
