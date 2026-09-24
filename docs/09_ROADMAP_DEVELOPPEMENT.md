# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub main audité : 01ca1e857947d969556481e5593c5712d137f5ad
```

Le HEAD doit être revérifié au démarrage de chaque nouveau batch. Le document détaillé des améliorations est `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Jalons intégrés avant 19.2

- 18.1 à 18.8 : tools Agent read-only, sélection multi-marchés, expérimentation, recovery et résilience réseau ;
- 18.9A à 18.9C : Control Plane backend/frontend et validation comportementale ;
- 18.10 à 18.13 : refonte UX, guide opérateur, simplification, dark mode et modernisation ;
- Batch 19.1 : comptabilité SPOT canonique intégrée, clôture documentaire au HEAD `01ca1e8...`.

## Batch 19.2 — Monitoring et mark-to-market déterministes

**État du patch : implémenté par ChatGPT, à valider/intégrer localement par l'opérateur.**

Résultat :

- mark SPOT canonique basé sur le dernier prix ticker Kraken causal ;
- timestamp et source du mark exposés par position ;
- `market_value = quantity * mark_price` ;
- `unrealized_pnl = market_value - remaining_cost_basis` lorsque la comptabilité 19.1 est complète ;
- marks absents/périmés explicitement indisponibles ;
- positions legacy valorisables au marché sans inventer un P&L latent ;
- agrégats `PortfolioState` : cash, coût restant, valeur SPOT, P&L réalisé/latent, equity et exposition lorsque calculables ;
- monitor backend SPOT/PERPETUAL sans LLM, cadence/timeout/staleness configurables ;
- valorisation SPOT alimentée par la source de marché canonique et le monitor, séparée de l'exécution du broker ;
- recovery compatible sans migration SQL ni replay historique ;
- API/types/cockpit Positions enrichis ;
- suppression du rapprochement TypeScript entre position et dernier marché global ;
- tests ciblés 19.2 couvrant valorisation, recovery, staleness, coûts, Decimal et no-look-ahead.

Le Batch 19.2 ne comprend ni watchlist dynamique, ni optimisation IA à exposition saturée, ni charts/WebSocket cockpit.

## Prochaine séquence

### Batch 19.3 — Mode gestion et optimisation de consommation IA

- déterminer si une nouvelle exposition est possible à partir de l'état canonique valorisé ;
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

La comptabilité SPOT 19.1 fournit la base de coût ; le mark-to-market 19.2 fournit maintenant l'état courant fiable nécessaire au mode gestion. Discovery/watchlist introduira ensuite un nouvel état durable et une autre cadence IA. Les charts restent séparés en source backend puis rendu frontend.

## Cadences à maintenir distinctes

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY/SELL/HOLD ;
3. **découverte/révision de watchlist IA** : nettement plus lente.

## Périmètres ultérieurs

- LIVE reste séparé et ultérieur ;
- FUTURE daté reste hors exécution tant qu'un domaine dédié n'est pas décidé ;
- multi-quote/FX reste à traiter explicitement ;
- enrichissement research additionnel uniquement sur besoin mesuré.
