# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs, les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers Broker/Kraken, SPOT sans short/levier, PERPETUAL linéaire avec protections déterministes, audit durable, no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence courante

```text
HEAD GitHub vérifié au lancement 19.7   : 2d51cb68d55e34065626902d3792988976da11d9
Référence fonctionnelle Batch 19.6A     : 3c53af3bdb1ef53c574e26afe9b6178a374d9f06
Référence fonctionnelle Batch 19.6B     : a446628918a614d2ae0ac3b55243881aad5ef410
Batch 19.5                              : intégré
Batch 19.6A                             : intégré
Batch 19.6B                             : intégré sur GitHub main
Batch 19.7                              : validé localement, commit fonctionnel 8b969b4
```

## Décisions historiques toujours actives

- ADR-173 à ADR-181 : StrategyRevision immuable, contrat Agent protégé, digests, Campaign snapshot, identité expérimentale, distinction Campaign/paper_run, runtime backend et recovery ;
- ADR-182 à ADR-188 : frontend client du Control Plane, API unique, validators backend, preview canonique, activation et reprise distinctes ;
- ADR-189/190 : adaptation JSON `market_type` à la frontière API et typing sans changement runtime ;
- ADR-191 à ADR-204 : cockpit orienté opérateur, aide progressive, règles métier backend, simplification UX et dark mode ;
- ADR-205 : comptabilité SPOT canonique backend ;
- ADR-206 / ADR-215 / ADR-216 / ADR-217 : monitoring et valorisation ;
- ADR-207 / ADR-218 / ADR-219 / ADR-220 : `NORMAL` / `MANAGEMENT`, `CapacityEvaluator` et économie IA ;
- ADR-221 à ADR-226 : discovery/watchlist dynamique, audit, univers effectif, whitelist et recovery ;
- ADR-227 à ADR-230 : projection d'explicabilité, corrélation par cycle et distinction HOLD/REJECT/FAILED ;
- ADR-231 à ADR-234 : pipeline candles 19.6A, cache/process, causalité et streams backend partagés ;
- ADR-235 à ADR-238 : vue Marchés 19.6B, univers sans ranking frontend, markers issus des fills et Lightweight Charts comme rendu seulement.

## ADR-210 / ADR-227 à ADR-230 — Explicabilité opérateur

**INTÉGRÉS AU BATCH 19.5.**

Le cockpit expose séparément les rationales disponibles, les faits de sélection, le statut/les raisons Risk et l'exécution PAPER. La projection est construite depuis les faits persistés et ne devient jamais une nouvelle source de vérité.

L'Historique consomme le détail corrélé du cycle. Positions expose seulement une activité auditée liée au même marché lorsqu'aucune provenance directe n'existe. HOLD, REJECT, MODIFY et FAILED conservent des sémantiques distinctes.

## ADR-211 — Kraken/backend restent la source canonique des charts

**INTÉGRÉ AU BATCH 19.6A ; consommé par le frontend intégré au Batch 19.6B.**

Le frontend consomme uniquement les contrats backend candles. Il n'ouvre pas de connexion directe parallèle à Kraken. Le backend normalise les données fournisseur, maintient le cache et diffuse les updates cockpit.

## ADR-212 — Historique REST + streaming fournisseur, sans candle inventée

**INTÉGRÉ AU BATCH 19.6A.**

SPOT : historique `/0/public/OHLC` + WebSocket v2 `ohlc`. PERPETUAL : Futures charts + feed public `trade` agrégé. Un trou non récupérable reste visible comme trou ; aucune candle synthétique n'est créée.

## ADR-213 — Cache process-local borné, pas de table SQL 19.6A

**INTÉGRÉ AU BATCH 19.6A.**

Le cache candles est une mémoire technique de diffusion/recovery, pas une nouvelle source durable. La persistence sera réévaluée seulement si un besoin produit/recovery hors process l'exige.

## ADR-214 — Quatre cadences distinctes

**INTÉGRÉ AU BATCH 19.6A.**

1. monitoring / mark-to-market ;
2. cycle stratégique IA ;
3. discovery / watchlist IA ;
4. streaming marché / candles.

La quatrième cadence est purement technique, sans LLM et sans décision stratégique.

## ADR-231 — Clé candle canonique et timeframes fermés

**INTÉGRÉ AU BATCH 19.6A.**

Toute série est identifiée par `(symbol canonique, market_type, timeframe)`. FUTURE daté est explicitement rejeté par ce pipeline.

## ADR-232 — La candle courante est mutable, la candle finale ne régresse pas

**INTÉGRÉ AU BATCH 19.6A.**

Une update avec le même `open_time` remplace la candle courante si elle est plus récente. Une candle déjà finalisée ne peut pas régresser vers un état courant. Les séries restent chronologiques et bornées.

## ADR-233 — Le backend partage un seul stream par clé

**INTÉGRÉ AU BATCH 19.6A.**

Plusieurs consommateurs cockpit reçoivent le même flux backend. Les streams appartiennent au lifespan backend ; fermer/redémarrer le frontend ne stoppe ni le moteur trading ni le service backend.

## ADR-234 — Limites historiques fournisseur explicites

**INTÉGRÉ AU BATCH 19.6A.**

Spot OHLC est borné à 720 rows. PERPETUAL vise jusqu'à 1000 rows via Futures charts mais conserve uniquement ce que le fournisseur renvoie réellement.

## ADR-235 — La vue Marchés reste un consommateur strict du backend

**INTÉGRÉ AU BATCH 19.6B — COMMIT FONCTIONNEL `a446628`.**

Le frontend charge uniquement le marché/timeframe actif depuis les contrats 19.6A. Il utilise le proxy same-origin `/backend` pour REST et WebSocket, n'ouvre aucune connexion Kraken directe, conserve un petit cache mémoire borné et nettoie socket/listeners/timers à chaque changement ou démontage.

## ADR-236 — L'univers Marchés ne crée aucun ranking frontend

**INTÉGRÉ AU BATCH 19.6B — COMMIT FONCTIONNEL `a446628`.**

Ordre des faits utilisés : watchlist effective de l'explicabilité discovery lorsqu'elle existe ; univers de campagne actif seulement comme bootstrap si la watchlist manque ; positions ouvertes toujours réinjectées. Le frontend déduplique mais ne classe pas stratégiquement les marchés.

## ADR-237 — Markers uniquement depuis les fills persistés

**INTÉGRÉ AU BATCH 19.6B — COMMIT FONCTIONNEL `a446628`.**

Un marker n'existe que si un fill PAPER réel est retourné par `/executions`. BUY/SELL viennent du payload canonique du fill. `reduce_only=true` peut annoter une réduction. Aucune clôture n'est inférée depuis une variation de position ou une candle. Le détail d'un marker recharge `/cycles/{cycle_id}` afin de réutiliser l'explicabilité 19.5 ; si la projection manque, l'UI reste explicitement partielle.

## ADR-238 — Lightweight Charts est une couche de rendu, pas une source métier

**INTÉGRÉ AU BATCH 19.6B — COMMIT FONCTIONNEL `a446628`.**

TradingView Lightweight Charts rend OHLC/volume/markers à partir des faits backend. Les timeframes autorisés sont centralisés selon les capacités 19.6A. Le frontend n'utilise pas les candles pour recalculer P&L, exposition, liquidation, Risk ou stratégie.

## ADR-239 — Les overlays de position sont une projection stricte du portefeuille backend

**VALIDÉ LOCALEMENT AU BATCH 19.7 — COMMIT FONCTIONNEL `8b969b4`, NON ENCORE POUSSÉ.**

Les lignes de prix de position du chart Marchés ne sont créées qu'à partir des champs déjà fournis par `/portfolio` : `average_entry_price`, `mark_price` et, uniquement pour PERPETUAL, `liquidation_price`. Une valeur absente ou non numérique n'est pas reconstruite. La conversion de la chaîne canonique en nombre sert uniquement à l'API de rendu Lightweight Charts ; aucune formule financière n'est introduite.

Pour SPOT, une position n'est projetée que sur le symbole correspondant à `asset/settlement_asset` ; le frontend n'effectue aucune conversion multi-quote/FX. Pour PERPETUAL, la correspondance reste le symbole canonique exact. `mark_observed_at` reste un fait affichable mais ne crée aucune règle frontend de staleness.

Chaque overlay possède une identité bornée au marché et un label explicite (`Prix moyen`, `Mark backend`, `Liquidation`). Les niveaux proches ne sont pas fusionnés : ce sont des faits distincts ; le rendu s'appuie sur l'alignement des labels de l'échelle prix. Les `price lines` natives sont supprimées avant remplacement et abandonnées lors de la recréation du chart, afin qu'un changement de marché, de position ou de thème ne conserve ni duplication ni ligne étrangère.

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
- filtrage factuel sans ranking ; fallback/recovery et interaction NORMAL/MANAGEMENT ;
- positions ouvertes réinjectées dans l'univers effectif ; audit durable sans migration SQL ;
- validation finale opérateur : 12 tests discovery, 578 tests backend avec 2 warnings, frontend lint/typecheck/build ;
- intégré sur GitHub au commit `de65c6677ce01f9c75da5545fe81553a021f588d`.

## Changelog — 2026-09-25 — Batch 19.5

- projection API d'explicabilité depuis les payloads canoniques persistés ;
- séparation discovery/contexte, sélection marché, Agent, Risk et PAPER ;
- traitement explicite HOLD, MODIFY, REJECT, FAILED et legacy partiel ;
- Accueil/Historique/Positions enrichis sans causalité inventée ;
- validation opérateur : 8 tests ciblés, 586 tests backend avec 2 warnings, frontend lint/typecheck/build ;
- intégré sur GitHub au commit `07050faea54bbed89cf250b34f8e97bd10d94bd3`.

## Changelog — 2026-09-25 — Batch 19.6A

- modèle candle OHLCV canonique et timeframes fermés ;
- cache process-local borné et dédupliqué ;
- historique/streaming SPOT et PERPETUAL ; hub backend partagé, reconnect/backfill, gap recovery et staleness ;
- API historique + statut + WebSocket cockpit ; lifecycle FastAPI indépendant du frontend ;
- aucune table SQL, aucun LLM, aucun changement Risk ;
- validation ChatGPT préalable : 18 tests ciblés + `py_compile` ;
- validation opérateur finale : 53 tests ciblés, 604 tests backend, 2 warnings de dépréciation ;
- intégré sur GitHub `main` au commit `3c53af3bdb1ef53c574e26afe9b6178a374d9f06`.

## Changelog — 2026-09-25 — Batch 19.6B

- vue Marchés et navigation cockpit dédiée ;
- onglets watchlist/positions, marché actif lazy-loaded ;
- chandeliers + volume via TradingView Lightweight Charts ;
- consommation REST + WebSocket cockpit 19.6A avec cache mémoire, reconnexion et cleanup ;
- états loading/error/stale ;
- contexte position backend SPOT/PERPETUAL ;
- markers issus uniquement des fills persistés et détails via l'explicabilité 19.5 ;
- aucune connexion Kraken frontend, aucun ranking, aucun calcul Risk/P&L parallèle ;
- validation opérateur : `pnpm test` **6/6**, `pnpm lint`, `pnpm typecheck` et `pnpm build` passés ; `git diff --check` sans erreur de whitespace ;
- commit fonctionnel intégré sur GitHub `main` : `a446628918a614d2ae0ac3b55243881aad5ef410` (`feat: add cockpit market charts and trade markers`) ;
- clôture documentaire poussée sur GitHub `main` : `b5a26f77d1951f8eb39df30b5b6f3b5b81f4d585` (`docs: finalize Batch 19.6B integration state`) ;
- synchronisation documentaire post-push : `2d51cb68d55e34065626902d3792988976da11d9` (`docs: sync Batch 19.6B post-push state`).

## Changelog — 2026-09-25 — Batch 19.7

- overlays `Prix moyen`, `Mark backend` et `Liquidation` depuis les faits canoniques `/portfolio` uniquement ;
- liquidation affichée uniquement pour PERPETUAL et uniquement lorsqu'elle est fournie ;
- aucune reconstruction de valeur absente, aucun calcul frontend de P&L/exposition/liquidation/prix moyen ;
- SPOT strictement borné au `settlement_asset` canonique, sans multi-quote/FX ;
- lifecycle natif Lightweight Charts avec création/suppression des price lines, labels explicites, styles light/dark et nettoyage lors des changements de faits/marché/thème ;
- chandeliers, volumes et markers de fills 19.6B conservés ;
- validation ChatGPT préalable : **17/17 tests Node passés** ;
- validation opérateur locale : `pnpm test` **17/17**, `pnpm lint`, `pnpm typecheck` et `pnpm build` passés ; `git diff --check` sans erreur de whitespace, avertissements LF -> CRLF uniquement ;
- commit fonctionnel local `main` : `8b969b434916d89f6b6aa127c3bac9c27e990966` (`feat: add canonical position overlays to market charts`) ; présence sur GitHub `main` à confirmer après push.
