# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading **PAPER** pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est uniquement un cockpit de contrôle et de visualisation.

Référence GitHub intégrée vérifiée après le recalibrage net/cost-aware :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
Dernier commit fonctionnel : 463850d8281faebe86a6ee733d58781c349015d0
Commit                     : refactor: make strategic agent cost aware
```

Le correctif PAPER PERPETUAL, le cycle multi-décisions / multi-marchés, l'inspecteur LLM, le refresh initial des marks PAPER, le premier recalibrage des prompts stratégiques et le recalibrage **cost-aware / net-equity-aware** sont intégrés dans cette base.

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

L'objectif économique transmis aux Campaigns courantes est la **progression de l'equity nette après coûts**. Les frais, le spread, le slippage et le funding lorsqu'il est disponible dans les faits fournis font partie du résultat économique. Cet objectif n'introduit aucun seuil de profit, quota de trades, cooldown, durée minimale, score algorithmique ni garantie de rendement.

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

Un marché admissible ou techniquement tradable n'est pas, à lui seul, une opportunité économiquement intéressante. La watchlist reste un choix du même Agent et doit servir la comparaison stratégique des meilleures opportunités disponibles, sans score déterministe.

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

Le contexte `position-management-v1` reste descriptif et reconstructible. Il ne contient aucun `should_sell`, take-profit, timer ou signal algorithmique. Les formulations de gestion sont directionnellement neutres sur PERPETUAL : réduire un LONG utilise `SELL`, réduire un SHORT utilise `BUY`, et aucune direction n'est privilégiée.

## 8. Trading Style et contexte multi-timeframes

`TradingStyle.SCALP` / `SWING`, `trading-style-map-v1`, `ExecutionCostContext` et `strategic-mtf-v1` restent canoniques.

- SCALP : `1m`, `5m`, `15m`, `30m` ;
- SWING : `1h`, `4h`, `1d`.

`StrategicMultiTimeframeContextService` réutilise le `CandleStreamService` backend partagé. `history_as_of(...)` impose la causalité : aucune révision/candle postérieure au temps de décision n'est injectée. Les gaps restent explicites, sans interpolation.

Le style enrichit le jugement de l'Agent mais ne devient ni une règle Risk, ni un timer de sortie, ni un ranking déterministe.

Le style SCALP actuel est un mode minute/intraday. Il n'est pas assimilé à du HFT sub-milliseconde et reste compatible avec un Agent LLM tant que les contrôles de fraîcheur et les latences observées sont cohérents avec le cas d'usage.

## 9. Agressivité stratégique

L'agressivité reste un niveau canonique entier de `1` à `10`. Le mapping historique `aggressiveness-map-v1` reste réservé aux identités expérimentales durables ; les instructions LLM courantes utilisent désormais `aggressiveness-map-v3`. Le mapping courant précédent `v2` reste un état Git historique et n'est pas réécrit.

L'agressivité courante peut influencer :

- la volonté d'agir ;
- le degré d'initiative ;
- l'acceptation d'une opportunité moins parfaite mais encore défendable aux niveaux élevés.

Elle ne doit pas être interprétée comme une obligation d'augmenter le nombre de trades, le turnover, les micro-trades ou la rotation. Même au niveau `10/10`, la quantité proposée reste proportionnée à la qualité/conviction de la thèse, aux faits fournis, aux coûts, à l'exposition existante et au capital déjà engagé.

`HOLD`, conserver du cash ou conserver une position existante restent des allocations stratégiques valides à tous les niveaux. Une faible conviction ne doit pas être transformée mécaniquement en petite position « pour essayer ».

## 10. Allocation du capital et coût d'opportunité

Dans un univers multi-marchés, l'Agent raisonne sur l'allocation globale du capital entre cash, positions existantes et nouvelles opportunités.

Une rotation n'est pas justifiée simplement parce qu'une autre opportunité est tradable. Réduire ou fermer une position puis ouvrir ou augmenter une autre entraîne plusieurs coûts d'exécution. L'Agent doit donc comparer la position/cash actuels aux alternatives et ne provoquer une rotation que lorsque la justification stratégique reste suffisamment forte après prise en compte des coûts disponibles.

Cette règle reste qualitative et stratégique : aucun seuil chiffré, minimum de profit, durée de détention, cooldown ou score d'opportunité n'est introduit.

## 11. Cycle stratégique multi-marchés / multi-décisions

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

## 12. Causalité intra-cycle et autorité Risk

Pour chaque décision, Risk évalue l'état de portefeuille **courant**, donc après les éventuelles exécutions des décisions précédentes du même cycle.

Conséquences :

- un SELL peut libérer du capital qu'une décision ultérieure du même plan peut ensuite utiliser ;
- un BUY précédent peut réduire la capacité disponible pour une décision suivante ;
- `HOLD` et `REJECT` restent des faits auditables mais ne stoppent pas les décisions suivantes ;
- aucune décision ultérieure n'est évaluée sur un snapshot de portefeuille obsolète.

Risk conserve la décision finale `ALLOW` / `MODIFY` / `REJECT` pour chaque élément du plan. Aucun output LLM ne devient directement un ordre.

## 13. Contrat quantité/action

Le schéma Structured Outputs et la validation applicative restent alignés :

```text
BUY  -> proposed_quantity > 0
SELL -> proposed_quantity > 0
HOLD -> proposed_quantity = null
```

Le chemin multi-marchés conserve `market_states` comme univers causal, `management_mode=true` comme restriction de gestion, l'interdiction du short SPOT et le contrôle Risk exclusif du levier, de la marge, de l'exposition, de la liquidation et de `reduce_only`.

Sur PERPETUAL, le contrat reste symétrique : `BUY` ouvre/augmente LONG ou réduit SHORT ; `SELL` ouvre/augmente SHORT ou réduit LONG. Le présent recalibrage n'ajoute aucun biais LONG/SHORT déterministe.

## 14. Atomicité PAPER du cycle

Le cycle multi-décisions est transactionnel au niveau du ledger PAPER : un checkpoint est pris au début de la trajectoire.

Si une défaillance **technique** survient dans Risk ou Broker après des mutations PAPER, le cycle devient `FAILED` et le ledger est restauré au checkpoint du début de cycle. Les faits d'échec restent auditables ; les effets économiques partiels du cycle ne subsistent pas dans le portefeuille PAPER.

`HOLD` et `REJECT` ne sont pas des erreurs techniques et ne provoquent pas de rollback.

## 15. Persistence et compatibilité historique

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

## 16. API, cockpit et analytics

L'API et le cockpit exposent la trajectoire ordonnée du cycle plutôt qu'un seul triplet Agent/Risk/exécution.

Les analytics restent économiques : ils comptent les fills/trades réellement exécutés. Un `HOLD`, un `REJECT` ou une décision sans fill ne devient pas artificiellement un trade.

Le frontend ne recalcule ni Risk, ni P&L, ni causalité. Il affiche les faits persistés dans leur ordre.

L'inspecteur LLM intégré permet de visualiser en lecture seule les payloads réellement envoyés à la Responses API, avec rétention bornée et sans exposer les secrets de transport.

## 17. Comptabilité, monitoring et charts

Accounting, mark-to-market, equity, exposition, monitors, candles, streaming, markers de fills et overlays restent canoniques côté backend. Le contexte candles sert à informer l'Agent ; il n'est jamais une source parallèle de vérité d'exécution ou de portefeuille.

Les moniteurs PAPER effectuent désormais un premier refresh de marks avant que le runtime soit considéré initialisé. En cas d'échec, la valorisation reste incomplète et Capacity/Risk restent fail-closed.

## 18. Fraîcheur des données

Risk possède un contrôle explicite de fraîcheur :

- timestamp indisponible -> `MARKET_FRESHNESS_UNAVAILABLE` ;
- dépassement de `RiskPolicy.stale_after` -> `MARKET_DATA_STALE`.

La configuration `kraken_stale_after_seconds` est optionnelle et vaut `None` par défaut. Elle qualifie la fraîcheur des données provider lorsqu'elle est configurée. Au HEAD audité, la composition Campaign ne renseigne pas `RiskPolicy.stale_after`, donc le rejet stale existe dans Risk mais n'est pas activé par défaut sur ce chemin. Un futur durcissement SCALP doit d'abord mesurer la latence réelle `MarketState -> LLM -> Risk` avant de fixer un seuil spécifique.

## 19. Constat expérimental motivant le recalibrage cost-aware

Une session PAPER réelle d'environ 9 heures, partie d'un capital de `100`, a montré un turnover élevé : `1 246` fills sur `395` cycles, avec un P&L brut positif d'environ `+0,727` mais une equity finale d'environ `97,713` et un P&L net d'environ `-2,287` après frais, spread, slippage et funding.

Ce run montre qu'une activité importante peut être économiquement défavorable lorsque l'avantage brut est trop faible relativement aux coûts. Il motive le recalibrage vers la qualité économique nette et l'allocation du capital. **Il ne démontre pas à lui seul la performance générale ni un biais structurel durable de la stratégie.**

## 20. Audit du biais SELL / SHORT PERPETUAL

L'audit du contrat courant classe les éléments ainsi :

- **confirmé** : le mapping BUY/SELL PERPETUAL, le planner, la sélection multi-marchés et l'autorité Risk sont directionnellement symétriques ; aucune règle centrale n'impose ou ne favorise explicitement SHORT ;
- **confirmé** : le mapping d'agressivité courant `v2` poussait davantage l'initiative, la rotation et parfois la fréquence potentielle, ce qui pouvait favoriser le turnover global sans expliquer à lui seul la direction SHORT ;
- **confirmé** : le texte générique de gestion parlait de « signal automatique de vente », formulation asymétrique pour la réduction d'un SHORT ; elle est neutralisée dans le recalibrage intégré ;
- **corrigé** : objectif explicite d'equity nette après coûts, coût d'opportunité et comparaison rotation/conservation ;
- **à décider** : l'existence d'un biais SHORT réellement persistant dans les décisions du modèle. Une seule session ne suffit pas à l'établir ; il faut comparer plusieurs runs et les contextes de marché avant toute règle corrective directionnelle.

Aucun quota LONG/SHORT, contre-biais déterministe ni modification du Risk Engine n'est introduit.

## 21. Hors périmètre actuel

- LIVE ;
- `ADAPTIVE_AI` tant qu'il n'est pas cadré ;
- modification du Risk Engine selon le style ;
- fermeture automatique selon une durée de détention ;
- take-profit fixe ou trailing stop déterministe ;
- ranking technique déterministe d'opportunité ;
- seuil minimum de profit imposé à BUY/SELL ;
- cooldown stratégique arbitraire ;
- nombre maximal de trades choisi par une règle de stratégie ;
- quota LONG/SHORT ;
- second pipeline/cache OHLC ou second Agent stratégique ;
- promesse de rendement ;
- seuil SCALP stale spécifique non mesuré.

## 22. Validation

Validation locale du recalibrage intégré dans `463850d`, réalisée le 28 septembre 2026 :

- tests ciblés `test_control_plane_prompt.py`, `test_multi_market_provider.py`, `test_trading_style.py` et `test_position_management_rotation.py` : `47/47` passés ;
- suite backend complète `pytest -q` : `100 %` passée, sans échec ;
- deux avertissements de dépréciation Starlette/AnyIO restent présents et sont hors périmètre.

Les validations historiques des batches précédents restent consultables dans leur documentation et dans Git.
