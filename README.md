# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **PAPER** sur Kraken,
pilotée par **un seul Agent IA stratégique**. L'Agent choisit le marché à analyser et propose
`BUY`, `SELL` ou `HOLD`; un **Risk Engine déterministe** conserve l'autorité finale et reste le
seul composant autorisé à créer un `ExecutionIntent`.

## Référence de développement

État intégré courant :

```text
repository : Ax-07/AI-Spot-Trader
branche    : main
HEAD       : 4042e0b0e6394de788009229e3dae5924cd732d7
commit     : fix: support nested Kraken derivative margin schedules
```

Les **Batches 18.1, 18.2 et 18.3 sont intégrés** sur `main`. Le Batch 18.3 a validé en PAPER le
pipeline multi-marchés/cross-symbol et la branche PERPETUAL réelle, puis corrigé le parsing
fail-closed des `marginSchedules` publics Kraken lorsqu'ils sont imbriqués par région/profil.

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

## Architecture intégrée — Batch 18.2, validée en Batch 18.3

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

Le Batch 18.2 intégré ajoute :

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

## Kraken Derivatives public

Le parser des instruments accepte les formes publiques observées de `marginLevels`,
`retailMarginLevels` et `marginSchedules`, y compris les schedules imbriqués par région/profil.
Chaque feuille reste validée fail-closed. Comme le runtime public ne connaît pas le tier privé du
compte, il conserve une politique volontairement conservatrice : le taux de marge public le plus
strict disponible est retenu.

## Migrations PostgreSQL

La migration `0004_multi_market_selection` est intégrée. Elle a été appliquée avec succès sur
PostgreSQL lors de la validation locale précédant l'intégration.

Chaîne intégrée :

```text
0001_audit_journal
-> 0002_paper_runs
-> 0003_agent_tool_traces
-> 0004_multi_market_selection
```

Le downgrade de `0004` refuse de s'exécuter si des runs multi-marchés existent, car les anciennes
colonnes singleton ne pourraient pas les représenter honnêtement.

## Validation jusqu'au Batch 18.3

Validation locale confirmée :

```text
pytest backend : 449 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF avant commit
```

Validation comportementale PAPER confirmée :

- sélection cross-symbol SPOT réelle ;
- univers mixte `SPOT:BTC/USD + PERPETUAL:ETH/USD` réellement chargé et recherché ;
- plusieurs cycles mixtes SPOT terminés `COMPLETED` ;
- branche `PERPETUAL:ETH/USD` validée séparément de la sélection au `MarketState`, puis décision
  `HOLD` et Risk `ALLOW` ;
- catalogue public Kraken Derivatives parsé après correction (296 instruments lors du smoke).

Deux incidents ponctuels ont été observés sans reproduction durable : un timeout de reacquisition
SPOT au stage `MARKET` et un `LLMTransportError` au stage `MARKET_SELECTION`.

Non revendiqué : aucune sélection PERPETUAL spontanée depuis l'univers mixte n'a été observée et
aucun fill réel n'a été produit pendant ces smokes (`HOLD` reste une décision valide).

Les deux warnings Starlette/AnyIO sont non bloquants.

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
