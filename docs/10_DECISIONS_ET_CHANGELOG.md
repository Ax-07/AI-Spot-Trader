# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs,
> les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Kraken, SPOT sans short/levier, PERPETUAL linéaire avec protections déterministes, audit
durable, no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE
séparé.

## Référence auditée du Batch 19.3

```text
HEAD GitHub main audité : 44670a249ba662b2afd50a0a9e2a0e63ea4ed76d
Commit                 : feat: add canonical mark-to-market and unrealized pnl
```

Les Batches 19.1 et 19.2 sont intégrés. Le Batch 19.3 est livré comme patch local ; son intégration GitHub reste explicite et postérieure à la validation opérateur.

## Décisions historiques toujours actives

- ADR-173 à ADR-181 : StrategyRevision immuable, contrat Agent protégé, digests, Campaign snapshot,
  identité expérimentale, distinction Campaign/paper_run, runtime backend et recovery ;
- ADR-182 à ADR-188 : frontend client du Control Plane, API unique, validators backend, preview
  canonique, activation et reprise distinctes ;
- ADR-189/190 : adaptation JSON `market_type` à la frontière API et typing sans changement runtime ;
- ADR-191/192 : Vue d'ensemble comme surface principale et réutilisation des panneaux canoniques ;
- ADR-193 à ADR-195 : aide progressive, règles métier au backend et guide opérateur ;
- ADR-196 à ADR-204 : simplification opérateur, navigation orientée tâches, profils Risk UX,
  `next-themes`, tokens sémantiques et modernisation du cockpit.

## ADR-205 — Comptabilité SPOT canonique backend

**INTÉGRÉE AU BATCH 19.1.**

Méthode : coût moyen pondéré économique. `average_entry_price = remaining_cost_basis / quantity`; le coût restant utilise les débits cash BUY réels frais inclus ; les SELL libèrent la base au prorata et réalisent le P&L sur le crédit net. Spread/slippage sont déjà incorporés dans les prix de fill et ne sont jamais recomptés.

Les snapshots antérieurs sans base de coût restent `accounting_complete=false` sans reconstruction historique.

## ADR-206 — Séparer le monitoring déterministe du cycle stratégique IA

**INTÉGRÉE AU BATCH 19.2.**

`PaperSpotMarkToMarketMonitor` et `PaperDerivativeMarkToMarketMonitor` sont des services backend indépendants du `TradingEngine` et du LLM. Ils ne sélectionnent aucun trade et ne produisent aucun ordre.

## ADR-215 — Mark SPOT = dernier prix ticker Kraken causal

**INTÉGRÉE AU BATCH 19.2.**

La référence de valorisation SPOT est `LAST_PRICE` issue d'une observation Kraken datée. Une observation future par rapport à l'horloge du ledger est rejetée ; une observation plus ancienne ne remplace pas un mark plus récent.

```text
market_value   = quantity * mark_price
unrealized_pnl = market_value - remaining_cost_basis
```

## ADR-216 — Staleness fail-closed pour la valorisation live

**INTÉGRÉE AU BATCH 19.2.**

Un mark plus ancien que le seuil configuré n'est plus exposé dans le snapshot. Le backend ne prolonge pas artificiellement la validité d'un prix lors d'une panne de données.

## ADR-217 — Agrégats portefeuille calculés dans le ledger

**INTÉGRÉE AU BATCH 19.2.**

Le ledger expose cash, coût restant SPOT, valeur SPOT, P&L réalisé/latent SPOT, equity et exposition lorsque les données nécessaires existent. Le frontend ne recalcule pas ces métriques financières.

## ADR-207 — Saturation d'exposition = restriction déterministe du champ des actions

**IMPLÉMENTÉE DANS LE PATCH BATCH 19.3.**

Le backend introduit `CapacityEvaluator` avant la sélection de marché. Son rôle est uniquement de constater si une nouvelle augmentation d'exposition est théoriquement possible avec les faits déjà disponibles avant `MarketState`.

Deux états :

```text
NORMAL      -> sélection stratégique normale + tools read-only éventuels
MANAGEMENT  -> positions ouvertes uniquement + recherche d'ouverture désactivée
```

Le même Agent choisit encore le marché parmi les positions ouvertes et décide HOLD/réduction/clôture. Le déterministe ne classe pas les positions et ne crée pas une stratégie de sortie.

## ADR-218 — CapacityEvaluator partage exactement la RiskPolicy active

**IMPLÉMENTÉE DANS LE PATCH BATCH 19.3.**

`composition.py` et `campaign_composition.py` construisent une seule instance `RiskPolicy`, transmise à `CapacityEvaluator` et `RiskEngine`. Il n'existe pas de deuxième copie de configuration Risk susceptible de diverger.

Le CapacityEvaluator ne duplique pas les contrôles qui dépendent du `MarketState` : minimum d'ordre, contrat, levier instrument, marge exacte, frais, fraîcheur et liquidation restent exclusivement sous l'autorité de Risk.

Aucun plafond global SPOT n'est inventé car la politique actuelle n'en possède pas.

## ADR-219 — MANAGEMENT est fail-closed et Risk interdit les hausses d'exposition

**IMPLÉMENTÉE DANS LE PATCH BATCH 19.3.**

Une valorisation incomplète produit MANAGEMENT avec raison explicite. Risk reçoit le mode du cycle et rejette toute action augmentant l'exposition avec `MANAGEMENT_EXPOSURE_INCREASE`.

HOLD reste autorisé. Les actions réductrices continuent dans les chemins SPOT SELL et PERPETUAL `reduce_only` existants. Aucune sortie Agent ne contourne Risk.

Le mode n'est pas un état persistant : il est recalculé à chaque cycle, y compris après recovery.

## ADR-220 — Économie IA mesurée uniquement avec des faits observables

**IMPLÉMENTÉE DANS LE PATCH BATCH 19.3.**

En MANAGEMENT, `OpenAIDecisionProvider` désactive la boucle de tools pendant la sélection et expose `new_opening_research_skipped=true` dans le contexte audité. Les traces de tools du cycle restent vides.

Aucun compteur de tokens n'existe actuellement dans l'infrastructure durable. Le Batch 19.3 n'invente donc ni estimation de tokens ni nombre fictif d'appels économisés.

## ADR-208/209 — Univers admissible, watchlist stratégique et révisions

**PLANIFIÉ.** Cible :

```text
univers techniquement admissible = filtrage backend déterministe
watchlist                         = sélection du même Agent stratégique
univers surveillé                 = watchlist + toutes les positions ouvertes
```

Le schéma de persistence/watchlist reste à décider au batch dédié.

## ADR-210 — Exposer le `rationale` sans le confondre avec Risk

**PLANIFIÉ.** L'UI doit montrer séparément le rationale stratégique et `ALLOW / MODIFY / REJECT` avec raisons déterministes.

## ADR-211 à ADR-214 — Charts, données et cadences

**PLANIFIÉS.** Kraken/backend restent la source canonique des charts ; Lightweight Charts est le renderer privilégié ; historique REST + temps réel WebSocket + accumulation backend éventuelle ; monitoring, stratégie et discovery restent trois cadences distinctes ; les charts sont chargés à la demande.

## Changelog — 2026-09-24 — Batch 19.1

- comptabilité SPOT canonique au coût moyen pondéré ;
- coût restant all-in, ventes partielles et P&L réalisé ;
- compatibilité historique via `accounting_complete=false` ;
- API/types/cockpit enrichis ;
- intégration GitHub clôturée au HEAD `01ca1e8...`.

## Changelog — 2026-09-24 — Batch 19.2

- mark SPOT causal `LAST_PRICE` et P&L latent backend ;
- agrégats portefeuille et equity/exposition backend ;
- monitor SPOT/PERPETUAL sans LLM ;
- séparation exécution/valorisation ;
- compatibilité snapshot/recovery sans migration SQL ;
- API et cockpit Positions branchés uniquement sur les valeurs backend ;
- intégration GitHub au HEAD `44670a2...`.

## Changelog — 2026-09-25 — Batch 19.3

- resynchronisation sur le HEAD GitHub `44670a249b...` ;
- audit TradingCycleRunner/Agent/tools/Risk/PortfolioState/Control Plane/audit ;
- ajout de `CapacityEvaluator` déterministe avec `NORMAL` / `MANAGEMENT` ;
- même `RiskPolicy` partagée entre CapacityEvaluator et RiskEngine ;
- sélection MANAGEMENT limitée aux positions ouvertes ;
- tools de recherche d'ouverture désactivés en MANAGEMENT ;
- même Agent conservé pour sélection de gestion et décision finale ;
- Risk bloque explicitement toute augmentation d'exposition en MANAGEMENT ;
- mode/reason/search-skip audités sans nouvel état durable ni migration SQL ;
- aucune métrique tokens inventée ;
- frontend inchangé ;
- aucune modification GitHub effectuée par ChatGPT.
