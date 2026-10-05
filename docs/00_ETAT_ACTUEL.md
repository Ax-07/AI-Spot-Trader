# 00 — État actuel

## Référence de reprise — Batch 49.2 préparé

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub audité au démarrage    : 3194fce620f5e31672c6b52ef8986daddeea3a25
HEAD GitHub                        : feat: activate perpetual paper trading
Batch 49.1                         : INTÉGRÉ SUR GITHUB main
Batch 49.2                         : PATCH PROPOSÉ — NON INTÉGRÉ À GITHUB À LA LIVRAISON
```

Le Batch 49.1 est bien intégré sur `main`. La référence `8704eec` encore présente dans l'ancienne version de ce document était obsolète.

## État fonctionnel proposé par le Batch 49.2

Le runtime PAPER conserve un seul Agent stratégique et la chaîne canonique :

```text
Market Attention Radar
-> shortlist bornée
-> projection identité {symbol, market_type}
-> validation catalogue/configuration Kraken
-> univers Agent typé SPOT/PERPETUAL
-> même Agent IA : BUY / SELL / HOLD
-> Risk Engine
-> PaperBroker
```

Le Radar choisit **où regarder**. Il ne choisit jamais l'action, la taille, le levier, `reduce_only` ou l'autorisation Risk.

## Frontière 49.2 / 49.3

Le Batch 49.2 transmet uniquement :

```text
symbol
market_type
```

Il ne transmet pas encore au prompt stratégique les données Radar/Analytics : `analytics_ranking.score`, Open Interest, Funding, Liquidations, CVD, Aggressor Differential, structure détaillée ni diagnostics Radar. Cet enrichissement est réservé au Batch 49.3.

## Architecture retenue

`MarketDiscoveryCoordinator` reste la frontière canonique de l'univers dynamique. Il accepte désormais deux sources exclusives :

- mode historique `LEGACY_AGENT`, conservé pour compatibilité/tests ;
- mode production `RADAR_SHORTLIST`, utilisé par les Campaigns dynamiques après 49.2.

En mode Radar, aucun second ranking ni seconde shortlist n'est créé. Seuls les `ExecutableMarket` de la shortlist sont projetés, puis validés contre le catalogue public Kraken et les contraintes Campaign/Risk déjà existantes : type autorisé, quote de règlement, statut tradable, PERPETUAL linéaire, whitelist éventuelle et présence dans le catalogue.

Le `DynamicMarketTradingCycleRunner` réutilise ensuite sans duplication `MultiMarketTradingCycleRunner`, le même Agent, le même Risk Engine et le même `PaperBroker`.

## Mode dégradé

Pour les nouvelles ouvertures, le chemin Radar est **fail-closed** lorsque le Radar est indisponible, stale, vide ou sans candidat exécutable. Aucun bootstrap n'est silencieusement transformé en opportunité de remplacement.

Si des positions sont déjà ouvertes, elles restent gérables par le même Agent en mode MANAGEMENT uniquement ; ce fallback n'autorise aucune nouvelle exposition.

Les `FUTURE` datés restent non exécutables. SPOT reste sans short/levier/marge. PERPETUAL linéaire reste LONG/SHORT sous autorité finale du Risk Engine.

## Fichiers fonctionnels principaux du patch 49.2

```text
backend/src/ai_spot_trader/market/discovery.py
backend/src/ai_spot_trader/trading/discovery_runner.py
backend/src/ai_spot_trader/campaign_composition.py
backend/src/ai_spot_trader/core/control_plane_runtime.py
backend/src/ai_spot_trader/main.py
backend/tests/test_batch49_2_radar_agent_universe.py
```

Documentation active mise à jour : `README.md`, `docs/00_ETAT_ACTUEL.md`, `docs/01_PROJECT_MASTER.md`, `docs/09_ROADMAP_DEVELOPPEMENT.md`, `docs/10_DECISIONS_ET_CHANGELOG.md` et `docs/49_2_RADAR_AGENT_UNIVERSE.md`.

## Suite

```text
49.3 — contexte Radar/Analytics causal fourni à l'Agent
49.4 — observabilité des décisions et performances PAPER SPOT/PERP
```

Aucun LIVE, aucune API Kraken Futures privée et aucun ordre réel Kraken ne font partie du Batch 49.2.
