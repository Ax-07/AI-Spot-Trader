# Batch 36 — Simplification UX de la terminologie financière

## Statut

**Patch proposé/local non intégré.**

Base auditée :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 58b59ba0cab25e9011d26014c51005aac1365af2
Commit     : fix: recover market attention runtime and clarify historical errors
```

Le HEAD GitHub a été revérifié avant modification. Les Batches 34 / 34.1 / 34.2 / 35 sont intégrés dans ce HEAD.

## Objectif

Retirer le terme technique `notional/notionnel` du parcours utilisateur normal lorsque le contexte permet un libellé français plus clair, sans modifier la sémantique, les calculs ni les contrats techniques.

Vocabulaire UX retenu :

- limite d’ordre : `Montant max par ordre` ;
- valeur d’une position : `Valeur de la position` ;
- limite PERPETUAL : `Valeur max d’une position` ;
- valeur économique d’une exécution : `Montant de l’ordre` / `montant échangé` ;
- Radar : `Valeur échangée estimée en USD` et `Méthode d’estimation USD`.

## Audit frontend

### Confirmé — libellés visibles corrigés

- `simple-configurator.tsx` : `Max notional / ordre` et `Notional position dérivée max` ;
- `control-plane-panel.tsx` : `Max order notional` et `Position notional max` ;
- `positions-panel.tsx` : colonne PERPETUAL `Notional` ;
- `markets-panel.tsx` : fait PERPETUAL `Notional` ;
- `market-attention-dock.tsx` : `Méthode notionnel` et description `contexte notionnel USD` ;
- `history-panel.tsx` : colonne `Notional`, détail du turnover et ratio `Coûts / notional`.

`history-panel.tsx` est une occurrence UX supplémentaire trouvée lors de l’audit global du frontend ; elle est incluse pour éviter de laisser le terme dans un parcours utilisateur principal.

### Technique — conservé

Les identifiants et champs techniques restent inchangés, notamment :

```text
risk_max_order_notional
risk_max_derivative_position_notional
notional
position.notional
current_notional_usd
baseline_notional_usd
notional_delta_usd
notional_method
total_notional
costs_to_notional_fraction
```

Les modèles TypeScript, helpers, tests techniques, API, persistence, backend, Risk Engine et analytics ne sont pas renommés.

### Historique / documentation

Les anciennes notes de batches et ADR qui décrivent explicitement le concept technique de notionnel ne sont pas réécrites mécaniquement. `docs/00_ETAT_ACTUEL.md`, `docs/09_ROADMAP_DEVELOPPEMENT.md` et la référence courante de `docs/10_DECISIONS_ET_CHANGELOG.md` sont seulement réalignés sur le HEAD intégré actuel.

### À décider

Aucun remplacement d’`exposition` n’est effectué : l’exposition portefeuille et la valeur d’une position restent des concepts distincts dans le cockpit.

## Invariants préservés

Aucun changement de comportement n’est introduit dans : Agent, prompts stratégiques, Trading Reasoning Doctrine, Risk Engine, Broker, PAPER, SPOT/PERPETUAL, Kraken, Market Discovery, Market Attention, pricing, frais, spread, slippage, sizing, exposition, calcul du notionnel, API ou persistence.

Aucune migration backend/API n’est ajoutée. Aucun helper de formatage n’est créé uniquement pour tester des chaînes statiques.

## Fichiers du batch

Frontend :

- `frontend/src/components/cockpit/simple-configurator.tsx` ;
- `frontend/src/components/cockpit/control-plane-panel.tsx` ;
- `frontend/src/components/cockpit/positions-panel.tsx` ;
- `frontend/src/components/cockpit/markets-panel.tsx` ;
- `frontend/src/components/cockpit/market-attention-dock.tsx` ;
- `frontend/src/components/cockpit/history-panel.tsx`.

Documentation :

- `docs/00_ETAT_ACTUEL.md` ;
- `docs/09_ROADMAP_DEVELOPPEMENT.md` ;
- `docs/10_DECISIONS_ET_CHANGELOG.md` ;
- `docs/36_BATCH_UX_TERMINOLOGIE_FINANCIERE.md`.

## Validation attendue

```text
cd frontend
pnpm test
pnpm lint
pnpm typecheck
pnpm build
cd ..
git diff --check
git status --short
```

Aucun `pytest` backend n’est requis tant qu’aucun fichier backend n’est modifié.

## Validations exécutées par ChatGPT

- vérification des blobs sources modifiés contre les SHA GitHub du HEAD `58b59ba` : conforme ;
- parse/transpilation syntaxique TypeScript des six composants TSX modifiés : succès ;
- audit local des occurrences `notional/notionnel` dans les composants modifiés : les occurrences restantes sont des identifiants/champs techniques ;
- `git diff --check` sur une reconstruction Git exacte des fichiers HEAD concernés : succès ;
- `git status --short` sur cette reconstruction : uniquement les dix fichiers du Batch 36 sont modifiés/créés.

Les commandes `pnpm test`, `pnpm lint`, `pnpm typecheck` et `pnpm build` n’ont pas pu être exécutées dans l’environnement ChatGPT : `pnpm@10.15.1` n’y est pas installé et Corepack ne peut pas accéder au registre npm. Elles restent donc obligatoires localement après extraction.
