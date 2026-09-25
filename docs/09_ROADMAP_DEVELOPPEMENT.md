# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub vérifié après push 19.7       : 9dcaf028de81b68ed357d1e6712fa833626353b9
Référence fonctionnelle Batch 19.6A     : 3c53af3bdb1ef53c574e26afe9b6178a374d9f06
Référence fonctionnelle Batch 19.6B     : a446628918a614d2ae0ac3b55243881aad5ef410
Batch 19.5                              : intégré sur GitHub main
Batch 19.6A                             : intégré sur GitHub main
Batch 19.6B                             : intégré sur GitHub main
Batch 19.7                              : intégré sur GitHub main, commit fonctionnel 8b969b4
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
- Batch 19.6A : backend candles OHLCV, cache borné, recovery et streaming cockpit partagé ;
- Batch 19.6B : vue Marchés, Lightweight Charts, consommation REST/WS 19.6A et markers de fills persistés ; validation locale complète au commit `a446628`.
- Batch 19.7 : overlays de position canoniques (`Prix moyen`, `Mark backend`, `Liquidation` PERPETUAL) depuis `/portfolio`, intégrés au commit `8b969b4`.

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

**État : intégré sur GitHub `main`.**

Référence fonctionnelle : `a446628918a614d2ae0ac3b55243881aad5ef410` (`feat: add cockpit market charts and trade markers`). Clôture documentaire poussée ensuite au commit `b5a26f77d1951f8eb39df30b5b6f3b5b81f4d585`, puis synchronisée au HEAD `2d51cb68d55e34065626902d3792988976da11d9`.

Périmètre intégré dans le commit fonctionnel :

- navigation visible `Accueil | Marchés | Positions | Historique | Réglages` ;
- marchés = watchlist effective backend lorsqu'elle existe, sinon univers de campagne actif comme bootstrap, puis ajout des positions ouvertes ; aucune sélection/ranking stratégique TypeScript ;
- onglets marché responsive, un seul marché/timeframe chargé à la demande ;
- `lightweight-charts` pour chandeliers OHLC et volume ;
- historique initial par `GET /api/v1/markets/candles`, puis WebSocket `/api/v1/markets/candles/stream` via le proxy cockpit `/backend` ;
- reconnexion frontend bornée, cleanup et petit cache mémoire non persistant ;
- timeframes strictement alignés sur les capacités 19.6A ;
- contexte de position affiché depuis `/portfolio`, sans recalcul depuis les candles ;
- markers BUY/SELL créés uniquement depuis les fills persistés `/executions` ; `reduce_only` peut annoter une réduction ; aucune clôture n'est déduite sans fait canonique ;
- sélection d'un marker -> `/cycles/{cycle_id}` pour réutiliser l'explicabilité 19.5 ;
- aucune connexion frontend directe à Kraken, aucun P&L/Risk parallèle, aucune candle/fill/causalité inventée.

Validation opérateur locale :

- `pnpm test` : **6/6 passés** ;
- `pnpm lint` : **passé sans erreur ni warning** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé** ;
- `git diff --check` : **aucune erreur de whitespace** ; avertissements LF -> CRLF uniquement ;
- arbre de travail propre après commit.

Le warning `MODULE_TYPELESS_PACKAGE_JSON` du test runner reste non bloquant.

## Batch 19.7 — Overlays de position sur les charts Marchés

**État : intégré sur GitHub `main`.**

Périmètre intégré :

- projection frontend stricte des faits `/portfolio` déjà typés ; aucun nouveau contrat backend ;
- ligne `Prix moyen` seulement si `average_entry_price` existe ;
- ligne `Mark backend` seulement si `mark_price` existe ;
- ligne `Liquidation` seulement pour PERPETUAL et si `liquidation_price` existe ;
- pour SPOT, la position doit correspondre au symbole construit avec l'actif détenu et le `settlement_asset` canonique ; aucune conversion multi-quote/FX ;
- conversion texte -> nombre uniquement pour le rendu Lightweight Charts, sans formule financière ;
- `createPriceLine` / `removePriceLine` natifs ; cleanup sur changement de marché, position, thème et démontage ;
- thème light/dark purement visuel ; labels distincts conservés même lorsque les niveaux sont proches, avec alignement des labels de l'échelle prix ;
- aucune règle frontend de staleness sur `mark_observed_at` ;
- chandeliers, volumes et markers de fills 19.6B conservés.

Référence fonctionnelle intégrée : `8b969b434916d89f6b6aa127c3bac9c27e990966` (`feat: add canonical position overlays to market charts`). Clôture documentaire poussée au commit `9dcaf028de81b68ed357d1e6712fa833626353b9`.

Validation opérateur locale :

- `pnpm test` : **17/17 passés** ;
- `pnpm lint` : **passé** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé** ;
- `git diff --check` : **aucune erreur de whitespace**, avertissements LF -> CRLF uniquement.

Validation ChatGPT préalable : `node --test --experimental-strip-types src/lib/market-candles.test.mjs` : **17/17 passés**. Le warning `MODULE_TYPELESS_PACKAGE_JSON` reste non bloquant. Le push GitHub `main` a été vérifié au HEAD `9dcaf028de81b68ed357d1e6712fa833626353b9`.

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
