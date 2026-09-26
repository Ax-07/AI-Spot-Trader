# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading **PAPER** pilotée par **un seul Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est uniquement un cockpit de contrôle et de visualisation.

Référence GitHub vérifiée après intégration du Batch 19.9B :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 88be7d50111c2e6210225071d3f1af3f7f07b4f0
Commit     : feat: add strategic multi-timeframe context
```

Les Batches 19.9A et 19.9B sont intégrés à GitHub `main`. La distinction `SCALP` / `SWING` est désormais opérationnelle côté contexte de données multi-timeframes remis au même Agent stratégique.

## 2. Invariants fonctionnels

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement, LIVE séparé ;
- SPOT + PERPETUAL selon les capacités intégrées ;
- actions `BUY`, `SELL`, `HOLD` ;
- Luna par défaut, Sol sélectionnable ;
- Risk Engine déterministe = autorité finale ;
- aucune sortie LLM/tool ne déclenche directement Broker/Kraken ;
- coûts PAPER, spread, slippage, accounting et mark-to-market canoniques dans le backend ;
- décisions, sélections et HOLD auditables ;
- aucun look-ahead ;
- aucun secret dans prompts/logs/frontend/Git ;
- frontend non nécessaire au fonctionnement du moteur.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## 3. Modèle utilisateur : Session

Le concept utilisateur principal est `Session`. Il s'agit d'une façade/projection sur les composants existants, pas d'un nouveau moteur ni d'une nouvelle table :

```text
Session UX
-> Strategy = identité stable
-> StrategyRevision(s) = instructions immuables
-> Campaign(s) = snapshots de configuration immuables
-> paper_run(s) = exécutions/recovery
```

L'identifiant de Session est le `strategy_id`. Les objets techniques restent accessibles uniquement dans le parcours avancé.

## 4. Façade backend Session

La façade `/api/v1/sessions` fournit :

- création atomique ;
- liste/détail ;
- modification versionnée ;
- duplication ;
- archivage logique ;
- start/stop/resume/run-cycle.

Aucune table `sessions` n'est introduite. `Strategy.archived_at` porte l'archivage logique. La Campaign la plus récente de la Strategy est la configuration courante.

### Création atomique

Le navigateur ne doit plus orchestrer :

```text
create Strategy -> create Campaign -> activate -> start
```

La persistence crée Strategy + StrategyRevision 1 + Campaign dans une transaction unique. `Créer et démarrer` effectue ensuite l'activation fraîche et le `start` côté backend.

### Mise à jour

Les faits historiques restent immuables :

- nom seul : rename Strategy ;
- instructions modifiées : nouvelle StrategyRevision ;
- configuration modifiée : nouvelle Campaign ;
- instructions + configuration modifiées : nouvelle revision puis nouvelle Campaign liée à cette revision.

Une Session RUNNING doit être arrêtée avant modification/archivage.

### Duplication

Une duplication crée une nouvelle Strategy avec son propre ID, sa révision 1 et sa Campaign initiale. Aucun `paper_run` ni historique de l'original n'est recopié.

## 5. Statuts Session

Les statuts sont dérivés des faits :

- `DRAFT` / Brouillon : aucune exécution ;
- `READY` / Prête : Campaign active chargée, moteur arrêté ;
- `RUNNING` / En cours ;
- `STOPPED` / Arrêtée : historique existant, non active ;
- `RESUMABLE` / À reprendre : run récupérable laissé ouvert après interruption/restart ;
- `ARCHIVED` / Archivée.

Aucune colonne parallèle de statut Session n'est ajoutée.

## 6. Lifecycle et recovery

Les mécanismes canoniques restent autoritaires : activation fraîche, reprise, moteur start/stop/run-cycle et recovery du ledger PAPER.

- une Campaign déjà exécutée ne peut pas être fresh-activée ;
- reprise explicite requise ;
- aucune reprise silencieuse après restart ;
- `Arrêter` une Session ferme le runtime actif et termine durablement le `paper_run` ;
- `Tester 1 cycle` laisse le runtime chargé et le moteur arrêté après le cycle.

## 7. Univers de marchés

Deux modes utilisateur :

### Automatique — IA

```text
Kraken catalogue
-> filtre déterministe d'admissibilité
-> candidats
-> même Agent IA choisit une watchlist
-> même Agent décide BUY / SELL / HOLD
-> Risk autorise/modifie/refuse
```

`paper_executable_markets` est un bootstrap/fallback. Il ne signifie pas que l'Agent doit trader cette paire. `market_discovery` contient la politique dynamique.

### Manuel

- `market_discovery = null` ;
- `paper_executable_markets` = univers choisi ;
- `risk_allowed_pairs` = même univers ;
- l'Agent conserve BUY/SELL/HOLD uniquement dans cet univers ;
- Risk reste final.

## 8. Market Discovery

Defaults canoniques :

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

Les defaults frontend sont centralisés pour refléter ceux du backend ; le backend reste la référence de validation.

## 9. NORMAL / MANAGEMENT

Les règles 19.3 restent autoritaires : `NORMAL` peut renouveler la watchlist ; `MANAGEMENT` n'ouvre pas une recherche destinée à de nouvelles positions et reste limité à la gestion des positions ouvertes. Risk refuse l'augmentation d'exposition incompatible.

## 10. Comptabilité, analytics et charts

Les Batches 19.1–19.7 restent canoniques : accounting/mark-to-market/equity/exposition côté backend, explicabilité depuis les faits persistés, candles backend, streaming partagé, fills persistés et overlays provenant exclusivement du portefeuille backend.

La façade Session ne duplique aucune de ces logiques.

## 11. Cockpit

Navigation normale :

```text
Accueil
Sessions
Marchés
Positions
Historique
Réglages
```

`Réglages > Avancé` conserve Strategy, StrategyRevision, Campaign, prompt preview, digests, IDs et commandes techniques nécessaires au diagnostic.

## 12. Hors périmètre 19.8

- LIVE ;
- second Agent IA ;
- refonte Risk/accounting/charts ;
- ranking stratégique algorithmique ;
- table `sessions` ;
- restauration d'une Session archivée ;
- refonte graphique générale.

## 13. Trading Style canonique — Batch 19.9A

Le style stratégique appartient à la `Campaign` et ne remplace ni l'agressivité ni la cadence persistée. Deux valeurs sont définies :

```text
SCALP
SWING
```

La configuration conserve `paper-control-plane-config-v1`. Les champs `trading_style` et `trading_style_mapping_version` sont optionnels et absents du payload canonique lorsqu'ils valent `null`, de sorte qu'une Campaign historique garde exactement son ancien `configuration_digest`. Un changement de style modifie en revanche l'identité de configuration et produit une nouvelle Campaign immuable via le mécanisme Session existant.

Le mapping `trading-style-map-v1` produit un `TradingStyleContext` structuré. `ExecutionCostContext` expose exactement `paper_fee_rate`, `paper_spread_bps` et `paper_slippage_bps` à l'Agent. Les deux contextes suivent le même Agent dans Discovery, Market Selection et décision finale ; le runner dynamique les retransmet au runner canonique.

Invariants :

- style et agressivité sont orthogonaux ;
- le style ne modifie aucune limite Risk ;
- aucune durée SCALP/SWING ne déclenche une liquidation ;
- aucun score déterministe d'opportunité n'est ajouté ;
- `agent-contract-v1` reste inchangé.

## 14. Contexte stratégique multi-timeframes — Batch 19.9B

Le Batch 19.9B raccorde les préférences de `trading-style-map-v1` au pipeline candles canonique sans dupliquer le mapping style -> timeframes :

- SCALP : `1m`, `5m`, `15m`, `30m` ;
- SWING : `1h`, `4h`, `1d`.

Le contexte versionné `strategic-mtf-v1` est construit par `StrategicMultiTimeframeContextService` à partir du `CandleStreamService` backend partagé. Il utilise `history_as_of(...)` pour exclure toute donnée non disponible au temps de décision, conserve explicitement les gaps sans interpolation et expose `AVAILABLE` / `PARTIAL` / `MISSING` ainsi que l'état stale.

Le contexte est compact et borné : 32 marchés maximum, 128 KiB JSON maximum, concurrence de lecture bornée et profondeur spécifique par timeframe. Discovery reste volontairement légère ; l'enrichissement candles intervient pour l'univers remis à Market Selection.

`MultiTimeframeDecisionProvider` construit un snapshot au `MarketSelectionInput.created_at`, le remet à Market Selection puis réutilise exactement le même snapshot pour l'`AgentInput` final. Le fallback legacy single-market avec style explicite construit son snapshot au temps de l'`AgentInput`.

Le même Agent IA conserve la décision stratégique. `ExecutionCostContext` reste séparé, le Risk Engine reste inchangé et aucune statistique technique n'est convertie en règle déterministe BUY/SELL/HOLD.

## 15. Hors périmètre actuel

- LIVE ;
- `ADAPTIVE_AI` tant qu'il n'est pas cadré ;
- modification du Risk Engine selon le style ;
- fermeture automatique d'une position selon une durée de détention ;
- ranking technique déterministe d'opportunité ;
- second pipeline/cache OHLC ou second Agent stratégique.
