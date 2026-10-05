# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent disponibles dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les références nécessaires à la reprise.

## Principes actifs

Un seul Agent IA stratégique. Le Risk Engine déterministe conserve l'autorité finale. Aucune sortie LLM ne déclenche directement Broker/Kraken.

L'exécution courante est **PAPER uniquement** :

- SPOT exécutable sans short, levier ni marge ;
- PERPETUAL Kraken linéaire exécutable en LONG/SHORT sous contrôle Risk ;
- FUTURE daté non exécutable ;
- LIVE indisponible tant qu'un batch séparé ne l'active pas explicitement.

Le Market Attention Radar priorise **l'attention** et, depuis le Batch 49.2 proposé, peut fournir l'univers candidat au même Agent stratégique. Il ne décide jamais BUY/SELL/HOLD et ne possède aucune autorité Risk ou Broker.

## Référence courante

```text
Base GitHub auditée 49.2     : 3194fce620f5e31672c6b52ef8986daddeea3a25
Batch 49.1 intégré           : 3194fce — feat: activate perpetual paper trading
Batch 48 clôturé             : 8704eec — docs: mark batch 48 integrated
Batch 49.2                   : PATCH PROPOSÉ — NON INTÉGRÉ À LA LIVRAISON
```

## Changelog — 2026-10-05 — Batch 49.2 Radar shortlist vers univers Agent — patch proposé

Base GitHub auditée au démarrage : `3194fce620f5e31672c6b52ef8986daddeea3a25` (`feat: activate perpetual paper trading`).

### Audit confirmé

- `MarketAttentionOverviewV6Analytics.shortlist` conserve un `ExecutableMarket` typé sur chaque candidat ;
- le Radar final peut contenir `analytics_ranking` et `perpetual_analytics`, mais ces objets ne sont pas nécessaires pour construire l'univers Agent ;
- `MarketDiscoveryCoordinator` est déjà la frontière canonique de l'univers dynamique ;
- `DynamicMarketTradingCycleRunner` remet déjà une liste d'`ExecutableMarket` au runner multi-marchés canonique ;
- `MultiMarketTradingCycleRunner` acquiert les `MarketState` typés et crée `CycleDecisionPlanInput` ;
- `agent/planner.py` interdit déjà une décision hors des couples `(symbol, market_type)` causaux ;
- Risk et Broker sont appelés uniquement après le plan stratégique canonique ;
- `RoutedExecutableMarketDataSource` sait déjà valider/routiner SPOT et PERPETUAL dynamiques ;
- `MarketDiscoveryPolicy` rejette déjà `FUTURE` comme type dynamique ;
- `ExecutableMarket` rejette les `FUTURE` datés au niveau domaine.

### Patch 49.2

- `MarketDiscoveryCoordinator` accepte désormais exactement une source : `LEGACY_AGENT` ou `RADAR_SHORTLIST` ;
- le mode historique Agent reste disponible pour compatibilité/tests ;
- la composition des Campaigns dynamiques utilise `RADAR_SHORTLIST` et n'instancie plus `OpenAIWatchlistSelector` ;
- la frontière Radar ne lit que `item.market`, donc `symbol` + `market_type` ;
- la shortlist est revalidée contre le catalogue public Kraken et les contraintes Campaign/Risk existantes ;
- les nouvelles ouvertures sont fail-closed si le Radar est indisponible/stale/vide ou si aucun candidat n'est exécutable ;
- des positions déjà ouvertes peuvent continuer à être gérées en mode MANAGEMENT uniquement ;
- aucun nouveau chemin Risk/Broker n'est créé ;
- aucun champ Analytics 47.5/48 n'est injecté prématurément dans le prompt stratégique ;
- aucun poids Analytics n'est modifié ;
- aucune migration ni endpoint LIVE n'est ajouté.

## ADR-357 — Le Radar alimente la frontière canonique de Market Discovery

**ADOPTÉ DANS LE PATCH 49.2 — NON INTÉGRÉ À LA LIVRAISON.**

Solutions comparées :

1. remplacer entièrement Market Discovery par un second runner Radar : rejeté car dupliquerait orchestration/audit ;
2. conserver Market Discovery puis ajouter une seconde shortlist Radar : rejeté car deux sources concurrentes de candidats ;
3. **faire du Radar une source de candidats derrière `MarketDiscoveryCoordinator` : retenu**.

Motifs :

- réutilise le runner dynamique et le pipeline multi-marchés existants ;
- conserve les contrats d'audit et de `market_type` ;
- supprime l'ancien double choix stratégique de watchlist + plan ;
- ne donne aucune autorité d'exécution au Radar.

## ADR-358 — La frontière 49.2 est une projection identité-only

**ADOPTÉ DANS LE PATCH 49.2 — NON INTÉGRÉ À LA LIVRAISON.**

Le seul payload conceptuellement transféré du Radar vers l'univers Agent est :

```text
{ symbol, market_type }
```

Ne traversent pas cette frontière en 49.2 : score Analytics, Open Interest, Funding, Liquidations, CVD, Aggressor Differential, Market Structure détaillée et diagnostics Radar.

Motif : séparer clairement la question « où regarder ? » de la question 49.3 « quels faits Radar exposer à l'Agent ? ».

## ADR-359 — Une panne Radar est fail-closed pour les nouvelles ouvertures

**ADOPTÉ DANS LE PATCH 49.2 — NON INTÉGRÉ À LA LIVRAISON.**

```text
Radar utilisable + candidats exécutables -> plan normal
Radar inutilisable + positions ouvertes  -> MANAGEMENT uniquement
Radar inutilisable + aucune position      -> cycle FAILED avant Agent/Risk/Broker
```

Le bootstrap n'est jamais promu silencieusement en opportunité lorsque le Radar est en panne. Une erreur technique n'est donc jamais interprétée comme un signal de marché.

## ADR-360 — La shortlist Radar est revalidée contre l'exécutabilité Kraken/Campaign

**ADOPTÉ DANS LE PATCH 49.2 — NON INTÉGRÉ À LA LIVRAISON.**

Être dans la shortlist Radar ne suffit pas à être présenté comme nouvelle opportunité. Le marché doit aussi satisfaire les contraintes factuelles déjà canoniques :

- type présent dans `MarketDiscoveryPolicy.market_types` ;
- quote égale au settlement asset ;
- statut marché tradable ;
- PERPETUAL linéaire ;
- présence dans le catalogue public Kraken ;
- whitelist Risk éventuelle.

Les `FUTURE` datés restent non exécutables.

---

## Changelog — 2026-10-05 — Batch 49.1 activation officielle PERPETUAL PAPER — intégré

Commit intégré : `3194fce620f5e31672c6b52ef8986daddeea3a25` (`feat: activate perpetual paper trading`).

### Audit confirmé

- `MarketType` distingue déjà `SPOT`, `PERPETUAL` et `FUTURE` ;
- `MarketSelectionInput`, `CycleDecisionPlanInput`, `AgentInput`, `DecisionCandidate` et `ExecutionIntent` conservent le `market_type` ;
- le JSON Schema du plan Agent accepte explicitement `SPOT` et `PERPETUAL` ;
- le prompt stratégique courant connaît la sémantique BUY/LONG et SELL/SHORT PERPETUAL ;
- `RoutedExecutableMarketDataSource` route SPOT et derivatives ;
- les campagnes statiques et dynamiques savent déjà représenter `PERPETUAL` ;
- `RiskEngine` accepte les PERPETUAL linéaires et contrôle quantité, levier, marge, caps notionnels/exposition, liquidation et retournement ;
- `PaperBroker` exécute déjà les PERPETUAL linéaires en PAPER ;
- le ledger gère `DerivativePosition`, LONG/SHORT, funding, P&L, marge et liquidation théorique ;
- le cockpit possède déjà les champs de configuration dérivés et l'affichage marge/levier/liquidation.

### Patch 49.1

- `operator-chat-v2` remplace le contrat opérateur SPOT-only ;
- le contrat indique PAPER uniquement, SPOT + PERPETUAL linéaire, FUTURE daté et LIVE indisponibles ;
- aucun nouveau contrôle de levier n'est confié au LLM ;
- aucun endpoint privé Kraken Futures n'est ajouté ;
- aucune nouvelle configuration frontend n'est créée ;
- un test d'intégration dédié prouve le passage Agent -> `DecisionCandidate` -> Risk -> `ExecutionIntent` -> `PaperBroker` -> `DerivativePosition` ;
- le test couvre ouverture LONG/SHORT, fermeture opposée, `HOLD`, conservation de `market_type` et absence de retournement direct ;
- Radar, ranking Analytics et shortlist restent inchangés.

## ADR-353 — L'univers d'exécution PAPER officiel est SPOT + PERPETUAL linéaire

**ADOPTÉ — Batch 49.1 intégré via `3194fce`.**

L'ancien invariant global « SPOT uniquement » est obsolète pour le PAPER. Il reste vrai uniquement pour les règles propres au SPOT : aucun short, levier ni marge sur cette famille.

Les PERPETUAL Kraken linéaires sont exécutables par le même Agent stratégique, sous le même Risk Engine déterministe et via le `PaperBroker`. Les `FUTURE` datés restent interdits.

## ADR-354 — Aucun retournement direct PERPETUAL dans un seul ExecutionIntent

**ADOPTÉ — Batch 49.1 intégré via `3194fce`.**

Une action opposée à une position existante sert d'abord à la réduire ou la fermer :

```text
LONG + SELL  -> reduce_only LONG
SHORT + BUY  -> reduce_only SHORT
```

Si la quantité demandée dépasse la position :

- avec réduction de quantité autorisée, Risk borne à la quantité détenue et ferme sans ouvrir l'autre sens ;
- sinon Risk rejette l'accidental reversal.

Une exposition opposée éventuelle doit être créée par une décision ultérieure, une fois la fermeture réellement appliquée au portefeuille.

## ADR-355 — Le levier PERPETUAL reste entièrement déterministe

**ADOPTÉ — Batch 49.1 intégré via `3194fce`.**

Le LLM ne produit pas de champ de levier stratégique. Le levier d'un `ExecutionIntent` dérivé provient de la configuration/policy et reste borné par :

- `paper_derivative_leverage` ;
- `risk_max_derivative_leverage` ;
- les contraintes de marge applicables à l'instrument ;
- les caps de position/exposition et la marge disponible.

Aucun prompt ou chat ne peut contourner ces contrôles.

## ADR-356 — Radar et exécution restent séparés en 49.1

**ADOPTÉ — Batch 49.1 intégré via `3194fce`.**

Le fait que le PAPER sache exécuter des PERPETUAL ne donne aucune autorité au Radar. Le ranking 47.5 et l'observabilité 48 restent read-only. Le Batch 49.2 fait uniquement de la shortlist une source d'univers ; l'autorité stratégique reste chez l'Agent.

---

## Changelog — 2026-10-05 — Batch 48 observabilité ranking Analytics — intégré

Base GitHub auditée au démarrage : `4278a5c732b9636b06144ff58e8485b3350a2c0d` (`docs: mark batch 47.5 integrated`).

Commit fonctionnel intégré : `ebb664c538f7a77ffe1a51ef4a44536a83cb484e` (`feat: add analytics ranking observability`).

Clôture documentaire intégrée : `8704eec57de09792d0a51e080fdeb7b2a39d2381` (`docs: mark batch 48 integrated`).

### Audit confirmé

- le Radar possède déjà un historique process-local borné ;
- `MarketAttentionPolicy.history_limit=96` par défaut ;
- `refresh_seconds=300` par défaut ;
- la couche Analytics conserve ses snapshots via une `deque(maxlen=history_limit)` ;
- l'API expose déjà un historique borné ;
- `analytics_ranking` contient les faits nécessaires à l'observation causale ;
- la persistence SQL existante est une frontière d'audit économique/PAPER, pas une télémétrie générique Radar ;
- le cockpit expose déjà le diagnostic instantané 47.5.

### Options comparées

1. snapshot courant uniquement : insuffisant pour les fréquences et la stabilité ;
2. nouvelle agrégation glissante séparée : rejetée car double le buffer historique ;
3. nouvelle persistence durable : prématurée et plus lourde qu'il n'est justifié ;
4. historique Radar existant + persistence PAPER : rejeté car couplage de responsabilités ;
5. **agrégation à la demande sur l'historique Radar borné existant : retenue et intégrée**.

### Batch 48 intégré

- nouveau module `attention_analytics_observability.py` ;
- agrégation auto-bornée à 96 snapshots ;
- aucune mutation des snapshots sources ;
- aucune nouvelle base, table, `deque`, rotation ou cache ;
- distribution score `0..4` ;
- contribution des quatre familles ;
- déduplication défensive des familles et séries par candidat ;
- statuts des cinq séries ;
- distinction entre score nul et absence d'Analytics exploitable ;
- reranking applicable/effectif/sans mouvement ;
- `rank_change=0` distinct d'un rang absent ;
- candidats montés/descendus/inchangés ;
- distribution exacte de `rank_change` et moyenne/max de `abs(rank_change)` ;
- déduplications/conflits CVD/Aggressor ;
- ventilation SPOT/PERPETUAL/ALL ;
- couverture descriptive par marché ;
- fenêtre temporelle explicite ;
- payloads legacy ignorés explicitement et comptés ;
- route additive `/api/v1/market-attention/observability` ;
- dock cockpit compact séparé ;
- aucune modification du score 47.5 ou de sa clé de tri ;
- aucune dépendance Agent/Risk/Broker ;
- aucune donnée de P&L futur.

### Limite assumée

L'historique utilisé est process-local. Un redémarrage backend remet la fenêtre d'observation à zéro. Cette limite est exposée et documentée plutôt que masquée par une persistence improvisée.

## ADR-349 — L'observabilité Batch 48 réutilise l'historique Radar borné

**ADOPTÉ — Batch 48 intégré via `ebb664c`.**

Le diagnostic agrégé est calculé à la demande depuis les snapshots déjà conservés par le Radar.

Motifs :

- aucune duplication d'infrastructure ;
- mémoire déjà bornée ;
- causalité directe ;
- comportement reproductible sur une même séquence de snapshots ;
- coût d'implémentation faible ;
- séparation nette vis-à-vis de l'audit trading.

## ADR-350 — La persistence PAPER n'est pas utilisée comme télémétrie Radar générique

**ADOPTÉ — Batch 48 intégré via `ebb664c`.**

Les tables et writers PAPER servent la continuité économique, l'audit des décisions, du Risk et des exécutions. Leur réutilisation pour chaque refresh Radar créerait un couplage non justifié et modifierait les conséquences d'une indisponibilité du store.

Une persistence Radar durable, si elle devient nécessaire, devra faire l'objet d'une décision séparée avec contrat de rétention et migrations explicites.

## ADR-351 — `rank_change=0` est une observation, pas une absence de donnée

**ADOPTÉ — Batch 48 intégré via `ebb664c`.**

Un candidat applicable dont `rank_change == 0` est compté comme inchangé. Un candidat non applicable ou un `rank_change` absent est compté séparément.

Cette distinction est nécessaire pour mesurer correctement les snapshots où Analytics est applicable mais n'a aucun effet sur le rang.

## ADR-352 — Le diagnostic Batch 48 n'évalue aucune rentabilité

**ADOPTÉ — Batch 48 intégré via `ebb664c`.**

Les métriques utilisent uniquement les snapshots et diagnostics disponibles au moment de leur observation. Aucun rendement futur, P&L futur, meilleur point d'entrée rétrospectif ou autre donnée postérieure n'entre dans l'agrégation.

Les métriques peuvent décrire le comportement du ranking ; elles ne démontrent pas qu'il est rentable et n'autorisent aucune calibration automatique.

## Validation finale Batch 48

Validation locale utilisateur exécutée avant intégration :

```text
python -m pytest -q : PASS — 1155 passed, 2 warnings
pnpm typecheck      : PASS
pnpm test           : PASS — 86/86
git diff --check    : PASS — avertissements LF -> CRLF uniquement
git push origin main: PASS — puis clôture documentaire 8704eec
git status --short  : vide après push
```

Warnings connus non bloquants :

- `StarletteDeprecationWarning` dans `fastapi.testclient` ;
- dépréciation `anyio.abc.BlockingPortal` dans `starlette.testclient` ;
- warning Node `MODULE_TYPELESS_PACKAGE_JSON`.

Aucun test non exécuté n'est déclaré PASS.

---

## Changelog — 2026-10-05 — Batch 47.5 multi-analytics ranking — intégré

Commit fonctionnel intégré : `d988de42dd684b597a78a6ce1d6d32a86147bf37` (`feat: add bounded multi-analytics radar ranking`).

Clôture documentaire intégrée : `4278a5c732b9636b06144ff58e8485b3350a2c0d` (`docs: mark batch 47.5 integrated`).

### Décisions 47.5 actives dans leur périmètre Radar

- score entier `0..4` ;
- quatre familles indépendantes : `OPEN_INTEREST`, `FUNDING`, `LIQUIDATION_VOLUME`, `ORDER_FLOW` ;
- disponibilité seule = 0 ;
- seules les caractéristiques 47.2–47.4 actives et `AVAILABLE` peuvent contribuer ;
- anomalies positives/négatives signées symétriques pour l'attention ;
- CVD + Aggressor concordants = +1 maximum, avec déduplication diagnostiquée ;
- CVD + Aggressor opposés = 0 sur order-flow, avec conflit diagnostiqué ;
- données absentes, partielles, insuffisantes, stale, technical error ou N/A = 0 sans malus ;
- aucun changement des seuils/statistiques 47.2–47.4 ;
- aucun nouveau scanner/cache/cursor ;
- budget réseau maximal inchangé à 50 appels Analytics/refresh ;
- `interest_level` inchangé ;
- `candidate_limit` inchangé ;
- aucun filtre ou candidat créé par Analytics ;
- score injecté après intérêt et Structure confirmée ;
- `SPOT` inchangé ;
- en `ALL`, slots SPOT figés et réordonnancement seulement entre PERP ;
- aucune modification Agent / Risk Engine / Broker dans le Batch 47.5 ;
- aucune exécution PERPETUAL ajoutée par le Batch 47.5.

Ces deux derniers points décrivent le périmètre historique du Batch 47.5 ; ils ne remplacent pas la décision courante sur le runtime PAPER.

## ADR-345 — Score Analytics séparé et plafonné à quatre familles

**ADOPTÉ — Batch 47.5 intégré via `d988de4`.**

Le score d'attention Analytics est distinct de `interest_level`. Il vaut au maximum 4 : OI, Funding, Liquidations et Order Flow valent chacun au plus +1.

## ADR-346 — CVD et Aggressor Differential forment une seule composante order-flow

**ADOPTÉ — Batch 47.5 intégré via `d988de4`.**

```text
un seul actif            -> +1
deux actifs concordants  -> +1 total
deux actifs opposés      -> 0 + conflit diagnostiqué
```

## ADR-347 — Analytics ne peut ni créer un candidat ni modifier `interest_level`

**ADOPTÉ — Batch 47.5 intégré via `d988de4`.**

Hiérarchie :

```text
interest_level
-> Structure confirmée
-> analytics_ranking.score
-> reste de la clé canonique
```

En scope `ALL`, les positions SPOT restent fixes.

## ADR-348 — Une série Analytics indisponible est neutre

**ADOPTÉ — Batch 47.5 intégré via `d988de4`.**

Seul le statut `AVAILABLE` permet d'utiliser une caractéristique. Données absentes, `PARTIAL`, `INSUFFICIENT_HISTORY`, `STALE`, `TECHNICAL_ERROR` ou `NOT_APPLICABLE` contribuent 0 sans malus.

Une panne technique ne devient jamais une information de marché.

## Décisions antérieures toujours actives dans leur périmètre

- Batch 47.4 : cinq séries Analytics dans un scanner/cache/cursor/sémaphore uniques ; CVD sur variation ; Aggressor signé ; MAD robuste ; aucun fallback ratio pour les séries signées.
- Batch 47.3 : Funding relatif signé et Liquidation Volume agrégé, sans split LONG/SHORT inventé.
- Batch 47.2 : `PerpetualAnalyticsScanner` est l'infrastructure historique canonique ; Open Interest est analysé relativement à sa baseline.
- Batch 47.1 : snapshot Futures bulk canonique partagé ; OI/funding instantanés distincts des historiques.
- ADR-330 : cible baseline adaptative 12 périodes, plancher 6.
- ADR-328 : anomalie robuste médiane + MAD.
- ADR-329 : ratios historiques observables.
- ADR-325 : policy/scan Structure séparés.
- ADR-326 : BOS/CHOCH descriptifs et symétriques.
- ADR-327 : filtres Structure fail-closed sur UNKNOWN.
- ADR-323 : liquidité PERP via `volumeQuote` USD validé.
- ADR-324 : couverture observée, jamais auto-corrigée.
- ADR-321 : volume PERP USD via turnover quote Kraken.
- ADR-322 : une shortlist PERP vide n'est pas réparée en abaissant le scoring.
