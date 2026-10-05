# 00 — État actuel

## Référence de reprise — Batch 49.3 intégré

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
Base auditée au démarrage 49.3  : f0d4f94d2ed9b8f02eadb7ea021aa3fc817c973b
HEAD GitHub vérifié à la clôture   : d08cd31e6a795a8beb09530c2bc9a3f32f94fe35
Commit HEAD                        : feat: expose causal radar analytics context to agent
Batch 49.1                         : INTÉGRÉ SUR GITHUB main
Batch 49.2                         : INTÉGRÉ SUR GITHUB main via f0d4f94
Batch 49.3                         : INTÉGRÉ SUR GITHUB main via d08cd31
```

Le Batch 49.3 est intégré sur `main` via `d08cd31`. La documentation de reprise est alignée sur cet état intégré.

## État fonctionnel intégré par le Batch 49.3

La chaîne PAPER dynamique reste unique :

```text
Market Attention Radar
-> shortlist bornée
-> validation catalogue/configuration Kraken
-> univers Agent typé SPOT/PERPETUAL
-> projection causale Radar/Analytics bornée pour ces seuls marchés
-> même Agent IA : BUY / SELL / HOLD
-> Risk Engine déterministe
-> PaperBroker
```

Le Radar choisit **où regarder** et fournit désormais des faits descriptifs figés pour aider le raisonnement. Il ne choisit jamais l'action, la taille, le levier, `reduce_only` ou l'autorisation Risk.

## Architecture 49.3

La solution retenue est un contexte dédié `RadarAnalyticsStrategicContext`, référencé depuis `CycleDecisionPlanInput`. `StrategicMultiTimeframeContext` reste consacré aux candles stratégiques existantes.

Le `DynamicMarketTradingCycleRunner` relit le même service Radar après Discovery uniquement pour figer les faits du cycle. Le timestamp doit être exactement celui enregistré par l'audit Discovery ; sinon les nouvelles ouvertures échouent fermées. Le contexte est ensuite filtré sur les `market_states` effectivement visibles par le plan et injecté dans **le même appel** `generate_decision_plan(...)` via un décorateur sans second appel LLM.

## Faits exposés

Par marché, le contexte reste borné et déterministe :

- identité `{symbol, market_type}` ;
- activité, tendance récente, caractéristiques et volume 24h ;
- liquidité/microstructure SPOT utile ;
- synthèse Market Structure et au plus quatre timeframes ;
- pour PERPETUAL : score Analytics 47.5 `0..4`, composantes OI/Funding/Liquidations/ORDER_FLOW et déduplication CVD/Aggressor ;
- valeurs causales compactes Open Interest, Funding, Liquidation Volume, CVD et Aggressor Differential ;
- statuts explicites `AVAILABLE`, `PARTIAL`, `STALE`, `INSUFFICIENT_HISTORY`, `TECHNICAL_ERROR`, `NOT_APPLICABLE` ou `UNAVAILABLE`.

Ne sont pas exposés : diagnostics techniques internes, erreurs brutes, couverture globale du scanner, ranks avant/après, historique brut, swings complets, données futures, résultats/P&L futurs ou métadonnées d'observabilité inutiles.

## Causalité et mode dégradé

Chaque timestamp inclus doit être `<=` au snapshot Radar figé, lui-même `<=` à la frontière de décision. Une donnée future ou un changement de snapshot entre Discovery et projection provoque un échec fermé pour les nouvelles ouvertures.

Une position déjà ouverte reste gérable en MANAGEMENT si le Radar/contexte devient indisponible. Une donnée dégradée n'est jamais convertie en signal positif ou négatif artificiel.

SPOT conserve `NOT_APPLICABLE` pour les Analytics Futures. PERPETUAL conserve LONG/SHORT sous Risk. `FUTURE` daté reste non exécutable.

## Invariants inchangés

- un seul Agent IA stratégique ;
- PAPER uniquement ;
- Kraken ;
- SPOT + PERPETUAL linéaire ;
- aucun LIVE ni API Kraken Futures privée ;
- aucun champ Radar/Analytics ne crée un `ExecutionIntent` ;
- aucun champ Radar/Analytics ne définit levier, marge ou `reduce_only` ;
- Risk Engine déterministe = autorité finale ;
- score Analytics 47.5 inchangé, avec CVD + Aggressor dans une seule famille `ORDER_FLOW` ;
- aucun look-ahead ni recalibration post-hoc ;
- aucun secret versionné.

## Validation intégrée du Batch 49.3

```text
backend python -m pytest -q : PASS — 1189 passed, 2 warnings
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 86/86
git diff --check            : PASS — avertissements LF/CRLF uniquement
git status --short          : PASS — working tree propre après push
push GitHub main            : PASS — d08cd31
```

## Suite

```text
49.4 — observabilité des décisions et performances PAPER SPOT/PERP
```

Le Batch 49.3 n'ajoute aucune migration, aucun endpoint LIVE et aucun ordre Kraken réel.
