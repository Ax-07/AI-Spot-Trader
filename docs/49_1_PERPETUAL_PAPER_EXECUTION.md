# Batch 49.1 — Activation officielle du trading PERPETUAL PAPER par l’Agent

## Statut

```text
Repository              : Ax-07/AI-Spot-Trader
Branche                 : main
Base GitHub auditée     : 8704eec57de09792d0a51e080fdeb7b2a39d2381
Commit de base          : docs: mark batch 48 integrated
Livraison 49.1          : PATCH PROPOSÉ — NON INTÉGRÉ À GITHUB
```

Le HEAD réel de GitHub `main` a été vérifié au démarrage et correspondait à la référence ci-dessus.

## Décision architecturale

L'ancien invariant général :

```text
exécution SPOT uniquement
aucun short / levier / PERPETUAL
```

est obsolète pour le runtime PAPER.

Le contrat courant devient :

```text
PAPER
- SPOT exécutable ;
- PERPETUAL Kraken linéaire exécutable ;
- LONG et SHORT PERPETUAL autorisés sous contrôle du Risk Engine.

LIVE
- indisponible ;
- aucune exécution réelle Kraken ;
- aucune authentification Futures privée ajoutée.
```

Le même Agent IA reste le décideur stratégique.

**L’IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Audit préalable

### Confirmé

Le HEAD `8704eec` possède déjà les briques canoniques suivantes :

- `MarketType.SPOT`, `MarketType.PERPETUAL`, `MarketType.FUTURE` ;
- `ExecutableMarket` typé ;
- `MarketSelectionInput`, `CycleDecisionPlanInput`, `AgentInput`, `DecisionCandidate` et `ExecutionIntent` conservant `market_type` ;
- JSON Schema du plan Agent limité à `SPOT` / `PERPETUAL` ;
- prompt stratégique avec sémantique BUY/LONG et SELL/SHORT PERPETUAL ;
- `RoutedExecutableMarketDataSource` avec routage SPOT / derivatives ;
- validation des PERPETUAL linéaires et rejet des `FUTURE` datés pour l'exécution ;
- `RiskEngine` dérivés avec contrôle du levier, de la marge, du notionnel, de l'exposition totale, du buffer liquidation et de la quantité ;
- `PaperBroker` capable d'exécuter les PERPETUAL linéaires ;
- `DerivativePosition` et ledger isolé LONG/SHORT ;
- funding, P&L réalisé/latent et mark-to-market dérivé ;
- liquidation théorique ;
- paramètres Campaign/Session dérivés ;
- Market Discovery capable de conserver `PERPETUAL` dans `market_types` ;
- frontend capable de configurer le levier/les limites dérivées et d'afficher levier, marge et liquidation d'une position PERPETUAL.

### Obsolète

- `docs/00_ETAT_ACTUEL.md` déclarait encore l'exécution SPOT-only ;
- `docs/09_ROADMAP_DEVELOPPEMENT.md` conservait le même invariant ;
- `docs/10_DECISIONS_ET_CHANGELOG.md` déclarait SPOT-only dans les principes actifs ;
- `docs/01_PROJECT_MASTER.md` conservait SPOT comme invariant d'exécution général ;
- `backend/src/ai_spot_trader/chat/prompt.py` déclarait encore `Trading is SPOT only and PAPER only`.

Les mentions SPOT-only dans les documents historiques 47.x/48.x ne sont pas réécrites rétroactivement lorsqu'elles décrivent fidèlement le périmètre de leur batch.

### Manquant avant 49.1

Il manquait surtout :

- un contrat opérateur cohérent avec le runtime dérivés déjà intégré ;
- une décision courante explicite sur la sémantique de retournement ;
- une preuve d'intégration dédiée montrant qu'une décision PERPETUAL issue du provider Agent traverse Risk et Broker jusqu'au ledger ;
- une documentation active cohérente avec cette capacité.

## Architecture retenue

Aucune nouvelle implémentation dérivés parallèle n'est introduite.

```text
OpenAIMultiMarketDecisionProvider
        ↓
DecisionCandidate(market_type=PERPETUAL)
        ↓
RiskEngine / SequentialCycleRiskEngine
        ↓
ExecutionIntent(
    mode=PAPER,
    market_type=PERPETUAL,
    leverage=<valeur déterministe Risk>,
    reduce_only=<valeur déterministe Risk>
)
        ↓
PaperBroker
        ↓
PaperPortfolioLedger
        ↓
DerivativePosition
        ↓
mark-to-market / funding / P&L / liquidation théorique
        ↓
audit canonique du cycle
```

Le `market_type` reste explicite de bout en bout. `BTC/USD SPOT` et `BTC/USD PERPETUAL` sont deux marchés distincts.

## Sémantique BUY / SELL / HOLD PERPETUAL

La sémantique officielle est :

| État courant | Action Agent | Résultat Risk/Broker |
| --- | --- | --- |
| aucune position | `BUY` | ouvre LONG |
| aucune position | `SELL` | ouvre SHORT |
| LONG | `BUY` | augmente LONG |
| LONG | `SELL` | réduit ou ferme LONG avec `reduce_only` |
| SHORT | `BUY` | réduit ou ferme SHORT avec `reduce_only` |
| SHORT | `SELL` | augmente SHORT |
| LONG ou SHORT | `HOLD` | aucune exécution |

Aucune nouvelle action stratégique n'est ajoutée.

## Retournement de position

### Options auditées

1. **retournement atomique** : un SELL supérieur à un LONG fermerait le LONG puis ouvrirait automatiquement SHORT dans le même intent ;
2. **rejet systématique de tout ordre opposé supérieur à la position** ;
3. **fermeture bornée puis nouvelle décision ultérieure**.

### Décision

L'option 3 est retenue et correspond déjà au comportement canonique :

- une action opposée est `reduce_only` ;
- si la quantité dépasse la position et `risk_allow_quantity_reduction=true`, Risk borne la quantité à la position courante ;
- si cette réduction déterministe n'est pas autorisée, Risk rejette `DERIVATIVE_ACCIDENTAL_REVERSAL` ;
- aucun reliquat ne crée silencieusement une position opposée ;
- une nouvelle exposition opposée doit être proposée après la fermeture effective, dans une décision ultérieure.

Cette règle rend explicites les frais, la marge, le funding, le P&L réalisé et l'état causal du portefeuille entre fermeture et réouverture.

## Levier

L'Agent ne choisit pas le levier.

Le levier utilisé par un `ExecutionIntent` dérivé est déterminé par configuration et borné par le Risk Engine. Les paramètres canoniques restent :

```text
paper_derivative_leverage
risk_max_derivative_leverage
risk_max_derivative_position_notional
risk_max_total_derivative_exposure
risk_derivative_liquidation_buffer_ratio
paper_derivative_margin_mode
```

Le contrôle effectif tient aussi compte des contraintes de marge de l'instrument Kraken. Une sortie LLM ne peut jamais imposer arbitrairement un levier supérieur aux limites déterministes.

## Marge, liquidation, funding et coûts

La chaîne existante reste la source unique de vérité pour :

- marge initiale ;
- maintenance margin ;
- exposition notionnelle ;
- P&L réalisé ;
- P&L latent ;
- funding ;
- liquidation théorique ;
- réduction/fermeture ;
- frais ;
- spread ;
- slippage.

Aucune approximation alternative n'est ajoutée par le Batch 49.1.

## Univers Agent et Market Discovery

Le même Agent peut recevoir des `MarketState` SPOT et PERPETUAL. Le provider du plan stratégique encode `market_type` dans le schéma strict et refuse une décision qui cible un marché hors de l'univers causal fourni.

Les campagnes dynamiques savent déjà conserver `PERPETUAL` dans `MarketDiscoveryPolicy.market_types`, sous réserve d'un bootstrap compatible et des caps Risk dérivés requis.

Le Batch 49.1 ne remplace pas cette source par le Radar.

## Radar

Aucune modification du ranking Radar, du score Analytics ou de l'observabilité Batch 48.

```text
Radar shortlist
    X
univers Agent
```

Le raccordement réel est reporté au Batch 49.2.

Un PERPETUAL présent dans le Radar ne crée aucun ordre par lui-même.

## Frontend / Control Plane

Audit confirmé : les contrôles nécessaires existent déjà.

La configuration expose notamment :

- `paper_derivative_leverage` ;
- `risk_max_derivative_leverage` ;
- `risk_max_derivative_position_notional` ;
- `risk_max_total_derivative_exposure` ;
- `risk_derivative_liquidation_buffer_ratio` ;
- `paper_derivative_margin_mode=ISOLATED`.

Le cockpit Marchés sait déjà exposer une position dérivée avec levier, marge et liquidation théorique. Les types frontend possèdent les champs dérivés nécessaires.

Conclusion : **aucune nouvelle configuration frontend n'est ajoutée en 49.1**.

## Contrat opérateur

Le seul guard runtime actif trouvé qui contredisait encore la capacité canonique était :

```text
Trading is SPOT only and PAPER only.
```

Le patch introduit `operator-chat-v2` :

- PAPER uniquement ;
- SPOT + PERPETUAL linéaire ;
- SPOT sans short/levier/marge ;
- PERPETUAL LONG/SHORT sous Risk ;
- FUTURE daté et LIVE indisponibles ;
- chat toujours read-only et sans surface d'exécution.

Le chat n'acquiert aucune autorité de trading avec ce changement.

## Tests existants réutilisés

Le HEAD possède déjà des tests canoniques couvrant notamment :

- domaine dérivés ;
- ouverture LONG ;
- augmentation/réduction/fermeture LONG ;
- ouverture SHORT ;
- fermeture SHORT ;
- funding LONG/SHORT ;
- frais/spread/slippage ;
- levier et margin tiers ;
- caps de position et d'exposition ;
- marge insuffisante ;
- liquidation headroom ;
- `reduce_only` ;
- minimum/quantum de quantité ;
- compatibilité SPOT ;
- dynamic PERPETUAL ;
- campaign PERPETUAL ;
- FUTURE daté rejeté.

Fichiers principaux existants :

```text
backend/tests/test_derivatives_domain.py
backend/tests/test_derivatives_risk.py
backend/tests/test_derivatives_paper.py
backend/tests/test_capacity_management.py
backend/tests/test_dynamic_market_execution.py
backend/tests/test_dynamic_market_configuration.py
backend/tests/test_multi_market_provider.py
```

## Test ajouté 49.1

`backend/tests/test_batch49_1_perpetual_paper.py` ajoute une preuve de raccordement entre composants canoniques :

```text
sortie structurée Agent PERPETUAL
-> DecisionCandidate PERPETUAL
-> RiskAssessment
-> ExecutionIntent PAPER PERPETUAL
-> PaperBroker
-> Fill PERPETUAL
-> DerivativePosition LONG/SHORT
```

Il vérifie aussi :

- fermeture LONG via SELL `reduce_only` ;
- fermeture SHORT via BUY `reduce_only` ;
- `HOLD` sans intent ;
- conservation de `market_type` ;
- levier provenant de Risk ;
- liquidation théorique présente après ouverture ;
- quantité opposée surdimensionnée bornée à la fermeture sans retournement ;
- contrat `operator-chat-v2`.

## Fichiers du patch

```text
README.md
backend/src/ai_spot_trader/chat/prompt.py
backend/tests/test_batch49_1_perpetual_paper.py
docs/00_ETAT_ACTUEL.md
docs/01_PROJECT_MASTER.md
docs/09_ROADMAP_DEVELOPPEMENT.md
docs/10_DECISIONS_ET_CHANGELOG.md
docs/49_1_PERPETUAL_PAPER_EXECUTION.md
```

Aucun fichier frontend n'est modifié : l'audit a confirmé que les contrôles et représentations nécessaires existaient déjà.

## Hors périmètre

- connexion Radar -> univers Agent ;
- changement du ranking Radar ;
- recalibration Analytics ;
- nouveaux indicateurs ;
- exécution Kraken LIVE ;
- authentification Kraken Futures privée ;
- endpoint privé d'ordre Futures ;
- droit de retrait ;
- levier arbitraire choisi par le LLM ;
- bascule automatique PAPER -> LIVE.

## Validation attendue dans le repository complet

```powershell
python -m pytest -q

cd frontend
pnpm typecheck
pnpm test
cd ..

git diff --check
git status --short
```

Aucun test ne doit être déclaré PASS s'il n'a pas réellement été exécuté.

## Suite

Après validation et intégration de 49.1 :

```text
49.2 — Radar shortlist -> univers Agent SPOT + PERPETUAL
49.3 — contexte Radar/Analytics fourni à l'Agent
49.4 — observabilité des décisions et performances PAPER SPOT/PERP
```
