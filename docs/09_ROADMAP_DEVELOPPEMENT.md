# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub main audité : 44670a249ba662b2afd50a0a9e2a0e63ea4ed76d
```

Le HEAD doit être revérifié au démarrage de chaque nouveau batch. Le document détaillé des améliorations est `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Jalons intégrés avant 19.3

- 18.1 à 18.8 : tools Agent read-only, sélection multi-marchés, expérimentation, recovery et résilience réseau ;
- 18.9A à 18.9C : Control Plane backend/frontend et validation comportementale ;
- 18.10 à 18.13 : refonte UX, guide opérateur, simplification, dark mode et modernisation ;
- Batch 19.1 : comptabilité SPOT canonique ;
- Batch 19.2 : mark-to-market canonique, equity/exposition backend et monitors SPOT/PERPETUAL sans LLM, intégré au HEAD `44670a2...`.

## Batch 19.3 — Mode gestion et optimisation de consommation IA

**État du patch : implémenté par ChatGPT, à valider/intégrer localement par l'opérateur.**

Résultat :

- `CapacityEvaluator` déterministe branché avant la sélection de marché ;
- partage de la même instance `RiskPolicy` entre CapacityEvaluator et RiskEngine ;
- modes `NORMAL` et `MANAGEMENT` recalculés à chaque cycle ;
- aucune limite globale SPOT inventée ;
- saturation PERPETUAL détectable via plafond d'exposition totale et plafond par position déjà ouverte ;
- valorisation incomplète traitée explicitement en MANAGEMENT sans capacité fictive ;
- en MANAGEMENT, candidats de sélection limités aux positions réellement ouvertes ;
- tools read-only de recherche d'ouverture désactivés pendant la sélection MANAGEMENT ;
- même Agent stratégique conservé pour choisir parmi les positions ouvertes puis décider HOLD/réduction/clôture ;
- barrière Risk explicite contre toute augmentation d'exposition en MANAGEMENT ;
- logique SPOT SELL et PERPETUAL `reduce_only` existante conservée ;
- retour automatique à NORMAL après libération de capacité ;
- mode, raison et `new_opening_research_skipped` ajoutés à l'audit de cycle sans migration SQL ;
- aucun état de mode durable à restaurer ;
- aucune estimation de tokens fabriquée car l'infrastructure ne persiste pas d'usage tokens canonique ;
- aucun changement frontend.

Le Batch 19.3 ne comprend ni discovery/watchlist dynamique, ni refonte d'explicabilité, ni candles/WebSocket/charts, ni LIVE.

## Prochaine séquence

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

La comptabilité 19.1 et le mark-to-market 19.2 fournissent un état portfolio exploitable. Le Batch 19.3 utilise cet état pour supprimer la recherche d'ouverture quand elle est déterministement inutile ou incertaine, sans déplacer la stratégie hors de l'Agent. Discovery/watchlist 19.4 pourra ensuite introduire un nouvel état durable et une cadence IA plus lente sans mélanger les responsabilités.

## Cadences à maintenir distinctes

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY/SELL/HOLD, avec restriction MANAGEMENT si nécessaire ;
3. **découverte/révision de watchlist IA** : nettement plus lente.

## Périmètres ultérieurs

- LIVE reste séparé et ultérieur ;
- FUTURE daté reste hors exécution tant qu'un domaine dédié n'est pas décidé ;
- multi-quote/FX reste à traiter explicitement ;
- enrichissement research additionnel uniquement sur besoin mesuré.
