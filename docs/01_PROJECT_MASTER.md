# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading crypto PAPER pilotée par **un seul
Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est uniquement
un cockpit de contrôle et de visualisation.

Référence GitHub intégrée après Batch 18.11 :

```text
HEAD main : c02b9e8edd52b416969922f12a17e32f047d3989
message   : feat: add operator guide and contextual help
```

Les Batches 18.9A, 18.9B, 18.9C, 18.10 et 18.11 sont intégrés et validés.

## 2. Invariants fonctionnels

### Globaux

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement ; LIVE reste séparé et ultérieur ;
- actions finales `BUY`, `SELL`, `HOLD` ;
- Luna configurable par défaut dans les profils opérateur, Sol sélectionnable ;
- Risk Engine déterministe avec autorité finale ;
- seul Risk crée un `ExecutionIntent` ;
- aucune sortie LLM ni aucun tool ne déclenche Broker/Kraken ;
- coûts PAPER et funding pris en compte ;
- audit causal de toutes les décisions, `HOLD` inclus ;
- aucun secret dans les artefacts opérateur, prompts, logs, navigateur ou Git ;
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
marchés d'une campagne partagent actuellement le même actif de quote/règlement.

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

Le Batch 18.9C a validé le restart backend sans reprise silencieuse et la reprise explicite avec
nouveau `paper_run_id`, lineage et ledger restauré.

## 6. Control Plane backend — Batch 18.9A

### Strategy / StrategyRevision

`Strategy` est une identité durable nommable/archivable. Chaque `StrategyRevision` est immuable et
contient le texte opérateur, son digest, la version du contrat Agent protégé et son timestamp. Une
modification du texte crée obligatoirement une nouvelle révision.

### Contrat protégé

La composition canonique est :

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
cycle. Une Campaign est immuable : modifier un paramètre structurel crée une nouvelle Campaign.

## 7. Identité expérimentale v4

`paper-experiment-v4` est une identité de Campaign. Son digest dépend de :

```text
strategy_id
strategy_revision
strategy_prompt_digest
base_agent_contract_version
configuration_digest
```

Les protocoles v1/v2/v3 restent historiques et inchangés.

## 8. Campaign vs paper_run

```text
Campaign : environnement opérateur/expérimental immuable
paper_run : session d'exécution/recovery
```

Une Campaign peut posséder plusieurs runs liés par recovery. Une reprise ne peut utiliser qu'un
run ayant le même `campaign_id`. Une autre stratégie/révision/configuration produit une autre
Campaign.

## 9. Runtime dynamique

Le Control Plane ne crée pas de second moteur. `build_campaign_runtime()` assemble les mêmes
composants canoniques : `TradingCycleRunner`, `AuditedTradingCycleRunner`, `TradingEngine`,
`RiskEngine` et `PaperBroker`.

Activation/reprise est refusée pendant `RUNNING`. Un runtime `STOPPED` peut être fermé proprement
avant passage vers une autre Campaign.

## 10. Cockpit frontend — Batches 18.9B, 18.10 et 18.11

Le cockpit est un client HTTP du Control Plane, pas un runtime de trading. Il réutilise le rewrite
Next.js `/backend` et le client `frontend/src/lib/api/client.ts` existants.

Il permet :

- Strategy : créer, lister, renommer, archiver ;
- StrategyRevision : charger les révisions séquentielles jusqu'à `latest_revision`, créer une
  nouvelle révision immuable et comparer deux révisions via l'API ;
- prompt preview : visualiser les instructions canoniques et rappeler que l'input dynamique futur
  est `null` avant le cycle ;
- Campaign : créer des snapshots SPOT/PERPETUAL avec tous les champs de `CampaignConfiguration` ;
- sélectionner Luna/Sol, agressivité, cadence, capital, coûts et paramètres Risk ;
- fixer le levier PERPETUAL déterministe et la marge `ISOLATED` ;
- activer frais ou reprendre explicitement une Campaign ;
- envoyer uniquement les commandes moteur canoniques `run-cycle`, `start`, `stop` ;
- observer la Campaign active et le lineage des `paper_run`.

Le frontend ne reproduit pas les validators métier de `CampaignConfiguration`. Les réponses 409,
422 et 503 sont affichées comme refus/conflits backend. Fermer le frontend n'envoie jamais `stop`.

Le Control Plane UI ne persiste ni prompt, ni Campaign, ni secret dans `localStorage` ou
`sessionStorage`. Le stockage local historique du chat reste limité à un identifiant de session.

### Batch 18.10 — architecture UX intégrée

La direction **Option A — Vue d'ensemble** est intégrée :

- `CockpitShell` comme shell opérateur ;
- Vue d'ensemble comme landing ;
- navigation vers Pilotage, Activité, Performance et Assistant ;
- PAPER, Campaign active et état moteur visibles dans le header ;
- panneaux canoniques réutilisés comme vues secondaires.

### Batch 18.11 — aide opérateur intégrée

Le Batch 18.11 ajoute sans modifier les contrats backend :

- une vue principale **Guide** dans la navigation du `CockpitShell` ;
- un démarrage rapide depuis la Vue d'ensemble ;
- le pipeline pédagogique Agent → Risk → Broker PAPER ;
- des explications progressives ciblées sur `run-cycle`/Start, HOLD/Risk et états moteur ;
- un guide versionné dédié : `docs/11_GUIDE_OPERATEUR.md`.

Les aides contextuelles déjà présentes dans `ControlPlanePanel`, `CockpitDashboard`,
`AnalyticsPanel` et `ChatPanel` sont conservées et réutilisées plutôt que dupliquées.

Validation locale finale 18.11 : `pnpm lint`, `pnpm typecheck` et `pnpm build` passent ;
`git diff --check` ne relève aucune erreur hors avertissements de conversion LF → CRLF.

## 11. Validation comportementale — Batch 18.9C

La validation réelle a confirmé les parcours Strategy/StrategyRevision, preview, Campaign SPOT et
PERPETUAL, activation fraîche, `run-cycle`, Start/Stop, restart backend et recovery explicite.

Un BUY SPOT naturel et un BUY PERPETUAL naturel sur SOL/USD ont été observés, tous deux soumis au
Risk Engine déterministe. Des HOLD naturels ont aussi été observés. Aucun SELL naturel n'a été
observé et aucun SELL n'a été forcé.

Le correctif JSON `market_type` est intégré à la frontière Control Plane ; `ExecutableMarket` reste
strict dans le domaine. Le nettoyage mypy de trois routes API est type-only et sans changement
fonctionnel.

## 12. Secrets

Secrets serveur uniquement :

```text
OPENAI_API_KEY
DATABASE_URL
futures clés privées Kraken/LIVE
```

Ils ne sont jamais champs de `CampaignConfiguration` ni envoyés au cockpit.

## 13. Persistence

`0006_paper_control_plane` crée `strategies`, `strategy_revisions`, `campaigns` et
`paper_runs.campaign_id` nullable. Les anciennes rows restent valides avec `campaign_id=NULL`.

## 14. API

Le Control Plane expose Strategy/Revision, Campaign, activation/reprise et prompt preview. Les
commandes de trading restent exclusivement `/api/v1/engine/*`. `/api/v1/paper-runs` expose
`campaign_id`, `resumed_from_paper_run_id` et `recovery_version`.

## 15. État du jalon et périmètre suivant

Les Batches 18.9, 18.10 et 18.11 sont intégrés et validés sur les parcours PAPER actuels. Aucun
périmètre LIVE n'est implicitement ouvert : tout passage LIVE reste un projet/batch séparé avec
permissions, barrières et validation dédiées. Tout nouveau batch doit repartir du `main` GitHub
courant.
