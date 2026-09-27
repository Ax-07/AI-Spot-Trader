# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- Base GitHub vérifiée avant le Batch 19.13 : `18596ac9d4f6554aa4817a9bdb374ab597c2399f` (`fix: harden paper perpetual execution precision`).
- Le correctif PAPER PERPETUAL est donc **intégré** à GitHub `main`.
- Le présent état du repository inclut le Batch 19.13 multi-décisions / multi-marchés, validé avec les résultats ci-dessous.

## État courant du Batch 19.13

- un seul Agent IA stratégique ; au stade décisionnel d'un cycle, un seul appel stratégique produit un plan ordonné ;
- plusieurs décisions `BUY` / `SELL` / `HOLD` peuvent viser des marchés distincts dans le même cycle ;
- `RiskEngine` est exécuté séquentiellement pour chaque décision et chaque décision suivante observe le portefeuille PAPER après les exécutions précédentes ;
- `HOLD` et `REJECT` sont auditables et n'interrompent pas les décisions suivantes ;
- une défaillance technique Risk/Broker fait passer le cycle à `FAILED` et restaure atomiquement le checkpoint PAPER du cycle ;
- persistence d'audit 1:N pour décisions, évaluations Risk et intentions d'exécution ; API et cockpit exposent la trajectoire ordonnée ;
- analytics basés sur les fills/trades économiques réellement exécutés, pas sur le nombre de décisions ;
- `max_decisions_per_cycle` configurable, défaut `6`, limite dure `20` ;
- migration locale : `0006_paper_control_plane -> 0007_multi_decision_cycles` ;
- compatibilité historique conservée pour les anciens cycles et configurations.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

PAPER reste la phase courante. Aucune sortie LLM ne déclenche directement un ordre Kraken. Aucun look-ahead ni rendement n'est garanti.

## Validation locale fournie pour le Batch 19.13

- backend ciblé : `51 passed` ;
- backend complet : `698 passed, 2 warnings` ;
- `alembic upgrade head` : succès sur PostgreSQL réel ;
- frontend : `39 passed` ;
- `pnpm lint` : succès ;
- `pnpm typecheck` : succès ;
- `pnpm build` : succès.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer explicitement l'état intégré GitHub, les modifications locales fournies par l'opérateur et tout patch proposé non encore intégré.
