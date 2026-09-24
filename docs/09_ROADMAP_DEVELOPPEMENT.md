# 09 — Roadmap de développement

## Référence auditée

```text
HEAD GitHub de départ 18.9C : 6e5dcdc1c33103bdd29e9c6fae5c1aca07856808
Dernier commit code intégré : 1eb94e79c3b14fea04faca67d6b2c695b9a27f51
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
  StrategyRevision, preview canonique, Campaigns, activation/reprise et commandes moteur.

## Batch 18.9 — découpage

```text
18.9A — Control Plane + persistence + stratégie/prompt backend      INTÉGRÉ
18.9B — Cockpit de configuration + PERPETUAL UI                    INTÉGRÉ / VALIDÉ
18.9C — validation comportementale via cockpit                     VALIDÉ LOCALEMENT / PRÊT À INTÉGRER
```

## Batch 18.9C — validation comportementale réelle

Validation effectuée depuis le cockpit et les routes backend canoniques :

- création, renommage et archivage de Strategy ;
- création de StrategyRevision immuable, comparaison et prompt preview ;
- Campaign SPOT avec Luna, agressivité, capital, coûts et limites Risk ;
- Campaign PERPETUAL avec marge `ISOLATED`, levier déterministe et caps dérivés ;
- Campaign Sol persistée avec digests distincts, sans activation Sol dans ce batch ;
- activation fraîche et nouveau `paper_run_id` ;
- `run-cycle` isolé : un cycle puis retour à `STOPPED` ;
- Start/Stop : boucle autonome backend puis arrêt coopératif ;
- restart backend : moteur `UNAVAILABLE` et aucune Campaign active avant action opérateur ;
- reprise explicite : nouveau run, lineage `resumed_from_paper_run_id` et ledger exact restauré ;
- SPOT : BUY naturel SOL/USD, Risk `MODIFY` pour `MAX_ORDER_NOTIONAL_LIMIT`, fill PAPER,
  coûts appliqués, puis HOLD naturels ;
- PERPETUAL : BUY naturel SOL/USD, Risk `MODIFY`, levier 2, `ISOLATED`, marge, fill PAPER,
  position LONG et prix de liquidation persistés ;
- refus fail-closed validés : 409 sur Strategy archivée, 422 sur configuration invalide,
  503 sur `run-cycle` sans runtime ;
- aucun SELL naturel observé ; aucune décision stratégique n'a été forcée.

### Correctif JSON découvert pendant 18.9C

Le cockpit envoyait correctement `market_type` en JSON (`"SPOT"` / `"PERPETUAL"`), mais
`CampaignConfiguration` réutilisait directement le modèle domaine strict `ExecutableMarket`.
Pydantic refusait alors la chaîne JSON avant conversion vers `MarketType`.

Correction :

- adaptation des seules valeurs JSON canoniques `SPOT` / `PERPETUAL` vers `MarketType` à la
  frontière Control Plane ;
- modèle domaine `ExecutableMarket` conservé strict ;
- valeur inconnue conservée fail-closed et rejetée ;
- tests de régression JSON ajoutés.

### Nettoyage mypy découvert en validation finale

Le mypy global révélait quatre erreurs de typage déjà présentes sur le `main` intégré dans trois
routes API. Les valeurs runtime étaient valides mais typées `str` alors que les schémas de réponse
attendent des `Literal[...]`.

Correction locale sans changement fonctionnel :

- casts ciblés aux frontières de sérialisation `paper_runs` et `audit` ;
- annotation `Literal["MarketSelectionInput", "AgentInput"]` pour le prompt preview.

Validation locale finale :

```text
pytest backend : 506 passed, 2 warnings
ruff check backend : OK
mypy backend/src : OK, 89 source files
git diff --check : OK hors avertissements LF -> CRLF
```

## Plus tard

- enrichissement research uniquement sur besoin mesuré ;
- multi-quote/FX explicite avant tout univers multi-devise ;
- FUTURE daté seulement avec domaine/exécution dédiés ;
- LIVE dans un projet/batch séparé avec permissions et barrières explicites.
