# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub réel audité au démarrage du Batch 18.5 : `5cc2e2897d9a1dccba325f8a543b208360c6120d`
- Commit HEAD : `docs: record batch 18.3 behavioral validation`
- Dernier commit contenant du code validé avant le Batch 18.5 : `4042e0b0e6394de788009229e3dae5924cd732d7`
- Commit code : `fix: support nested Kraken derivative margin schedules`
- Batch 18.3 : **intégré** ; Batch 18.5 : **patch proposé, non intégré tant qu'il n'est pas validé/commité/poussé**.
- Prompt stratégique : `agent-strategy-v4`.

La référence `4042e0b...` reste utile comme dernier HEAD **code** validé de 18.3, mais ne doit plus
être présentée comme le HEAD GitHub courant puisque le commit documentaire `5cc2e289...` lui est
postérieur.

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

## Patch Batch 18.5 — protocole expérimental v3

Le patch introduit `paper-experiment-v3` pour les futures expériences multi-marchés. Cette identité
versionne le comportement déjà existant sans modifier la stratégie :

- univers exécutable exact `ExecutableMarket(symbol, market_type)` ;
- version du protocole de sélection causale en deux phases ;
- tools présents pendant la sélection et absents de la décision finale ;
- digest canonique des définitions OpenAI effectivement exposées par `ReadOnlyToolRegistry` ;
- bornes effectives : nombre maximal de calls, timeout, taille maximale des résultats et maximum
  de `list_markets.limit` ;
- inclusion de ces facteurs dans le `experiment_group_digest`, en continuant d'exclure uniquement
  `llm_model` et `replicate_index` pour la comparaison Luna/Sol.

`paper-experiment-v1` et `paper-experiment-v2` restent lisibles et leurs payloads/digests
historiques ne sont pas réinterprétés. `experiment_manifest=None` reste le chemin PAPER normal.
Aucune migration PostgreSQL n'est requise : les manifestes restent persistés dans les payloads JSON
existants.

## Validation intégrée Batch 18.3

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

Après intégration éventuelle de 18.5 : recovery durable du ledger PAPER multi-actifs, robustesse
réseau/observabilité bornée des erreurs transitoires, enrichissement mesuré des données de
recherche puis campagnes Luna/Sol multi-marchés sous protocole v3. Aucun de ces sujets n'est
implémenté par le Batch 18.5.
