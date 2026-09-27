# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading **PAPER** pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est uniquement un cockpit de contrôle et de visualisation.

Référence GitHub intégrée vérifiée au lancement du présent recalibrage :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 5fdd9a32bce45deda30c652b6b6f8c59e4996559
Commit     : fix: refresh paper marks before trading starts
```

Le correctif PAPER PERPETUAL, le cycle multi-décisions / multi-marchés, l'inspecteur LLM et le refresh initial des marks PAPER sont intégrés dans cette base.

## 2. Invariants fonctionnels

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement, LIVE séparé ;
- SPOT + PERPETUAL selon les capacités intégrées ;
- FUTURE daté interdit ;
- actions `BUY`, `SELL`, `HOLD` ;
- Luna par défaut, Sol sélectionnable ;
- Risk Engine déterministe = autorité finale ;
- aucune sortie LLM/tool ne déclenche directement Broker/Kraken ;
- coûts PAPER, spread, slippage, accounting et mark-to-market canoniques dans le backend ;
- toutes les décisions, sélections, `HOLD` et `REJECT` auditables ;
- aucun look-ahead ;
- aucun secret dans prompts/logs/frontend/Git ;
- frontend non nécessaire au fonctionnement du moteur.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

L'objectif expérimental `+4 %/jour` reste une cible de recherche non garantie au niveau projet. Il ne doit pas être injecté dans les instructions stratégiques courantes du LLM ni être utilisé pour forcer de l'activité.

## 3. Modèle utilisateur : Session

`Session` reste une façade/projection sur les composants canoniques :

```text
Session UX
-> Strategy = identité stable
-> StrategyRevision(s) = instructions immuables
-> Campaign(s) = snapshots de configuration immuables
-> paper_run(s) = exécutions/recovery
```

L'identifiant de Session est le `strategy_id`. Les objets techniques restent disponibles dans le parcours avancé.

## 4. Façade backend Session

La façade `/api/v1/sessions` conserve : création atomique, liste/détail, modification versionnée, duplication, archivage logique et lifecycle start/stop/resume/run-cycle.

Aucune table `sessions` n'est introduite. `Strategy.archived_at` porte l'archivage logique. Une modification de prompt crée une `StrategyRevision`, une modification de configuration crée une `Campaign`, et l'historique n'est jamais réécrit.

Une Campaign déjà exécutée ne peut pas être fresh-activée silencieusement ; la reprise est explicite. Fermer le cockpit ne stoppe pas le moteur backend.

## 5. Univers de marchés

### Automatique — IA

```text
Kraken catalogue
-> filtre déterministe d'admissibilité
-> candidats
-> même Agent IA choisit une watchlist
-> contexte stratégique causal
-> même Agent produit le plan décisionnel du cycle
```

`paper_executable_markets` est un bootstrap/fallback. `market_discovery` contient la politique dynamique.

### Manuel

- `market_discovery = null` ;
- `paper_executable_markets` = univers choisi ;
- `risk_allowed_pairs` = même univers ;
- le même Agent conserve la décision stratégique dans cet univers ;
- Risk reste final.

## 6. Market Discovery

Les defaults backend restent :

```text
catalog_refresh_seconds      = 900
watchlist_refresh_seconds    = 900
refresh_timeout_seconds      = 45
candidate_probe_limit        = 24
candidate_limit              = 12
watchlist_limit              = 6
max_snapshot_age_seconds     = 120
min_window_observations      = 2
require_complete_window      = false
```

Le filtrage déterministe reste technique/factuel et ne produit aucun score stratégique. Les recommandations UX de cadence liées au style n'écrasent jamais silencieusement les valeurs persistées.

## 7. NORMAL / MANAGEMENT et gestion des positions

Les positions ouvertes restent gérables en `NORMAL` comme en `MANAGEMENT`. `CapacityAssessment.management_markets` conserve les marchés correspondant aux positions ouvertes afin que le même Agent puisse arbitrer entre gestion d'inventaire, nouvelle opportunité et abstention.

En `MANAGEMENT`, aucune discovery destinée à ouvrir de nouvelles positions n'est lancée et Risk refuse toute hausse d'exposition incompatible.

Le contexte `position-management-v1` reste descriptif et reconstructible. Il ne contient aucun `should_sell`, take-profit, timer ou signal algorithmique.

## 8. Trading Style et contexte multi-timeframes

`TradingStyle.SCALP` / `SWING`, `trading-style-map-v1`, `ExecutionCostContext` et `strategic-mtf-v1` restent canoniques.

- SCALP : `1m`, `5m`, `15m`, `30m` ;
- SWING : `1h`, `4h`, `1d`.

`StrategicMultiTimeframeContextService` réutilise le `CandleStreamService` backend partagé. `history_as_of(...)` impose la causalité : aucune révision/candle postérieure au temps de décision n'est injectée. Les gaps restent explicites, sans interpolation.

Le style enrichit le jugement de l'Agent mais ne devient ni une règle Risk, ni un timer de sortie, ni un ranking déterministe.

Le style SCALP actuel est un mode minute/intraday. Il n'est pas assimilé à du HFT sub-milliseconde et reste compatible avec un Agent LLM tant que les contrôles de fraîcheur et les latences observées sont cohérents avec le cas d'usage.

## 9. Agressivité stratégique

L'agressivité reste un niveau canonique entier de `1` à `10`. Le mapping historique `aggressiveness-map-v1` reste réservé aux identités expérimentales durables ; les instructions LLM courantes utilisent `aggressiveness-map-v2`.

Elle peut influencer :

- la volonté d'agir ;
- le degré d'initiative ;
- la fréquence potentielle d'action ;
- la rotation stratégique ;
- l'acceptation d'une opportunité moins parfaite mais encore défendable.

Elle ne doit pas imposer une taille d'ordre. Même au niveau `10/10`, la quantité proposée reste proportionnée à la qualité/conviction de la thèse, aux faits fournis, aux coûts, à l'exposition existante et au capital déjà engagé.

`HOLD` reste valide à tous les niveaux. La qualité de la thèse prime sur la fréquence des trades ; aucun trade ne doit être généré simplement pour produire de l'activité ou atteindre une cible de rendement.

## 10. Cycle stratégique multi-marchés / multi-décisions

Le cycle décisionnel utilise un plan stratégique ordonné et borné.

Au **stade décisionnel du cycle**, le même Agent effectue un seul appel stratégique et produit plusieurs décisions portant sur des marchés distincts :

```text
contexte causal du cycle
-> même Agent IA
-> plan ordonné [D1, D2, ... Dn]
-> D1 : Risk -> exécution éventuelle -> portefeuille mis à jour
-> D2 : Risk -> exécution éventuelle -> portefeuille mis à jour
-> ...
-> Dn
```

`max_decisions_per_cycle` est configurable, vaut `6` par défaut et possède une limite dure de `20`.

Le plan peut mélanger `BUY`, `SELL` et `HOLD`. Il ne s'agit pas de plusieurs Agents ni de plusieurs appels stratégiques indépendants servant à contourner les contraintes : l'ordre est fourni par le même plan Agent et l'exécution est ensuite séquentielle.

## 11. Causalité intra-cycle et autorité Risk

Pour chaque décision, Risk évalue l'état de portefeuille **courant**, donc après les éventuelles exécutions des décisions précédentes du même cycle.

Conséquences :

- un SELL peut libérer du capital qu'une décision ultérieure du même plan peut ensuite utiliser ;
- un BUY précédent peut réduire la capacité disponible pour une décision suivante ;
- `HOLD` et `REJECT` restent des faits auditables mais ne stoppent pas les décisions suivantes ;
- aucune décision ultérieure n'est évaluée sur un snapshot de portefeuille obsolète.

Risk conserve la décision finale `ALLOW` / `MODIFY` / `REJECT` pour chaque élément du plan. Aucun output LLM ne devient directement un ordre.

## 12. Contrat quantité/action

Le schéma Structured Outputs et la validation applicative restent alignés :

```text
BUY  -> proposed_quantity > 0
SELL -> proposed_quantity > 0
HOLD -> proposed_quantity = null
```

Le chemin multi-marchés conserve `market_states` comme univers causal, `management_mode=true` comme restriction de gestion, l'interdiction du short SPOT et le contrôle Risk exclusif du levier, de la marge, de l'exposition, de la liquidation et de `reduce_only`.

## 13. Atomicité PAPER du cycle

Le cycle multi-décisions est transactionnel au niveau du ledger PAPER : un checkpoint est pris au début de la trajectoire.

Si une défaillance **technique** survient dans Risk ou Broker après des mutations PAPER, le cycle devient `FAILED` et le ledger est restauré au checkpoint du début de cycle. Les faits d'échec restent auditables ; les effets économiques partiels du cycle ne subsistent pas dans le portefeuille PAPER.

`HOLD` et `REJECT` ne sont pas des erreurs techniques et ne provoquent pas de rollback.

## 14. Persistence et compatibilité historique

Migration :

```text
0006_paper_control_plane
-> 0007_multi_decision_cycles
```

La persistence d'audit supporte explicitement des relations 1:N :

```text
TradingCycle
-> Decision(s) ordonnées
-> RiskAssessment(s)
-> ExecutionIntent(s)
-> Fill(s) réellement produits
```

Les anciens cycles/configurations restent lisibles. La compatibilité historique ne transforme pas artificiellement un ancien cycle mono-décision en plusieurs décisions.

Le `AGENT_SYSTEM_PROMPT` historique `agent-strategy-v4` reste figé pour préserver les protocoles expérimentaux v1/v2/v3 et leurs replays. Les Sessions/Campaigns actuelles passent par `StrategyInstructionsClient`, dont le contrat protégé courant peut évoluer de manière auditée.

## 15. API, cockpit et analytics

L'API et le cockpit exposent la trajectoire ordonnée du cycle plutôt qu'un seul triplet Agent/Risk/exécution.

Les analytics restent économiques : ils comptent les fills/trades réellement exécutés. Un `HOLD`, un `REJECT` ou une décision sans fill ne devient pas artificiellement un trade.

Le frontend ne recalcule ni Risk, ni P&L, ni causalité. Il affiche les faits persistés dans leur ordre.

L'inspecteur LLM intégré permet de visualiser en lecture seule les payloads réellement envoyés à la Responses API, avec rétention bornée et sans exposer les secrets de transport.

## 16. Comptabilité, monitoring et charts

Accounting, mark-to-market, equity, exposition, monitors, candles, streaming, markers de fills et overlays restent canoniques côté backend. Le contexte candles sert à informer l'Agent ; il n'est jamais une source parallèle de vérité d'exécution ou de portefeuille.

Les moniteurs PAPER effectuent désormais un premier refresh de marks avant que le runtime soit considéré initialisé. En cas d'échec, la valorisation reste incomplète et Capacity/Risk restent fail-closed.

## 17. Fraîcheur des données

Risk possède un contrôle explicite de fraîcheur :

- timestamp indisponible -> `MARKET_FRESHNESS_UNAVAILABLE` ;
- dépassement de `RiskPolicy.stale_after` -> `MARKET_DATA_STALE`.

La configuration `kraken_stale_after_seconds` est optionnelle et vaut `None` par défaut. Elle qualifie la fraîcheur des données provider lorsqu'elle est configurée. Au HEAD audité, la composition Campaign ne renseigne pas `RiskPolicy.stale_after`, donc le rejet stale existe dans Risk mais n'est pas activé par défaut sur ce chemin. Un futur durcissement SCALP doit d'abord mesurer la latence réelle `MarketState -> LLM -> Risk` avant de fixer un seuil spécifique.

## 18. Compatibilité avec la rotation du capital

La gestion stratégique des positions et la rotation peuvent s'étaler sur plusieurs cycles ou apparaître dans le même plan ordonné lorsque l'Agent le décide et que Risk l'autorise.

Il n'existe aucune règle déterministe `SELL -> BUY`, aucun take-profit fixe et aucun timer de liquidation.

## 19. Hors périmètre actuel

- LIVE ;
- `ADAPTIVE_AI` tant qu'il n'est pas cadré ;
- modification du Risk Engine selon le style ;
- fermeture automatique selon une durée de détention ;
- take-profit fixe ou trailing stop déterministe ;
- ranking technique déterministe d'opportunité ;
- second pipeline/cache OHLC ou second Agent stratégique ;
- promesse de rendement ;
- seuil SCALP stale spécifique non mesuré.

## 20. Validation

Les validations historiques des batches intégrés restent consultables dans leur documentation et dans Git. Toute validation du présent recalibrage doit être distinguée explicitement de ces résultats historiques.
