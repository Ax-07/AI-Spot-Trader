# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est un cockpit de contrôle et de visualisation qui peut être fermé sans arrêter le moteur.

Référence GitHub courante auditée au lancement du Batch 51.1 :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : e5887da5e8e6ebf0fa739a041c0226a6fed940dd
Commit     : feat: add strategic thesis observability
```

Les Batches 49.1 à 50.2 sont intégrés. Le Batch 51.1 est livré sous forme de patch à valider/intégrer localement.

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
- OpenAI Luna par défaut pour les premiers tests cloud, Sol sélectionnable par configuration ;
- provider stratégique configurable `OPENAI` / `OLLAMA` depuis le Batch 51.1 ;
- Risk Engine déterministe comme autorité finale ;
- aucune sortie LLM directement transmise au Broker/Kraken ;
- frais, spread et slippage pris en compte dans la chaîne d'exécution concernée ;
- décisions, `HOLD`, sélections, évaluations Risk et exécutions auditables ;
- aucun look-ahead ;
- aucun secret dans prompts, logs, frontend ou fichiers versionnés ;
- frontend non nécessaire au fonctionnement du moteur ;
- Market Attention détermine l'univers candidat et peut fournir des faits descriptifs causaux, mais n'a aucune autorité `BUY`/`SELL`/`HOLD` ni Risk ;
- la mémoire de thèse 50.1 est un fait applicatif structuré, jamais une mémoire conversationnelle opaque ni une chaîne de pensée cachée ;
- l'observabilité 50.2 est strictement read-only et ne crée ni second store, ni second Agent, ni appel LLM supplémentaire.

Principe central : **le Radar propose les marchés à examiner. Les faits Radar/Analytics et la mémoire stratégique aident l'Agent à raisonner. L'IA propose l'action. Le Risk Engine autorise, modifie ou refuse. Le cockpit observe.**

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

Depuis le Batch 50.1, la continuité stratégique d'une position est également durable. Le dernier cycle `COMPLETED` d'un `paper_run` porte un snapshot canonique des thèses actives. En reprise, si le run courant n'a encore aucun cycle `COMPLETED`, la lecture suit exclusivement `resumed_from_paper_run_id`.

Le Batch 50.2 ne modifie pas cette persistence : il lit les snapshots et les révisions déjà persistés.

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

La shortlist Radar n'est jamais un ordre ni une recommandation. Le ranking peut influencer **où l'Agent regarde** et fournir un indice descriptif visible ; il ne décide jamais **ce que l'Agent doit faire**.

## 5. Multi-timeframes stratégiques

Le mapping canonique `trading-style-map-v1` reste :

- SCALP : `1m`, `5m`, `15m`, `30m` ;
- SWING : `1h`, `4h`, `1d`.

`StrategicMultiTimeframeContextService` réutilise le `CandleStreamService` partagé. `history_as_of(...)` protège la causalité et empêche tout look-ahead.

`StrategicMultiTimeframeContext` reste consacré aux candles stratégiques. Les faits Radar utilisent un contrat dédié `RadarAnalyticsStrategicContext`. La mémoire de position 50.1 utilise un troisième contrat séparé `StrategicPositionContext` afin de ne pas mélanger les responsabilités.

## 6. Cycle stratégique

Un cycle produit un plan ordonné et borné via l'Agent stratégique unique :

```text
univers Radar validé
+ contexte candles causal
+ contexte Radar/Analytics causal et figé, si disponible
+ positions ouvertes + mémoire de thèse causale
-> Agent IA unique
-> plan [D1, D2, ... Dn]
   chaque décision = BUY/SELL/HOLD + thesis_update éventuelle/requise
-> chaque décision : Risk -> exécution éventuelle -> portefeuille courant
-> commit audit + portefeuille
-> projection des thèses actives réellement soutenues par l'exposition économique
```

Le `market_type` fait partie de l'identité de marché et doit rester explicite afin que `BTC/USD SPOT` et `BTC/USD PERPETUAL` ne puissent pas être confondus. Pour PERPETUAL, le côté `LONG/SHORT` fait également partie de l'identité de la mémoire stratégique.

`HOLD` et `REJECT` ne sont pas des erreurs techniques.

## 7. Cadences distinctes

L'application distingue le monitoring déterministe, la cadence du cycle stratégique IA, le cache/stream candles et la cadence du Market Attention Radar. Le Radar conserve sa cadence propre et ses caches ; il ne modifie jamais la cadence de l'Agent.

La mémoire de thèse n'ajoute aucune cadence LLM : elle est relue avant le même appel stratégique et mise à jour par la persistence après le résultat du cycle.

## 8. Transparence des appels IA

Le Batch 49.2 a supprimé du chemin dynamique de production l'ancien appel LLM de sélection de watchlist. Le même Agent n'est appelé qu'au stade stratégique canonique `generate_decision_plan(...)` pour choisir `BUY`, `SELL` ou `HOLD` dans l'univers déjà borné par le Radar et les contraintes déterministes.

Le Batch 49.3 conserve cette propriété : `FrozenRadarContextDecisionProvider` ne déclenche aucun appel supplémentaire ; il attache le contexte figé à `CycleDecisionPlanInput`, revalide le contrat puis délègue une seule fois au provider existant.

Le Batch 50.1 applique le même pattern avec `StrategicThesisContextDecisionProvider` : lecture durable du contexte, attachement à `CycleDecisionPlanInput`, revalidation, puis une seule délégation. Il n'existe pas d'« Agent mémoire ».

Le Batch 50.2 n'appelle aucun LLM : il projette uniquement des faits déjà persistés pour l'opérateur.

Les outils read-only Agent sont conservés. Ils servent des recherches ponctuelles ; ils ne remplacent pas les snapshots causalisés et figés du cycle.

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

Le contexte Radar/Analytics et la mémoire de thèse ne contiennent ni `ExecutionIntent`, ni levier, ni `reduce_only`, ni action automatique. Le Radar et la mémoire ne modifient ni Risk, ni Broker.

## 10. Market Attention Radar — scope, structure et Analytics

Le Radar courant combine les couches intégrées précédentes : scope runtime SPOT/PERPETUAL/ALL, activité multi-horizons, tendance récente, Market Structure causale, filtres volume/capitalisation, microstructure SPOT et Analytics Futures read-only pour PERPETUAL.

Pipeline conceptuel :

```text
catalogue Kraken complet
-> scope runtime / filtres déterministes
-> OHLCV / candles finalisées
-> activité + tendance + structure
-> microstructure lorsqu'applicable
-> Analytics Futures lorsqu'applicable
-> ranking d'attention borné
-> shortlist
```

Aucun de ces faits ne constitue une action de trading. Le ranking est un indice d'attention, pas une probabilité directionnelle ni un ordre.

## 11. Direction de tendance récente

La direction récente réutilise les seuils matériels existants : `UP`, `DOWN`, `NEUTRAL`, `UNKNOWN`, avec synthèse multi-timeframe pouvant produire `MIXED`. `TRENDING` est descriptif et n'est jamais un signal automatique.

## 12. Market Structure

La Market Structure lit des historiques natifs Kraken sur les timeframes concernés. Les pivots sont confirmés causalement après des candles situées à droite du pivot. États exposés :

```text
BULLISH / BEARISH / RANGE / TRANSITION / UNKNOWN / MIXED(synthèse)
```

`BOS` et `CHOCH` restent descriptifs. Aucun ne déclenche automatiquement `BUY` ou `SELL`.

## 13. Séparation tendance récente / structure

Les deux concepts restent indépendants : le mouvement récent n'est pas la géométrie de pivots confirmés. Cette séparation est conservée dans les faits remis à l'Agent.

## 14. Performance et cache Radar

Les enrichissements coûteux sont appliqués après les filtres déterministes pertinents. `CandleStreamService` reste le point d'accès canonique et réutilise son cache. La mémoire 50.1 et l'observabilité 50.2 ne modifient aucun cache Radar et ne mélangent pas ces responsabilités avec le Prompt Cache OpenAI.

## 15. Contrat API Radar

Les versions Radar intégrées restent celles des batches précédents. `informative_only=True` signifie toujours absence d'autorité de trading. La shortlist peut déterminer l'univers candidat et ses faits causaux peuvent être visibles par l'Agent sans devenir des ordres.

## 16. Isolation architecturale

Les couches Market Attention n'ont aucune dépendance Agent/Risk/Broker. Le contexte Radar est projeté avant l'appel Agent. Le contexte de thèse est projeté depuis la persistence avant le même appel Agent. Ces deux sources restent distinctes.

L'observabilité 50.2 dépend uniquement des contrats de domaine, des lectures d'audit et de la lineage PAPER. Elle n'importe aucune dépendance Risk, Broker ou LLM.

## 17. Microstructure

La microstructure Radar reste SPOT uniquement. En scope PERPETUAL, cette famille reste `NOT_APPLICABLE`. Cette limite d'observation ne limite pas l'exécution PAPER PERPETUAL linéaire.

## 18. Filtres volume et capitalisation

Le Radar supporte les filtres runtime `market_scope`, `min_volume_24h_usd`, `market_cap_categories`, `min_market_cap_usd`, `max_market_cap_usd`. CoinPaprika reste isolé derrière un provider read-only avec comportement fail-soft. Ces filtres ne produisent pas d'action Agent.

## 19. Exécution PERPETUAL PAPER officielle

Le runtime supporte l'univers typé `SPOT` / `PERPETUAL`, `RoutedExecutableMarketDataSource`, l'Agent multi-marchés, le Risk dérivés, `PaperBroker`, `DerivativePosition`, mark-to-market/funding et limites de levier/exposition.

Sémantique :

```text
BUY sans position   -> ouvrir LONG
SELL sans position  -> ouvrir SHORT
BUY avec LONG       -> augmenter LONG
SELL avec LONG      -> réduire/fermer LONG
BUY avec SHORT      -> réduire/fermer SHORT
SELL avec SHORT     -> augmenter SHORT
HOLD                -> aucune exécution
```

Un retournement direct ne contourne jamais `reduce_only`/Risk.

## 20. Radar shortlist vers univers Agent

En mode `RADAR_SHORTLIST`, chaque identité est revalidée contre les faits exécutables Kraken et les contraintes Campaign. En cas de Radar indisponible/stale/shortlist inexploitable, aucune nouvelle ouverture n'est inventée ; les positions existantes peuvent rester gérables en `MANAGEMENT`.

## 21. Contexte Radar / Analytics causal

`RadarAnalyticsStrategicContext` est strict, borné, trié et causal. Il expose activité/tendance/liquidité, structure compacte et Analytics PERPETUAL avec statuts explicites. Les données postérieures à la frontière du cycle sont rejetées.

## 22. Observabilité PAPER 49.4

La projection 49.4 étend l'historique économique avec vue TOTAL/SPOT/PERPETUAL, funnel Agent/Risk/exécution, ventilation stricte par marché et métriques attribuables. Elle ne crée aucun second moteur P&L et ne rétroagit pas sur la stratégie.

## 23. Mémoire de thèse stratégique 50.1

Le Batch 50.1 rend durable la continuité stratégique d'une position ouverte.

Contrat compact :

```text
thesis_id
symbol
market_type
side
origin
created_at
activated_at
horizon
thesis_summary
supporting_facts
invalidation_conditions
status
last_review
updated_at
```

Statuts : `NEW`, `CONFIRMED`, `WEAKENING`, `INVALIDATED`, `COMPLETED`.

La création d'une thèse proposée est séparée de son activation économique. Une entrée refusée par Risk ou sans fill ne crée pas de thèse active. Une position legacy sans mémoire expose `UNAVAILABLE_LEGACY`; aucune ancienne rationale n'est transformée en historique fictif.

La persistence choisie est **Option C : extension additive des faits de cycle + projection canonique** :

- `CycleDecisionPlan.decision_plan_payload` conserve la révision proposée de chaque décision ;
- `audit_cycles.strategic_thesis_state_payload` conserve le snapshot des thèses encore actives après un cycle `COMPLETED` ;
- un cycle `FAILED` ne promeut aucun snapshot ;
- le recovery suit la lineage explicite des `paper_run` ;
- le prochain cycle ne reçoit que la projection compacte correspondant à ses positions ouvertes/gérables.

`INVALIDATED`/`COMPLETED` ne sont jamais convertis automatiquement en SELL. L'Agent conserve la décision stratégique et Risk conserve l'autorité finale.

État intégré : commit `ebb859c4ed83aada1c0bf3edf17ece85336849b9`, suite backend `1217 passed, 2 warnings`, migration PostgreSQL `0008_strategic_thesis_state` appliquée.

Voir `docs/50_1_MEMOIRE_THESE_STRATEGIQUE.md`.

## 24. Observabilité des thèses stratégiques 50.2

Le Batch 50.2 ajoute une vue opérateur dédiée sans modifier le moteur ni la persistence.

Architecture retenue : **endpoint read-only dédié dans le routeur Analytics existant**.

```text
audit_cycles.strategic_thesis_state_payload
+ decision_plan_payload.thesis_updates
+ lineage paper_run
+ états de portefeuille persistés
        ↓
StrategicThesisObservabilityReport
        ↓
GET /api/v1/strategic-theses
        ↓
cockpit Historique
```

Règles de projection :

- les thèses actives proviennent uniquement du dernier snapshot `COMPLETED` durable ;
- l'exposition courante provient des états de portefeuille persistés des cycles `COMPLETED` ;
- une position sans thèse correspondante reste `UNAVAILABLE_LEGACY` ;
- aucune `rationale` historique n'est une source de vérité ;
- chaque révision est reliée au snapshot précédent et à celui du **même cycle**, jamais à un snapshot futur ;
- un `REJECT` d'ouverture peut être visible comme proposition non activée mais ne crée jamais une thèse active ;
- un cycle `FAILED` reste visible dans l'audit sans être promu ;
- une fermeture complète retire la thèse de la vue active tout en conservant la révision finale ;
- l'historique est borné par `history_limit` et conserve `total_revision_count` ;
- l'identité reste `(symbol, market_type, side)` ; SPOT reste LONG uniquement.

Le cockpit présente loading/error/empty/legacy, les faits de support, conditions d'invalidation, dernière revue et historique causal. Il rappelle explicitement que `INVALIDATED`, `COMPLETED` et `WEAKENING` ne constituent pas des ordres. Aucun calcul stratégique métier n'est recréé côté frontend.

Voir `docs/50_2_OBSERVABILITE_THESES_STRATEGIQUES.md`.

## 25. Provider LLM local / Ollama 51.1

Le Batch 51.1 introduit une frontière explicite de provider LLM sans modifier la stratégie ni créer de second Agent.

```text
StrategicThesisContextDecisionProvider
-> MultiTimeframeDecisionProvider
-> OpenAIMultiMarketDecisionProvider (nom legacy)
-> StrategyInstructionsClient / StructuredDecisionClient
   -> OpenAIResponsesClient
   -> OllamaStructuredDecisionClient
-> validation Pydantic canonique
-> Risk Engine
-> Broker PAPER
```

Décisions architecturales :

- `LLMProviderKind` distingue `OPENAI` et `OLLAMA` ; le nom évite de masquer le port domaine historique `LLMProvider` ;
- `LLMModel` reste réservé à Luna/Sol afin de préserver la sémantique et les snapshots Campaign existants ;
- en 51.1, le provider est une configuration process/runtime et le modèle local vient de `AI_SPOT_TRADER_OLLAMA_MODEL` ;
- `OPENAI_API_KEY` n'est obligatoire que pour `OPENAI` ;
- aucun fallback `OLLAMA -> OPENAI` n'existe ;
- `build_structured_decision_client(...)` centralise la sélection du transport afin que les compositions legacy et Campaign suivent la même règle ;
- le nom `OpenAIMultiMarketDecisionProvider` est conservé pour compatibilité : son rôle est déjà provider-agnostique, le renommage est une dette de nommage à traiter séparément ;
- le chat opérateur n'est pas câblé sur Ollama dans 51.1 et reste donc indisponible en mode local plutôt que de provoquer un fallback implicite ;
- Risk, Broker, Radar, mémoire de thèse, contexte multi-timeframe et contrats BUY/SELL/HOLD restent inchangés.

Ollama utilise `/api/chat` avec le JSON Schema canonique dans `format`. Le texte JSON retourné traverse ensuite exactement la même validation Pydantic métier. Les tools read-only sont convertis vers le format Ollama mais réutilisent le registre, les handlers, les timeouts et le budget existants.

L'audit LLM expose désormais `provider`, `model`, `status`, `error_type` et `latency_ms` en plus du payload borné déjà conservé. Aucun secret HTTP ou clé n'est ajouté au store.

Configuration initiale :

```text
AI_SPOT_TRADER_LLM_PROVIDER=OLLAMA
AI_SPOT_TRADER_OLLAMA_BASE_URL=http://localhost:11434
AI_SPOT_TRADER_OLLAMA_MODEL=qwen3.5:9b
AI_SPOT_TRADER_OLLAMA_TIMEOUT_SECONDS=60
```

Le modèle Ollama reste configurable. Le candidat `qwen3.5:9b` n'est pas codé dans la logique Agent ; il n'est qu'une valeur par défaut de configuration.

Limites 51.1 : le sélecteur UX/persisté par Session est reporté à 51.2 ; le chat opérateur est OpenAI-only ; une vraie inférence et la combinaison réelle tools + structured output doivent être smoke-testées sur le serveur Ollama local de l'opérateur.
