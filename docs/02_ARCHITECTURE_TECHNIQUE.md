# 02 — Architecture technique

## 1. Référence

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD audité avant Batch 19.4 : bfef06d78dc34089541272c2944518499d4a1530
```

Le Batch 19.3 est intégré. Le Batch 19.4 est livré comme patch à valider/intégrer localement.

## 2. Architecture générale

```text
Next.js cockpit
  -> FastAPI
     -> Control Plane PostgreSQL
     -> CampaignRuntimeManager
        -> TradingEngine
        -> AuditedTradingCycleRunner
        -> DynamicMarketTradingCycleRunner (si market_discovery)
           -> MarketDiscoveryCoordinator
              -> MarketResearchService
                 -> KrakenMarketResearchBackend
              -> OpenAIWatchlistSelector
                 -> même OpenAIDecisionProvider / même client / même modèle
           -> TradingCycleRunner canonique
        -> CapacityEvaluator
        -> RiskEngine
        -> PaperBroker
        -> PaperPortfolioLedger
        -> monitors mark-to-market SPOT/PERPETUAL
```

Le frontend n'est jamais dans la chaîne d'exécution.

## 3. Séparation catalogue / candidat / watchlist / exécution

`MarketResearchService` reste la frontière canonique de recherche publique Kraken. Le Batch 19.4 ne crée pas un nouveau scanner fournisseur.

```text
Kraken catalogue
-> compatibilité déterministe
-> rotation bornée de marchés à sonder
-> snapshots de recherche causaux
-> candidats factuels
-> même Agent -> watchlist
-> watchlist + positions ouvertes
-> RoutedExecutableMarketDataSource
```

Le filtrage déterministe vérifie uniquement des propriétés techniques/factuelles : type, quote, statut, contrat PERPETUAL linéaire, fraîcheur et profondeur minimale d'observation. Aucun indicateur n'est converti en score d'opportunité.

## 4. `MarketDiscoveryPolicy`

La politique est persistée dans la Campaign quand la découverte est activée. Elle borne les appels et la taille des inputs LLM : cadence catalogue/watchlist, timeout global de refresh, nombre maximum de marchés sondés, candidats et éléments de watchlist, fraîcheur et observations minimales.

Le champ `market_discovery` est `exclude_if=None` dans le modèle Pydantic. Une ancienne Campaign statique sérialisée avant 19.4 conserve donc son payload et son digest historique.

## 5. `MarketDiscoveryCoordinator`

Le coordinateur détient uniquement un cache process-local :

- catalogue ;
- timestamp de refresh ;
- curseur de probe rotatif ;
- dernière watchlist stratégique valide ;
- dernier audit de découverte.

Le probe rotatif évite qu'une taille candidate bornée sélectionne toujours le même préfixe lexical. Ce mécanisme assure une couverture technique progressive ; il ne classe pas les marchés.

Le refresh est borné par `asyncio.timeout`. Une erreur Kraken, LLM ou validation entraîne un fallback vers la watchlist précédente, ou vers le bootstrap si aucune watchlist n'existe encore. L'échec est temporisé jusqu'à la prochaine cadence au lieu d'être réessayé à chaque cycle.

## 6. Même Agent IA

`OpenAIWatchlistSelector` est un adaptateur sur **la même instance** `OpenAIDecisionProvider`. Il réutilise son client, son modèle et son horloge. La phase watchlist n'expose pas de tools : toutes les données présentées ont déjà été collectées par le pipeline déterministe de discovery.

Sortie structurée : une liste bornée de `(symbol, market_type, rationale)` exclusivement parmi les candidats. La sélection d'une watchlist ne crée aucun `ExecutionIntent`.

`StrategyInstructionsClient` ajoute le contrat discovery seulement lorsqu'un `market_discovery_context` est présent ; les prompts des cycles statiques restent inchangés.

## 7. Runner dynamique et CapacityEvaluator

`DynamicMarketTradingCycleRunner` est un orchestrateur mince qui prépare l'univers puis délègue le cycle de trading au `TradingCycleRunner` canonique. Risk/Broker/validations causales ne sont pas dupliqués.

Avant discovery, le runner calcule une première évaluation de capacité sur :

```text
bootstrap + watchlist en cache + positions ouvertes
```

Si le mode est `MANAGEMENT`, il enregistre `SKIPPED_MANAGEMENT` et ne déclenche aucune révision IA de watchlist. Le runner canonique recalcule ensuite la capacité sur l'univers effectif et applique les barrières 19.3.

En NORMAL :

```text
univers effectif = watchlist courante + marchés des positions ouvertes
```

Les positions ouvertes gagnent toujours sur la sortie de watchlist afin de rester gérables.

## 8. Exécution dynamique

`RoutedExecutableMarketDataSource` conserve son mode statique historique par défaut. En mode dynamique, une adresse hors bootstrap est acceptée uniquement si :

- symbole canonique ;
- type autorisé par `market_discovery.market_types` ;
- quote identique à `paper_settlement_asset` ;
- source Kraken capable de fournir le snapshot exact ;
- PERPETUAL effectivement linéaire.

L'existence/exécutabilité réelle reste prouvée par la source canonique, jamais par le texte LLM.

## 9. RiskPolicy et whitelist

`risk_allowed_pairs` devient nullable uniquement pour une Campaign dynamique. Valeur non nulle = whitelist supplémentaire ferme. Valeur nulle = pas de whitelist symbolique explicite, mais toutes les autres contraintes Risk restent actives.

Une Campaign statique continue d'exiger `risk_allowed_pairs` et tous ses bootstrap markets doivent y être présents.

## 10. Monitoring dynamique

Les monitors existants restent déterministes :

- SPOT : lorsqu'une position dynamique est détenue, le symbole `ASSET/settlement_asset` est dérivé uniquement pour demander un mark Kraken ;
- PERPETUAL : une position dynamique peut être marquée même si son symbole n'était pas dans le bootstrap initial.

Ces monitors ne modifient jamais la watchlist et n'appellent jamais le LLM.

## 11. Persistence / audit

Aucune migration SQL en 19.4. `DiscoveredMarketSelectionInput` étend `MarketSelectionInput` avec un `MarketDiscoveryAudit`. Le repository existant sérialise déjà le modèle complet dans `market_selection_input_payload` ; les faits de discovery entrent donc automatiquement dans l'audit et son digest.

L'audit indique au minimum : statut, counts, faits candidats, ancienne/nouvelle watchlist, ajout/maintien/retrait, rationales, erreur éventuelle et date du prochain refresh.

## 12. Recovery

`DynamicCampaignPaperRunLifecycle` sous-classe le lifecycle canonique uniquement pour la reprise dynamique. Avant la validation du parent, il lit le `current_portfolio_payload` durable et élargit l'univers du nouveau run avec les marchés des positions réellement ouvertes. Le base lifecycle effectue ensuite le handoff, les validations et la restauration habituels.

La watchlist n'est pas replayée ni persistée comme table mutable. Après reprise : positions d'abord ; watchlist reconstruite ensuite en NORMAL.

## 13. Comptabilité et Risk inchangés

Les Batches 19.1 à 19.3 restent canoniques : comptabilité SPOT, mark-to-market, equity/exposition, CapacityEvaluator partagé avec la même RiskPolicy et veto d'augmentation d'exposition en MANAGEMENT.

## 14. Frontend

Le configurateur simple produit une Campaign dynamique avec un bootstrap/secours. Les écrans avancés restent compatibles avec les Campaigns statiques. Aucune logique d'admissibilité, de ranking ou de Risk n'est introduite en TypeScript.

## 15. Hors périmètre

Explicabilité dédiée, candles/WebSocket/charts, LIVE, multi-agent, ranking algorithmique stratégique et nouvelle stratégie de trading restent hors Batch 19.4.
