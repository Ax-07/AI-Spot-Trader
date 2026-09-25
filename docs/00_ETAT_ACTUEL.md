# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub réel vérifié après le push du Batch 19.7 :
  `9dcaf028de81b68ed357d1e6712fa833626353b9`
  (`docs: finalize Batch 19.7 integration state`).
- Référence fonctionnelle intégrée du Batch 19.6A :
  `3c53af3bdb1ef53c574e26afe9b6178a374d9f06`
  (`feat: add backend candle cache and streaming`).
- Référence fonctionnelle intégrée du Batch 19.6B :
  `a446628918a614d2ae0ac3b55243881aad5ef410`
  (`feat: add cockpit market charts and trade markers`).
- Le commit `2d51cb68` reste la synchronisation documentaire post-19.6B ; le Batch 19.7 a ensuite été poussé sur GitHub `main`.
- Batch 19.7 : **intégré sur GitHub `main`**.
- Référence fonctionnelle intégrée Batch 19.7 :
  `8b969b434916d89f6b6aa127c3bac9c27e990966`
  (`feat: add canonical position overlays to market charts`).

## État fonctionnel

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- `NORMAL` / `MANAGEMENT`, discovery dynamique et watchlist auditée sont intégrés ;
- explicabilité 19.5 : contexte/discovery, sélection marché, Agent, Risk et exécution PAPER depuis les faits persistés ;
- backend candles 19.6A : historique, cache process-local borné, recovery et WebSocket cockpit partagé ;
- frontend 19.6B : vue Marchés, Lightweight Charts, timeframes backend, cache client borné, reconnexion et markers issus uniquement des fills persistés ;
- aucune connexion frontend directe à Kraken, aucun calcul Risk/P&L stratégique parallèle et aucune causalité inventée.

## Batch 19.7 — validation intégrée

Le Batch 19.7 ajoute uniquement des overlays de position sur le chart du marché actif :

- `Prix moyen` depuis `average_entry_price` ;
- `Mark backend` depuis `mark_price` ;
- `Liquidation` uniquement pour PERPETUAL et uniquement depuis `liquidation_price` ;
- aucune valeur absente n'est reconstruite ;
- aucune formule de P&L, exposition, liquidation ou prix moyen n'est ajoutée au frontend ;
- les lignes Lightweight Charts sont créées/supprimées proprement lors des changements de marché, de faits portefeuille et de thème ;
- les niveaux très proches restent des faits distincts, avec labels explicites et alignement des labels d'axe ;
- les chandeliers, volumes et markers 19.6B restent inchangés.

Validation opérateur locale communiquée :

- `pnpm test` : **17/17 tests passés** ;
- `pnpm lint` : **passé sans erreur** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé** ;
- `git diff --check` : **aucune erreur de whitespace** ; avertissements LF -> CRLF uniquement ;
- commit fonctionnel intégré : `8b969b434916d89f6b6aa127c3bac9c27e990966` ;
- clôture documentaire intégrée : `9dcaf028de81b68ed357d1e6712fa833626353b9`.

Validation ChatGPT préalable sur le patch : test runner Node de `market-candles.test.mjs`, **17/17 tests passés**.

## Validation intégrée Batch 19.6B

Validation opérateur locale communiquée :

- `pnpm test` : **6/6 tests passés** ;
- `pnpm lint` : **passé sans erreur ni warning** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé** ;
- `git diff --check` : **aucune erreur de whitespace** ; avertissements LF -> CRLF uniquement ;
- arbre de travail propre après le commit fonctionnel `a446628`.

Le warning Node `MODULE_TYPELESS_PACKAGE_JSON` du test runner reste non bloquant et ne justifie pas à lui seul l'ajout global de `"type": "module"`.

## Prochaine priorité

1. conserver séparées les modifications locales hors Batch 19.7 déjà présentes dans l'arbre de travail ;
2. au prochain batch, revérifier le HEAD GitHub réel et choisir le prochain chantier fonctionnel à partir de l'état intégré 19.7.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, lire ce document et distinguer clairement état intégré GitHub, modifications locales et patch proposé.
