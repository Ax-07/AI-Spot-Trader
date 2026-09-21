# 10 — Décisions et changelog

> Ce document consolide les décisions courantes. L'historique détaillé antérieur au Batch 16 reste disponible dans l'historique Git jusqu'au HEAD `c2e21f9b5b47086ea8dad336cc80ff15afa27ba0`.

## Principes historiques conservés

Les décisions intégrées des Batches 00 à 15.3 restent valides lorsqu'elles ne sont pas explicitement supersédées ici : agent unique, PAPER d'abord, Risk autorité finale, pas d'exécution directe LLM, audit durable, backend indépendant du frontend, no-look-ahead, contexte marché descriptif, chat opérateur latéral/non mutant.

Les anciennes mentions **SPOT uniquement / aucun future-perpetual** sont supersédées par les décisions Batch 16 ci-dessous uniquement pour le domaine Derivatives. Les règles SPOT correspondantes restent inchangées.

## Décisions Batch 16

### ADR-090 — Le projet devient SPOT + Kraken Derivatives

**ACCEPTÉE dans le patch Batch 16.** Le backend canonique peut représenter `SPOT`, `PERPETUAL` et `FUTURE`. SPOT conserve ses invariants historiques ; LONG/SHORT/levier/marge n'existent que dans le domaine dérivés.

### ADR-091 — Un seul pipeline et un seul agent

**ACCEPTÉE.** Aucun moteur dérivés parallèle. Le flux reste `Market -> Agent -> DecisionCandidate -> Risk -> ExecutionIntent -> Paper Broker`. L'agent garde `BUY/SELL/HOLD` et reçoit le type de marché dans `AgentInput`.

### ADR-092 — Perpetual linéaire uniquement pour la première exécution PAPER

**ACCEPTÉE.** Les contrats `PERPETUAL + LINEAR` sont exécutables. Les contracts `INVERSE` et les futures datés sont découverts/représentés mais refusés à l'exécution afin d'éviter d'utiliser des formules P&L/marge incorrectes.

### ADR-093 — Marge ISOLATED d'abord ; CROSS représenté mais fail-closed

**ACCEPTÉE.** La marge isolée permet un modèle déterministe et borné par position. `CROSS` existe dans le domaine pour éviter un cul-de-sac architectural mais la composition Batch 16 le refuse.

### ADR-094 — Levier déterministe, jamais choisi par le LLM

**ACCEPTÉE.** Le levier PAPER est un paramètre de configuration/Risk, par défaut `1x`. Risk applique son plafond interne et la limite dérivée des métadonnées instrument. L'agent ne peut ni demander ni augmenter le levier.

### ADR-095 — Anti-retournement et reduce-only produits par Risk

**ACCEPTÉE.** Une action opposée à une position existante devient une réduction/fermeture. Un ordre plus grand que la position ne peut pas la retourner silencieusement. Risk peut réduire la quantité si la politique le permet ; sinon il rejette.

### ADR-096 — Funding et mark-to-market avant AgentInput

**ACCEPTÉE.** Le market source Derivatives marque la position et accumule le funding dans le ledger avant que `TradingCycleRunner` ne prenne le snapshot portefeuille. HOLD peut donc refléter mark/funding sans créer d'exécution.

### ADR-097 — Modèle de liquidation conservateur

**ACCEPTÉE.** Le ledger calcule un prix de liquidation isolée estimé et Risk impose un buffer par rapport à la maintenance margin. Batch 16 ne prétend pas reproduire l'intégralité du moteur privé Kraken.

### ADR-098 — Kraken Derivatives public séparé de Kraken Spot

**ACCEPTÉE.** Une intégration publique dédiée utilise `https://futures.kraken.com/derivatives/api/v3`. Aucun endpoint privé d'ordre, aucune clé Kraken et aucun LIVE ne sont introduits.

### ADR-099 — Analytics combinés SPOT + Derivatives sans migration

**ACCEPTÉE.** Les positions dérivés sont persistées dans les payloads JSON existants. Les analytics ajoutent marge/unrealized/funding/exposition dérivés. Les fills SPOT historiques gardent leurs defaults et leur replay existant.

### ADR-100 — Prompt Agent `agent-strategy-v3`

**ACCEPTÉE.** Le prompt explique explicitement les sémantiques SPOT/PERPETUAL, LONG/SHORT, marge et levier tout en conservant la sortie structurée `BUY/SELL/HOLD`. Le LLM n'émet ni `reduce_only` ni levier.

## Changelog — 2026-09-21 — Batch 16 Kraken Derivatives PAPER

**État : patch local proposé depuis le HEAD GitHub `c2e21f9b5b47086ea8dad336cc80ff15afa27ba0`; non intégré tant que la validation locale utilisateur n'est pas terminée.**

Changements principaux :

- nouveaux enums `MarketType`, `DerivativeContractKind`, `PositionSide`, `MarginMode` ;
- nouveaux contrats `DerivativeInstrument`, `DerivativeMarketContext`, `DerivativePosition` ;
- enrichissement rétrocompatible de `MarketState`, `PortfolioState`, `DecisionCandidate`, `ExecutionIntent`, `Fill` ;
- client public Kraken Derivatives, parsing instruments/tickers et normalisation XBT/BTC ;
- PaperPortfolioLedger : LONG/SHORT, prix moyen, P&L, marge, funding, liquidation estimée ;
- PaperBroker : perpetual linéaire et reduce-only ;
- Risk Engine : levier, marge, notionnel position, exposition totale, buffer liquidation, anti-reversal ;
- composition runtime sélectionnable SPOT/PERPETUAL ;
- configuration et `.env.example` étendus ;
- prompt stratégique `agent-strategy-v3` ;
- API schemas et analytics PAPER étendus ;
- tests ciblés dérivés ajoutés.

Validation exécutée par ChatGPT :

```text
pytest ciblé Batch 16 : 23 passed
python -m compileall   : réussi
```

Non exécuté dans l'environnement de reconstruction : Ruff, mypy, suite backend complète, frontend lint/typecheck/build. Ces validations doivent être réalisées localement avant intégration.

## LIVE

Aucune décision de passage LIVE n'est incluse. LIVE restera un batch séparé avec clés sans droit de retrait, permissions minimales, idempotence, réconciliation et activation explicite.
