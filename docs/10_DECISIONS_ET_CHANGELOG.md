# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs, les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers Broker/Kraken, SPOT sans short/levier, PERPETUAL selon les capacités intégrées, audit durable, no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence courante

```text
HEAD GitHub vérifié après 19.9C        : b59020a4b354d9d56d593f3e39bcd608824bcd42
Référence intégrée                     : b59020a4b354d9d56d593f3e39bcd608824bcd42
Batch 19.9C                            : intégré à GitHub `main`
Validation opérateur post-19.9C        : frontend 29/29 ; lint/typecheck/build PASS ; git diff --check sans erreur
```

## Décisions historiques toujours actives

- ADR-173 à ADR-181 : StrategyRevision immuable, contrat Agent protégé, digests, Campaign snapshot, identité expérimentale, distinction Campaign/paper_run, runtime backend et recovery ;
- ADR-182 à ADR-190 : frontend client du Control Plane, API/validators backend, preview canonique, activation/reprise distinctes et typing frontière ;
- ADR-191 à ADR-204 : cockpit opérateur, aide progressive, règles métier backend et dark mode ;
- ADR-205 à ADR-226 : comptabilité, monitoring, `NORMAL`/`MANAGEMENT`, discovery/watchlist, whitelist et recovery ;
- ADR-227 à ADR-230 : explicabilité ;
- ADR-231 à ADR-238 : candles/streaming, vue Marchés, univers sans ranking frontend, markers de fills et Lightweight Charts comme rendu uniquement ;
- ADR-239 : overlays de position strictement issus du portefeuille backend ;
- ADR-240 à ADR-247 : façade Session, lifecycle, immutabilité et modes de marchés ;
- ADR-248 à ADR-255 : Trading Style, coûts Agent et contexte stratégique multi-timeframes ;
- ADR-256 à ADR-258 : UX Session du style, recommandations explicites et compatibilité legacy.

## ADR-240 — Session est une façade UX, pas un nouvel agrégat persistant

**ADOPTÉ AU BATCH 19.8.**

`Session` devient le concept utilisateur principal mais son identité technique reste la `Strategy`. Aucune table `sessions` n'est créée. La projection repose sur Strategy, StrategyRevision, Campaign, paper_run et le runtime actif.

Raison : préserver l'audit et les composants canoniques tout en masquant leur complexité dans le parcours normal.

## ADR-241 — La création Session est atomique côté backend

**ADOPTÉ AU BATCH 19.8.**

La création Strategy + StrategyRevision 1 + Campaign est réalisée dans une seule transaction persistence. Le navigateur n'orchestre plus plusieurs écritures pouvant laisser une Strategy orpheline si la création Campaign échoue.

`Créer et démarrer` enchaîne ensuite activation fraîche et démarrage du moteur dans le backend.

Le correctif post-19.8 précise l'implémentation de cet invariant : Strategy + StrategyRevision sont flushées avant l'INSERT Campaign afin que la FK composite `fk_campaigns_strategy_revision` soit satisfaite sur PostgreSQL. Ce flush intermédiaire ne termine pas la transaction et ne réduit donc pas l'atomicité.

## ADR-242 — Modifier une Session produit de nouveaux faits immuables

**ADOPTÉ AU BATCH 19.8.**

- rename seul : mise à jour du nom de Strategy ;
- prompt modifié : nouvelle StrategyRevision ;
- configuration modifiée : nouvelle Campaign ;
- les Campaigns et revisions historiques ne sont jamais écrasées.

Une Session RUNNING ne peut pas être modifiée silencieusement. Elle doit d'abord être arrêtée.

## ADR-243 — Supprimer une Session signifie archiver

**ADOPTÉ AU BATCH 19.8.**

L'action UX `Supprimer` utilise `Strategy.archived_at`. Campaigns, paper_runs, cycles, décisions, Risk assessments, executions/fills et données P&L restent persistés. La restauration d'une Session archivée est hors scope v1.

## ADR-244 — Les statuts Session sont dérivés

**ADOPTÉ AU BATCH 19.8.**

Aucune colonne de statut parallèle n'est ajoutée. Le statut dépend de l'archivage Strategy, de la Campaign courante, des runs existants et du runtime actif : `DRAFT`, `READY`, `RUNNING`, `STOPPED`, `RESUMABLE`, `ARCHIVED`.

## ADR-245 — Arrêter une Session ferme le runtime et le paper_run

**ADOPTÉ AU BATCH 19.8.**

Le simple `engine.stop` historique laisse la Campaign chargée. L'action Session `stop` doit être une fin explicite de Session : arrêter la boucle si nécessaire, fermer le runtime, persister `ended_at` sur le `paper_run` puis libérer la Campaign active.

Le contrôle technique `engine.stop` reste disponible dans le mode avancé pour les diagnostics historiques.

## ADR-246 — Deux modes de marchés explicites

**ADOPTÉ AU BATCH 19.8.**

- `AUTOMATIC_AI` : `market_discovery` présent ; le bootstrap/fallback ne constitue pas une obligation de trader ; la watchlist reste choisie par le même Agent IA parmi les candidats déterministes ;
- `MANUAL` : `market_discovery = null`, `paper_executable_markets` et `risk_allowed_pairs` sont alignés sur l'univers explicite.

Aucun second moteur de sélection ni ranking TypeScript n'est introduit.

## ADR-247 — Les defaults Market Discovery restent canoniques et visibles

**ADOPTÉ AU BATCH 19.8.**

La configuration avancée expose les valeurs effectives : 900 s catalogue, 900 s watchlist, timeout 45 s, probe 24, candidats 12, watchlist 6, snapshot 120 s, 2 observations minimales, fenêtre complète non requise. Le backend conserve la validation autoritaire.

## ADR-248 — Trading Style est une propriété versionnée de Campaign

**ADOPTÉ AU BATCH 19.9A.**

`TradingStyle` contient `SCALP` et `SWING`. La Campaign persiste `trading_style` et `trading_style_mapping_version`. Ces champs sont optionnels et omis de la sérialisation canonique lorsqu'ils sont absents : les digests historiques restent identiques. `paper-control-plane-config-v1` est conservé et aucune migration SQL n'est nécessaire.

## ADR-249 — Style et agressivité sont orthogonaux

**ADOPTÉ AU BATCH 19.9A.**

Le style décrit l'horizon et la manière d'interpréter les faits de marché ; l'agressivité décrit la posture stratégique. Aucun mapping style -> agressivité ni style -> Risk n'est autorisé.

## ADR-250 — Les coûts PAPER sont un contexte factuel de l'Agent

**ADOPTÉ AU BATCH 19.9A.**

`ExecutionCostContext` expose exactement `paper_fee_rate`, `paper_spread_bps` et `paper_slippage_bps` aux phases stratégiques. Le backend ne convertit pas ces coûts en score d'opportunité.

## ADR-251 — Un même overlay contextuel suit les trois phases Agent

**ADOPTÉ AU BATCH 19.9A.**

`TradingStyleContext` + `ExecutionCostContext` sont propagés à `MarketDiscoveryInput`, `MarketSelectionInput` et `AgentInput`. Le runner dynamique doit les transmettre au runner canonique qu'il reconstruit. Aucun second Agent n'est créé et `agent-contract-v1` reste inchangé.

## ADR-252 — Aucune sortie temporisée liée au style

**ADOPTÉ AU BATCH 19.9A.**

Les guidances de détention SCALP/SWING sont descriptives. Une durée écoulée ne produit jamais automatiquement SELL/HOLD, ne ferme aucune position et ne modifie aucune règle Risk.

## ADR-253 — Le contexte stratégique multi-timeframes réutilise le pipeline candles canonique

**ADOPTÉ AU BATCH 19.9B.**

`CampaignRuntimeManager` reçoit le `CandleStreamService` backend partagé et l'injecte dans la composition Campaign. `StrategicMultiTimeframeContextService` lit ce service ; aucun second provider, cache ou pipeline OHLC stratégique n'est créé.

La lecture décisionnelle utilise `history_as_of(...)` afin de ne retenir que les révisions et candles disponibles à l'instant `as_of`. Les gaps restent explicites et ne sont jamais interpolés.

## ADR-254 — Un snapshot multi-timeframes causal et borné est partagé dans le cycle Agent

**ADOPTÉ AU BATCH 19.9B.**

Le contexte `strategic-mtf-v1` est construit au `MarketSelectionInput.created_at`, attaché à Market Selection puis réutilisé inchangé pour l'`AgentInput` final du même cycle. Discovery reste légère et ne reçoit pas l'historique multi-timeframes riche.

Les bornes v1 sont explicites : 32 marchés maximum, 128 KiB JSON maximum, concurrence de lecture limitée à 4 et profondeur bornée par timeframe. Les états `AVAILABLE`, `PARTIAL`, `MISSING`, les gaps et stale sont conservés comme faits descriptifs.

## ADR-255 — Le multi-timeframes enrichit les faits, pas l'autorité stratégique ou Risk

**ADOPTÉ AU BATCH 19.9B.**

Le service 19.9B consomme le mapping `trading-style-map-v1` sans le dupliquer. Les statistiques OHLCV résumées ne produisent aucune règle `indicateur -> BUY/SELL/HOLD`. Le même Agent stratégique décide ; `ExecutionCostContext` reste séparé ; Risk Engine, broker, contrats de sortie Agent et timers de position restent inchangés.

## ADR-256 — Le style est exposé dans la Session sans coupler les dimensions

**ADOPTÉ AU BATCH 19.9C.**

Le configurateur Session expose `SCALP` / `SWING`, mais style, agressivité, mode de sélection des marchés et Risk restent quatre dimensions indépendantes. Le frontend persiste `trading_style` et `trading_style_mapping_version` sans créer de nouvelle autorité métier.

## ADR-257 — Changer de style ne réécrit jamais silencieusement les personnalisations

**ADOPTÉ AU BATCH 19.9C.**

Un changement de style modifie uniquement le style sélectionné. Les recommandations SCALP `60 s` / `300 s` et SWING `900 s` / `1800 s` pour cadence stratégique / watchlist refresh ne sont appliquées que lors de l'initialisation UX prévue ou via l'action explicite `Réappliquer les valeurs conseillées`. L'édition d'une Session reconstruit toujours les valeurs réellement persistées.

## ADR-258 — Legacy sans inférence et timeframes d'affichage en lecture seule

**ADOPTÉ AU BATCH 19.9C.**

Une Campaign historique sans `trading_style` reste `Hérité / non défini` ; le frontend n'infère aucun style. Les timeframes associées sont affichées en lecture seule depuis `trading-style-map-v1` : SCALP `1m/5m/15m/30m`, SWING `1h/4h/1d`. Cette représentation d'affichage ne construit pas le contexte runtime `strategic-mtf-v1`.

## Changelog — 2026-09-26 — Batch 19.9C intégré

- commit GitHub `b59020a4b354d9d56d593f3e39bcd608824bcd42` (`feat: add session trading style UX`) ;
- parent `792711217513db6e9825a96e15ec59c74d33b192` (`docs: sync post-19.9B state`) ;
- exposition `SCALP` / `SWING` dans le configurateur Session ;
- persistance de `trading_style` et `trading_style_mapping_version` avec `trading-style-map-v1` ;
- affichage des timeframes stratégiques en lecture seule ;
- recommandations UX SCALP `60 s` / `300 s` et SWING `900 s` / `1800 s` ;
- changement de style sans écrasement silencieux et réapplication explicite des recommandations ;
- compatibilité des Sessions historiques via `Hérité / non défini`, sans inférence ;
- reconstruction persist-first des formulaires ;
- style, agressivité, sélection des marchés et Risk maintenus indépendants ;
- aucun fichier backend, aucun timer de fermeture et aucune règle runtime cachée ajoutés ;
- validation locale opérateur : `pnpm test` 29/29, lint/typecheck/build PASS, `git diff --check` sans erreur ; warnings Node `MODULE_TYPELESS_PACKAGE_JSON` et Git LF → CRLF non bloquants.

## Changelog — 2026-09-26 — Batch 19.9B intégré

- commit GitHub `88be7d50111c2e6210225071d3f1af3f7f07b4f0` (`feat: add strategic multi-timeframe context`) ;
- parent `a4f841c7c23e3af1b44a9cbb104ccc44d5cad2d9` (`docs: sync post-19.9A state`) ;
- ajout de `StrategicMultiTimeframeContextService` et du contrat `strategic-mtf-v1` ;
- ajout de `MultiTimeframeDecisionProvider` autour du même Agent stratégique ;
- partage du `CandleStreamService` backend entre cockpit et Campaign runtimes ;
- ajout de la lecture causale `history_as_of(...)` ;
- mapping SCALP/SWING toujours exclusivement fourni par `trading-style-map-v1` ;
- contexte compact : 32 marchés max, 128 KiB JSON max, concurrence et profondeurs bornées ;
- snapshot Market Selection réutilisé pour la décision finale ;
- Discovery maintenue légère ;
- gaps, stale et disponibilité `AVAILABLE` / `PARTIAL` / `MISSING` exposés explicitement ;
- `ExecutionCostContext`, Risk Engine, broker et `agent-contract-v1` inchangés ;
- compatibilité préservée pour les Campaigns historiques sans `trading_style` ;
- validation locale : tests ciblés `57 passed, 2 warnings` ; backend complet `629 passed, 2 warnings` ; `git diff --check` sans erreur.

## Changelog — 2026-09-26 — Batch 19.9A intégré

- commit GitHub `4b6a851addea74d72af2c433827c935a87d4bc04` (`feat: add canonical scalp swing trading style`) ;
- ajout de `TradingStyle.SCALP` / `TradingStyle.SWING` ;
- mapping canonique `trading-style-map-v1` ;
- ajout de `TradingStyleContext` et `ExecutionCostContext` ;
- extension rétrocompatible de `CampaignConfiguration` sans migration SQL ;
- préservation du payload/digest historique lorsque le style est absent ;
- propagation structurée vers Discovery, Market Selection et décision finale ;
- forwarding explicite dans `DynamicMarketTradingCycleRunner` ;
- sections d'instructions canoniques dérivées des contextes ;
- Risk Engine, `RiskPolicy`, cadence persistée et contrat `agent-contract-v1` inchangés ;
- fondations Trading Style désormais consommées par le contexte multi-timeframes intégré au Batch 19.9B.

## Changelog — 2026-09-25 — Correctif post-19.8 création Session

- commit GitHub `0d964624a641aad509f5728264f873c1a837af97` (`fix: preserve session creation FK ordering`) ;
- correction de l'ordre de flush SQLAlchemy lors de la création atomique Strategy + StrategyRevision + Campaign ;
- Strategy + Revision sont flushées avant Campaign dans la même transaction ;
- aucune migration SQL ni modification de schéma ;
- ajout d'un test de non-régression avec foreign keys SQLite activées ;
- le configurateur affiche désormais le feedback d'erreur backend lors d'un échec create/start ;
- cause observée avant correction : `HTTP 409 · session creation conflicted` sur PostgreSQL ;
- validation fonctionnelle opérateur : création et démarrage de Session réussis après redémarrage backend ;
- validation locale : backend `607 passed`, 2 warnings ; frontend `21/21`, lint/typecheck/build passés ; `git diff --check` sans erreur.

## Changelog — 2026-09-25 — Batch 19.8 intégré

- commit GitHub `f3a8eae8528648c07723aa97350852428254acc7` (`feat: add user-facing Sessions workflow`) ;
- façade backend Session sans migration SQL ;
- endpoints CRUD + start/stop/resume/run-cycle ;
- création atomique ;
- update versionné et immutable-history ;
- duplication indépendante et archivage logique ;
- arrêt de Session avec fermeture du run ;
- navigation Sessions et page de gestion ;
- configurateur simple/avancé réutilisé pour create/edit ;
- modes Automatique IA / Manuel ;
- typing frontend de `market_discovery` et whitelist Risk aligné sur le backend ;
- validation locale initiale : backend `606 passed`, frontend `21/21`, lint/typecheck/build passés, `git diff --check` sans erreur.
