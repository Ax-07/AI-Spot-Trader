# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est un cockpit de contrôle et de visualisation qui peut être fermé sans arrêter le moteur.

Référence GitHub vérifiée à la clôture du Batch 49.3 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : d08cd31e6a795a8beb09530c2bc9a3f32f94fe35
Commit     : feat: expose causal radar analytics context to agent
```

Les Batches 49.1, 49.2 et 49.3 sont intégrés. Le Batch 49.3 est intégré via `d08cd31`.

## 2. Invariants fonctionnels

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- premières versions en PAPER ;
- SPOT et PERPETUAL Kraken linéaire comme familles d'exécution PAPER autorisées ;
- SPOT sans short, levier ni marge ;
- PERPETUAL avec LONG/SHORT sous contrôle du Risk Engine ;
- FUTURE daté non exécutable ;
- LIVE hors périmètre tant qu'une décision séparée ne l'active pas explicitement ;
- actions stratégiques `BUY`, `SELL`, `HOLD` ;
- Luna par défaut pour les premiers tests, Sol sélectionnable par configuration ;
- Risk Engine déterministe comme autorité finale ;
- aucune sortie LLM directement transmise au Broker/Kraken ;
- frais, spread et slippage pris en compte dans la chaîne d'exécution concernée ;
- décisions, `HOLD`, sélections, évaluations Risk et exécutions auditables ;
- aucun look-ahead ;
- aucun secret dans prompts, logs, frontend ou fichiers versionnés ;
- frontend non nécessaire au fonctionnement du moteur ;
- Market Attention détermine l'univers candidat et peut fournir des faits descriptifs causaux, mais n'a aucune autorité `BUY`/`SELL`/`HOLD` ni Risk.

Principe central : **le Radar propose les marchés à examiner. Les faits Radar/Analytics aident l'Agent à raisonner. L'IA propose l'action. Le Risk Engine autorise, modifie ou refuse.**

La cible expérimentale `+4 %/jour` reste un objectif de recherche non garanti, jamais une promesse de rendement.

## 3. Persistance et sessions

`Session` reste une façade sur les objets canoniques :

```text
Session UX
-> Strategy
-> StrategyRevision(s)
-> Campaign(s) immuables
-> paper_run(s)
```

Une modification de configuration crée un nouveau snapshot Campaign sans réécrire l'historique.

## 4. Market Discovery et Radar

`MarketDiscoveryCoordinator` est la frontière canonique qui résout l'univers dynamique remis au cycle multi-marchés. Depuis le Batch 49.2 intégré via `f0d4f94`, le chemin de production dynamique consomme la shortlist du Market Attention Radar au lieu d'effectuer une seconde sélection LLM de watchlist.

```text
Kraken / Radar
-> filtres déterministes Radar
-> shortlist bornée
-> projection {symbol, market_type}
-> validation catalogue/configuration Kraken
-> univers dynamique canonique
-> même Agent stratégique
```

Le mode historique `LEGACY_AGENT` reste disponible dans `MarketDiscoveryCoordinator` pour compatibilité et tests ; il n'est plus le chemin composé des Campaigns dynamiques.

Le Batch 49.3 ajoute ensuite une projection **distincte de l'identité d'univers** : seuls les marchés effectivement admis peuvent recevoir un `RadarAnalyticsStrategicContext`. La shortlist et le contexte restent deux responsabilités séparées.

La shortlist Radar n'est jamais un ordre ni une recommandation. Le ranking peut influencer **où l'Agent regarde** et, en 49.3, fournir un indice descriptif visible ; il ne décide jamais **ce que l'Agent doit faire**.

## 5. Multi-timeframes stratégiques

Le mapping canonique `trading-style-map-v1` reste :

- SCALP : `1m`, `5m`, `15m`, `30m` ;
- SWING : `1h`, `4h`, `1d`.

`StrategicMultiTimeframeContextService` réutilise le `CandleStreamService` partagé. `history_as_of(...)` protège la causalité et empêche tout look-ahead.

`StrategicMultiTimeframeContext` reste consacré aux candles stratégiques. Le Batch 49.3 ne le surcharge pas avec les faits Radar : ceux-ci utilisent un contrat dédié `RadarAnalyticsStrategicContext`, également référencé depuis `CycleDecisionPlanInput`.

## 6. Cycle stratégique

Un cycle produit un plan ordonné et borné via l'Agent stratégique unique :

```text
univers Radar validé
+ contexte candles causal
+ contexte Radar/Analytics causal et figé, si disponible
-> Agent IA unique
-> plan [D1, D2, ... Dn]
-> chaque décision : Risk -> exécution éventuelle -> portefeuille courant
```

Le `market_type` fait partie de l'identité de marché et doit rester explicite afin que `BTC/USD SPOT` et `BTC/USD PERPETUAL` ne puissent pas être confondus.

`HOLD` et `REJECT` ne sont pas des erreurs techniques.

## 7. Cadences distinctes

L'application distingue le monitoring déterministe, la cadence du cycle stratégique IA, le cache/stream candles et la cadence du Market Attention Radar. Le Radar conserve sa cadence propre et ses caches ; il ne modifie jamais la cadence de l'Agent.

## 8. Transparence des appels IA

Le Batch 49.2 a supprimé du chemin dynamique de production l'ancien appel LLM de sélection de watchlist. Le même Agent n'est appelé qu'au stade stratégique canonique `generate_decision_plan(...)` pour choisir `BUY`, `SELL` ou `HOLD` dans l'univers déjà borné par le Radar et les contraintes déterministes.

Le Batch 49.3 conserve cette propriété : `FrozenRadarContextDecisionProvider` ne déclenche aucun appel supplémentaire ; il attache le contexte figé à `CycleDecisionPlanInput`, revalide le contrat puis délègue une seule fois au provider existant.

Les outils read-only Agent sont conservés. Ils servent des recherches ponctuelles ; ils ne remplacent pas le snapshot Radar causalisé et figé du cycle.

Le Market Attention Radar ne produit lui-même aucun ordre et n'appelle jamais directement Risk ou Broker.

## 9. Risk, coûts et exécution

La chaîne d'exécution PAPER canonique est :

```text
Agent
-> DecisionCandidate
-> Risk Engine
-> ExecutionIntent
-> PaperBroker
-> ledger
-> audit
```

Pour les PERPETUAL linéaires, le ledger produit des `DerivativePosition` et le monitoring dérivé assure mark-to-market, funding, P&L et liquidation théorique. Le Risk Engine reste l'unique autorité pour le levier exécutable, la marge, les caps notionnels/exposition, la granularité de quantité, `reduce_only` et le buffer de liquidation.

Le contexte Radar/Analytics ne contient ni `ExecutionIntent`, ni levier, ni `reduce_only`, ni action automatique. Le Radar ne modifie ni Risk, ni Broker. Le slippage microstructure du Radar est une **simulation théorique read-only** obtenue en parcourant le snapshot L2 ; aucun ordre réel ou PAPER n'est construit par le Radar.

## 10. Market Attention Radar v4 — scope et tendance récente

Le Batch 41 intégré conserve le Radar v3 comme socle et ajoute une couche v4 de scope runtime et de direction de tendance :

```text
catalogue Kraken complet
        ↓
scope runtime SPOT / PERPETUAL / ALL
        ↓
population réellement éligible
        ↓
rotation / scan_limit
        ↓
CandleStreamService / OHLCV 5m canonique finalisé
        ↓
facts récents 5m / 15m / 1h / 4h
        ↓
direction récente par horizon + synthèse globale
        ↓
caractéristiques / intérêt / shortlist
        ↓
microstructure SPOT uniquement lorsque applicable
```

Le scope par défaut est `ALL`, afin de préserver le comportement historique si l'utilisateur ne modifie aucun réglage.

## 11. Direction de tendance récente

La direction Batch 41 réutilise les seuils matériels `_MATERIAL_RETURN` existants. Par horizon :

- `UP` si `price_return >= +seuil` ;
- `DOWN` si `price_return <= -seuil` ;
- `NEUTRAL` si le rendement reste strictement entre les deux seuils ;
- `UNKNOWN` si l'horizon est incomplet ou non exploitable.

La synthèse globale est multi-timeframe : conflit matériel positif/négatif => `MIXED`; au moins deux horizons matériels alignés sans conflit => `UP` ou `DOWN`; aucun mouvement matériel avec au moins deux horizons exploitables => `NEUTRAL`; sinon => `UNKNOWN`.

`TRENDING` est dérivé de la même synthèse et n'est présent que pour une synthèse globale `UP` ou `DOWN`.

## 12. Market Structure v5 — géométrie des swings

Le Batch 42 intégré ajoute une information distincte de la tendance récente. Pour chaque candidat de shortlist, le Radar lit directement les historiques natifs Kraken :

```text
CandleStreamService.history_as_of(...)
  ├─ CandleKey(market, 5m)
  ├─ CandleKey(market, 15m)
  ├─ CandleKey(market, 1h)
  └─ CandleKey(market, 4h)
```

Par défaut, environ 100 candles finalisées sont analysées par timeframe. Aucun timeframe supérieur n'est reconstruit artificiellement à partir du 5m.

Les pivots sont confirmés causalement après un nombre explicite de candles situées à droite du pivot. Les swing highs sont classés `HH/LH`, les swing lows `HL/LL`, avec une tolérance explicite pour les quasi-égalités. Une seule rupture isolée ne suffit pas à déclarer une structure complète.

États exposés :

```text
BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN
```

La synthèse multi-timeframe peut exposer `MIXED`. Des événements descriptifs `BOS_UP`, `BOS_DOWN`, `CHOCH_UP`, `CHOCH_DOWN` peuvent être ajoutés uniquement lorsque la séquence de pivots confirmés le justifie.

## 13. Séparation tendance récente / structure

Les deux concepts restent indépendants :

```text
recent_trend      = mouvement récent mesuré par les horizons Batch 41
market_structure  = géométrie des pivots confirmés sur historique natif plus long
```

Exemple valide :

```text
Tendance récente H4 : DOWN
Structure H4         : TRANSITION
Swings               : HH → HL → LH → LL
```

Aucun des deux ne constitue une action stratégique. Un `BOS` ou un `CHOCH` reste descriptif et n'est jamais un signal automatique.

## 14. Performance et cache

La Market Structure est enrichie **après** la constitution déterministe de la shortlist. Avec `candidate_limit=10` et quatre timeframes, le nombre de séries demandées par refresh est donc borné à 40. `CandleStreamService` reste le point d'accès canonique et réutilise son cache ; un historique natif déjà à jour n'est pas systématiquement retéléchargé.

## 15. Contrat API Radar

Batch 41 intégré : `market-attention-radar-v4`.

Batch 42 intégré : `market-attention-radar-v5` pour les snapshots réellement enrichis de `market_structure`. Les routes acceptent et sérialisent aussi un service v4 injecté afin de ne pas casser les tests/intégrations Batch 41.

Batch 43 intégré : `market-attention-radar-v6`, ajoutant l'état runtime des filtres ainsi que `volume_24h_usd` et les métadonnées de capitalisation sur les candidats.

`informative_only=True` reste validé côté backend : ce champ signifie que le Radar ne produit aucune action de trading. Le Batch 49.2 autorise sa shortlist à devenir une **source d'univers**, sans transférer d'autorité stratégique. Le Batch 49.3 expose une projection causale et bornée de faits descriptifs sans modifier ce principe.

Les Batches 47.1 à 47.5 ajoutent les Analytics Futures read-only et leur influence bornée sur le ranking des PERP déjà retenus ; le Batch 48 ajoute leur observabilité agrégée. Le Batch 49.3 ne change ni leurs poids ni leur calibration.

## 16. Isolation architecturale

La couche v5 hérite de la couche v4. Le Batch 43 ajoute une couche v6 sans second pipeline candles et sans dépendance Agent/Risk/Broker. L'Agent stratégique reste le seul agent IA de l'application.

Le contexte 49.3 est une projection séparée, construite avant l'appel Agent. Il n'introduit aucune dépendance du provider LLM vers un service Radar mutable pendant l'appel.

Le fait que la shortlist Radar détermine l'univers candidat et que certains faits Radar soient visibles par l'Agent ne donne aucune autorité d'exécution au Radar.

## 17. Microstructure

La microstructure du Radar reste **SPOT uniquement**. En scope `PERPETUAL`, aucun sous-scan microstructure SPOT n'est lancé et les marchés dérivés restent `NOT_APPLICABLE` pour cette famille de données. En scope `ALL`, seuls les éléments SPOT peuvent être enrichis par `/Depth` et `/Trades`.

Le contexte 49.3 expose seulement une projection compacte utile : statut/qualité/fraîcheur, spread bps, profondeur quote totale et book imbalance. Les détails L2, erreurs brutes et simulations exhaustives restent hors prompt.

Cette limitation du Radar ne limite pas l'univers d'exécution PAPER : les PERPETUAL linéaires peuvent être exécutés par la chaîne Agent/Risk/PaperBroker. En revanche, aucune exécution LIVE n'est disponible.

## 18. Batch 43 — filtres volume et capitalisation

Le Batch 43 intégré ajoute des filtres backend runtime :

```text
market_scope
min_volume_24h_usd
market_cap_categories
min_market_cap_usd
max_market_cap_usd
```

Le filtre de capitalisation intervient dès que les métadonnées sont disponibles, avant le scan OHLCV. Le filtre volume intervient au premier endroit fiable après OHLCV et avant microstructure/Market Structure.

Le volume 24h est calculé causalement à partir des candles Kraken déjà présentes dans le cache. Aucune conversion de devise ou d'unité non prouvée n'est inventée : une valeur non calculable reste `UNKNOWN` et est fail-closed lorsqu'un seuil volume est actif.

La capitalisation est une vraie métadonnée externe read-only :

```text
prix / OHLCV / tendance / structure / microstructure = Kraken
market cap / supply / rank                          = CoinPaprika
trading / Risk / Broker / ordres                    = inchangés
```

CoinPaprika est isolé derrière `MarketMetadataProvider`, sans secret, avec cache long et comportement fail-soft. Une indisponibilité du provider n'arrête jamais le Radar ; la capitalisation reste `UNKNOWN` en l'absence de donnée exploitable.

Catégories applicatives centralisées :

```text
MICRO  < 100 M$
SMALL  100 M$ à < 1 Md$
MID    1 Md$ à < 10 Md$
LARGE  >= 10 Md$
```

Ces catégories sont des conventions de l'application et non une définition universelle du marché.

## 19. Batch 49.1 — exécution PERPETUAL PAPER officielle

Le Batch 49.1 intégré confirme et officialise les composants canoniques :

- univers typé `SPOT` / `PERPETUAL` ;
- `RoutedExecutableMarketDataSource` ;
- provider Agent et JSON Schema multi-marchés avec `market_type` ;
- validation des contrats PERPETUAL linéaires ;
- `RiskEngine` dérivés ;
- `PaperBroker` dérivés ;
- `DerivativePosition` et ledger ;
- mark-to-market, funding et liquidation théorique ;
- paramètres Session/Campaign de levier et limites Risk ;
- cockpit de configuration et affichage des positions dérivées.

Sémantique PERPETUAL retenue :

```text
BUY sans position   -> ouvrir LONG
SELL sans position  -> ouvrir SHORT
BUY avec LONG       -> augmenter LONG
SELL avec LONG      -> réduire/fermer LONG
BUY avec SHORT      -> réduire/fermer SHORT
SELL avec SHORT     -> augmenter SHORT
HOLD                -> aucune exécution
```

Un retournement direct LONG → SHORT ou SHORT → LONG dans un seul intent est interdit. Une action opposée sert d'abord à réduire/fermer la position courante avec `reduce_only`. Une ouverture opposée éventuelle doit être une décision ultérieure après fermeture, ce qui garde la chaîne déterministe, causale et auditable.

## 20. Batch 49.2 — Radar shortlist vers univers Agent

**Intégré via `f0d4f94`.**

Le raccordement retenu réutilise la frontière `MarketDiscoveryCoordinator` au lieu de créer une deuxième discovery. En mode `RADAR_SHORTLIST`, la dernière shortlist admissible du Radar est projetée exclusivement en identités `ExecutableMarket(symbol, market_type)`.

Chaque identité est revalidée contre les faits exécutables Kraken et les contraintes Campaign : quote de règlement, type activé, statut tradable, contrat PERPETUAL linéaire, whitelist Risk éventuelle et présence au catalogue. L'ordre de priorité du Radar borne d'abord les candidats à `watchlist_limit`, puis le tuple effectif est trié déterministement pour respecter les contrats du cycle.

La frontière d'univers reste identité-only. Les objets Radar complets ne deviennent jamais le contrat de discovery ou son audit.

### Mode dégradé 49.2

```text
Radar AVAILABLE/PARTIAL + snapshot frais + candidats exécutables
    -> univers normal Radar

Radar ERROR/NOT_CONFIGURED/STALE/trop ancien/shortlist vide/aucun candidat exécutable
    -> aucune nouvelle ouverture
    -> s'il existe des positions : MANAGEMENT uniquement
    -> sinon : cycle technique FAILED avant Agent/Risk/Broker
```

Le bootstrap de Campaign ne devient donc jamais silencieusement un signal de remplacement lorsque le Radar tombe en panne.

## 21. Batch 49.3 — contexte Radar / Analytics causal pour l'Agent

Le contexte dédié `RadarAnalyticsStrategicContext` est strict, immuable, borné et trié déterministement. Il peut contenir uniquement des identités déjà présentes dans le plan stratégique.

Les faits retenus couvrent activité/tendance/liquidité, Market Structure compacte et, pour PERPETUAL, Analytics OI/Funding/Liquidations/CVD/Aggressor avec statuts explicites. Le score 47.5 reste exactement plafonné à quatre familles, CVD et Aggressor restant une seule composante `ORDER_FLOW`.

Le runner vérifie que le snapshot relu pour produire le contexte possède exactement le même `observed_at` que celui utilisé par Discovery. Toute donnée imbriquée postérieure à cette frontière est rejetée. Le plan vérifie ensuite que le contexte ne postdate pas `created_at`.

Pour SPOT, les Analytics Futures sont explicitement `NOT_APPLICABLE`. Pour une série PERPETUAL absente ou dégradée, le statut reste visible et aucune valeur artificielle n'est inventée.

Le contexte sérialisé n'expose pas les diagnostics internes, ranks avant/après, `rank_change`, erreurs brutes, données futures, `ExecutionIntent`, levier ou `reduce_only`.

Voir `docs/49_3_AGENT_RADAR_ANALYTICS_CONTEXT.md`.
