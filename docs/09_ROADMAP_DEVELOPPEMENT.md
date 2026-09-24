# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub main audité : dbdc8f83bb39c158ec7331ce2adba616d2922842
```

Le HEAD doit être revérifié au démarrage de chaque nouveau batch. Le document détaillé des améliorations est `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Jalons intégrés avant 19.1

- 18.1 à 18.8 : tools Agent read-only, sélection multi-marchés, expérimentation, recovery et résilience réseau ;
- 18.9A à 18.9C : Control Plane backend/frontend et validation comportementale ;
- 18.10 à 18.13 : refonte UX, guide opérateur, simplification, dark mode et modernisation ;
- cadrage des améliorations futures jusqu'aux batches 19.x : HEAD `dbdc8f83...`.

## Batch 19.1 — Comptabilité SPOT canonique

**État du patch : implémenté, à valider/intégrer localement par l'opérateur.**

Résultat :

- `AssetPosition` enrichi avec prix moyen d'entrée, coût de revient restant, P&L réalisé et indicateur de complétude ;
- BUY successifs au coût économique moyen pondéré (`remaining_cost_basis / quantity`) ;
- frais BUY inclus dans le coût de revient via le débit cash réel ;
- ventes partielles avec libération de base de coût au prorata et P&L réalisé net ;
- vente totale fermant la position ;
- P&L réalisé de SELL porté également par le Fill durable ;
- aucune double prise en compte spread/slippage/frais ;
- persistence/recovery via le JSON `PortfolioState` existant, sans migration SQL ;
- compatibilité des anciens snapshots via `accounting_complete=false` ;
- contrat API et types cockpit enrichis ;
- affichage frontend backend-sourced, sans P&L latent reconstruit ;
- tests ciblés dédiés à la comptabilité SPOT.

Le P&L latent/mark-to-market complet reste volontairement hors 19.1.

## Prochaine séquence

### Batch 19.2 — Monitoring et mark-to-market déterministes

- acquisition prix/marks Kraken adaptée au monitoring ;
- revalorisation SPOT et PERPETUAL ;
- P&L latent, exposition, marge, liquidation et funding lorsque pertinent ;
- snapshot cohérent consommable par API, Agent et analytics ;
- cadence dédiée/configurable ;
- aucun choix stratégique dans le monitor.

### Batch 19.3 — Mode gestion et optimisation de consommation IA

- déterminer si une nouvelle exposition est possible ;
- éviter recherche/tools d'ouverture inutiles lorsque la capacité est saturée ;
- concentrer le même Agent sur les positions existantes ;
- HOLD/réduction/clôture ;
- Risk toujours final ;
- métriques d'appels/tools/tokens réellement observables.

### Batch 19.4 — Découverte dynamique et watchlist versionnée

- univers techniquement admissible déterministe ;
- mode manuel conservé ;
- cadence indépendante ;
- sélection/watchlist par le même Agent ;
- persistence/versionnement/audit ;
- invariant `marchés surveillés = watchlist + positions ouvertes`.

### Batch 19.5 — Explicabilité opérateur

- afficher le `rationale` de l'Agent ;
- séparer explicitement rationale stratégique et résultat Risk ;
- corréler décisions/trades/positions/historique.

### Batch 19.6A — Backend candles, cache et streaming cockpit

- historique initial Kraken REST ;
- mises à jour Kraken WebSocket ;
- normalisation/cache/persistence éventuelle ;
- API historique et WebSocket cockpit ;
- backfill/recovery sans look-ahead.

### Batch 19.6B — Vue Marchés, Lightweight Charts et markers

- navigation Marchés ;
- onglets par marché surveillé ;
- Lightweight Charts ;
- overlays position/mark/liquidation ;
- markers BUY/SELL/réduction/clôture ;
- détails fill/rationale/Risk ;
- lazy loading/cache.

## Pourquoi cet ordre

La comptabilité SPOT doit exister avant le mark-to-market. Le monitoring doit ensuite fournir un état courant fiable avant le mode gestion. Discovery/watchlist introduit un nouvel état durable et une autre cadence IA. Les charts restent séparés en source backend puis rendu frontend.

## Cadences à maintenir distinctes

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY/SELL/HOLD ;
3. **découverte/révision de watchlist IA** : nettement plus lente.

## Périmètres ultérieurs

- LIVE reste séparé et ultérieur ;
- FUTURE daté reste hors exécution tant qu'un domaine dédié n'est pas décidé ;
- multi-quote/FX reste à traiter explicitement ;
- enrichissement research additionnel uniquement sur besoin mesuré.
