# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub intégré : `e19255df2ff0f2d432034808abeacca88832d403`
- Commit : `feat: add causal executable market selection`
- Batch 18.2 : **intégré** sur ce HEAD.
- Prompt stratégique : `agent-strategy-v4`.

## État intégré après Batch 18.2

Le **même Agent stratégique** sélectionne un marché exécutable dans l'univers PAPER typé, puis
reçoit le `MarketState` canonique exact de ce marché avant de produire `BUY`, `SELL` ou `HOLD`.

Sont intégrés notamment :

- `ExecutableMarket`, `MarketSelectionInput` et `MarketSelection` durable ;
- `select_market()` puis acquisition causale du marché choisi ;
- routeur SPOT/PERPETUAL strict, avec refus FUTURE/inverse/hors univers ;
- `AI_SPOT_TRADER_PAPER_EXECUTABLE_MARKETS` ;
- migration `0004_multi_market_selection` ;
- `paper_runs.execution_universe_payload` sans faux marqueur `MULTI` ;
- persistance/API de la sélection même en cas d'échec avant décision ;
- analytics `paper-analytics-v3` avec marks SPOT causaux par actif.

## Frontières conservées

- un seul Agent IA ; Kraken ; PAPER uniquement ;
- SPOT sans short, levier ni marge ;
- PERPETUAL linéaire seulement lorsqu'il est supporté par le domaine actuel, marge ISOLATED ;
- aucune présélection algorithmique stratégique, aucun scanner/ranking/opportunity score ;
- Risk seul crée `ExecutionIntent`, choisit levier effectif et `reduce_only` ;
- aucun tool -> Broker/Risk ; aucun LLM -> Broker ;
- sources research strictement distinctes des sources execution ;
- causalité/no-look-ahead ; décisions, HOLD et sélections auditables ;
- LIVE séparé et ultérieur.

Principe : **l'Agent cherche, sélectionne et propose ; le Risk Engine autorise, modifie ou refuse.**

## Validation confirmée avant intégration

```text
pytest backend : 447 passed, 2 warnings
ruff check backend : OK
mypy backend/src : OK, 79 source files
Alembic 0004 sur PostgreSQL : OK
git diff --check : OK hors warnings LF/CRLF
```

Les deux warnings Starlette/AnyIO sont non bloquants.

Non confirmé : smoke PAPER multi-marchés / cross-symbol réel.

## Suite à auditer

Candidats sans décision d'architecture à ce stade : smoke multi-marchés, protocole expérimental
versionné Agent/tools/sélection, recovery durable du ledger PAPER multi-actifs, enrichissement
mesuré des données de recherche et campagnes Luna/Sol multi-marchés.
