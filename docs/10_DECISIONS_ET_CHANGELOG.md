# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs,
> les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Kraken, SPOT sans short/levier, PERPETUAL linéaire avec protections déterministes, audit
durable, no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE
séparé.

## Référence auditée du Batch 19.2

```text
HEAD GitHub main audité : 01ca1e857947d969556481e5593c5712d137f5ad
Commit                 : docs: finalize Batch 19.1 integration state
```

Le Batch 19.1 est intégré. Le Batch 19.2 est livré comme patch local ; son intégration GitHub reste explicite et postérieure à la validation opérateur.

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

**IMPLÉMENTÉE DANS LE BATCH 19.2.**

``PaperSpotMarkToMarketMonitor` et `PaperDerivativeMarkToMarketMonitor` sont des services backend indépendant du `TradingEngine` et du LLM. Il ne sélectionne aucun trade et ne produit aucun ordre.

Paramètres techniques par défaut :

```text
cadence SPOT MTM  : 5 s
cadence PERP MTM  : 15 s
timeout observation: 5 s
staleness mark     : 30 s
```

Ces valeurs sont configurables par environnement et ne changent pas silencieusement la stratégie de Campaign.

## ADR-215 — Mark SPOT = dernier prix ticker Kraken causal

**IMPLÉMENTÉE DANS LE BATCH 19.2.**

La référence de valorisation SPOT est `LAST_PRICE` issue d'une observation Kraken datée. Une observation future par rapport à l'horloge du ledger est rejetée ; une observation plus ancienne ne remplace pas un mark plus récent.

Définitions :

```text
market_value   = quantity * mark_price
unrealized_pnl = market_value - remaining_cost_basis
```

Le mark ne simule pas un SELL et n'ajoute donc ni frais, ni spread, ni slippage de sortie hypothétique.

## ADR-216 — Staleness fail-closed pour la valorisation live

**IMPLÉMENTÉE DANS LE BATCH 19.2.**

Un mark plus ancien que le seuil configuré n'est plus exposé dans le snapshot : prix courant, valeur de marché et P&L latent deviennent indisponibles. Le backend ne prolonge pas artificiellement la validité d'un prix lors d'une panne de données.

Une position legacy avec coût inconnu peut exposer `market_value`, mais jamais un `unrealized_pnl` canonique.

## ADR-217 — Agrégats portefeuille calculés dans le ledger

**IMPLÉMENTÉE DANS LE BATCH 19.2.**

Le frontend et l'API ne recalculent pas les métriques financières. Le ledger expose cash, coût restant SPOT, valeur SPOT, P&L réalisé/latent SPOT, equity et exposition lorsque les données nécessaires existent.

Définition de l'equity :

```text
equity = cash settlement
       + valeur SPOT
       + Σ(margin_used + unrealized_pnl + cumulative_funding) dérivés
```

Le P&L réalisé n'est pas rajouté : il est déjà reflété dans le cash.

Le total réalisé SPOT commence à zéro pour une nouvelle lignée 19.2 et est ensuite persisté dans `PortfolioState`. Pour un snapshot antérieur qui ne permet pas de connaître l'historique complet, il reste `None`; aucun replay des fills n'est lancé.

## ADR-207 — Saturation d'exposition = restriction déterministe du champ des actions

**PLANIFIÉE / NON IMPLÉMENTÉE.** Le backend pourra utiliser l'état valorisé 19.2 pour constater qu'aucune nouvelle exposition n'est possible. Le même Agent choisira encore parmi HOLD/réduction/clôture ; Risk reste final.

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

- resynchronisation sur le HEAD GitHub `01ca1e8579...` ;
- audit ledger/broker/pricing/Kraken/recovery/analytics/Agent/Risk/API/frontend ;
- mark SPOT causal `LAST_PRICE` et P&L latent backend ;
- agrégats portefeuille et equity/exposition backend ;
- monitor SPOT/PERPETUAL sans LLM avec cadence/timeout/staleness configurables ;
- séparation exécution/valorisation : le broker met à jour la comptabilité, tandis que la source de marché et le monitor rafraîchissent le mark ;
- compatibilité snapshot/recovery sans migration SQL ;
- API et cockpit Positions branchés uniquement sur les valeurs backend ;
- tests ciblés ajoutés ;
- aucune modification GitHub effectuée par ChatGPT.
