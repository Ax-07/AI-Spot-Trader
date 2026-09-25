# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs,
> les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Kraken, SPOT sans short/levier, PERPETUAL linéaire avec protections déterministes, audit
durable, no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE
séparé.

## Référence auditée du Batch 19.4

```text
HEAD GitHub main audité : bfef06d78dc34089541272c2944518499d4a1530
Commit                 : feat: add deterministic capacity management mode
```

Les Batches 19.1, 19.2 et 19.3 sont intégrés. Le Batch 19.4 est livré comme patch local ; son intégration GitHub reste explicite et postérieure à la validation opérateur.

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

## ADR-206 / ADR-215 / ADR-216 / ADR-217 — Monitoring et valorisation

**INTÉGRÉS AU BATCH 19.2.**

- monitors SPOT/PERPETUAL backend indépendants du LLM ;
- mark SPOT causal `LAST_PRICE` ;
- staleness fail-closed ;
- agrégats cash, valeur SPOT, P&L latent/réalisé, equity et exposition calculés dans le ledger ;
- aucun calcul financier canonique dupliqué dans le frontend.

## ADR-207 — Saturation d'exposition = restriction déterministe du champ des actions

**INTÉGRÉE AU BATCH 19.3.**

`CapacityEvaluator` constate uniquement si une augmentation d'exposition est théoriquement possible avant acquisition du `MarketState`.

```text
NORMAL      -> sélection stratégique normale + tools read-only éventuels
MANAGEMENT  -> positions ouvertes uniquement + recherche d'ouverture désactivée
```

Le même Agent choisit encore le marché parmi les positions ouvertes et décide HOLD/réduction/clôture. Le déterministe ne classe pas les positions et ne crée pas une stratégie de sortie.

## ADR-218 — CapacityEvaluator partage exactement la RiskPolicy active

**INTÉGRÉE AU BATCH 19.3.**

Une seule instance `RiskPolicy` est transmise à `CapacityEvaluator` et `RiskEngine`. Les contrôles dépendant du `MarketState` restent exclusivement chez Risk.

## ADR-219 — MANAGEMENT est fail-closed et Risk interdit les hausses d'exposition

**INTÉGRÉE AU BATCH 19.3.**

Une valorisation incomplète produit MANAGEMENT avec raison explicite. Risk rejette toute action augmentant l'exposition avec `MANAGEMENT_EXPOSURE_INCREASE`. Le mode est recalculé à chaque cycle et n'est pas un état durable.

## ADR-220 — Économie IA mesurée uniquement avec des faits observables

**INTÉGRÉE AU BATCH 19.3.**

En MANAGEMENT, la boucle de tools d'ouverture est désactivée et `new_opening_research_skipped=true` est audité. Aucun compteur de tokens fictif n'est introduit.

## ADR-221 — Le catalogue Kraken existant devient la source canonique de discovery

**IMPLÉMENTÉE DANS LE PATCH BATCH 19.4.**

`MarketResearchService` et `KrakenMarketResearchBackend` sont réutilisés. Aucun scanner parallèle Kraken n'est ajouté. Le cache de catalogue est process-local, 15 min par défaut.

Le déterministe peut éliminer un marché pour des raisons factuelles : type, quote settlement, statut, contrat linéaire, snapshot absent/périmé, historique causal insuffisant ou whitelist Risk explicite. Il ne calcule aucun score d'opportunité. Un refresh complet est borné à 45 s par défaut et `MarketDiscoveryInput.created_at` est fixé après acquisition des candidats afin de préserver la causalité.

## ADR-222 — La watchlist est une sélection périodique du même Agent

**IMPLÉMENTÉE DANS LE PATCH BATCH 19.4.**

Un `OpenAIWatchlistSelector` est un adaptateur sur la même instance `OpenAIDecisionProvider` : même client de stratégie, même modèle et même horloge. Il n'existe pas de second Agent.

La sortie structurée contient plusieurs marchés et leurs rationales. Le backend impose :

- au moins un marché ;
- maximum `watchlist_limit` ;
- unicité ;
- appartenance stricte à l'univers candidat ;
- SPOT/PERPETUAL uniquement.

La watchlist n'est jamais une instruction d'ordre.

## ADR-223 — Watchlist process-local, audit durable, reconstruction après restart

**IMPLÉMENTÉE DANS LE PATCH BATCH 19.4.**

Aucune table SQL mutable de watchlist n'est introduite. Chaque cycle transporte dans l'audit : statut de discovery, taille du catalogue, candidats avec leurs snapshots factuels, timestamps de l'input/sélection, watchlist précédente/effective, ajouts, maintiens, retraits, rationales et erreur éventuelle.

Après restart :

- en `NORMAL`, la watchlist est reconstruite au premier refresh utile ;
- en `MANAGEMENT`, la discovery d'ouverture est ignorée et les positions restaurées sont gérées immédiatement ;
- la dernière watchlist n'est pas rejouée comme décision stratégique historique.

Ce choix réduit la surface de persistence et évite de transformer un cache stratégique en état métier autoritaire. Une persistence dédiée pourra être reconsidérée si un besoin produit mesuré l'exige.

## ADR-224 — Univers effectif = watchlist + positions ouvertes, avec bootstrap immuable

**IMPLÉMENTÉE DANS LE PATCH BATCH 19.4.**

`paper_executable_markets` reste dans la Campaign comme bootstrap/garde-fou/fallback. Pour une Campaign dynamique :

```text
univers admissible factuel -> watchlist Agent
univers cycle NORMAL       -> watchlist + positions ouvertes
univers cycle MANAGEMENT   -> positions ouvertes uniquement au transport Agent
```

Une position ouverte reste donc gérable si son marché est retiré de la watchlist. Le routeur d'exécution dynamique n'autorise que le type configuré et la quote settlement de Campaign, puis exige toujours un snapshot Kraken canonique.

## ADR-225 — `risk_allowed_pairs=null` est réservé aux Campaigns dynamiques

**IMPLÉMENTÉE DANS LE PATCH BATCH 19.4.**

Une Campaign statique conserve l'obligation de whitelist explicite couvrant tous ses marchés. Une Campaign dynamique peut utiliser `null` pour laisser la frontière Kraken/type/quote définir l'adresse admissible ; une whitelist non nulle reste un garde-fou additionnel qui restreint aussi les candidats de discovery.

Les autres limites Risk restent inchangées et autoritaires.

## ADR-226 — Recovery dynamique étend le lifecycle canonique, sans second ledger

**IMPLÉMENTÉE DANS LE PATCH BATCH 19.4.**

`DynamicCampaignPaperRunLifecycle` réutilise `CampaignPaperRunLifecycle`. Lors d'une reprise explicite, il ajoute au nouvel univers de run les marchés correspondant aux positions durables avant de laisser les validations de recovery existantes s'exécuter. Aucune nouvelle table, aucun replay d'ordres et aucun ledger parallèle.

## ADR-210 — Exposer le `rationale` sans le confondre avec Risk

**PLANIFIÉ 19.5.** L'UI doit montrer séparément rationale stratégique et `ALLOW / MODIFY / REJECT` avec raisons déterministes. Le rationale de watchlist 19.4 devient une source supplémentaire à présenter clairement comme **sélection de surveillance**, pas comme justification d'ordre.

## ADR-211 à ADR-214 — Charts, données et cadences

**PLANIFIÉS 19.6.** Kraken/backend restent la source canonique des charts ; Lightweight Charts est le renderer privilégié ; historique REST + temps réel WebSocket + accumulation backend éventuelle ; monitoring, stratégie et discovery restent trois cadences distinctes ; les charts sont chargés à la demande.

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
- mode/reason/search-skip audités sans état durable ;
- intégré sur GitHub au commit `bfef06d78dc34089541272c2944518499d4a1530`.

## Changelog — 2026-09-25 — Batch 19.4

- resynchronisation sur le HEAD GitHub `bfef06d78dc34089541272c2944518499d4a1530` ;
- correction documentaire : 19.3 n'est plus décrit comme patch local ;
- `MarketDiscoveryPolicy`, cache catalogue et coordinateur de discovery ;
- présélection factuelle Kraken sans ranking algorithmique ;
- watchlist multi-marchés sélectionnée par le même Agent ;
- fallback dernière watchlist/bootstrap, timeout 45 s et cadence de retry bornée ;
- interaction explicite avec NORMAL/MANAGEMENT ;
- positions ouvertes réinjectées dans l'univers effectif ;
- routeur/mark-to-market/recovery adaptés aux marchés dynamiques ;
- audit détaillé des faits candidats, timestamps et diffs de watchlist sans migration SQL ;
- configurateur simple orienté « paire de départ/secours » ;
- aucune modification GitHub effectuée par ChatGPT.
