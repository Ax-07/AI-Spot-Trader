# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié après push du Batch 19.6B, avant cette synchronisation documentaire :
  `b5a26f77d1951f8eb39df30b5b6f3b5b81f4d585`
  (`docs: finalize Batch 19.6B integration state`).
- Référence fonctionnelle intégrée du Batch 19.6A :
  `3c53af3bdb1ef53c574e26afe9b6178a374d9f06`
  (`feat: add backend candle cache and streaming`).
- Référence fonctionnelle intégrée du Batch 19.6B :
  `a446628918a614d2ae0ac3b55243881aad5ef410`
  (`feat: add cockpit market charts and trade markers`).
- Batch 19.6B : **intégré sur GitHub `main`** ; validation locale complète confirmée avant push.

## État fonctionnel

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- `NORMAL` / `MANAGEMENT`, discovery dynamique et watchlist auditée sont intégrés ;
- explicabilité 19.5 : contexte/discovery, sélection marché, Agent, Risk et exécution PAPER depuis les faits persistés ;
- backend candles 19.6A : historique, cache process-local, recovery et WebSocket cockpit partagé ;
- frontend 19.6B : vue Marchés, Lightweight Charts, timeframes backend, cache client borné, reconnexion et markers issus uniquement des fills persistés ;
- aucune connexion frontend directe à Kraken, aucun calcul Risk/P&L stratégique parallèle et aucune causalité inventée.

## Validation Batch 19.6B

Validation opérateur locale communiquée :

- `pnpm test` : **6/6 tests passés** ;
- `pnpm lint` : **passé sans erreur ni warning** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé** ;
- `git diff --check` : **aucune erreur de whitespace** ; avertissements LF -> CRLF uniquement ;
- arbre de travail propre après le commit fonctionnel `a446628`.

Le warning Node `MODULE_TYPELESS_PACKAGE_JSON` du test runner reste non bloquant et ne justifie pas à lui seul l'ajout global de `"type": "module"`.

## Prochaine priorité

1. démarrer le prochain batch dans une nouvelle discussion avec resynchronisation obligatoire sur GitHub `main` ;
2. revérifier le HEAD GitHub réel et relire ce document ;
3. poursuivre uniquement depuis cet état intégré, en distinguant toute modification locale ultérieure.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, lire ce document et distinguer clairement état intégré GitHub, modifications locales et patch proposé.
