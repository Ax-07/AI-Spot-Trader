# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading crypto **PAPER** pilotée par **un seul
Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est uniquement
un cockpit de contrôle et de visualisation.

Base GitHub auditée pour le Batch 18.12 :

```text
HEAD main audité      : c6cf03e62ce49ad6b294ea1d4c44d933b4688b0a
Référence fonctionnelle 18.11 : c02b9e8edd52b416969922f12a17e32f047d3989
```

Le Batch 18.12 est livré comme patch multi-fichiers et n'est pas réputé intégré tant que la
validation locale et le commit ne sont pas effectués.

## 2. Invariants fonctionnels

### Globaux

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement ; LIVE reste séparé et ultérieur ;
- actions finales `BUY`, `SELL`, `HOLD` ;
- Luna configurable par défaut, Sol sélectionnable ;
- Risk Engine déterministe avec autorité finale ;
- seul Risk crée un `ExecutionIntent` ;
- aucune sortie LLM ni aucun tool ne déclenche Broker/Kraken ;
- coûts PAPER et funding pris en compte ;
- audit causal de toutes les décisions, `HOLD` inclus ;
- aucun secret dans prompts, logs, navigateur ou Git ;
- aucun look-ahead ;
- frontend non nécessaire au fonctionnement du moteur.

### SPOT

- aucun short ;
- aucun levier/margin ;
- `SELL` réduit uniquement une position détenue/disponible.

### PERPETUAL

- contrats linéaires uniquement ;
- LONG/SHORT ;
- marge `ISOLATED` ;
- levier déterministe/configuré, jamais choisi par le LLM ;
- Risk contrôle marge, exposition, liquidation, `reduce_only` et anti-reversal ;
- contrats inverses, CROSS et futures datés restent non exécutables.

## 3. Pipeline canonique

```text
PortfolioState
-> MarketSelectionInput
-> même Agent + tools read-only éventuels
-> MarketSelection
-> acquisition MarketState exécutable exact
-> AgentInput
-> même Agent -> BUY/SELL/HOLD
-> RiskEngine -> ALLOW/MODIFY/REJECT
-> ExecutionIntent éventuel
-> PaperBroker
-> audit + ledger durable
```

Aucun composant déterministe ni frontend ne choisit l'opportunité à la place de l'Agent.

## 4. Univers exécutable

`ExecutableMarket(symbol, market_type)` représente la frontière d'exécution. L'univers est trié,
sans doublon, limité à SPOT/PERPETUAL, et chaque symbole doit être autorisé par Risk. Tous les
marchés d'une Campaign partagent actuellement le même actif de quote/règlement.

Les sources de recherche Kraken sont séparées des sources d'exécution. Un snapshot de recherche
n'est jamais promu silencieusement en `MarketState` d'exécution.

## 5. Recovery PAPER

`paper-ledger-recovery-v1` reste le mécanisme canonique :

- nouveau `paper_run_id` par lifetime ;
- `resumed_from_paper_run_id` explicite ;
- snapshot initial/courant durable du ledger ;
- rollback mémoire sur cycle FAILED ou erreur d'audit ;
- aucun replay de MarketSelection, décision, Risk, Broker ou Fill ;
- validation fail-closed de l'état restauré.

Un restart backend ne reprend jamais silencieusement une Campaign. La reprise opérateur reste une
action explicite.

## 6. Control Plane backend

### Strategy / StrategyRevision

`Strategy` est une identité durable nommable/archivable. Chaque `StrategyRevision` est immuable et
contient le texte opérateur, son digest, la version du contrat Agent protégé et son timestamp.
Modifier le texte crée une nouvelle révision.

### Contrat Agent protégé

```text
PROTECTED_AGENT_CONTRACT
+ StrategyRevision.strategy_prompt
+ AggressivenessContext canonique
```

Le contrat protégé impose PAPER, les sémantiques SPOT/PERP, les sorties structurées et l'autorité
finale de Risk. Il n'est exposé à aucune mutation API.

### Campaign

Une Campaign snapshotte stratégie/révision et configuration structurelle non sensible. Elle inclut
modèle, agressivité, cadence, capital, univers, coûts, levier/marge, limites Risk et deadlines de
cycle. Elle est immuable.

`paper-experiment-v4` identifie l'expérience à partir de la Strategy/Revision et du digest de
configuration.

## 7. Campaign vs paper_run

```text
Campaign  : configuration expérimentale immuable
paper_run : session d'exécution/recovery
```

Une Campaign peut posséder plusieurs runs liés par recovery. Une reprise doit conserver le même
`campaign_id`.

## 8. Runtime dynamique

Le Control Plane ne crée pas de second moteur. `build_campaign_runtime()` assemble les composants
canoniques : `TradingCycleRunner`, `AuditedTradingCycleRunner`, `TradingEngine`, `RiskEngine` et
`PaperBroker`.

Activation/reprise est refusée pendant `RUNNING`. Un runtime `STOPPED` peut être remplacé proprement
par une autre Campaign selon les contrats backend.

## 9. API canonique utilisée par le cockpit

Le frontend reste un client HTTP du backend via `/backend` et `frontend/src/lib/api/client.ts`.
Routes principales :

- Strategy/Revision : création, lecture, renommage, archivage, comparaison ;
- Campaign : création, lecture, activation fraîche, reprise ;
- moteur : `run-cycle`, `start`, `stop` ;
- lecture : portfolio, market, cycles, décisions, risk-assessments, executions, analytics,
  paper-runs ;
- prompt preview et chat informatif.

Les réponses backend 409/422/503 restent autoritaires et ne sont pas contournées côté UI.

## 10. Évolution du cockpit

### Batches 18.9B à 18.11

Le cockpit historique a d'abord exposé directement Strategy, StrategyRevision, Campaign, activation,
recovery et commandes moteur. Le Batch 18.10 a ajouté une Vue d'ensemble ; le Batch 18.11 a ajouté
un Guide et de l'aide contextuelle.

### Batch 18.12 — UX orientée tâches

Le Batch 18.12 conserve les contrats précédents mais change le modèle mental principal :

```text
Accueil
Configurer
Positions
Historique
Réglages
```

Le parcours débutant n'exige plus de comprendre Strategy/Revision/Campaign.

#### Assistant de configuration

Le frontend orchestre les appels canoniques :

```text
create Strategy (crée aussi Revision r1)
-> create Campaign
-> éventuellement activate Campaign
-> éventuellement start Engine
```

Il ne fusionne pas ces concepts dans le backend et n'ajoute aucune transaction métier parallèle.
En cas d'échec intermédiaire, les objets déjà persistés restent auditables dans les réglages avancés.

#### Profils Risk UX

`Prudent`, `Équilibré` et `Agressif` ne sont que des fonctions de traduction vers les champs
existants de `CampaignConfiguration`. `Personnalisé` expose les champs détaillés. Le backend reste
seul responsable de la validation et le Risk Engine garde l'autorité finale à l'exécution.

Mappings initiaux du patch 18.12 :

- Prudent : ordre max 5 % capital ; PERP 1x ; position 10 % ; exposition totale 20 % ; buffer 1.25 ;
- Équilibré : ordre max 10 % ; PERP 2x ; position 20 % ; exposition totale 40 % ; buffer 1.15 ;
- Agressif : ordre max 20 % ; PERP 3x ; position 35 % ; exposition totale 70 % ; buffer 1.10.

#### Divulgation progressive

- la landing expose état, configuration humaine, capital, P&L, positions et **Action suivante** ;
- les détails Strategy/Revision/Campaign, digests, IDs et recovery restent sous
  `Réglages > Avancé` ;
- Guide et Assistant deviennent secondaires au lieu d'occuper la navigation principale.

#### Positions

Le frontend utilise uniquement `PortfolioResponse` et les analytics backend. Pour PERPETUAL, les
métriques par position viennent du backend. Pour SPOT, le contrat ne fournit pas de coût moyen ni de
P&L unitaire : ces valeurs ne sont pas reconstruites côté navigateur.

#### Historique

La vue regroupe par `cycle_id` les faits déjà canoniques : décision Agent, résultat Risk, éventuelle
exécution/fills et erreur. Cette corrélation est de présentation uniquement.

## 11. Frontend sans logique métier parallèle

Le frontend ne :

- valide pas à la place de `CampaignConfiguration` ;
- ne calcule pas de portefeuille alternatif ;
- ne décide pas BUY/SELL/HOLD ;
- ne crée pas d'`ExecutionIntent` ;
- ne simule pas le Risk Engine ;
- ne simule pas le Broker ;
- ne persiste aucun secret.

Fermer le frontend n'envoie jamais `stop`.

## 12. Validation comportementale historique

Le Batch 18.9C a déjà confirmé sur les contrats canoniques : Strategy/Revision, Campaign SPOT et
PERPETUAL, activation fraîche, `run-cycle`, Start/Stop, restart backend et recovery explicite.
Des BUY naturels SPOT/PERPETUAL soumis à Risk `MODIFY` et des HOLD naturels ont été observés.

## 13. Persistence et migrations

La migration `0006_paper_control_plane` crée `strategies`, `strategy_revisions`, `campaigns` et le
lien `paper_runs.campaign_id`. Le Batch 18.12 ne demande aucune migration.

## 14. Secrets

Secrets serveur uniquement, notamment :

```text
OPENAI_API_KEY
DATABASE_URL
futures clés privées Kraken/LIVE
```

Ils ne sont jamais champs de `CampaignConfiguration` ni envoyés au cockpit.

## 15. État du jalon

Les Batches 18.9 à 18.11 sont intégrés. Le Batch 18.12 est un patch frontend/documentation préparé
sur `c6cf03e...`, sans changement backend. Il doit être validé localement avec les commandes frontend
standard avant intégration. LIVE reste un batch/projet séparé.
