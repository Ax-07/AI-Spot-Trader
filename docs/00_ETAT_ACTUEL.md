# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence auditée au démarrage du Batch 15.3

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub intégré audité : `bb1aa047157deb1b62d27de952fa53ec14992f09` (`docs: finalize Batch 15.2 state`).
- Le parent fonctionnel `97d529647179c6769a6bdc528b9d9f5e7c85c119` intègre le Batch 15.2 (`feat: add multi-horizon market context`).
- Le document précédent référençait encore `97d529647179c6769a6bdc528b9d9f5e7c85c119` comme HEAD intégré ; `bb1aa047` ne modifie que la documentation de clôture du Batch 15.2.

## État confirmé avant le patch

Le Batch 15.2 est intégré et validé. Les essais PAPER réels ont confirmé le contexte 5 min / 30 min, mais ont aussi montré que les tickers successifs du moteur étaient conservés dans le même `MarketStateBuilder` que les clôtures OHLC 1 minute.

Conséquence confirmée : le nombre d'observations et les statistiques descriptives pouvaient dépendre de `trading_cadence_seconds`, alors que la cadence moteur ne doit pas modifier l'échantillonnage du contexte marché.

## Batch 15.3 — contexte marché indépendant de la cadence

Patch livré sans moteur Market parallèle :

- `MarketStateBuilder` reste l'unique calculateur des fenêtres descriptives ;
- les observations retenues dans le builder constituent uniquement la série statistique déterministe ;
- le ticker courant devient une observation de snapshot non persistée dans cette série ;
- `MarketState.last_price`, `MarketContext.last_observed_at` et la fraîcheur restent basés sur le ticker courant ;
- un `statistics_as_of` distinct ancre les fenêtres sur la dernière observation statistique causale disponible ;
- le runtime Kraken utilise la dernière clôture OHLC 1 minute retenue comme ancre statistique ;
- sans nouvelle clôture OHLC, des cycles supplémentaires ne changent donc pas artificiellement compte, min/max/range, rendement ou volatilité réalisée ;
- quand une nouvelle clôture devient disponible, elle est ajoutée une seule fois et l'ancre statistique avance naturellement ;
- les clôtures à ou après le ticker courant restent exclues ;
- les fenêtres vides/partielles restent explicites et honnêtes ;
- l'ordre temporel strict des tickers successifs reste contrôlé ;
- aucun indicateur stratégique, score BUY/SELL/HOLD, changement Agent/Risk, Kraken privé ou LIVE.

Le chemin d'exécution reste strictement :

```text
Market -> Agent -> DecisionCandidate -> Risk -> ExecutionIntent -> Paper Broker
```

## Validation exécutée par ChatGPT

Dans un harness ciblé reconstruit depuis le HEAD GitHub audité :

- `pytest` Market State + Kraken Market Data : **38 tests passés** ;
- `compileall` des 4 fichiers Python créés/modifiés : **réussi** ;
- contrôles déterministes ajoutés pour snapshots répétés sans nouvelle bougie, simulation cadence 10 s vs 120 s, ticker courant, fraîcheur, no-look-ahead, fenêtres partielles, ordre strict et snapshots successifs.

Validation locale confirmée le 21 septembre 2026 : **315 tests passés**, 2 warnings externes ; Ruff **All checks passed** ; mypy **94 fichiers sans erreur** ; `git diff --check` sans erreur, avec uniquement les warnings Windows LF -> CRLF.

## Limites conservées

- PAPER/SPOT uniquement ; aucun LIVE, aucune API Kraken privée.
- Chat opérateur strictement conversationnel et non mutant.
- Ledger PAPER toujours mémoire ; recovery/réconciliation après crash différés.
- Aucun exactly-once global ledger/PostgreSQL.
- La granularité OHLC 1 minute reste un mécanisme descriptif de bootstrap et d'échantillonnage fixe, pas une stratégie de trading.

## Prochaine étape

Le Batch 15.3 est validé localement et prêt à être commit/push sur `main`. Après intégration, poursuivre les essais PAPER contrôlés en conservant la comparaison de cadences comme contrôle expérimental. Le LIVE reste séparé et hors périmètre.
