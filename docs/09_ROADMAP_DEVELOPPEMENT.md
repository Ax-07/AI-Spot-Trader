# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub post-push Batch 19.8 : f3a8eae8528648c07723aa97350852428254acc7
Batch 19.8 intégré                 : feat: add user-facing Sessions workflow
Validation locale                  : backend 606 passed ; frontend tests/lint/typecheck/build passés
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Jalons intégrés

- 18.1 à 18.8 : tools Agent read-only, sélection multi-marchés, expérimentation, recovery et résilience réseau ;
- 18.9A à 18.9C : Control Plane backend/frontend et validation comportementale ;
- 18.10 à 18.13 : refonte UX, guide opérateur, simplification, dark mode et modernisation ;
- 19.1 : comptabilité SPOT canonique ;
- 19.2 : mark-to-market, equity/exposition backend et monitors sans LLM ;
- 19.3 : `CapacityEvaluator`, `NORMAL` / `MANAGEMENT` et barrière Risk ;
- 19.4 : discovery Kraken et watchlist multi-marchés par le même Agent ;
- 19.5 : explicabilité Agent/Risk/exécution depuis les faits persistés ;
- 19.6A : backend candles, cache borné, recovery et streaming partagé ;
- 19.6B : vue Marchés, Lightweight Charts et markers de fills persistés ;
- 19.7 : overlays de position canoniques `Prix moyen`, `Mark backend`, `Liquidation` ;
- 19.8 : façade utilisateur **Session**, CRUD/lifecycle versionné, configurateur simple/avancé et choix de marchés Automatique IA / Manuel.

## Batch 19.8 — Sessions v1

**État : intégré à GitHub `main` et validé localement.**

Objectif atteint : remplacer dans le parcours normal les concepts techniques Strategy/Revision/Campaign/paper_run par une façade utilisateur **Session** sans casser les faits canoniques existants.

### Backend

- façade `/api/v1/sessions` ;
- création transactionnelle Strategy + Revision 1 + Campaign ;
- projection de Session depuis Strategy/Campaign/runs/runtime ;
- mise à jour versionnée sans mutation d'historique ;
- duplication indépendante ;
- archivage logique via `Strategy.archived_at` ;
- lifecycle start/stop/resume/run-cycle ;
- arrêt = fermeture durable du runtime et du `paper_run` ;
- aucune migration SQL, aucune table `sessions`.

### Frontend

- navigation visible `Accueil | Sessions | Marchés | Positions | Historique | Réglages` ;
- page Sessions responsive ;
- création/édition simple et avancée ;
- mode `Automatique — IA` avec Market Discovery ;
- mode `Manuel` avec univers explicite ;
- technical Control Plane conservé dans `Réglages > Avancé` ;
- dette TypeScript `market_discovery`/`risk_allowed_pairs` corrigée.

### Statuts UX

```text
Brouillon
Prête
En cours
Arrêtée
À reprendre
Archivée
```

Ils sont dérivés des faits persistés et du runtime, jamais stockés comme une vérité concurrente.

### Validation obtenue

- backend complet : `606 passed`, 2 warnings de dépendances ;
- frontend : `21/21` tests passés ;
- `pnpm lint` : passé ;
- `pnpm typecheck` : passé ;
- `pnpm build` : passé ;
- `git diff --check` : aucune erreur de whitespace.

## Cadences à maintenir distinctes

1. monitoring / mark-to-market : déterministe, sans LLM ;
2. cycle stratégique IA : BUY / SELL / HOLD ;
3. discovery / watchlist IA : même Agent, cadence lente ;
4. streaming marché / candles : technique, déterministe, sans LLM.

## Périmètres ultérieurs

- LIVE reste séparé et ultérieur ;
- restauration d'une Session archivée si besoin produit démontré ;
- multi-quote/FX à traiter explicitement ;
- persistence durable des candles uniquement sur besoin démontré ;
- aucun ranking algorithmique stratégique ne doit être introduit silencieusement.
