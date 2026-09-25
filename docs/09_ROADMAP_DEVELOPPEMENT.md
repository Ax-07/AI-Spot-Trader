# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub main observé          : e7e4c8248406516eada576b3907e77dc8b72a0e4
Référence fonctionnelle Batch 19.4 : de65c6677ce01f9c75da5545fe81553a021f588d
État Batch 19.5                    : validation automatisée locale réussie, commit/push en attente
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch. Le document détaillé des améliorations est `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Jalons intégrés

- 18.1 à 18.8 : tools Agent read-only, sélection multi-marchés, expérimentation, recovery et résilience réseau ;
- 18.9A à 18.9C : Control Plane backend/frontend et validation comportementale ;
- 18.10 à 18.13 : refonte UX, guide opérateur, simplification, dark mode et modernisation ;
- Batch 19.1 : comptabilité SPOT canonique ;
- Batch 19.2 : mark-to-market canonique, equity/exposition backend et monitors SPOT/PERPETUAL sans LLM ;
- Batch 19.3 : `CapacityEvaluator`, modes `NORMAL` / `MANAGEMENT`, désactivation de la recherche d'ouverture inutile et barrière Risk contre les hausses d'exposition en MANAGEMENT ;
- Batch 19.4 : découverte dynamique Kraken, watchlist multi-marchés auditée, même Agent stratégique, fallback/recovery et configurateur simplifié.

## Batch 19.4 — Découverte dynamique et watchlist auditée

**État : intégré sur GitHub.**

Référence fonctionnelle : `de65c6677ce01f9c75da5545fe81553a021f588d` (`feat: add dynamic audited market discovery`).

Validation opérateur communiquée :

- `tests/test_market_discovery.py` : 12 tests passés ;
- suite backend complète : 578 tests passés, 2 warnings de dépréciation ;
- frontend : `pnpm lint`, `pnpm typecheck`, `pnpm build` passés.

Résultat intégré :

- `MarketDiscoveryPolicy` optionnel et versionné dans `CampaignConfiguration` ;
- compatibilité ascendante : une Campaign sans policy conserve son univers statique ;
- `paper_executable_markets` reste le bootstrap/garde-fou immuable d'une Campaign dynamique ;
- catalogue canonique réutilisé via `MarketResearchService` + adaptateurs Kraken existants ;
- cache catalogue 15 min par défaut ;
- refresh watchlist 15 min par défaut, déclenché uniquement par un cycle `NORMAL`, borné à 45 s ;
- filtrage factuel sans ranking ;
- sélection multi-marchés par le même Agent stratégique, avec rationale global et par marché ;
- fallback explicite : dernière watchlist valide, sinon bootstrap Campaign ;
- univers effectif : watchlist + toutes les positions ouvertes ;
- `MANAGEMENT` évalué avant discovery ;
- audit sans migration SQL via extension persistée de `MarketSelectionInput` ;
- aucun second Agent, aucun ordre déclenché par la watchlist, aucun changement de l'autorité Risk.

## Batch 19.5 — Explicabilité opérateur

**État : validation automatisée locale réussie ; intégration GitHub en attente du commit/push.**

Architecture mise en place :

```text
faits canoniques persistés du cycle
-> projection backend typée d'explicabilité
-> /cycles/latest et /cycles/{cycle_id}
-> cockpit Accueil / Historique
```

Le Batch 19.5 :

- n'ajoute aucune table SQL ni ledger ;
- ne recalcule ni stratégie, ni Risk, ni P&L ;
- sépare discovery/watchlist, contexte `NORMAL` / `MANAGEMENT`, sélection du marché du cycle, décision Agent, résultat Risk et exécution PAPER ;
- expose quantité proposée, demandée et autorisée sans faire croire que Risk change l'action ou le marché ;
- distingue HOLD, REJECT et échec technique ;
- conserve les artefacts produits avant un `FAILED`, notamment un intent existant avant un échec Broker ;
- affiche explicitement l'absence de rationale sur les historiques legacy ;
- fait charger à l'Historique les détails corrélés de chaque cycle au lieu de joindre des pages indépendantes ;
- présente dans Positions uniquement une **activité auditée liée au même marché**, pas une provenance de position.

Validation locale exécutée par l'opérateur sur le repository complet :

- `pytest tests/test_cycle_explainability.py` : **8 tests passés** ;
- `pytest` : **586 tests passés**, 2 warnings de dépréciation ;
- `pnpm lint` : **passé** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé** ;
- `git diff --check` : aucune erreur, seulement des avertissements LF -> CRLF.

La revue visuelle light/dark + responsive reste la dernière validation opérateur à distinguer des tests automatisés avant clôture définitive.

## Prochaine séquence

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

La comptabilité 19.1 et le mark-to-market 19.2 fournissent un état portfolio exploitable. Le Batch 19.3 supprime la recherche d'ouverture quand elle est déterministement inutile ou incertaine. Le Batch 19.4 renouvelle un univers stratégique plus large sans gaspiller d'IA en MANAGEMENT. Le Batch 19.5 rend ces traces canoniques lisibles avant que 19.6 n'ajoute les charts et markers.

## Cadences à maintenir distinctes

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY / SELL / HOLD ;
3. **découverte/révision de watchlist IA** : beaucoup plus lente, 15 min par défaut.

## Périmètres ultérieurs

- LIVE reste séparé et ultérieur ;
- FUTURE daté reste hors exécution tant qu'un domaine dédié n'est pas décidé ;
- multi-quote/FX reste à traiter explicitement ;
- enrichissement research additionnel uniquement sur besoin mesuré ;
- persistence mutable autonome de watchlist à reconsidérer seulement si le cache process-local + audit de cycle devient insuffisant.
