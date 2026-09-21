# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié au démarrage du Batch 16 : `c2e21f9b5b47086ea8dad336cc80ff15afa27ba0` (`docs: finalize Batch 15.3 integration`).
- Référence fonctionnelle précédente : `d0f6d46b9adb37117051a7a497a8d55075c41d32` (`fix: decouple market context from engine cadence`).
- Le présent Batch 16 est un **patch local proposé**, non intégré à GitHub tant qu'il n'a pas été validé et commité par l'utilisateur.

## Batch 16 — SPOT + Kraken Derivatives en PAPER

Le projet n'est plus conceptuellement limité au SPOT. Le même backend et le même agent stratégique peuvent traiter :

- `SPOT` : règles historiques inchangées, aucun short ni levier ; `SELL` exige une position détenue ;
- `PERPETUAL` Kraken Derivatives : positions `LONG`/`SHORT`, marge isolée, levier déterministe, P&L réalisé/non réalisé, funding, exposition et risque de liquidation ;
- `FUTURE` daté : métadonnées de domaine prévues et découverte possible, mais exécution PAPER volontairement refusée dans ce batch ;
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

## Validation disponible dans le livrable

Exécuté par ChatGPT sur la copie de reconstruction du patch :

```text
pytest ciblé Batch 16 : 23 passés
python -m compileall   : réussi
```

Non exécuté dans l'environnement ChatGPT faute d'outils installés : `ruff` et `mypy`.

La validation complète doit être exécutée sur le dépôt local utilisateur après extraction : suite `pytest`, Ruff, mypy, `git diff --check` et `git status --short`.

## Prochaine étape

Valider le ZIP Batch 16 dans `E:\AI-Spot-Trader`. Si la suite complète passe, commiter/pousser le batch puis lancer un premier smoke test PERPETUAL PAPER avec paramètres conservateurs (`1x`, faible notionnel, limites d'exposition strictes).
