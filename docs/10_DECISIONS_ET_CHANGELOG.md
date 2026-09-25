# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs, les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers Broker/Kraken, SPOT sans short/levier, PERPETUAL linéaire avec protections déterministes, audit durable, no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence courante

```text
HEAD GitHub main observé au début 19.6A : 07050faea54bbed89cf250b34f8e97bd10d94bd3
Batch 19.5                               : intégré
Batch 19.6A                              : patch proposé, non intégré
```

Validation opérateur communiquée pour 19.5 : 8 tests ciblés ; suite backend complète 586 tests passés avec 2 warnings ; frontend lint/typecheck/build passés. La revue visuelle 19.5 reste une validation séparée si elle n'a pas été réalisée.

## Décisions historiques toujours actives

- ADR-173 à ADR-181 : StrategyRevision immuable, contrat Agent protégé, digests, Campaign snapshot, identité expérimentale, distinction Campaign/paper_run, runtime backend et recovery ;
- ADR-182 à ADR-188 : frontend client du Control Plane, API unique, validators backend, preview canonique, activation et reprise distinctes ;
- ADR-189/190 : adaptation JSON `market_type` à la frontière API et typing sans changement runtime ;
- ADR-191 à ADR-204 : cockpit orienté opérateur, aide progressive, règles métier backend, simplification UX et dark mode ;
- ADR-205 : comptabilité SPOT canonique backend ;
- ADR-206 / ADR-215 / ADR-216 / ADR-217 : monitoring et valorisation ;
- ADR-207 / ADR-218 / ADR-219 / ADR-220 : `NORMAL` / `MANAGEMENT`, `CapacityEvaluator` et économie IA ;
- ADR-221 à ADR-226 : discovery/watchlist dynamique, audit, univers effectif, whitelist et recovery ;
- ADR-227 à ADR-230 : projection d'explicabilité, corrélation par cycle et distinction HOLD/REJECT/FAILED.

## ADR-210 / ADR-227 à ADR-230 — Explicabilité opérateur

**INTÉGRÉS AU BATCH 19.5.**

Le cockpit expose séparément les rationales disponibles, les faits de sélection, le statut/les raisons Risk et l'exécution PAPER. La projection est construite depuis les faits persistés et ne devient jamais une nouvelle source de vérité.

L'Historique consomme le détail corrélé du cycle. Positions expose seulement une activité auditée liée au même marché lorsqu'aucune provenance directe n'existe. HOLD, REJECT, MODIFY et FAILED conservent des sémantiques distinctes.

## ADR-211 — Kraken/backend restent la source canonique des charts

**MATÉRIALISÉ DANS LE PATCH 19.6A.**

Le frontend futur 19.6B consomme uniquement les contrats backend candles. Il n'ouvre pas de connexion directe parallèle à Kraken.

Le backend normalise les données fournisseur vers `Candle`, maintient le cache et diffuse les updates cockpit.

## ADR-212 — Historique REST + streaming fournisseur, sans candle inventée

**MATÉRIALISÉ DANS LE PATCH 19.6A.**

SPOT : historique `/0/public/OHLC` + WebSocket v2 `ohlc`.

PERPETUAL : Futures charts pour l'historique/backfill + feed public `trade` pour la candle courante. Les trades sont agrégés sans créer de candle pour un intervalle sans donnée réelle.

Un trou ou une reconnexion déclenche un backfill. Les rows récupérées sont fusionnées/dédupliquées ; un trou non récupérable reste visible comme trou.

## ADR-213 — Cache process-local borné, pas de table SQL 19.6A

**DÉCISION 19.6A.**

Le besoin actuel est une mémoire technique de diffusion/recovery, pas un nouveau ledger durable. `CandleCache` est donc process-local, borné par clé et dédupliqué.

Ajouter une table SQL maintenant créerait une seconde responsabilité durable sans besoin démontré. La persistence sera réévaluée seulement si un besoin produit/recovery hors process l'exige.

## ADR-214 — Quatre cadences distinctes

**DÉCISION 19.6A.**

1. monitoring / mark-to-market ;
2. cycle stratégique IA ;
3. discovery / watchlist IA ;
4. streaming marché / candles.

La quatrième cadence est purement technique, sans LLM et sans décision stratégique.

## ADR-231 — Clé candle canonique et timeframes fermés

**NOUVELLE DÉCISION 19.6A.**

Toute série est identifiée par `(symbol canonique, market_type, timeframe)`. Les timeframes sont énumérés et validés par famille fournisseur afin d'éviter une explosion d'abonnements ou des valeurs prétendument supportées.

FUTURE daté est explicitement rejeté par le pipeline 19.6A.

## ADR-232 — La candle courante est mutable, la candle finale ne régresse pas

**NOUVELLE DÉCISION 19.6A.**

Une update avec le même `open_time` remplace la candle courante si elle est plus récente. Une candle déjà finalisée ne peut pas être remplacée par une version non finalisée. Les séries sont conservées en ordre chronologique et tronquées à une profondeur maximale.

## ADR-233 — Le backend partage un seul stream par clé

**NOUVELLE DÉCISION 19.6A.**

Plusieurs consommateurs cockpit reçoivent le même flux backend. Un nouveau navigateur ne crée pas un nouvel abonnement Kraken pour une clé déjà active.

Le nombre de streams backend et la taille des queues clients sont bornés. Les streams appartiennent au lifespan backend et sont fermés proprement au shutdown.

## ADR-234 — Limites historiques fournisseur explicites

**NOUVELLE DÉCISION 19.6A.**

Le endpoint Spot OHLC est borné à 720 rows : 19.6A ne promet pas 1000 candles Spot qu'il ne peut pas obtenir réellement via cette API.

Kraken Futures charts accepte une cible de profondeur plus grande ; 19.6A demande au maximum 1000 rows et conserve uniquement ce que le fournisseur renvoie effectivement.

## Changelog — 2026-09-24 — Batch 19.1

- comptabilité SPOT canonique au coût moyen pondéré ;
- coût restant all-in, ventes partielles et P&L réalisé ;
- compatibilité historique via `accounting_complete=false` ;
- API/types/cockpit enrichis.

## Changelog — 2026-09-24 — Batch 19.2

- mark SPOT causal `LAST_PRICE` et P&L latent backend ;
- agrégats portefeuille et equity/exposition backend ;
- monitor SPOT/PERPETUAL sans LLM ;
- séparation exécution/valorisation ;
- compatibilité snapshot/recovery sans migration SQL.

## Changelog — 2026-09-25 — Batch 19.3

- `CapacityEvaluator` déterministe avec `NORMAL` / `MANAGEMENT` ;
- même `RiskPolicy` partagée entre CapacityEvaluator et RiskEngine ;
- sélection MANAGEMENT limitée aux positions ouvertes ;
- tools de recherche d'ouverture désactivés en MANAGEMENT ;
- Risk bloque explicitement toute augmentation d'exposition en MANAGEMENT ;
- intégré sur GitHub au commit `bfef06d78dc34089541272c2944518499d4a1530`.

## Changelog — 2026-09-25 — Batch 19.4

- discovery Kraken et watchlist multi-marchés par le même Agent ;
- filtrage factuel sans ranking ;
- fallback/recovery et interaction NORMAL/MANAGEMENT ;
- positions ouvertes réinjectées dans l'univers effectif ;
- audit détaillé sans migration SQL ;
- validation finale opérateur : 12 tests discovery, 578 tests backend avec 2 warnings, frontend lint/typecheck/build ;
- intégré sur GitHub au commit `de65c6677ce01f9c75da5545fe81553a021f588d`.

## Changelog — 2026-09-25 — Batch 19.5

- projection API d'explicabilité depuis les payloads canoniques persistés ;
- séparation discovery/contexte, sélection marché, Agent, Risk et PAPER ;
- traitement explicite HOLD, MODIFY, REJECT, FAILED et legacy partiel ;
- Accueil/Historiques/Positions enrichis sans causalité inventée ;
- validation opérateur : 8 tests ciblés, 586 tests backend avec 2 warnings, frontend lint/typecheck/build ;
- intégré sur GitHub au commit `07050faea54bbed89cf250b34f8e97bd10d94bd3` ;
- revue visuelle light/dark + responsive à conserver séparément si non réalisée.

## Changelog — 2026-09-25 — Batch 19.6A (patch proposé, non intégré)

- modèle candle OHLCV canonique et timeframes fermés ;
- cache process-local borné et dédupliqué ;
- historique Spot OHLCV en conservant la candle courante ;
- streaming Spot WebSocket v2 OHLC avec unsubscribe ;
- historique PERPETUAL via Futures charts et stream via trades publics agrégés ;
- hub backend partagé, reconnect/backfill, gap recovery et staleness ;
- API historique + statut + WebSocket cockpit ;
- lifecycle FastAPI indépendant du frontend ;
- aucune table SQL, aucun LLM, aucun changement Risk ;
- tests exécutés par ChatGPT sur le workspace reconstruit : `tests/test_candle_streaming.py` = **18 passés**, `py_compile` = passé ;
- suite backend complète restant à exécuter par l'opérateur sur le repository complet avant intégration.
