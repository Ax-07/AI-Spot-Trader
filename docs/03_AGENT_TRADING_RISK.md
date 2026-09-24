# 03 — Agent, trading et Risk

## 1. Principe d'autorité

**L'Agent propose. Le Risk Engine autorise, modifie ou refuse.**

L'Agent est stratégique. Risk, Broker, comptabilité, monitoring et contraintes structurelles restent déterministes.

## 2. Agent unique aujourd'hui

```text
MarketSelectionInput -> select_market() -> MarketSelection
AgentInput           -> generate_decision() -> DecisionCandidate
```

Il s'agit du même `OpenAIDecisionProvider`, du même modèle et du même rôle stratégique.

## 3. Trois rythmes, toujours un seul Agent

1. monitoring/mark-to-market déterministe — **sans LLM** ;
2. décision stratégique de trading — **même Agent IA** ;
3. découverte/révision de watchlist — **même Agent IA**, cadence plus lente.

Cette séparation ne crée pas un second agent.

## 4. Contrat Agent protégé

Le contrat applicatif impose notamment :

- PAPER uniquement ;
- sorties structurées BUY/SELL/HOLD ;
- décision limitée au contexte exécutable fourni ;
- SPOT sans short/levier/marge ;
- sémantique LONG/SHORT PERPETUAL ;
- levier et `reduce_only` déterministes ;
- aucune invention de faits absents ;
- aucun LLM -> Broker/Kraken ;
- aucun tool -> Broker/Risk ;
- Risk final.

## 5. Rationale et explicabilité

Le `DecisionCandidate.rationale` reste une explication stratégique explicite et persistée, jamais une instruction d'exécution. L'UI doit le distinguer des raisons déterministes `ALLOW / MODIFY / REJECT` produites par Risk.

## 6. SPOT

`BUY` acquiert la base. `SELL` réduit un actif détenu. Risk vérifie notamment symbole/type, whitelist, chronologie/fraîcheur, cash quote, position disponible, max notional et coûts PAPER.

Aucun short, leverage ou margin SPOT.

### Comptabilité Batch 19.1

Le `PortfolioState` transmis à l'Agent peut désormais contenir pour chaque position SPOT :

- quantité et disponible ;
- `average_entry_price` ;
- `remaining_cost_basis` ;
- `realized_pnl` ;
- `accounting_complete`.

Ces valeurs sont calculées exclusivement par le backend déterministe. L'Agent ne calcule jamais le coût moyen ni le P&L.

`accounting_complete=false` signifie qu'une position historique ne dispose pas d'une base de coût suffisamment fiable pour présenter ces valeurs. L'Agent ne doit pas les inventer.

Le P&L latent n'est pas encore fourni comme champ canonique de position par 19.1 ; il dépendra du mark-to-market du Batch 19.2.

## 7. PERPETUAL

`BUY` exprime/augmente LONG ou réduit SHORT. `SELL` exprime/augmente SHORT ou réduit LONG.

Risk garde le contrôle du contrat, taille, levier, marge, notional, exposition, buffer liquidation, `reduce_only`, anti-reversal et marge `ISOLATED`. Le LLM ne choisit jamais le levier effectif.

## 8. Mode gestion quand aucune nouvelle exposition n'est possible

Le backend pourra constater de manière déterministe qu'une nouvelle exposition est interdite. Dans ce cas, l'Agent ne recherchera pas de nouvelles ouvertures et son contexte portera sur les positions ouvertes ; HOLD, réduction et clôture resteront soumises à Risk.

## 9. Découverte périodique des marchés

Le backend fournit un univers techniquement admissible ; le même Agent produit la sélection stratégique/watchlist. Le déterministe ne doit pas calculer un score d'opportunité qui remplace le choix stratégique de l'Agent.

## 10. Watchlist et positions ouvertes

Invariant cible :

```text
univers surveillé = watchlist IA actuelle + toutes les positions ouvertes
```

## 11. Recovery

Le recovery restaure un `PortfolioState` durable et ne réexécute jamais sélection, Agent, Risk, Broker ou Fill.

Pour 19.1 :

- une nouvelle position SPOT comptabilisée restaure exactement prix moyen, coût restant et P&L réalisé courant ;
- une position legacy sans coût historique reste marquée incomplète ;
- aucune donnée future n'est utilisée pour compléter artificiellement son historique.

## 12. Interdits maintenus

- aucun LIVE ;
- aucun second Agent ;
- aucun scanner/ranking déterministe choisissant le trade ;
- aucun ordre direct LLM/tool ;
- aucune modification post-hoc d'une décision ;
- aucun look-ahead ;
- aucune obligation de trader ;
- aucun calcul stratégique déporté dans le frontend.

Le séquencement détaillé est documenté dans `docs/11_AMELIORATIONS_PLANIFIEES.md`.
