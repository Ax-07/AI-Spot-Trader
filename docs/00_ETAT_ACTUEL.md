# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- Référence fonctionnelle Batch 16.5 : `595bd2c8b4311ac255db927515207f10875b1505` (`feat: enrich perpetual paper market context`).
- Clôture documentaire Batch 16.5 intégrée sur `main` : `84272713b66439a16e7769da83eccc1514aa64f7` (`docs: finalize Batch 16.5 integration`).
- Validation comportementale Batch 16.6 intégrée sur `main` : `251d530ad12951605068c1c8eb8cbeb313c36b49` (`docs: validate Batch 16.6 Luna perpetual behavior`).
- Prompt stratégique `agent-strategy-v4` en français intégré sur `main` : `bacf29c83b4f29477ee9e35a1a65756a866ba250` (`feat: localize agent strategy prompt to French`).

## Batch 16.5 — Contexte PERPETUAL intégré

Le contexte PERPETUAL réutilise le pipeline canonique `MarketStateBuilder` avec bougies publiques Kraken Futures Charts `mark` en `1m`, fenêtres descriptives 5 min / 30 min, rendement, range, volatilité réalisée et fraîcheur sans look-ahead. Mark/index/funding restent dans `DerivativeMarketContext`. Aucun indicateur ne produit directement BUY/SELL/HOLD.

Cycle de référence Batch 16.5 :

- `paper_run_id = 8bbfe6a5-a5d5-4c32-96dc-eb9c5e4113d2` ;
- `cycle_id = c097f3fc-4954-4985-a364-f6ffe99b24e6` ;
- `COMPLETED`, contexte non nul ;
- fenêtres 5 min / 30 min complètes avec 6 / 31 observations ;
- fraîcheur observée `0.773542 s` ;
- mark/index/funding présents.

## Batch 16.6 — Validation comportementale Luna PERPETUAL PAPER

Run propre via composition normale, sans harness ni décision forcée :

- `paper_run_id = c9443243-57ca-43de-9356-adc1e6fe3226` ;
- `BTC/USD / PF_XBTUSD`, `PERPETUAL`, `ISOLATED`, levier déterministe `1x` ;
- capital `1000 USD`, agressivité `2`, GPT-5.6 Luna ;
- 8 cycles `COMPLETED`, 0 `FAILED` ;
- 8/8 `AgentInput.market_state.context != null` ;
- fenêtres 5 min / 30 min complètes sur les 8 cycles avec 6 / 31 observations ;
- causalité vérifiée sur les 8 cycles ; fraîcheur observée entre `1.021449 s` et `1.110151 s` ;
- 8 décisions Luna naturelles `HOLD` ;
- rationales cohérentes avec les rendements 5m/30m, l'absence de position et le funding positif réellement fournis ; aucun indicateur absent n'a été observé dans les rationales ;
- 8 Risk `ALLOW`, 0 `ExecutionIntent`, 0 fill, 0 trade ;
- analytics : capital final `1000 USD`, P&L brut/net `0`, frais/spread/slippage/funding `0`, exposition `0`, drawdown `0` ;
- isolation confirmée : 8 cycles propres au run, 0 `cycle_id` commun avec le run Batch 16.5 ;
- run clôturé proprement : `started_at = 2026-09-22 08:35:12.561639 UTC`, `ended_at = 2026-09-22 08:41:03.924351 UTC`.

Aucun BUY/SELL naturel n'est apparu. Ce n'est pas un échec du batch et aucune modification du prompt, de l'agressivité ou de Risk n'est justifiée pour provoquer un trade.

## Prompt stratégique courant

Le prompt Agent courant est `agent-strategy-v4`.

- instructions humaines en français ;
- valeurs contractuelles techniques inchangées : `BUY`, `SELL`, `HOLD`, `SPOT`, `PERPETUAL`, `FUTURE`, `LONG`, `SHORT` ;
- `rationale` demandé en français ;
- même `OpenAIDecisionProvider`, même schéma structuré, mêmes frontières Agent -> Risk -> Broker ;
- aucune permission supplémentaire donnée au LLM.

La localisation v4 a été validée localement par `pytest backend/tests/test_agent_provider.py` (`30 passed`) et Ruff ciblé (`All checks passed!`).

## Invariants

Un seul Agent stratégique. PAPER uniquement. Risk garde l'autorité finale. Levier `1x` et `ISOLATED` déterministes pour ce protocole. Aucun LLM -> Broker direct. Aucun look-ahead. Aucun secret ni clé Kraken privée nécessaire. HOLD reste un résultat stratégique valide.

## Validation

Dernière validation complète du code : Batch 16.5.

```text
pytest backend                                  : 357 passed, 2 warnings externes
ruff check backend                             : All checks passed
mypy --config-file backend\pyproject.toml ... : Success, 107 source files
git diff --check                               : aucune erreur ; avertissements LF -> CRLF uniquement
```

Validation ciblée postérieure pour `agent-strategy-v4` :

```text
pytest backend/tests/test_agent_provider.py     : 30 passed
ruff check prompt.py + test_agent_provider.py  : All checks passed
git diff --check                               : aucune erreur ; avertissements LF -> CRLF uniquement
```

Prochaine étape : Batch 17 — Robustesse Derivatives, dans une nouvelle discussion et sans forcer BUY/SELL à partir du résultat 16.6.
