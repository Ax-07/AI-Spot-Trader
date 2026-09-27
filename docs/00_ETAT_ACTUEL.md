# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié le 27 septembre 2026 : `aa404e46c1f05269ac2279507aa746b3af7a965d` (`fix: harden multi-market LLM plan contract`).
- Le Batch 19.13 multi-marchés / multi-décisions et son durcissement du contrat LLM sont donc **intégrés** à GitHub `main`.
- Le présent correctif PERPETUAL est un **patch proposé au-dessus de `aa404e4`, non encore intégré à GitHub**.

## Correctif ciblé PERPETUAL après `aa404e4`

Le commit `aa404e4` a correctement durci le nouveau chemin de planification multi-marchés :

- JSON Schema strict par variante `BUY` / `SELL` / `HOLD` ;
- `BUY` / `SELL` avec quantité strictement positive et `HOLD` avec `proposed_quantity=null` ;
- validation fail-closed, univers causal, détection des doublons et `max_decisions_per_cycle` ;
- diagnostics sans sortie LLM brute et aucun retry LLM silencieux ;
- un seul Agent stratégique ; aucune sortie LLM ne déclenche directement un ordre ;
- Risk Engine déterministe avec autorité finale.

Il a cependant ajouté par erreur un garde-fou `_ensure_spot_only_session()` dans `campaign_composition.py` et des instructions protégées SPOT-only dans `strategy_client.py`. Ce garde-fou provoque l'échec d'activation d'une Session PAPER PERPETUAL, ensuite exposé par l'API Sessions sous `HTTP 503 · Session operation is unavailable`.

Le patch courant retire uniquement cette restriction artificielle et réaligne les instructions stratégiques sur l'architecture déjà canonique :

- `SPOT` autorisé en PAPER ;
- `PERPETUAL` linéaire autorisé en PAPER, avec les règles dérivés et contrôles Risk existants ;
- `FUTURE` daté reste interdit à l'exécution et à la discovery ;
- la discovery dynamique, le multi-market, les plafonds d'exposition, la marge isolée, le levier et les protections de liquidation restent déterministes.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Validation

Baseline fournie par l'opérateur après `aa404e4`, avant ce correctif :

- tests ciblés multi-market : `36 passed` ;
- backend complet : `718 passed, 2 warnings`.

Dans l'environnement ChatGPT, les fichiers Python du présent patch sont vérifiés syntaxiquement. Le checkout complet du repository n'est pas disponible dans cet environnement isolé ; les suites `pytest` post-correctif restent donc à exécuter localement après extraction du ZIP.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer explicitement l'état intégré GitHub, les modifications locales fournies par l'opérateur et tout patch proposé non encore intégré.
