# 09 — Roadmap de développement

## Règle de lecture

Un batch est **intégré** uniquement après validation locale, commit et push confirmés sur GitHub
`main`. Un ZIP livré par ChatGPT reste un patch proposé tant que ces étapes ne sont pas réalisées.

## Historique intégré synthétique

- Batches 00–15.3 : socle SPOT PAPER, Agent, Risk, Broker, PostgreSQL, API/cockpit, analytics et expériences.
- Batch 16 : Kraken Derivatives PAPER, LONG/SHORT, marge ISOLATED, levier déterministe, funding, P&L et anti-reversal.
- Batch 16.2 : isolation durable par `paper_run_id`.
- Batch 16.3 : smokes LONG/SHORT contrôlés.
- Batch 16.5 : contexte PERPETUAL causal via `MarketStateBuilder` et bougies mark publiques.
- Batch 16.6 : validation comportementale Luna sans forcer BUY/SELL.
- Prompt `agent-strategy-v4` : localisation française.
- Batch 17 : durcissement fail-closed de la frontière Kraken Derivatives publique.
- Batch 18.1 : tools Agent read-only bornés, boucle Responses function calling, traces causales et migration `0003_agent_tool_traces`.
- Batch 18.2 : sélection causale du marché exécutable par le même Agent, univers PAPER typé, routeur SPOT/PERPETUAL, persistance/API multi-marchés, migration `0004_multi_market_selection` et analytics causal v3.
- Batch 18.3 : validation comportementale PAPER multi-marchés/cross-symbol et correction du parsing des `marginSchedules` Kraken Derivatives imbriqués.

Référence intégrée actuelle :

```text
main = 4042e0b0e6394de788009229e3dae5924cd732d7
fix: support nested Kraken derivative margin schedules
```

## Batch 18.2 — intégré

Le même Agent stratégique exécute deux phases causales :

```text
MarketSelectionInput
-> recherche/sélection par l'Agent
-> MarketSelection
-> acquisition du MarketState exécutable exact
-> AgentInput final
-> BUY/SELL/HOLD
-> Risk
-> Broker éventuel
```

Le périmètre intégré conserve les invariants suivants : aucun second Agent, aucun
scanner/ranking/opportunity score, séparation stricte research/execution, SPOT sans short/levier,
PERPETUAL linéaire uniquement lorsque supporté, Risk autorité finale et aucune exécution directe
par le LLM ou un tool.

Validation locale confirmée avant intégration 18.2 :

```text
pytest backend : 447 passed, 2 warnings
ruff check backend : OK
mypy backend/src : OK, 79 source files
Alembic 0003_agent_tool_traces -> 0004_multi_market_selection sur PostgreSQL : OK
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

## Batch 18.3 — intégré

### Objectif

Valider réellement le pipeline PAPER multi-marchés/cross-symbol de 18.2 avec le provider réel et
les sources Kraken publiques, sans forcer BUY/SELL ni transformer un résultat HOLD en échec.

### Résultats confirmés

- sélection cross-symbol SPOT réelle ;
- `paper_runs.execution_universe_payload` multi-marché réel avec projection historique
  `market_type/symbol = NULL` ;
- univers mixte `SPOT:BTC/USD + PERPETUAL:ETH/USD` chargé et recherché ;
- plusieurs cycles mixtes SPOT terminés `COMPLETED / HOLD` ;
- branche singleton `PERPETUAL:ETH/USD` validée de la sélection jusqu'au `MarketState`, à la
  décision `HOLD` et à `Risk=ALLOW/HOLD_NO_EXECUTION` ;
- catalogue public Derivatives parsé après correction : 296 instruments lors du smoke ;
- séparation research/execution observée : les snapshots de research restent des traces et le
  marché sélectionné est reacquis par la source d'exécution dédiée.

### Défaut découvert et intégré

Le payload public Kraken expose désormais notamment :

```text
marginSchedules
  -> région
    -> retail | professional
      -> [tiers de marge]
```

Le parser historique supposait une map directe `nom -> ligne de marge` et échouait avec
`KrakenPayloadError: initialMargin is invalid`. Le commit `4042e0b` aplatit les feuilles reconnues,
les valide toutes fail-closed et conserve la sémantique conservatrice existante : taux publics les
plus stricts retenus faute de tier privé prouvable.

### Validation locale confirmée

```text
pytest backend/tests/test_kraken_derivatives.py backend/tests/test_kraken_derivatives_context.py : 27 passed
pytest backend : 449 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF avant commit
```

Les deux warnings Starlette/AnyIO restent non bloquants.

### Limites honnêtes du smoke

- aucune sélection PERPETUAL spontanée n'a été observée depuis l'univers mixte ;
- aucun fill réel n'a été produit, les décisions observées ayant été `HOLD` ;
- un timeout SPOT au stage `MARKET` a été observé une fois puis non reproduit sur plusieurs cycles
  suivants ;
- un `LLMTransportError` au stage `MARKET_SELECTION` a été observé isolément.

Ces limites ne remettent pas en cause les branches validées, mais elles restent des axes de
robustesse/expérimentation à mesurer au lieu d'être déclarées résolues.

## Prochain vrai batch — candidats à auditer

Aucune priorité architecturale n'est décidée ici. Candidats :

- protocole expérimental versionné Agent/tools/sélection dans `ExperimentManifest` ;
- recovery/restart durable du ledger PAPER multi-actifs ;
- robustesse réseau et observabilité bornée des erreurs transitoires Market/LLM ;
- enrichissement mesuré des données de recherche : order book, trades, funding historique, news ;
- campagnes Luna/Sol sur univers multi-marché ;
- valorisation multi-quote avec FX explicite seulement si le besoin est mesuré ;
- FUTURE daté seulement si le domaine correspondant est réellement implémenté ;
- LIVE toujours dans un batch séparé.
