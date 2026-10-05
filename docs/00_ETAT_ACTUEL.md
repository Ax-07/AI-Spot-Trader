# 00 — État actuel

## Référence de reprise — Batch 49.1 préparé

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub audité au démarrage    : 8704eec57de09792d0a51e080fdeb7b2a39d2381
HEAD GitHub                        : docs: mark batch 48 integrated
Batch 48 fonctionnel               : ebb664c — feat: add analytics ranking observability
Clôture documentaire Batch 48      : 8704eec — docs: mark batch 48 integrated
Batch 49.1                         : PATCH PROPOSÉ — NON INTÉGRÉ À GITHUB À LA LIVRAISON
```

Le HEAD GitHub réel a été revérifié au démarrage du Batch 49.1 et correspondait exactement à `8704eec57de09792d0a51e080fdeb7b2a39d2381`.

## Exécution PAPER courante proposée par le Batch 49.1

L'ancien invariant général « exécution SPOT uniquement / aucun short / aucun levier / aucune exécution PERPETUAL » est obsolète pour le runtime PAPER.

Le contrat courant devient :

- un seul Agent IA stratégique ;
- PAPER uniquement ; LIVE reste séparé et indisponible ;
- SPOT exécutable sans short, levier ni marge ;
- PERPETUAL Kraken linéaire exécutable en LONG ou SHORT ;
- FUTURE daté non exécutable ;
- le même `market_type` reste explicite de l'univers Agent jusqu'au Broker ;
- le levier, la marge, `reduce_only`, les caps notionnels/exposition et le buffer liquidation restent déterministes ;
- aucune sortie LLM ne déclenche directement un ordre ;
- le `PaperBroker` reste l'unique broker de ce batch.

Principe inchangé : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Chaîne canonique PERPETUAL PAPER

```text
Agent
-> DecisionCandidate
-> Risk Engine
-> ExecutionIntent
-> PaperBroker
-> DerivativePosition
-> mark-to-market / funding / P&L / liquidation théorique
-> audit
```

L'audit du HEAD confirme que cette infrastructure existait déjà avant 49.1. Le batch ne crée pas de pipeline dérivés parallèle ; il officialise la capacité, aligne le contrat opérateur et ajoute une preuve d'intégration dédiée.

## Sémantique BUY / SELL / HOLD PERPETUAL

```text
sans position + BUY   -> ouverture LONG
sans position + SELL  -> ouverture SHORT
LONG + BUY            -> augmentation LONG
LONG + SELL           -> réduction / fermeture LONG
SHORT + SELL          -> augmentation SHORT
SHORT + BUY            -> réduction / fermeture SHORT
HOLD                   -> aucune exécution
```

Un retournement direct dans un seul `ExecutionIntent` n'est pas autorisé. Une quantité opposée supérieure à la position courante est bornée à la fermeture si la réduction de quantité est autorisée, sinon rejetée. L'ouverture de la direction inverse doit intervenir dans une décision ultérieure, après fermeture effective.

## Levier, marge et valorisation

Le levier exécutable est borné par :

- `paper_derivative_leverage` ;
- `risk_max_derivative_leverage` ;
- la limite de levier/marge de l'instrument Kraken ;
- les caps de position et d'exposition totale ;
- la marge disponible ;
- le buffer de liquidation.

Le ledger PAPER canonique comptabilise marge, P&L réalisé/latent, funding, frais, spread, slippage et liquidation théorique. Le frontend possède déjà les contrôles et surfaces nécessaires pour afficher les paramètres PERP et les positions dérivées ; aucun doublon UI n'est ajouté dans 49.1.

## Radar

Le Market Attention Radar reste déterministe, causal, informatif et read-only. Le Batch 49.1 ne modifie ni son ranking ni sa shortlist et ne raccorde pas encore le Radar à l'univers Agent.

Le raccordement réel `Radar shortlist -> univers Agent SPOT + PERPETUAL` reste le Batch 49.2.

## Patch Batch 49.1

Fichiers fonctionnels du patch :

- `backend/src/ai_spot_trader/chat/prompt.py` : contrat opérateur `operator-chat-v2`, aligné sur SPOT + PERPETUAL PAPER ;
- `backend/tests/test_batch49_1_perpetual_paper.py` : preuve Agent -> Risk -> Broker -> ledger, LONG/SHORT, fermeture, HOLD, conservation du `market_type` et absence de retournement direct.

Documentation active mise à jour :

- `README.md` ;
- `docs/00_ETAT_ACTUEL.md` ;
- `docs/01_PROJECT_MASTER.md` ;
- `docs/09_ROADMAP_DEVELOPPEMENT.md` ;
- `docs/10_DECISIONS_ET_CHANGELOG.md` ;
- `docs/49_1_PERPETUAL_PAPER_EXECUTION.md`.

Les documents historiques des Batches 47/48 conservent leurs invariants d'époque et ne sont pas réécrits rétroactivement.

## Suite

```text
49.2 — Radar shortlist -> univers Agent SPOT + PERPETUAL
49.3 — contexte Radar/Analytics fourni à l'Agent
49.4 — observabilité des décisions et performances PAPER SPOT/PERP
```

Aucun LIVE, aucune authentification Kraken Futures privée et aucun ordre réel Kraken ne font partie de 49.1.
