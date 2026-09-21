# 10 — Décisions et changelog

> Ce document consolide les décisions courantes. L'historique détaillé antérieur au Batch 16 reste disponible dans l'historique Git jusqu'au HEAD `c2e21f9b5b47086ea8dad336cc80ff15afa27ba0`.

## Principes historiques conservés

Les décisions intégrées des Batches 00 à 15.3 restent valides lorsqu'elles ne sont pas explicitement supersédées ici : agent unique, PAPER d'abord, Risk autorité finale, pas d'exécution directe LLM, audit durable, backend indépendant du frontend, no-look-ahead, contexte marché descriptif, chat opérateur latéral/non mutant.

Les anciennes mentions **SPOT uniquement / aucun future-perpetual** sont supersédées par les décisions Batch 16 ci-dessous uniquement pour le domaine Derivatives. Les règles SPOT correspondantes restent inchangées.

## Décisions Batch 16

### ADR-090 — Le projet devient SPOT + Kraken Derivatives
**ACCEPTÉE.** Le backend canonique peut représenter `SPOT`, `PERPETUAL` et `FUTURE`. SPOT conserve ses invariants historiques ; LONG/SHORT/levier/marge n'existent que dans le domaine dérivés.

### ADR-091 — Un seul pipeline et un seul agent
**ACCEPTÉE.** Aucun moteur dérivés parallèle. Le flux reste `Market -> Agent -> DecisionCandidate -> Risk -> ExecutionIntent -> Paper Broker`.

### ADR-092 — Perpetual linéaire uniquement pour la première exécution PAPER
**ACCEPTÉE.** Les contrats `PERPETUAL + LINEAR` sont exécutables. Les contrats `INVERSE` et futures datés sont découverts/représentés mais refusés à l'exécution.

### ADR-093 — Marge ISOLATED d'abord ; CROSS représenté mais fail-closed
**ACCEPTÉE.** `CROSS` existe dans le domaine mais la composition Batch 16 le refuse.

### ADR-094 — Levier déterministe, jamais choisi par le LLM
**ACCEPTÉE.** Le levier PAPER est un paramètre de configuration/Risk, par défaut `1x`.

### ADR-095 — Anti-retournement et reduce-only produits par Risk
**ACCEPTÉE.** Une action opposée réduit/ferme la position ; un dépassement ne peut pas la retourner silencieusement.

### ADR-096 — Funding et mark-to-market avant AgentInput
**ACCEPTÉE.** Le market source Derivatives marque la position et accumule le funding dans le ledger avant le snapshot portefeuille.

### ADR-097 — Modèle de liquidation conservateur
**ACCEPTÉE.** Le ledger calcule un prix de liquidation isolée estimé et Risk impose un buffer par rapport à la maintenance margin.

### ADR-098 — Kraken Derivatives public séparé de Kraken Spot
**ACCEPTÉE.** Intégration publique dédiée via `https://futures.kraken.com/derivatives/api/v3`. Aucun endpoint privé d'ordre, aucune clé Kraken et aucun LIVE.

### ADR-099 — Analytics combinés SPOT + Derivatives sans migration
**ACCEPTÉE.** Les positions dérivés sont persistées dans les payloads JSON existants ; les analytics ajoutent marge/unrealized/funding/exposition dérivés.

### ADR-100 — Prompt Agent `agent-strategy-v3`
**ACCEPTÉE.** Le prompt explique explicitement les sémantiques SPOT/PERPETUAL, LONG/SHORT, marge et levier tout en conservant `BUY/SELL/HOLD`.

## Changelog — 2026-09-21 — Batch 16 Kraken Derivatives PAPER

**État : intégré sur GitHub `main` au commit `06e3185c8a8c638263427842ab6591a2397810e0` (`feat: add Kraken derivatives paper trading`).**

Changements principaux : nouveaux enums/contrats dérivés, client public Kraken Derivatives, PaperPortfolioLedger LONG/SHORT, PaperBroker perpetual linéaire/reduce-only, Risk Engine levier/marge/notionnel/exposition/liquidation/anti-reversal, composition runtime SPOT/PERPETUAL, configuration étendue, prompt `agent-strategy-v3`, API/analytics étendus et tests dérivés.

Validation locale finale confirmée le 21 septembre 2026 :

```text
pytest            : 338 passés, 2 warnings externes
ruff check .       : All checks passed
mypy .             : Success: no issues found in 101 source files
git diff --check   : aucune erreur, warnings LF -> CRLF uniquement
```

Tests ciblés exécutés par ChatGPT : **23 passés** ; `compileall` : **réussi**.

## LIVE

Aucune décision de passage LIVE n'est incluse. LIVE restera un batch séparé avec clés sans droit de retrait, permissions minimales, idempotence, réconciliation et activation explicite.
