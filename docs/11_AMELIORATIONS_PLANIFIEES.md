# 11 — Améliorations planifiées

> Référence de reprise des chantiers 19.x. Ce document distingue ce qui est **intégré**, ce qui est un **patch proposé à valider/intégrer** et ce qui reste **planifié**.

## 1. Référence

```text
Repository                   : Ax-07/AI-Spot-Trader
Branche                      : main
HEAD GitHub main observé     : 07050faea54bbed89cf250b34f8e97bd10d94bd3
État Batch 19.5              : intégré sur GitHub main
État Batch 19.6A             : patch proposé, non intégré
Date                         : 2026-09-25
```

Les Batches 19.1 à 19.5 sont intégrés. Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## 2. Invariants transverses

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement ;
- SPOT + PERPETUAL linéaire ;
- aucune sortie LLM ne déclenche directement Broker/Kraken ;
- Risk Engine déterministe = autorité finale ;
- IA = choix stratégique ;
- calculs, comptabilité, monitoring, capacité, filtrage technique, statistiques et streaming candles = déterministes ;
- frontend jamais source de vérité trading ;
- aucun secret dans prompts/logs/docs/Git ;
- frais, spread, slippage et funding pris en compte sans double comptage ;
- HOLD auditable ;
- aucun look-ahead ni sélection rétrospective ;
- aucune candle manquante inventée.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## 3. Cadences cibles

| Cadence | But | LLM |
| --- | --- | --- |
| Monitoring / mark-to-market | prix, marks, P&L, exposition, marge, liquidation, funding | non |
| Cycle stratégique | BUY / SELL / HOLD, avec restriction MANAGEMENT si nécessaire | oui, Agent unique |
| Discovery / watchlist | réévaluer les marchés intéressants | oui, même Agent |
| Streaming marché / candles | historique, candle courante, recovery, diffusion cockpit | non |

Le monitoring utilise ses cadences techniques propres. La discovery reste beaucoup plus lente. Le streaming candles est une quatrième cadence indépendante : il ne déclenche aucune décision Agent et n'intervient pas dans l'autorisation Risk.

# 4. Comptabilité SPOT par position — INTÉGRÉE 19.1

Confirmé : coût économique moyen pondéré, coût restant frais BUY inclus, ventes partielles au prorata, P&L réalisé net, pas de double comptage spread/slippage/frais, recovery JSON et compatibilité `accounting_complete=false`.

# 5. Monitoring / mark-to-market — INTÉGRÉ 19.2

Confirmé : marks SPOT causaux, P&L latent backend, agrégats portfolio, monitors backend indépendants de l'Agent et cockpit branché sur les champs canoniques.

# 6. Mode gestion lorsque l'exposition est saturée — INTÉGRÉ 19.3

Confirmé : `CapacityEvaluator`, `NORMAL` / `MANAGEMENT`, même `RiskPolicy`, recherche d'ouverture désactivée en MANAGEMENT, Risk bloque les hausses d'exposition et aucun nouvel état durable n'est créé.

# 7. Discovery automatique et watchlist — INTÉGRÉ 19.4

Confirmé : catalogue `MarketResearchService`, filtrage factuel sans ranking, watchlist sélectionnée par le même Agent, fallback, interaction avec MANAGEMENT, univers effectif incluant les positions, audit durable sans table mutable dédiée et recovery canonique.

Validation opérateur communiquée : 12 tests discovery, 578 tests backend avec 2 warnings de dépréciation, `pnpm lint`, `pnpm typecheck`, `pnpm build` passés.

# 8. Explicabilité des décisions IA — INTÉGRÉE 19.5

Le Batch 19.5 transforme les faits du journal de cycle en une vue de présentation typée et défensive sans créer une nouvelle source de vérité.

## 8.1 Architecture intégrée

```text
CycleAuditDetail existant
  + contexte capacité/discovery
  + MarketSelection
  + DecisionCandidate
  + RiskAssessment
  + ExecutionIntent / Fill
-> CycleExplainabilityResponse
-> /api/v1/cycles/latest
-> /api/v1/cycles/{cycle_id}
```

Décisions conservées : aucune nouvelle table SQL, aucun ledger parallèle, aucun recalcul stratégique/Risk/P&L, parsing tolérant des historiques partiels et aucune rationale inventée.

## 8.2 Sémantique opérateur

La projection distingue réellement :

- contexte `NORMAL` / `MANAGEMENT` ;
- `REFRESHED`, `CACHE_REUSED`, `FALLBACK`, `SKIPPED_MANAGEMENT` ;
- sélection du marché du cycle ;
- BUY / SELL / HOLD et rationale Agent ;
- ALLOW / MODIFY / REJECT et raisons Risk ;
- fill(s), intent sans fill et FAILED à son stage propre.

Positions ne prétend pas connaître la provenance d'une position lorsque les IDs d'origine ne sont pas portés par le modèle ; elle affiche seulement une activité auditée liée au même marché.

## 8.3 Validation 19.5

Communiquée par l'opérateur sur le repository complet :

- `pytest tests/test_cycle_explainability.py` : **8 tests passés** ;
- `pytest` : **586 tests passés**, 2 warnings de dépréciation ;
- `pnpm lint` : **passé** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé**.

Référence intégrée : `07050faea54bbed89cf250b34f8e97bd10d94bd3`.

La revue visuelle light/dark, desktop/mobile reste une validation opérateur distincte si elle n'a pas encore été réalisée.

# 9. Nouvel espace Marchés — PLANIFIÉ 19.6B

Navigation cible :

```text
Accueil | Marchés | Positions | Historique | Réglages
```

La vue Marchés affichera en onglets les marchés surveillés. Le frontend n'a aucune autorité sur la watchlist ou le moteur.

# 10. Charts chandeliers — PLANIFIÉ 19.6B

Renderer privilégié : **TradingView Lightweight Charts** avec données Kraken normalisées par le backend.

À afficher lorsque disponible : OHLC, volume, prix courant, prix moyen, mark/liquidation PERPETUAL et événements BUY/SELL/réduction/clôture.

Le frontend 19.6B doit consommer les endpoints 19.6A et ne pas se connecter directement à Kraken.

# 11. Historique candles + WebSocket — PATCH PROPOSÉ 19.6A

## 11.1 Pipeline

```text
SPOT      : Kraken REST OHLC + Kraken WS v2 OHLC
PERPETUAL : Kraken Futures charts + Futures WS trade
                         |
                         v
                 Candle OHLCV canonique
                         |
              cache backend process-local
                         |
          API historique + WebSocket cockpit
```

Le backend gère normalisation, déduplication, candle courante mutable, finalisation, recovery et limites de profondeur.

## 11.2 Modèle canonique

Chaque candle porte au minimum :

- symbole canonique ;
- type de marché ;
- timeframe ;
- `open_time` / `close_time` UTC ;
- open/high/low/close ;
- volume ;
- `is_final` ;
- `updated_at` causal.

Les clés sont séparées par `symbol + market_type + timeframe`. Une candle future ou une candle finale prétendument disponible avant sa clôture est refusée.

## 11.3 Timeframes explicites

SPOT 19.6A : `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`, `15d`.

PERPETUAL 19.6A : `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `12h`, `1d`, `1w`.

FUTURE daté n'est pas supporté par le pipeline 19.6A.

## 11.4 Historique initial

SPOT : le endpoint OHLC est réellement borné à **720 rows**. La cible générale « environ 1000 » n'est donc pas annoncée comme atteignable pour Spot via cette API seule.

PERPETUAL : Kraken Futures charts est interrogé avec une cible bornée à 1000 rows. Le backend accepte une profondeur plus faible si c'est ce que le fournisseur retourne réellement.

Aucune donnée n'est interpolée ou reconstruite artificiellement.

## 11.5 Cache

Le cache choisi est process-local :

- profondeur maximale bornée, 1000 par défaut ;
- ordre temporel garanti ;
- déduplication par `open_time` ;
- remplacement de la candle courante par sa version la plus récente ;
- aucune régression d'une candle finale vers un état courant ;
- aucune croissance mémoire illimitée.

Aucune migration SQL n'est ajoutée en 19.6A. Une persistence durable sera réévaluée seulement si un besoin concret de reprise hors process apparaît.

## 11.6 WebSocket et recovery

SPOT réutilise le WebSocket public v2 Kraken et le canal `ohlc`.

PERPETUAL utilise le feed public Futures `trade` afin de mettre à jour la candle courante à partir de trades réels. Il ne crée pas de candle vide pour une période sans trade.

Le hub backend :

- effectue un backfill au démarrage ;
- retente après déconnexion ;
- effectue un backfill lorsqu'un gap est détecté ;
- fusionne et déduplique ;
- conserve l'ordre causal ;
- expose les erreurs/staleness ;
- ne réécrit pas rétroactivement une donnée inexistante.

## 11.7 Lifecycle et multi-consommateurs

Un seul stream provider est créé par `CandleKey`. Plusieurs clients cockpit consomment le même flux backend.

Le nombre de streams et la taille des queues consommateurs sont bornés. Les abonnements appartiennent au backend ; fermer le frontend ne stoppe ni le moteur trading ni un stream backend déjà ouvert.

Au shutdown FastAPI, tous les tasks et transports candles sont nettoyés.

## 11.8 API cockpit

Contrats proposés :

```text
GET /api/v1/markets/candles
GET /api/v1/markets/candles/status
WS  /api/v1/markets/candles/stream
```

Le WebSocket cockpit envoie un snapshot initial puis les updates temps réel.

## 11.9 Validation exécutée par ChatGPT

Dans le workspace reconstruit du patch :

- `pytest -q tests/test_candle_streaming.py` : **18 tests passés** ;
- `py_compile` des fichiers 19.6A : **passé**.

Les tests ciblés couvrent parsing SPOT/Futures, ordre, déduplication, candle courante, nouvelle candle, profondeur, séparation des clés, historique incomplet, no-look-ahead, reconnect/backfill, absence de duplication, unsubscribe/cleanup, plusieurs consommateurs, staleness/erreur, API historique et WebSocket cockpit.

La suite backend complète reste à exécuter localement sur le repository complet avant intégration. `ruff` n'était pas disponible dans l'environnement ChatGPT.

# 12. Ordre global

| Ordre | Batch | Résultat principal | Statut |
| ---: | --- | --- | --- |
| 1 | 19.1 — Comptabilité SPOT | coût moyen, coût restant, P&L réalisé, recovery | intégré |
| 2 | 19.2 — Monitoring | P&L latent et état vivant sans LLM | intégré |
| 3 | 19.3 — Mode gestion | évite recherche IA inutile quand ouverture indisponible | intégré |
| 4 | 19.4 — Discovery/watchlist | univers dynamique audité, même Agent | intégré |
| 5 | 19.5 — Explicabilité | rationale visible vs Risk | intégré |
| 6 | 19.6A — Candles/streaming | données chart canoniques | patch proposé, validation opérateur requise |
| 7 | 19.6B — Marchés/charts | rendu, onglets, markers | planifié |

## 13. Validation restant à faire avant intégration 19.6A

Sur le repository complet :

- tests ciblés 19.6A + tests Kraken REST/WebSocket/market data existants ;
- `pytest` complet ;
- `git diff --check` ;
- éventuelle vérification réseau manuelle Kraken en environnement de test si souhaitée.

Le frontend n'est pas modifié par 19.6A : aucun `pnpm lint/typecheck/build` supplémentaire n'est requis pour ce patch.

## 14. Critères 19.6B ultérieurs

- lint/typecheck/build frontend ;
- light/dark ;
- changement onglet/timeframe ;
- markers cohérents avec les fills ;
- overlays cohérents avec les faits backend ;
- aucun calcul stratégique/Risk dupliqué côté frontend.
