# 09 — Roadmap de développement

## Référence auditée

```text
HEAD GitHub intégré 18.9C : 5fc7704e7ca43ded4c2565b21871b81fe2161b0a
Message                    : fix: finalize batch 18.9C behavioral validation
```

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

## Plus tard

- enrichissement research uniquement sur besoin mesuré ;
- multi-quote/FX explicite avant tout univers multi-devise ;
- FUTURE daté seulement avec domaine/exécution dédiés ;
- LIVE dans un projet/batch séparé avec permissions et barrières explicites.
