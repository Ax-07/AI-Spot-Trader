# Batch 49.2 — Radar shortlist → univers Agent SPOT + PERPETUAL

## Objectif

Faire de la shortlist finale du Market Attention Radar la source des marchés candidats examinés par l'Agent stratégique, sans transférer au Radar la décision de trading ni l'autorité Risk.

```text
Kraken / Radar
-> filtres déterministes Radar
-> shortlist bornée
-> projection {symbol, market_type}
-> validation exécutabilité Kraken/Campaign
-> même Agent stratégique
-> BUY / SELL / HOLD
-> Risk Engine
-> PAPER Broker
```

Le Radar répond à **où regarder**. L'Agent répond à **quoi faire**. Le Risk Engine répond à **ce qui est autorisé**.

## Base auditée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 3194fce620f5e31672c6b52ef8986daddeea3a25
Commit     : feat: activate perpetual paper trading
```

Le Batch 49.1 est intégré à cette base et la chaîne Agent → Risk → PaperBroker SPOT + PERPETUAL linéaire est réutilisée sans duplication.

## Architecture retenue

Trois approches ont été comparées :

1. remplacer Market Discovery par un runner Radar dédié ;
2. conserver Market Discovery puis appliquer une seconde shortlist Radar ;
3. faire du Radar une source derrière la frontière canonique `MarketDiscoveryCoordinator`.

La troisième option est retenue. Elle minimise la duplication et conserve les contrats existants de `DynamicMarketTradingCycleRunner`, `MultiMarketTradingCycleRunner`, audit, Risk et Broker.

`MarketDiscoveryCoordinator` accepte exactement une source :

```text
LEGACY_AGENT       compatibilité historique/tests
RADAR_SHORTLIST    composition production dynamique Batch 49.2
```

La composition des Campaigns dynamiques utilise `RADAR_SHORTLIST`. `OpenAIWatchlistSelector` n'est plus utilisé dans ce chemin : il n'y a donc plus un appel IA pour choisir la watchlist puis un second pour choisir l'action.

## Frontière d'identité

Le Radar final peut porter de nombreux faits : activité, structure, microstructure et Analytics. Batch 49.2 ne transfère que :

```json
{
  "symbol": "BTC/USD",
  "market_type": "PERPETUAL"
}
```

La projection lit uniquement `shortlist_item.market`. Elle ne sérialise pas le snapshot Radar complet.

Sont explicitement réservés au Batch 49.3 :

```text
analytics_ranking.score
Open Interest
Funding
Liquidations
CVD
Aggressor Differential
Market Structure détaillée
diagnostics Radar
```

Le fait que ces données puissent influencer le ranking interne du Radar ne signifie pas qu'elles sont visibles par l'Agent en 49.2.

## Validation d'exécutabilité

Chaque identité de la shortlist est recoupée avec le catalogue public Kraken déjà utilisé par Market Discovery. Un candidat doit respecter :

- le `market_type` autorisé par la Campaign ;
- quote asset identique au settlement asset ;
- statut Kraken tradable ;
- contrat `PERPETUAL` linéaire ;
- whitelist Risk éventuelle ;
- présence effective dans le catalogue exécutable.

`BTC/USD SPOT` et `BTC/USD PERPETUAL` restent deux identités différentes de bout en bout.

Les `FUTURE` datés restent refusés par `MarketDiscoveryPolicy` et `ExecutableMarket`.

## Shortlist et ordre

Le Radar reste responsable de sa priorité d'attention. `MarketDiscoveryCoordinator` parcourt sa shortlist dans cet ordre, ignore les identités non exécutables et borne les identités acceptées à `watchlist_limit`.

Une fois la membership déterminée, le tuple effectif est trié de façon déterministe par `(market_type, symbol)` pour respecter les contrats canoniques du cycle. Ce tri ne crée ni candidat ni score.

## Mode dégradé

Le comportement 49.2 est explicitement fail-closed pour les nouvelles ouvertures.

```text
Radar AVAILABLE/PARTIAL + snapshot frais + candidat exécutable
    -> univers Radar normal

Radar ERROR / NOT_CONFIGURED
    -> aucune nouvelle ouverture

Radar STALE ou timestamp trop ancien/futur/invalide
    -> aucune nouvelle ouverture

shortlist vide
    -> aucune nouvelle ouverture

shortlist sans candidat exécutable
    -> aucune nouvelle ouverture
```

Le bootstrap de Campaign n'est pas utilisé comme opportunité de remplacement lors d'une panne Radar.

Si des positions sont déjà ouvertes, `DynamicMarketTradingCycleRunner` peut encore réinjecter ces marchés pour les gérer. Un évaluateur de capacité local force alors le mode `MANAGEMENT` : aucune nouvelle exposition n'est possible, mais le même Agent/Risk/Broker canonique peut réduire, fermer ou conserver les positions selon les règles existantes.

Sans position ouverte, le cycle s'arrête en échec technique avant l'Agent stratégique, le Risk Engine et le Broker.

## Autorités inchangées

Le Radar ne possède aucune référence au Risk Engine ni au Broker. Le pipeline reste :

```text
Radar -> univers uniquement
Agent -> stratégie BUY/SELL/HOLD
Risk -> ALLOW/MODIFY/REJECT
PaperBroker -> exécution PAPER éventuelle
```

Aucun LIVE, aucune API privée Kraken Futures et aucun ordre réel ne sont ajoutés.

## Fichiers fonctionnels

```text
backend/src/ai_spot_trader/market/discovery.py
backend/src/ai_spot_trader/trading/discovery_runner.py
backend/src/ai_spot_trader/campaign_composition.py
backend/src/ai_spot_trader/core/control_plane_runtime.py
backend/src/ai_spot_trader/main.py
backend/tests/test_batch49_2_radar_agent_universe.py
```

## Couverture de tests ajoutée

Le test dédié couvre :

- shortlist SPOT ;
- shortlist PERPETUAL ;
- scope mixte avec même symbole SPOT/PERPETUAL ;
- conservation de `market_type` ;
- marché catalogue hors shortlist non présenté ;
- quote incompatible, marché absent et whitelist Risk ;
- shortlist vide ;
- Radar `ERROR` / `STALE` / trop ancien ;
- PERPETUAL désactivé par Campaign ;
- aucune fuite des champs Analytics 49.3 ;
- FUTURE daté toujours rejeté ;
- panne Radar sans position arrêtée avant Agent/Risk/Broker ;
- passage du seul univers Radar au seam du runner canonique.

## Suite

Le Batch 49.3 pourra décider quelles données Radar/Analytics causales sont utiles à l'Agent et sous quelle forme. Il devra conserver les poids 47.5, éviter tout look-ahead et ne jamais transformer les métriques en action automatique.
