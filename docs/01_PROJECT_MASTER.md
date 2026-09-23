# 01 — Project Master

## 1. Mission

AI Spot Trader est une application expérimentale de trading crypto PAPER pilotée par **un seul
Agent IA stratégique**. Le backend constitue l'application de trading ; le frontend est uniquement
un cockpit de contrôle et de visualisation.

Référence intégrée auditée au départ du Batch 18.9A :

```text
main = 2b0d227454f2bf894b075b8deef3378e2fe823b4
last code = 0886216324106d941c3df0e30f074e24dbe1d33a
```

## 2. Invariants fonctionnels

### Globaux

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement ; LIVE reste séparé et ultérieur ;
- actions finales `BUY`, `SELL`, `HOLD` ;
- Luna par défaut, Sol configurable ;
- Risk Engine déterministe avec autorité finale ;
- seul Risk crée un `ExecutionIntent` ;
- aucune sortie LLM ni aucun tool ne déclenche Broker/Kraken ;
- coûts PAPER et funding pris en compte ;
- audit causal de toutes les décisions, `HOLD` inclus ;
- aucun secret dans les artefacts opérateur, prompts, logs ou Git ;
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
- levier déterministe/configuré ;
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

Aucun composant déterministe ne choisit l'opportunité à la place de l'Agent.

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

## 6. Control Plane — Batch 18.9A

### Strategy

`Strategy` est une identité durable nommable/archivable. Le renommage ne modifie aucune expérience
historique.

### StrategyRevision

Chaque révision est immuable et contient :

```text
strategy_id
strategy_revision
strategy_prompt
strategy_prompt_digest
base_agent_contract_version
created_at
```

Une modification de prompt crée obligatoirement une nouvelle révision.

### Contrat protégé

Le texte éditable n'est pas le contrat technique de l'application. La composition canonique est :

```text
PROTECTED_AGENT_CONTRACT
+ StrategyRevision.strategy_prompt
+ AggressivenessContext canonique
```

Le contrat protégé impose les invariants PAPER/Risk/Broker/SPOT/PERP et la sortie structurée. Il
n'est exposé à aucune mutation API.

### Campaign

Une campagne snapshotte stratégie/révision et configuration structurelle non sensible. Elle ne
contient aucun secret serveur. Sa configuration inclut modèle, agressivité, cadence, capital,
univers, coûts, levier/marge, limites Risk et deadlines de cycle.

Une campagne est immuable après création. Modifier un paramètre structurel crée une nouvelle
campagne.

## 7. Identité expérimentale v4

`paper-experiment-v4` est une identité de campagne, pas une réinterprétation du JSON
`ExperimentManifest` historique. Son `experiment_digest` dépend de :

```text
strategy_id
strategy_revision
strategy_prompt_digest
base_agent_contract_version
configuration_digest
```

Le `configuration_digest` encode tous les paramètres effectifs de la Campaign, y compris les
limites Risk PERPETUAL absentes du vieux `ExperimentRiskPolicySnapshot` v3.

`paper-experiment-v1`, `v2` et `v3` restent inchangés et validés avec leur logique historique.

## 8. Campaign vs paper_run

```text
Campaign : environnement opérateur/expérimental immuable
paper_run : session d'exécution/recovery
```

Une campagne peut posséder plusieurs runs liés par recovery. Une reprise ne peut utiliser qu'un
run ayant le même `campaign_id`. Une autre stratégie/révision/configuration produit une autre
campagne et ne peut donc pas être reprise comme si elle était identique.

## 9. Runtime dynamique

Le Control Plane ne crée pas de second moteur. `build_campaign_runtime()` assemble les mêmes
composants canoniques :

```text
TradingCycleRunner
AuditedTradingCycleRunner
TradingEngine
RiskEngine
PaperBroker
```

L'activation/reprise est refusée pendant qu'un moteur actif est `RUNNING`. Un runtime `STOPPED`
peut être fermé proprement avant le passage vers une autre campagne.

## 10. Secrets

Secrets serveur uniquement :

```text
OPENAI_API_KEY
DATABASE_URL
futures clés privées Kraken/LIVE
```

Ils ne sont jamais champs de `CampaignConfiguration`. Les modèles API sont `extra="forbid"` et
les StrategyRevision refusent des motifs usuels de secret dans le texte opérateur.

## 11. Persistence

`0006_paper_control_plane` crée :

```text
strategies
strategy_revisions
campaigns
paper_runs.campaign_id (nullable FK)
```

Les anciennes rows restent valides avec `campaign_id=NULL`.

## 12. API

Le Control Plane expose les CRUDs limités Strategy/Revision, la création/lecture Campaign,
l'activation/reprise et le prompt preview. Les commandes de trading restent exclusivement les
routes historiques `/api/v1/engine/*`.

## 13. Périmètre suivant

Le Batch 18.9B construira le cockpit frontend à partir de ces contrats backend. Il ne doit pas
introduire de logique de trading frontend ni arrêter le moteur lorsque l'UI se ferme.
