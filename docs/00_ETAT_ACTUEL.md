# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié au démarrage du Batch 16.5 : `0b7303c9e0737f39ac81a5af2517f2f7953c133c` (`docs: finalize Batch 16.3 integration`).
- Le Batch 16.5 est validé localement au 22 septembre 2026, mais reste non intégré tant qu'il n'a pas été commit et push sur `main`.

## Batch 16.4 — Run Agent réel PERPETUAL PAPER confirmé

Premier run réel GPT-5.6 Luna via la composition normale, sans harness ni décision forcée :

- `paper_run_id = 36fe73e0-f52f-4e27-995b-c5c848f46da2` ;
- `BTC/USD / PF_XBTUSD`, perpetual linéaire, `ISOLATED`, levier déterministe `1x` ;
- capital `1000 USD`, agressivité `2` ;
- 4 cycles `COMPLETED`, 0 `FAILED` ;
- 4 décisions Luna naturelles `HOLD` ;
- 4 Risk `ALLOW / HOLD_NO_EXECUTION` ;
- 0 intent, fill ou trade ;
- exposition et P&L finaux nuls ;
- run durablement clôturé avec `ended_at`.

L'audit du vrai `AgentInput` a confirmé que la source Kraken Derivatives fournissait mark/index/funding/instrument mais `market_state.context = null`.

## Batch 16.5 — Contexte PERPETUAL validé localement

Le contexte PERPETUAL réutilise désormais le pipeline canonique `MarketStateBuilder` :

- bougies publiques Kraken Futures Charts `mark` en résolution `1m` ;
- normalisation en `MarketObservation` ;
- fenêtres descriptives 5 min / 30 min déjà utilisées en SPOT ;
- rendement, range, volatilité réalisée et fraîcheur calculés sans look-ahead ;
- seules les bougies clôturées strictement avant le ticker courant entrent dans les statistiques ;
- mark/index/funding/instrument restent inchangés dans `DerivativeMarketContext` ;
- aucune donnée privée Kraken et aucun LIVE ;
- aucun indicateur ne produit directement BUY/SELL/HOLD.

Validation réelle après redémarrage complet du backend :

- `paper_run_id = 8bbfe6a5-a5d5-4c32-96dc-eb9c5e4113d2` ;
- `cycle_id = c097f3fc-4954-4985-a364-f6ffe99b24e6`, statut `COMPLETED` ;
- vrai `AgentInput` PERPETUAL avec `market_state.context != null` ;
- fenêtre 5 min complète : 6 observations, rendement `-0.0008283458359064427`, volatilité réalisée `0.0003195517675049489` ;
- fenêtre 30 min complète : 31 observations, rendement `0.002818639241644028`, volatilité réalisée `0.0004142619704073510` ;
- fraîcheur observée `0.773542 s` ;
- mark/index/funding toujours présents dans `DerivativeMarketContext`.

Le critère principal du Batch 16.5 est donc satisfait. BUY, SELL ou HOLD restent tous des résultats stratégiques valides.

## Invariants

Un seul Agent stratégique. GPT-5.6 Luna pour les tests actuels. PAPER uniquement. Risk garde l'autorité finale. Levier `1x` et `ISOLATED` déterministes. Aucun LLM -> Broker direct. Aucun look-ahead. Aucun secret ni clé Kraken privée nécessaire.

## Validation Batch 16.5 confirmée

```text
pytest backend                                  : 357 passed, 2 warnings externes
ruff check backend                             : All checks passed
mypy --config-file backend\pyproject.toml ... : Success, 107 source files
git diff --check                               : aucune erreur ; avertissements LF -> CRLF uniquement
smoke Luna PERPETUAL PAPER                     : COMPLETED, context 5m/30m non nul
```

Étape restante avant intégration : revue du diff, commit puis push explicite sur `main`.
