# 11 — Améliorations planifiées

> Référence de reprise des chantiers 19.x. Ce document distingue ce qui est **intégré**, ce qui est **validé localement en attente d'intégration** et ce qui reste **planifié**.

## 1. Référence

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub main observé           : e7e4c8248406516eada576b3907e77dc8b72a0e4
Référence fonctionnelle Batch 19.4 : de65c6677ce01f9c75da5545fe81553a021f588d
État Batch 19.5                    : validation automatisée locale réussie, commit/push en attente
Date                               : 2026-09-25
```

Les Batches 19.1, 19.2, 19.3 et 19.4 sont intégrés. Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## 2. Invariants transverses

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement ;
- SPOT + PERPETUAL linéaire ;
- aucune sortie LLM ne déclenche directement Broker/Kraken ;
- Risk Engine déterministe = autorité finale ;
- IA = choix stratégique ;
- calculs, comptabilité, monitoring, capacité, filtrage technique et statistiques = déterministes ;
- frontend jamais source de vérité trading ;
- aucun secret dans prompts/logs/docs/Git ;
- frais, spread, slippage et funding pris en compte sans double comptage ;
- HOLD auditable ;
- aucun look-ahead ni sélection rétrospective.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## 3. Cadences cibles

| Cadence | But | LLM |
| --- | --- | --- |
| Monitoring / mark-to-market | prix, marks, P&L, exposition, marge, liquidation, funding | non |
| Cycle stratégique | BUY / SELL / HOLD, avec restriction MANAGEMENT si nécessaire | oui, Agent unique |
| Discovery / watchlist | réévaluer les marchés intéressants | oui, même Agent |

Le monitoring utilise par défaut une cadence de 5 s en SPOT et 15 s en PERPETUAL, avec 5 s de timeout et 30 s de staleness. Le Batch 19.4 ajoute une cadence de discovery indépendante de 15 min par défaut, évaluée uniquement pendant les cycles `NORMAL`.

# 4. Comptabilité SPOT par position — INTÉGRÉE 19.1

Confirmé : coût économique moyen pondéré, coût restant frais BUY inclus, ventes partielles au prorata, P&L réalisé net, pas de double comptage spread/slippage/frais, recovery JSON et compatibilité `accounting_complete=false`.

# 5. Monitoring / mark-to-market — INTÉGRÉ 19.2

Confirmé : marks SPOT causaux, P&L latent backend, agrégats portfolio, monitors backend indépendants de l'Agent et cockpit branché sur les champs canoniques.

# 6. Mode gestion lorsque l'exposition est saturée — INTÉGRÉ 19.3

Confirmé : `CapacityEvaluator`, `NORMAL` / `MANAGEMENT`, même `RiskPolicy`, recherche d'ouverture désactivée en MANAGEMENT, Risk bloque les hausses d'exposition et aucun nouvel état durable n'est créé.

# 7. Discovery automatique et watchlist — INTÉGRÉ 19.4

Confirmé : catalogue `MarketResearchService`, filtrage factuel sans ranking, watchlist sélectionnée par le même Agent, fallback, interaction avec MANAGEMENT, univers effectif incluant les positions, audit durable sans table mutable dédiée et recovery canonique.

Validation opérateur communiquée : 12 tests discovery, 578 tests backend avec 2 warnings de dépréciation, `pnpm lint`, `pnpm typecheck`, `pnpm build` passés.

# 8. Explicabilité des décisions IA — VALIDÉE LOCALEMENT 19.5

Le `rationale` et les autres faits nécessaires existaient déjà dans le journal de cycle. Le Batch 19.5 les transforme en une vue de présentation typée et défensive sans créer de nouvelle source de vérité.

## 8.1 Architecture backend mise en place

```text
CycleAuditDetail existant
  + market_selection_input.capacity_context
  + market_selection_input.market_discovery
  + MarketSelection persisté
  + DecisionCandidate persisté
  + RiskAssessment persisté
  + ExecutionIntent / Fill persistés
-> CycleExplainabilityResponse
-> /api/v1/cycles/latest
-> /api/v1/cycles/{cycle_id}
```

Décisions :

- aucune nouvelle table SQL ;
- aucun ledger parallèle ;
- aucune mutation du contenu canonique ;
- aucun nouveau calcul stratégique ou financier ;
- aucune reconstitution approximative de Risk ;
- parsing tolérant des historiques partiels ;
- les absences restent `null`/vides au lieu d'être inventées.

## 8.2 Discovery / contexte

La projection distingue :

- `REFRESHED` : nouvelle sélection IA de watchlist, avec rationale global et par entrée si persisté ;
- `CACHE_REUSED` : watchlist réutilisée, aucun nouvel appel IA de sélection ;
- `FALLBACK` : refresh en échec, watchlist précédente/bootstrap maintenu ;
- `SKIPPED_MANAGEMENT` : discovery volontairement non lancée en MANAGEMENT.

Le contexte `NORMAL` / `MANAGEMENT`, sa raison et les capacités SPOT/PERP sont présentés séparément.

## 8.3 Agent IA / Risk

L'UI présente séparément :

- marché du cycle et rationale de `MarketSelection` ;
- BUY / SELL / HOLD et `DecisionCandidate.rationale` ;
- quantité proposée ;
- `RiskAssessment.status` ;
- quantité demandée et quantité autorisée ;
- raisons et limites évaluées.

Pour `MODIFY`, l'action, le symbole et le type de marché ne sont jamais présentés comme modifiés par Risk : seule la quantité autorisée diffère.

## 8.4 Exécution PAPER

La projection expose l'état dérivé uniquement de la présence des artefacts persistés :

- fill(s) réel(s) ;
- intent créé sans fill ;
- absence attendue pour HOLD ;
- absence après REJECT ;
- absence avant un échec technique ;
- absence sans cause plus précise disponible.

Les fills exposent leurs faits persistés utiles : quantité, prix de référence, prix exécuté, notional, frais, spread et slippage lorsqu'ils existent.

## 8.5 FAILED et legacy

Un `FAILED` reste distinct d'un `REJECT`.

- échec Agent : aucun artefact aval n'est inventé ;
- échec Risk : les artefacts Agent déjà produits restent visibles ;
- échec Broker après intent : l'intent reste visible même sans fill ;
- rationale absente : affichage explicite « Rationale non disponible pour cet historique ».

## 8.6 Accueil

La carte « Dernière décision » affiche : action, marché, contexte éventuel, rationale IA, rationale de sélection de marché si disponible, statut/raisons Risk, quantité demandée/autorisée et état d'exécution PAPER.

## 8.7 Historique

La page `/cycles` reste l'index récent. Chaque carte charge ensuite `/cycles/{cycle_id}` afin d'utiliser un graphe corrélé unique plutôt que de joindre trois pages indépendantes.

Parcours affiché :

```text
Discovery / contexte
-> Agent IA
-> Risk Engine
-> Exécution PAPER
```

Les JSON canoniques restent accessibles dans « Détails techniques ».

## 8.8 Positions

En l'absence de provenance directe sur le modèle de position, le cockpit affiche uniquement une **activité auditée récente liée au même symbole + type de marché**.

Il ne présente jamais cette corrélation comme la décision ou le fill ayant créé la position.

## 8.9 Validation locale

Exécuté par l'opérateur sur le repository complet le 2026-09-25 :

- `pytest tests/test_cycle_explainability.py` : **8 tests passés** ;
- `pytest` : **586 tests passés**, avec 2 warnings de dépréciation ;
- `pnpm lint` : **passé** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé** ;
- `git diff --check` : aucune erreur de whitespace, uniquement des avertissements LF -> CRLF.

Les cas ciblés couvrent BUY+ALLOW+fill, MODIFY, REJECT, HOLD, FAILED avant/après intent, legacy sans rationale, NORMAL/MANAGEMENT, les quatre statuts discovery, les corrélations d'IDs et l'absence de mutation des payloads.

Reste à effectuer comme validation opérateur distincte avant clôture définitive : revue visuelle light/dark, desktop/mobile, rationales longues/absentes, nombreuses raisons Risk et longs symboles/identifiants.

# 9. Nouvel espace Marchés — PLANIFIÉ 19.6B

Navigation cible :

```text
Accueil | Marchés | Positions | Historique | Réglages
```

La vue Marchés affichera en onglets les marchés surveillés. Le frontend n'a aucune autorité sur la watchlist ou le moteur.

# 10. Charts chandeliers — PLANIFIÉ 19.6B

Renderer privilégié : **TradingView Lightweight Charts** avec données Kraken normalisées par le backend.

À afficher lorsque disponible : OHLC, prix courant, volume, prix moyen, mark/liquidation PERPETUAL et événements BUY/SELL/réduction/clôture.

# 11. Historique candles + WebSocket — PLANIFIÉ 19.6A

Pipeline cible :

```text
Kraken REST -> historique initial
Kraken WebSocket -> updates temps réel
backend -> normalisation/cache/persistence éventuelle
WebSocket cockpit -> frontend
```

Le backend doit gérer déduplication, candle courante mutable, reconnect/backfill et limitations de profondeur sans inventer de données.

# 12. Ordre global

| Ordre | Batch | Résultat principal | Statut |
| ---: | --- | --- | --- |
| 1 | 19.1 — Comptabilité SPOT | coût moyen, coût restant, P&L réalisé, recovery | intégré |
| 2 | 19.2 — Monitoring | P&L latent et état vivant sans LLM | intégré |
| 3 | 19.3 — Mode gestion | évite recherche IA inutile quand ouverture indisponible | intégré |
| 4 | 19.4 — Discovery/watchlist | univers dynamique audité, même Agent | intégré |
| 5 | 19.5 — Explicabilité | rationale visible vs Risk | validation automatisée locale réussie / intégration en attente |
| 6 | 19.6A — Candles/streaming | données chart canoniques | planifié |
| 7 | 19.6B — Marchés/charts | rendu, onglets, markers | planifié |

## 13. Validation attendue

### 19.5

- suite backend complète : **passée (586 tests, 2 warnings)** ;
- lint/typecheck/build frontend : **passés** ;
- rationale watchlist, décision et Risk clairement séparés : **couvert par les tests ciblés et la projection** ;
- HOLD/MODIFY/REJECT/FAILED/legacy : **couverts par les tests ciblés ; revue visuelle restante** ;
- aucune causalité de position inventée : **invariant conservé**.

### 19.6A

- parsing OHLC, déduplication, reconnect/backfill ;
- persistence/cache ;
- WebSocket cockpit ;
- staleness/lifecycle.

### 19.6B

- lint/typecheck/build ;
- light/dark ;
- changement onglet/timeframe ;
- cleanup subscriptions ;
- markers cohérents avec les fills.
