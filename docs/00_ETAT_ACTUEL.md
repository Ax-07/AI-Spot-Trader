# 00 — État actuel

## Référence de reprise — Batch 49.4 intégré

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
Base auditée au démarrage 49.4      : e7d605aa2b6393516c0ccd391cd4d11193c18671
HEAD GitHub vérifié à la clôture   : 2e552cbaf1b8ffcae9244c1fb472f1ee8fb0f193
Commit HEAD                        : feat: add paper trading observability
Batch 49.3                         : INTÉGRÉ SUR GITHUB main via d08cd31
Batch 49.4                         : INTÉGRÉ SUR GITHUB main via 2e552cb
```

Le Batch 49.4 est intégré sur `main` via `2e552cb`. La documentation de reprise est alignée sur cet état fonctionnel intégré.

## État fonctionnel intégré par le Batch 49.4

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

## Validation intégrée du Batch 49.4

```text
backend python -m pytest -q : PASS — 1195 passed, 2 warnings
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 89/89
git diff --check            : PASS — avertissements LF/CRLF uniquement
git status --short          : PASS — working tree propre après push
push GitHub main            : PASS — 2e552cb
```

Les warnings Node `MODULE_TYPELESS_PACKAGE_JSON` observés pendant `pnpm test` sont non bloquants. Aucun changement global de `package.json` n'est requis pour la clôture 49.4.
