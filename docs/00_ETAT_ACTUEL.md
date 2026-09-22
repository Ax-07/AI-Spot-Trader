# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub courant après intégration du Batch 17 : `25efe21194a61140c426a47c261f74f76799e4ea` (`fix: harden Kraken derivatives paper metadata`).
- Base d’audit du Batch 17 : `b859b5f813e458ca26633406a557462953d39e5e` (`docs: sync current state after agent prompt v4`).
- Référence fonctionnelle Batch 16.5 : `595bd2c8b4311ac255db927515207f10875b1505` (`feat: enrich perpetual paper market context`).
- Validation comportementale Batch 16.6 : `251d530ad12951605068c1c8eb8cbeb313c36b49`.
- Prompt stratégique courant : `agent-strategy-v4`, intégré au commit `bacf29c83b4f29477ee9e35a1a65756a866ba250`.

## Batch 17 — Robustesse Derivatives

**État : intégré sur GitHub `main` au commit `25efe21194a61140c426a47c261f74f76799e4ea` (`fix: harden Kraken derivatives paper metadata`).**

L'audit du support Kraken Derivatives PAPER a confirmé que l'architecture canonique reste saine : un seul pipeline `Market -> Agent -> Risk -> PaperBroker`, ledger multi-position one-way par symbole, Risk globalisant l'exposition dérivés et modèle de liquidation isolée cohérent sous l'hypothèse d'un taux de maintenance constant.

Le périmètre retenu est limité au durcissement de la frontière publique Kraken :

- prise en charge des trois formes publiques de marge `marginLevels`, `retailMarginLevels` et `marginSchedules` ;
- validation fail-closed des entrées de marge, seuils, taux et drapeau `tradeable` ;
- suppression du défaut implicite `contractValueTradePrecision=None -> 1` ;
- cohérence `maxPositionSize >= min_order_quantity` lorsqu'une limite est fournie ;
- `markPrice` devient obligatoire pour le ticker PAPER Derivatives : aucun fallback silencieux vers `last` ;
- rejet fail-closed d'un ticker explicitement `suspended` ou `postOnly`, et des flags malformed/conflictuels.

Le modèle de marge reste volontairement **conservateur et account-agnostic** : tant qu'aucun contexte privé ne permet de prouver le barème applicable au compte, le parser retient les taux publics les plus stricts observés au lieu d'inventer un tier. Le support dynamique des tiers par taille, une liquidation Kraken plus fidèle et la reprise durable du portefeuille PAPER restent des sujets séparés.

Aucun changement Agent, prompt, Risk, Broker, ledger, frontend, API privée Kraken ou LIVE n'est inclus. Aucun enrichissement funding historique / volume / order book n'est ajouté faute de besoin mesuré.

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
- causalité vérifiée ;
- 8 décisions Luna naturelles `HOLD` ;
- 8 Risk `ALLOW`, 0 `ExecutionIntent`, 0 fill, 0 trade ;
- analytics finaux inchangés à `1000 USD`, sans P&L ni exposition ;
- run clôturé proprement.

Aucun BUY/SELL naturel n'est apparu. Ce n'est pas un échec du batch et aucune modification du prompt, de l'agressivité ou de Risk n'est justifiée pour provoquer un trade.

## Invariants

Un seul Agent stratégique. SPOT + Derivatives PAPER. Risk garde l'autorité finale. Levier déterministe, jamais choisi par le LLM. Aucun LLM -> Broker direct. `reduce_only` et anti-reversal restent côté Risk/exécution. Aucun look-ahead. Aucun secret ni clé Kraken privée nécessaire. HOLD reste un résultat stratégique valide. Backend indépendant du frontend.

Le ledger PAPER reste process-local : un redémarrage backend crée un nouveau portefeuille et un nouveau run. Aucune reprise automatique d'un ancien run n'est autorisée tant qu'un recovery durable du ledger n'existe pas.

## Validation du Batch 17

Exécuté par ChatGPT dans l'environnement de livraison :

```text
python -m py_compile derivatives.py + test_kraken_derivatives.py : OK
pytest ciblé isolé test_kraken_derivatives.py                     : 17 passed
harness isolé exécutant le parser production modifié             : OK
```

Validation locale finale confirmée le 22 septembre 2026 :

```text
pytest backend                                  : 371 passed, 2 warnings externes
ruff check backend                             : All checks passed
mypy --config-file backend\pyproject.toml ... : Success, 74 source files
git diff --check                               : aucune erreur ; warnings LF -> CRLF uniquement
```

La première exécution complète a détecté un unique test obsolète dans `backend/tests/test_experiments.py` : le digest figé correspondait encore à `agent-strategy-v3`. Comme `prompt_version` fait partie de l'identité expérimentale et que `agent-strategy-v4` est déjà intégré sur `main`, la valeur attendue a été mise à jour vers `831b95456aa5612d2762e567c0e65579c8776dad753913e40750178c985c3d09`. Le test ciblé a ensuite passé, puis la suite complète a confirmé `371 passed`.

Le Batch 17 est intégré sur GitHub `main` au commit `25efe21194a61140c426a47c261f74f76799e4ea`. Le working tree était propre immédiatement après le push.
