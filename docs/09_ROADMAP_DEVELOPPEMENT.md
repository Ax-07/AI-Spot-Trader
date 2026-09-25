# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub main observé au début 19.6A : 07050faea54bbed89cf250b34f8e97bd10d94bd3
Batch 19.5                               : intégré sur GitHub main
Batch 19.6A                              : patch proposé, non intégré
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
- Batch 19.5 : projection d'explicabilité opérateur Agent/Risk/exécution depuis les faits persistés.

## Batch 19.5 — Explicabilité opérateur

**État : intégré sur GitHub `main`.**

Référence : `07050faea54bbed89cf250b34f8e97bd10d94bd3` (`feat: add operator AI and risk explainability`).

Résultat intégré :

- aucune table SQL ni ledger parallèle ;
- `/api/v1/cycles/latest` et `/api/v1/cycles/{cycle_id}` séparent contexte/discovery, sélection du marché, décision Agent, résultat Risk et exécution PAPER ;
- HOLD, MODIFY, REJECT et FAILED restent sémantiquement distincts ;
- les historiques incomplets n'inventent ni rationale ni causalité ;
- Accueil, Historique et Positions consomment une présentation défensive de faits canoniques.

Validation automatisée locale communiquée par l'opérateur :

- `pytest tests/test_cycle_explainability.py` : 8 tests passés ;
- `pytest` : 586 tests passés, 2 warnings de dépréciation ;
- `pnpm lint`, `pnpm typecheck`, `pnpm build` : passés.

La revue visuelle light/dark + responsive reste une validation opérateur distincte si elle n'a pas encore été réalisée.

## Batch 19.6A — Backend candles, cache et streaming cockpit

**État : patch proposé, non intégré.**

Architecture proposée :

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

Choix :

- clé canonique `symbol + market_type + timeframe` ;
- aucune persistence SQL ajoutée : le besoin est un cache de diffusion/recovery, pas une nouvelle source durable ;
- profondeur cache par défaut bornée à 1000 ; historique Spot réellement borné à 720 rows par l'endpoint Kraken OHLC ;
- PERPETUAL : cible jusqu'à 1000 candles via charts, profondeur effective laissée au fournisseur ;
- déduplication, remplacement de la candle courante, finalisation causale et tri chronologique ;
- aucune candle synthétique pour combler un trou ;
- backfill REST après reconnexion ou gap détecté ;
- un stream backend partagé par plusieurs consommateurs cockpit, avec nombre total de streams borné ;
- streams détenus par le backend et nettoyés au shutdown ; fermer le frontend ne ferme pas le moteur ni le service de candles ;
- timeframes explicites et bornés par capacités fournisseur ; FUTURE daté hors périmètre ;
- aucune IA, aucun ranking stratégique et aucun changement Risk.

Validation exécutée par ChatGPT sur le workspace reconstruit du patch :

- `pytest -q tests/test_candle_streaming.py` : **18 tests passés** ;
- `python -m py_compile ...` sur les fichiers 19.6A : **passé** ;
- `ruff` non disponible dans l'environnement ;
- suite backend complète non exécutée, le repository complet ne pouvant pas être cloné dans cet environnement.

## Prochaine séquence

### Validation/intégration opérateur 19.6A

Exécuter les tests ciblés Kraken/candles puis `pytest` sur le repository complet. Ne marquer 19.6A intégré qu'après commit/push réel.

### Batch 19.6B — Vue Marchés, Lightweight Charts et markers

- navigation Marchés ;
- onglets par marché surveillé ;
- Lightweight Charts ;
- overlays position/mark/liquidation ;
- markers BUY/SELL/réduction/clôture ;
- détails fill/rationale/Risk ;
- lazy loading côté cockpit sans seconde connexion Kraken.

## Cadences à maintenir distinctes

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY / SELL / HOLD ;
3. **discovery / watchlist IA** : lente, même Agent, 15 min par défaut ;
4. **streaming marché / candles** : technique, déterministe, sans LLM et indépendant des trois précédentes.

## Périmètres ultérieurs

- LIVE reste séparé et ultérieur ;
- FUTURE daté reste hors exécution et hors streaming 19.6A ;
- multi-quote/FX reste à traiter explicitement ;
- persistence durable des candles à reconsidérer seulement sur besoin démontré ;
- aucun ranking algorithmique stratégique ne doit être introduit silencieusement.
