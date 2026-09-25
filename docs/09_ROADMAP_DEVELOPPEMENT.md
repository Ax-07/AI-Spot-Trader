# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub main audité : bfef06d78dc34089541272c2944518499d4a1530
```

Le HEAD doit être revérifié au démarrage de chaque nouveau batch. Le document détaillé des améliorations est `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Jalons intégrés avant 19.4

- 18.1 à 18.8 : tools Agent read-only, sélection multi-marchés, expérimentation, recovery et résilience réseau ;
- 18.9A à 18.9C : Control Plane backend/frontend et validation comportementale ;
- 18.10 à 18.13 : refonte UX, guide opérateur, simplification, dark mode et modernisation ;
- Batch 19.1 : comptabilité SPOT canonique ;
- Batch 19.2 : mark-to-market canonique, equity/exposition backend et monitors SPOT/PERPETUAL sans LLM ;
- Batch 19.3 : `CapacityEvaluator`, modes `NORMAL` / `MANAGEMENT`, désactivation de la recherche d'ouverture inutile et barrière Risk contre les hausses d'exposition en MANAGEMENT ; intégré au HEAD `bfef06d...`.

## Batch 19.4 — Découverte dynamique et watchlist auditée

**État du patch : implémenté par ChatGPT, à valider/intégrer localement par l'opérateur.**

Résultat visé :

- `MarketDiscoveryPolicy` optionnel et versionné dans `CampaignConfiguration` ;
- compatibilité ascendante : une Campaign sans policy conserve exactement son univers statique ;
- `paper_executable_markets` devient le bootstrap/garde-fou immuable d'une Campaign dynamique ;
- catalogue canonique réutilisé via `MarketResearchService` + adaptateurs Kraken existants ;
- cache catalogue 15 min par défaut ;
- refresh watchlist 15 min par défaut, déclenché uniquement par un cycle `NORMAL`, borné à 45 s ;
- filtrage factuel sans ranking : type, quote settlement, statut, contrat PERPETUAL linéaire, disponibilité/fraîcheur snapshot et historique causal ;
- rotation déterministe du sous-ensemble sondé pour couvrir progressivement un catalogue trop large ;
- limites par défaut : 24 marchés sondés, 12 candidats Agent, 6 marchés watchlist ;
- sélection multi-marchés par le même Agent stratégique, avec rationale global et par marché ;
- validation fail-closed : toute sortie LLM hors candidats, dupliquée ou trop grande est refusée ;
- fallback explicite : dernière watchlist valide, sinon bootstrap Campaign ;
- panne Kraken/LLM temporisée par la cadence de refresh au lieu de relancer à chaque cycle ;
- univers effectif : watchlist + toutes les positions ouvertes ;
- positions existantes toujours gérables après retrait de watchlist ;
- `MANAGEMENT` évalué avant discovery : aucun refresh destiné à ouvrir de nouvelles expositions ;
- recovery Campaign canonique conservé avec extension de l'univers au moment de la reprise pour les positions dynamiques durables ;
- audit sans migration SQL via extension persistée de `MarketSelectionInput` : statut, candidats et leurs snapshots factuels, watchlist, ajouts/maintiens/retraits, rationale, erreur et prochain refresh ;
- configurateur simple : paire de départ/secours seulement, discovery activée par défaut ;
- aucun second Agent, aucun ordre déclenché par la watchlist, aucun changement de l'autorité Risk.

Le Batch 19.4 ne comprend ni explicabilité produit 19.5, ni candles/WebSocket/charts 19.6, ni LIVE.

## Prochaine séquence

### Batch 19.5 — Explicabilité opérateur

- afficher le `rationale` de l'Agent ;
- séparer explicitement rationale stratégique et résultat Risk ;
- corréler décisions/trades/positions/historique ;
- exploiter aussi l'audit de watchlist 19.4 sans confondre sélection de marché et décision de trade.

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

La comptabilité 19.1 et le mark-to-market 19.2 fournissent un état portfolio exploitable. Le Batch 19.3 supprime la recherche d'ouverture quand elle est déterministement inutile ou incertaine. Le Batch 19.4 peut donc renouveler un univers stratégique plus large sans gaspiller d'IA en MANAGEMENT et sans déplacer le choix d'opportunité hors de l'Agent. L'explicabilité puis les charts peuvent s'appuyer sur ces traces canoniques.

## Cadences à maintenir distinctes

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY/SELL/HOLD, avec restriction MANAGEMENT si nécessaire ;
3. **découverte/révision de watchlist IA** : beaucoup plus lente, 15 min par défaut dans 19.4.

## Périmètres ultérieurs

- LIVE reste séparé et ultérieur ;
- FUTURE daté reste hors exécution tant qu'un domaine dédié n'est pas décidé ;
- multi-quote/FX reste à traiter explicitement ;
- enrichissement research additionnel (volume/spread/depth dédiés) uniquement sur besoin mesuré ;
- persistence mutable autonome de watchlist à reconsidérer seulement si le cache process-local + audit de cycle devient insuffisant.
