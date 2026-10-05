# 00 — État actuel

## Référence de reprise — Batch 49.4 préparé

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub audité 49.4            : e7d605aa2b6393516c0ccd391cd4d11193c18671
Commit HEAD                        : docs: close batch 49.3 integration
Batch 49.3 fonctionnel             : d08cd31e6a795a8beb09530c2bc9a3f32f94fe35
Batch 49.4                         : PATCH PROPOSÉ — NON INTÉGRÉ À GITHUB
```

Le commit `e7d605a` ne change que la clôture documentaire de 49.3 ; l'état fonctionnel intégré reste celui de `d08cd31`.

## État proposé par le Batch 49.4

Le pipeline de trading reste inchangé :

```text
Radar
-> Agent BUY / SELL / HOLD
-> Risk Engine déterministe
-> PaperBroker
-> faits persistés
-> Analytics / Economic History canoniques
-> projection read-only d'observabilité 49.4
```

La projection 49.4 étend additivement `/api/v1/economic-history` et le cockpit Historique. Elle expose :

- une vue `TOTAL / SPOT / PERPETUAL` ;
- le funnel Agent -> Risk -> exécution ;
- une ventilation stricte par `(symbol, market_type)` ;
- coûts, funding, montant échangé, fills, trades, P&L réalisé et exposition lorsque les faits permettent une attribution exacte ;
- les métriques indisponibles comme telles, sans attribution artificielle.

Le P&L brut/net global, le drawdown et l'exposition globale restent issus des calculs canoniques existants. Aucun second moteur P&L, aucune nouvelle persistence et aucun nouvel endpoint ne sont introduits.

## Limite volontaire importante

Les faits durables actuels ne permettent pas d'attribuer exactement les variations globales d'equity entre SPOT et PERPETUAL. En conséquence :

```text
TOTAL gross_pnl / net_pnl       : disponible, canonique
SPOT gross_pnl / net_pnl        : indisponible
PERPETUAL gross_pnl / net_pnl   : indisponible
```

Les P&L réalisés, coûts, funding, notionnels et expositions attribuables restent ventilés lorsqu'ils sont causalement déterminables.

## Invariants inchangés

- un seul Agent IA stratégique ;
- PAPER uniquement ;
- Kraken ;
- SPOT + PERPETUAL linéaire ;
- FUTURE daté non exécutable ;
- aucun LIVE ni API Kraken Futures privée ;
- Risk Engine déterministe = autorité finale ;
- aucune sortie LLM directement exécutable ;
- aucun changement du ranking Analytics 47.5 ni du contexte 49.3 ;
- aucune adaptation stratégique à partir des résultats 49.4 ;
- aucun look-ahead ni recalibration post-hoc ;
- aucun secret versionné.

## Validation du patch 49.4 dans cette livraison

```text
python -m py_compile des fichiers backend 49.4 : PASS
frontend test ciblé 49.4                         : PASS — 3/3
backend pytest ciblé 49.4                        : NON VALIDÉ — collecte impossible dans le sandbox partiel
suite backend complète                           : À EXÉCUTER LOCALEMENT
frontend pnpm typecheck / test complet           : À EXÉCUTER LOCALEMENT
```

Le Batch 49.4 reste un patch local proposé tant qu'il n'a pas été extrait, validé dans le repository complet puis commité/poussé explicitement par l'utilisateur.
