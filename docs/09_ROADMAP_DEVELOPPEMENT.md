# 09 — Roadmap de développement

## Référence auditée

```text
HEAD GitHub audité pour 18.10 : 34145a904c07af90e1c9ed370479cd5e5a0c0139
Message                        : docs: sync batch 18.9C integrated state
HEAD code/validation 18.9C     : 5fc7704e7ca43ded4c2565b21871b81fe2161b0a
```

Le commit `34145a9` synchronise la documentation de l'état 18.9C et ne modifie pas le code du
cockpit ou du backend.

## Jalons intégrés

- Batch 18.1 : tools Agent read-only et traces causales ;
- Batch 18.2 : sélection causale multi-marchés SPOT/PERPETUAL ;
- Batch 18.3 : validation comportementale et parsing Kraken margin schedules ;
- Batch 18.5 : `paper-experiment-v3` et identité tools/sélection ;
- Batch 18.6 : recovery `paper-ledger-recovery-v1`, migration `0005` ;
- Batch 18.7 : retries réseau bornés ;
- Batch 18.8 : validation réelle recovery/réseau, 20/20 cycles `COMPLETED`, tous `HOLD` ;
- Batch 18.9A : Control Plane backend, stratégies versionnées, Campaigns persistantes,
  `paper-experiment-v4`, migration `0006`, runtime canonique par Campaign ;
- Batch 18.9B : cockpit Control Plane frontend, configuration PAPER SPOT/PERPETUAL, Strategy,
  StrategyRevision, preview canonique, Campaigns, activation/reprise et commandes moteur ;
- Batch 18.9C : validation comportementale réelle via cockpit, correctif JSON `market_type` et
  nettoyage mypy des frontières API.

## Batch 18.9 — état intégré

```text
18.9A — Control Plane + persistence + stratégie/prompt backend      INTÉGRÉ
18.9B — Cockpit de configuration + PERPETUAL UI                    INTÉGRÉ / VALIDÉ
18.9C — validation comportementale via cockpit                     INTÉGRÉ / VALIDÉ
```

## Batch 18.9C — validation comportementale réelle

Validation effectuée depuis le cockpit et les routes backend canoniques :

- création, renommage et archivage de Strategy ;
- création de StrategyRevision immuable, comparaison et prompt preview ;
- Campaign SPOT avec Luna, agressivité, capital, coûts et limites Risk ;
- Campaign PERPETUAL avec marge `ISOLATED`, levier déterministe et caps dérivés ;
- Luna et Sol sélectionnables et persistés dans la configuration de Campaign ;
- activation fraîche et nouveau `paper_run_id` ;
- `run-cycle` isolé : un cycle puis retour à `STOPPED` ;
- Start/Stop : boucle autonome backend puis arrêt coopératif ;
- restart backend : moteur `UNAVAILABLE` et aucune Campaign active avant action opérateur ;
- reprise explicite : nouveau run, lineage `resumed_from_paper_run_id` et ledger restauré ;
- SPOT : BUY naturel SOL/USD, Risk `MODIFY` pour la limite de notional, fill PAPER et coûts appliqués,
  puis HOLD naturels ;
- PERPETUAL : BUY naturel SOL/USD, Risk `MODIFY`, levier 2, `ISOLATED`, marge, fill PAPER et
  position LONG persistée ;
- refus fail-closed validés : 409 sur Strategy archivée, 422 sur configuration invalide,
  503 sur `run-cycle` sans runtime ;
- aucun SELL naturel observé ; aucune décision stratégique n'a été forcée.

### Correctif JSON intégré

`CampaignConfiguration` adapte désormais à la frontière Control Plane les valeurs JSON canoniques
`SPOT` / `PERPETUAL` vers `MarketType` avant validation du modèle `ExecutableMarket` strict.
Les valeurs inconnues restent rejetées. Des tests de régression JSON couvrent SPOT, PERPETUAL et
le rejet fail-closed.

### Nettoyage mypy intégré

Les incompatibilités de typing préexistantes aux frontières de sérialisation ont été corrigées par
des annotations `Literal` / `cast` ciblées dans trois routes API, sans changement fonctionnel.

### Validation historique du commit intégré

Exécutée localement par l'opérateur avant le push de `5fc7704` :

```text
pytest backend : 506 passed, 2 warnings
ruff check backend : All checks passed
mypy backend/src : Success: no issues found in 89 source files
git diff --check : OK hors avertissements LF -> CRLF
working tree propre avant push
```

## Batch 18.10 — refonte UX/UI cockpit — livré, à valider localement

Objectif : transformer l'interface 18.9B, fonctionnelle mais dense, en cockpit opérateur lisible sans
modifier les contrats ou la logique du backend.

Direction retenue : **Option A — Vue d'ensemble**.

### Architecture UI cible livrée

```text
CockpitShell
├─ navigation latérale
│  ├─ Vue d'ensemble
│  ├─ Pilotage
│  ├─ Activité
│  ├─ Performance
│  └─ Assistant
├─ header opérateur
│  ├─ PAPER
│  ├─ Campaign / Strategy active
│  ├─ modèle + types de marchés
│  ├─ état moteur
│  └─ run-cycle / Start / Stop
└─ landing Vue d'ensemble
   ├─ KPI PAPER
   ├─ Marché & activité
   ├─ Actions rapides
   ├─ Dernières décisions de l'IA + statut Risk
   └─ Alertes système & backend
```

Les composants `ControlPlanePanel`, `CockpitDashboard`, `AnalyticsPanel` et `ChatPanel` restent
canoniques et sont réutilisés comme vues secondaires. Aucune implémentation parallèle de Strategy,
Campaign, Risk, Broker ou moteur de trading n'est introduite.

### Validation de livraison 18.10

Exécuté par ChatGPT :

```text
TypeScript transpile/syntax check : OK
typecheck ciblé avec contrats GitHub actuels : OK
harness structure UX/invariants : OK
git diff --check du patch : OK
```

À exécuter localement avec les dépendances du repository :

```powershell
cd frontend
pnpm lint
pnpm typecheck
pnpm build
cd ..
git diff --check
```

## Plus tard

- enrichissement research uniquement sur besoin mesuré ;
- multi-quote/FX explicite avant tout univers multi-devise ;
- FUTURE daté seulement avec domaine/exécution dédiés ;
- LIVE dans un projet/batch séparé avec permissions et barrières explicites.
