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

Référence intégrée actuelle :

```text
main = e158ea71d9f7cdf010d98d41be1968440c640a53
feat: add bounded read-only market research tools
```

Le Batch 18.1 est **intégré** sur cette référence.

## Batch 18.2 — Sélection causale du marché exécutable

**État : patch proposé, non intégré.**

### Objectif

Permettre au même Agent stratégique de choisir réellement un marché `SPOT` ou `PERPETUAL`
exécutable, puis d'obtenir le `MarketState` canonique exact de ce marché avant sa décision finale.

### Architecture retenue

Deux phases avec **le même Agent** :

```text
MarketSelectionInput
-> research/selection Agent
-> MarketSelection
-> acquisition executable MarketState
-> AgentInput final
-> BUY/SELL/HOLD
-> Risk
-> Broker éventuel
```

### Périmètre proposé

- `ExecutableMarket` typé ;
- univers `PAPER_EXECUTABLE_MARKETS` configurable/auditable ;
- `MarketSelectionInput` + `MarketSelection` avec rationale/traces/digest ;
- routeur exécution SPOT/PERPETUAL ;
- refus FUTURE, inverse, hors-univers et mismatch source ;
- séparation stricte sources research/execution ;
- recapture du portefeuille après snapshot Derivatives ;
- migration `0004_multi_market_selection` ;
- `paper_runs.execution_universe_payload` ;
- `market_selection_*_payload` sur les cycles ;
- API audit typée même en échec avant décision ;
- analytics multi-marchés causal `paper-analytics-v3` ;
- compatibilité du runner/provider mono-marché historique.

### Ce que 18.2 ne fait pas

- pas de scanner/ranking/momentum score ;
- pas de second Agent ;
- pas de `FUTURE` daté exécutable ;
- pas de contrat inverse ;
- pas de conversion multi-devise/FX ;
- pas d'order tool ;
- pas de LIVE/private Kraken ;
- pas de recovery durable du ledger.

### Critère de sortie

Avant intégration :

1. suite complète backend verte ;
2. Ruff + mypy verts ;
3. migration `0004` appliquée sur PostgreSQL de validation ;
4. API paper-runs/cycle audit vérifiée ;
5. smoke PAPER montrant au moins une sélection cross-symbol et, si configuré, un passage SPOT/PERPETUAL ;
6. `git diff --check` propre.

## Après 18.2 — pistes à décider

- version formelle du protocole Agent/tools/sélection dans `ExperimentManifest` ;
- recovery/restart durable du ledger PAPER multi-actifs ;
- valorisation multi-quote avec FX explicite si besoin mesuré ;
- snapshots/exécution FUTURE datés seulement si le domaine est réellement implémenté ;
- enrichissements de recherche mesurés : order book, trades, funding historique, news ;
- campagnes d'expériences Luna/Sol sur univers multi-marché ;
- LIVE toujours dans un batch séparé.
