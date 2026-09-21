# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub intégré : `06e3185c8a8c638263427842ab6591a2397810e0` (`feat: add Kraken derivatives paper trading`).
- Référence fonctionnelle précédente : `d0f6d46b9adb37117051a7a497a8d55075c41d32` (`fix: decouple market context from engine cadence`).
- Batch 16 intégré et validé localement le 21 septembre 2026.

## Batch 16 — SPOT + Kraken Derivatives en PAPER

Le projet supporte désormais dans le même backend et avec le même agent stratégique :

- `SPOT` : règles historiques inchangées, aucun short ni levier ; `SELL` exige une position détenue ;
- `PERPETUAL` Kraken Derivatives : positions `LONG`/`SHORT`, marge isolée, levier déterministe, P&L réalisé/non réalisé, funding, exposition et risque de liquidation ;
- `FUTURE` daté : métadonnées de domaine et découverte possibles, mais exécution PAPER refusée dans ce batch ;
- contrats inverses : découverts mais refusés à l'exécution PAPER ; seuls les perpetuals linéaires sont exécutables dans ce premier lot.

Le chemin canonique reste unique :

```text
Market -> Agent -> DecisionCandidate -> Risk -> ExecutionIntent -> Paper Broker
```

L'Agent conserve `BUY / SELL / HOLD`. En dérivés, `SELL` peut ouvrir/augmenter un `SHORT` et `BUY` ouvrir/augmenter un `LONG`. Une action opposée réduit/ferme la position existante ; aucun retournement LONG↔SHORT par dépassement n'est autorisé silencieusement.

## Garde-fous dérivés

- `Risk Engine` conserve l'autorité finale ;
- levier PAPER par défaut : `1x` ;
- plafond de levier interne explicite dans `RiskPolicy` ;
- caps explicites de notionnel par position et d'exposition dérivés totale pour un runtime PERPETUAL ;
- marge `ISOLATED` uniquement dans Batch 16 ; `CROSS` est représenté mais refusé à l'exécution ;
- buffer de liquidation déterministe ;
- coûts PAPER : frais, spread et slippage ;
- funding perpetual comptabilisé au mark-to-market ;
- `reduce_only` produit par Risk, jamais par le LLM ;
- aucune route Kraken privée ni ordre LIVE n'est ajoutée.

## Kraken public

La couche Derivatives publique utilise la base `https://futures.kraken.com/derivatives/api/v3` avec découverte des instruments et tickers publics. Aucun secret Kraken n'est requis pour le Batch 16.

## Validation Batch 16

Validation locale finale confirmée :

```text
pytest            : 338 passés, 2 warnings externes
ruff check .       : All checks passed
mypy .             : Success: no issues found in 101 source files
git diff --check   : aucune erreur, warnings LF -> CRLF uniquement
```

Tests ciblés exécutés par ChatGPT pendant le développement : **23 passés** ; `compileall` : **réussi**.

## Prochaine étape

Lancer dans une nouvelle discussion le Batch 16.1 : premier smoke test Kraken PERPETUAL PAPER avec paramètres conservateurs (`1x`, faible notionnel, limites d'exposition strictes), sans LIVE ni API privée.
