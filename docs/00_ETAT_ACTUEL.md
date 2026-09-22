# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub intégré : `e158ea71d9f7cdf010d98d41be1968440c640a53`
- Commit : `feat: add bounded read-only market research tools`
- Batch 18.1 : **intégré** sur ce HEAD ; validation locale opérateur confirmée avant Batch 18.2.
- Prompt stratégique : `agent-strategy-v4`.

## Batch 18.2 — patch proposé, non intégré

Objectif : permettre au **même Agent stratégique** de choisir réellement le marché exécutable
avant le snapshot final, sans second Agent ni sélection algorithmique.

Le patch proposé ajoute :

- `ExecutableMarket` et `MarketSelectionInput` ;
- `MarketSelection` durable : symbole, type, rationale, traces, timestamp et digest ;
- phase Agent `select_market()` puis acquisition canonique du marché choisi ;
- routeur d'exécution SPOT/PERPETUAL strict, avec refus FUTURE/inverse/hors univers ;
- `AI_SPOT_TRADER_PAPER_EXECUTABLE_MARKETS` comme univers PAPER typé ;
- migration `0004_multi_market_selection` ;
- `paper_runs.execution_universe_payload`, sans faux symbole/type `MULTI` ;
- persistance/API de la sélection même si le cycle échoue avant décision ;
- analytics `paper-analytics-v3` avec derniers marks SPOT causaux par actif.

## Frontières conservées

- un seul Agent IA ;
- Kraken ; PAPER uniquement ;
- SPOT sans short/levier/marge ;
- PERPETUAL linéaire seulement, marge ISOLATED ;
- Risk seul crée `ExecutionIntent`, choisit levier effectif et `reduce_only` ;
- aucun tool -> Broker/Risk ; aucun LLM -> Broker ;
- sources research distinctes des sources execution ;
- `PortfolioState` complet ;
- HOLD valide ;
- aucune donnée postérieure à la décision finale.

## Validation exécutée par ChatGPT

```text
40 tests ciblés Batch 18.2 : passed
compileall code/tests/migration : OK
```

Non exécuté ici : persistance async SQLite/PostgreSQL, suite complète, Ruff, mypy et Alembic réel.

## Prochaine étape

1. extraire le ZIP à la racine ;
2. exécuter la validation locale complète + `alembic upgrade head` ;
3. vérifier un smoke PAPER multi-marchés ;
4. intégrer seulement après validation, commit et push.
