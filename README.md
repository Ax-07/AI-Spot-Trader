# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **PAPER** sur Kraken,
pilotée par **un seul Agent IA stratégique**. L'Agent choisit le marché à analyser et propose
`BUY`, `SELL` ou `HOLD`; un **Risk Engine déterministe** conserve l'autorité finale et reste le
seul composant autorisé à créer un `ExecutionIntent`.

## Référence de développement

État intégré de départ du Batch 18.2 :

```text
repository : Ax-07/AI-Spot-Trader
branche    : main
HEAD       : e158ea71d9f7cdf010d98d41be1968440c640a53
commit     : feat: add bounded read-only market research tools
```

Le **Batch 18.1 est intégré** sur ce HEAD. Le Batch 18.2 livré ici est un **patch proposé non
intégré** tant que sa validation locale, son commit et son push ne sont pas confirmés.

## Principes

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- PAPER uniquement ;
- SPOT sans short, levier ni marge ;
- PERPETUAL linéaire avec LONG/SHORT, marge ISOLATED et protections déterministes ;
- le LLM ne choisit ni le levier ni `reduce_only` ;
- aucune sortie LLM et aucun tool ne déclenche directement un ordre ;
- frais, spread, slippage et funding restent pris en compte ;
- toutes les décisions, recherches et sélections causales sont auditables ;
- aucune clé Kraken privée n'est nécessaire ;
- aucun secret dans prompts, logs ou Git ;
- aucun look-ahead ;
- backend indépendant du frontend ;
- cible +4 %/jour = objectif expérimental, jamais une garantie.

Principe : **l'Agent cherche, sélectionne et propose ; Risk autorise, modifie ou refuse.**

## Architecture Batch 18.2

```text
PortfolioState complet
        |
        v
MarketSelectionInput
        |
        v
même Agent stratégique
   |        \
   |         +--> list_markets / get_market_snapshot (read-only)
   |                         |
   +-------------------------+
        |
        v
MarketSelection explicite
(symbol + market_type + rationale + traces + digest)
        |
        v
validation de l'univers PAPER exécutable
        |
        v
RoutedExecutableMarketDataSource
        |
        +--> source SPOT d'exécution
        |
        +--> source PERPETUAL d'exécution
        |
        v
MarketState canonique exact du marché sélectionné
        |
        v
AgentInput + même Agent
        |
        v
BUY / SELL / HOLD
        |
        v
Risk Engine -> ExecutionIntent éventuel -> PaperBroker
```

Il n'existe pas de second Agent, scanner, ranking, `opportunity score` ou présélection
algorithmique. Le code déterministe vérifie uniquement qu'un choix de l'Agent est techniquement
et réglementairement représentable par le runtime.

## Univers exécutable typé

Le Batch 18.2 ajoute :

```text
AI_SPOT_TRADER_PAPER_EXECUTABLE_MARKETS
```

Format :

```text
["SPOT:BTC/USD", "SPOT:ETH/USD", "PERPETUAL:SOL/USD"]
```

`paper_symbol + paper_market_type` restent le **bootstrap de compatibilité** et doivent appartenir
à cet univers lorsqu'il est configuré. Ils ne fixent plus le marché de chaque cycle.

Contraintes actuelles :

- uniquement `SPOT` et `PERPETUAL` linéaire ;
- `FUTURE` daté reste découvrable mais non exécutable ;
- chaque symbole exécutable doit rester présent dans `risk_allowed_pairs` ;
- tous les marchés d'un même runtime utilisent le même actif de règlement/quote ;
- la présence d'un instrument dans Kraken ou dans `list_markets` ne l'autorise jamais à elle seule.

## Recherche vs exécution

Les sources Kraken de **recherche** restent distinctes des sources de **trading/exécution**.
Une recherche Derivatives n'a aucun `market_sink` et ne peut donc ni marquer le ledger, ni
accumuler du funding, ni modifier le portefeuille.

Seule l'acquisition du marché finalement sélectionné passe par le routeur d'exécution. Pour un
PERPETUAL, cette acquisition peut mettre à jour le mark/funding d'une position déjà ouverte ; le
`PortfolioState` final fourni à l'Agent est capturé ensuite.

## Causalité et audit

Le journal permet de reconstruire :

```text
cycle
-> MarketSelectionInput
-> AgentToolTrace(s)
-> MarketSelection
-> MarketState exécutable
-> AgentInput final
-> DecisionCandidate
-> RiskAssessment
-> ExecutionIntent éventuel
-> Fill éventuel
```

Une panne après sélection mais avant décision finale conserve la sélection et ses traces.
Le digest du cycle inclut ces artefacts. Le résumé `/api/v1/cycles` expose aussi le `symbol` et le
`market_type` sélectionnés lorsqu'une décision n'existe pas encore.

## `paper_runs` multi-marchés

La migration `0004_multi_market_selection` ajoute un univers durable typé :

```text
paper_runs.execution_universe_payload
```

Les anciens runs singleton sont automatiquement backfillés. Pour un nouveau run réellement
multi-marché :

```text
paper_runs.symbol      = NULL
paper_runs.market_type = NULL
```

Aucun faux `symbol="MULTI"` ou `market_type="MULTI"` n'est inventé. L'API `/api/v1/paper-runs`
expose `execution_universe` et conserve les champs historiques uniquement pour un singleton réel.

## Analytics multi-marchés

`paper-analytics-v3` valorise les positions SPOT détenues à partir du **dernier mark SPOT causal
durable** connu pour chaque actif. Aucun prix futur ou prix courant hors journal n'est injecté.
Les positions Derivatives continuent d'utiliser leurs marks/P&L durables dans `PortfolioState`.

Si un actif détenu ne possède aucun mark causal disponible, l'analytics échoue explicitement au
lieu d'inventer une valorisation.

## Migrations PostgreSQL

Après extraction du patch à la racine :

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Chaîne attendue :

```text
0001_audit_journal
-> 0002_paper_runs
-> 0003_agent_tool_traces
-> 0004_multi_market_selection
```

Le downgrade de `0004` refuse de s'exécuter si des runs multi-marchés existent, car les anciennes
colonnes singleton ne pourraient pas les représenter honnêtement.

## Validation du patch 18.2

Exécuté par ChatGPT dans l'environnement de livraison :

```text
40 tests ciblés Batch 18.2 : passés
python -m compileall code/tests/migration : OK
```

La couche SQL async n'a pas pu être exécutée ici : `aiosqlite` n'est pas installé et l'environnement
n'a pas d'accès réseau pour l'ajouter. Ruff, mypy, la suite complète du repository et Alembic sur
votre PostgreSQL restent donc à exécuter localement.

Commandes minimales :

```powershell
backend\.venv\Scripts\python.exe -m pytest backend
backend\.venv\Scripts\ruff.exe check backend
backend\.venv\Scripts\mypy.exe --config-file backend\pyproject.toml backend\src
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
cd ..
git diff --check
git status --short
```

## Sécurité / LIVE

LIVE reste hors périmètre. Il nécessitera un batch séparé avec permissions minimales sans retrait,
idempotence, réconciliation, recovery et activation explicite.

## Documentation

- `docs/00_ETAT_ACTUEL.md` : reprise courte ;
- `docs/01_PROJECT_MASTER.md` : spécification principale ;
- `docs/02_ARCHITECTURE_TECHNIQUE.md` : architecture ;
- `docs/03_AGENT_TRADING_RISK.md` : responsabilités Agent/Risk ;
- `docs/09_ROADMAP_DEVELOPPEMENT.md` : roadmap ;
- `docs/10_DECISIONS_ET_CHANGELOG.md` : décisions et changelog.
