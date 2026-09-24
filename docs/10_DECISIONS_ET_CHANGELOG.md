# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs,
> les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Kraken, SPOT sans short/levier, PERPETUAL linéaire avec protections déterministes, audit
durable, no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE
séparé.

## Référence auditée du Batch 19.1

```text
HEAD GitHub main audité : dbdc8f83bb39c158ec7331ce2adba616d2922842
Commit                 : docs: plan upcoming trading improvements
```

Le Batch 19.1 est livré comme patch local ; son intégration GitHub reste explicite et postérieure à la validation opérateur.

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

**IMPLÉMENTÉE DANS LE BATCH 19.1.**

`AssetPosition` porte désormais :

- `average_entry_price` ;
- `remaining_cost_basis` ;
- `realized_pnl` ;
- `accounting_complete` ;
- en plus de `asset`, `quantity`, `available`.

### Méthode comptable retenue

La méthode est le **coût moyen pondéré**.

- `average_entry_price` représente le coût économique moyen unitaire : `remaining_cost_basis / quantity` ;
- spread et slippage sont déjà incorporés dans le prix réel du fill ;
- les frais BUY entrent dans `remaining_cost_basis` via le débit cash réel `notional + fee` et donc dans `average_entry_price` ;
- une vente partielle libère une fraction proportionnelle de `remaining_cost_basis` ;
- le P&L réalisé du SELL vaut `notional - fee - released_cost_basis` ;
- la quantité restante conserve le même prix moyen sous cette méthode ;
- une vente totale supprime la position ouverte ; le P&L du dernier SELL reste durable dans le Fill/audit.

Cette définition rend `average_entry_price` directement réconciliable avec le **coût économique restant all-in**, sans double comptage.

### Compatibilité historique

Les anciens snapshots sans champs comptables restent valides : les valeurs coût/prix moyen restent `None` et `accounting_complete=false`. Aucun coût historique n'est reconstruit à partir de fills futurs ou d'hypothèses.

Une position legacy reste comptablement incomplète tant qu'elle n'est pas fermée. Une nouvelle position ouverte ensuite par le broker 19.1 démarre avec une comptabilité complète.

### Persistence / recovery

Pas de migration SQL : les snapshots `PortfolioState` sont déjà persistés en JSON. `paper-ledger-recovery-v1` reste valable car il restaure le snapshot validé ; les nouveaux champs sont simplement inclus dans le contrat JSON.

### P&L latent

**NON IMPLÉMENTÉ PAR 19.1.** La valorisation courante nécessite un mark daté et reste le périmètre du Batch 19.2. Le frontend affiche donc `—` au lieu de la reconstruire.

## ADR-206 — Séparer le monitoring déterministe du cycle stratégique IA

**PLANIFIÉE / NON IMPLÉMENTÉE.** Prix/marks, P&L latent, exposition, marge, liquidation et funding pertinent doivent évoluer sans appel LLM. Le monitoring aura une cadence distincte et configurable.

## ADR-207 — Saturation d'exposition = restriction déterministe du champ des actions

**PLANIFIÉE / NON IMPLÉMENTÉE.** Le backend peut constater qu'aucune nouvelle exposition n'est possible et éviter les phases d'ouverture inutiles. Le même Agent choisit encore parmi HOLD/réduction/clôture ; Risk reste final.

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

- resynchronisation sur le HEAD GitHub `dbdc8f83...` ;
- audit de `AssetPosition`, ledger, broker/pricing, analytics, persistence/recovery, API et frontend ;
- extension de la comptabilité SPOT canonique au coût moyen pondéré ;
- prise en compte all-in des frais BUY dans le coût restant et des frais SELL dans le produit net ;
- spread/slippage conservés dans le prix de fill sans double comptage ;
- P&L réalisé SPOT exposé par les SELL fills ;
- compatibilité historique explicite via `accounting_complete=false` ;
- API/types/cockpit Positions enrichis ;
- guide opérateur et documentation synchronisés ;
- P&L latent/mark-to-market laissé au Batch 19.2 ;
- aucune modification GitHub effectuée par ChatGPT.
