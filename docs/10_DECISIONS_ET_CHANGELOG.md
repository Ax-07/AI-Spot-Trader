# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent disponibles dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les références nécessaires à la reprise.

## Principes actifs

Un seul Agent IA stratégique. Le Risk Engine déterministe conserve l'autorité finale. Aucune sortie LLM ne déclenche directement Broker/Kraken.

L'exécution courante est **PAPER uniquement** :

- SPOT exécutable sans short, levier ni marge ;
- PERPETUAL Kraken linéaire exécutable en LONG/SHORT sous contrôle Risk ;
- FUTURE daté non exécutable ;
- LIVE indisponible tant qu'un batch séparé ne l'active pas explicitement.

Le Market Attention Radar est observationnel : il peut prioriser **l'attention**, mais il ne décide jamais BUY/SELL/HOLD et ne possède aucune autorité d'exécution. Le Batch 49.1 ne le raccorde pas à l'univers Agent.

## Référence courante

```text
Base GitHub auditée 49.1     : 8704eec57de09792d0a51e080fdeb7b2a39d2381
Clôture Batch 48             : 8704eec — docs: mark batch 48 integrated
Batch 48 fonctionnel         : ebb664c — feat: add analytics ranking observability
Batch 49.1                   : PATCH PROPOSÉ — NON INTÉGRÉ À LA LIVRAISON
```

## Changelog — 2026-10-05 — Batch 49.1 activation officielle PERPETUAL PAPER — patch proposé

Base GitHub auditée au démarrage : `8704eec57de09792d0a51e080fdeb7b2a39d2381` (`docs: mark batch 48 integrated`).

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
- le cockpit possède déjà les champs de configuration dérivés et l'affichage marge/levier/liquidation ;
- le dernier contrat runtime actif encore contradictoire était le chat opérateur, qui déclarait encore « Trading is SPOT only ».

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

**ADOPTÉ DANS LE PATCH 49.1 — NON INTÉGRÉ À LA LIVRAISON.**

L'ancien invariant global « SPOT uniquement » est obsolète pour le PAPER. Il reste vrai uniquement pour les règles propres au SPOT : aucun short, levier ni marge sur cette famille.

Les PERPETUAL Kraken linéaires sont exécutables par le même Agent stratégique, sous le même Risk Engine déterministe et via le `PaperBroker`. Les `FUTURE` datés restent interdits.

Motifs :

- la capacité existe déjà dans les composants canoniques ;
- la conserver cachée derrière un invariant documentaire contradictoire augmente le risque opératoire ;
- une réimplémentation parallèle serait inutile et dangereuse ;
- le `market_type` est déjà propagé causalement dans les contrats.

## ADR-354 — Aucun retournement direct PERPETUAL dans un seul ExecutionIntent

**ADOPTÉ DANS LE PATCH 49.1 — NON INTÉGRÉ À LA LIVRAISON.**

Une action opposée à une position existante sert d'abord à la réduire ou la fermer :

```text
LONG + SELL  -> reduce_only LONG
SHORT + BUY  -> reduce_only SHORT
```

Si la quantité demandée dépasse la position :

- avec réduction de quantité autorisée, Risk borne à la quantité détenue et ferme sans ouvrir l'autre sens ;
- sinon Risk rejette l'accidental reversal.

Une exposition opposée éventuelle doit être créée par une décision ultérieure, une fois la fermeture réellement appliquée au portefeuille.

Motifs :

- séquentialité causale explicite ;
- pas de P&L/marge/funding implicites cachés dans un retournement atomique ;
- audit simple ;
- cohérence avec le Risk Engine et le ledger existants.

## ADR-355 — Le levier PERPETUAL reste entièrement déterministe

**ADOPTÉ DANS LE PATCH 49.1 — NON INTÉGRÉ À LA LIVRAISON.**

Le LLM ne produit pas de champ de levier stratégique. Le levier d'un `ExecutionIntent` dérivé provient de la configuration/policy et reste borné par :

- `paper_derivative_leverage` ;
- `risk_max_derivative_leverage` ;
- les contraintes de marge applicables à l'instrument ;
- les caps de position/exposition et la marge disponible.

Aucun prompt ou chat ne peut contourner ces contrôles.

## ADR-356 — Radar et exécution restent séparés en 49.1

**ADOPTÉ DANS LE PATCH 49.1 — NON INTÉGRÉ À LA LIVRAISON.**

Le fait que le PAPER sache exécuter des PERPETUAL ne donne aucune autorité au Radar. Le ranking 47.5 et l'observabilité 48 restent read-only.

Le raccordement `Radar shortlist -> univers Agent SPOT + PERPETUAL` est explicitement réservé au Batch 49.2.

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

Ces deux derniers points décrivent le périmètre historique du Batch 47.5 ; ils ne remplacent pas la décision courante du Batch 49.1 sur le runtime PAPER.

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
