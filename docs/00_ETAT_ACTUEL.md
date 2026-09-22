# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub intégré : `4042e0b0e6394de788009229e3dae5924cd732d7`
- Commit : `fix: support nested Kraken derivative margin schedules`
- Batch 18.3 : **intégré** sur ce HEAD après validation comportementale PAPER.
- Prompt stratégique : `agent-strategy-v4`.

## État intégré

Le **même Agent stratégique** sélectionne un marché dans l'univers PAPER typé, puis reçoit le
`MarketState` canonique exact de ce marché avant `BUY`, `SELL` ou `HOLD`.

Le chemin intégré supporte :

- univers exécutable `SPOT` + `PERPETUAL` linéaire ;
- recherche read-only distincte des sources d'exécution ;
- sélection causale durable puis reacquisition du marché exact ;
- Risk autorité finale, PaperBroker uniquement après `ExecutionIntent` ;
- journal/API/analytics multi-marchés ;
- parser Kraken Derivatives public compatible avec les `marginSchedules` directs ou imbriqués,
  toujours fail-closed et conservateur sur les marges publiques.

## Validation Batch 18.3

```text
pytest backend : 449 passed, 2 warnings
ruff check backend : OK
mypy backend/src : OK, 79 source files
git diff --check : OK hors warnings LF/CRLF avant commit
```

Smokes réels confirmés :

- cross-symbol SPOT ;
- univers mixte `SPOT:BTC/USD + PERPETUAL:ETH/USD` chargé et recherché ;
- plusieurs cycles mixtes SPOT `COMPLETED` ;
- `PERPETUAL:ETH/USD` validé séparément jusqu'à `MarketState -> HOLD -> Risk ALLOW` ;
- catalogue Derivatives public parsé : 296 instruments lors du smoke.

Non revendiqué : aucune sélection PERPETUAL spontanée depuis l'univers mixte et aucun fill réel
pendant ces smokes. Un timeout SPOT `MARKET` et un `LLMTransportError` de sélection ont été
observés isolément puis non reproduits durablement.

## Frontières conservées

- un seul Agent IA ; Kraken ; PAPER uniquement ;
- SPOT sans short, levier ni marge ;
- PERPETUAL linéaire seulement, marge ISOLATED et protections déterministes ;
- aucune présélection algorithmique stratégique, aucun scanner/ranking/opportunity score ;
- aucun tool -> Broker/Risk ; aucun LLM -> Broker ;
- causalité/no-look-ahead ; décisions, HOLD et sélections auditables ;
- LIVE séparé et ultérieur.

Principe : **l'Agent cherche, sélectionne et propose ; le Risk Engine autorise, modifie ou refuse.**

## Suite à auditer

Candidats sans priorité décidée : protocole expérimental versionné Agent/tools/sélection,
recovery durable du ledger PAPER multi-actifs, enrichissement mesuré des données de recherche,
campagnes Luna/Sol multi-marchés et robustesse réseau/observabilité des erreurs transitoires.
