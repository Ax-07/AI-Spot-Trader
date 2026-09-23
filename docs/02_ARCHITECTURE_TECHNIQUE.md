# 02 — Architecture technique

## 1. Référence

Base intégrée auditée avant Batch 18.9A :

```text
HEAD GitHub : 2b0d227454f2bf894b075b8deef3378e2fe823b4
Dernier code: 0886216324106d941c3df0e30f074e24dbe1d33a
```

## 2. Architecture générale

```text
FastAPI
  |
  +-- Control Plane persistence (PostgreSQL)
  |     +-- Strategy / StrategyRevision
  |     +-- Campaign
  |     +-- campaign_id -> paper_runs
  |
  +-- CampaignRuntimeManager (process-local ownership)
        |
        +-- runtime actif optionnel
              +-- TradingEngine
              +-- AuditedTradingCycleRunner
              +-- TradingCycleRunner
              +-- OpenAIDecisionProvider
              +-- RiskEngine
              +-- PaperBroker
              +-- PaperPortfolioLedger
              +-- Kraken public research/execution sources
```

Le manager ne possède aucune implémentation alternative du cycle. Il ne fait qu'assembler,
activer, fermer et déléguer vers les composants existants.

## 3. Nouveaux modules 18.9A

```text
agent/prompt.py
  contrat protégé, normalisation/digest stratégie, composition canonique
agent/strategy_client.py
  adapter transport qui remplace les instructions historiques par la composition de campagne

control_plane.py
  CampaignConfiguration whitelistée + digests v4
campaign_composition.py
  assemblage runtime canonique depuis Campaign
core/control_plane_runtime.py
  ownership d'un runtime actif maximum

persistence/models.py
  StrategyRecord, StrategyRevisionRecord, CampaignRecord, paper_runs.campaign_id
persistence/control_plane.py
  store async Strategy/Revision/Campaign
persistence/campaign_runs.py
  lifecycle recovery limité à une Campaign

api/control_plane_schemas.py
api/routes/control_plane.py
  surface REST opérateur

alembic/versions/0006_paper_control_plane.py
  schéma PostgreSQL
```

## 4. Contrat Agent et prompt

### Compatibilité historique

`AGENT_PROMPT_VERSION = agent-strategy-v4` et le texte `AGENT_SYSTEM_PROMPT` historique sont
conservés pour les manifestes v1/v2/v3.

### Nouveau runtime Campaign

```text
StrategyInstructionsClient
  -> lit AggressivenessContext déjà présent dans l'input structuré
  -> compose_agent_instructions()
       - PROTECTED_AGENT_CONTRACT / agent-contract-v1
       - StrategyRevision.strategy_prompt
       - AggressivenessContext
  -> délègue au même OpenAIResponsesClient
```

Le `MarketSelectionInput`/`AgentInput` JSON est inchangé et reste transmis séparément comme
`input_text`. Le preview retourne uniquement les instructions statiques réellement composables ;
`dynamic_input` reste `null` avant un cycle réel.

## 5. Digests

### Prompt

`strategy-prompt-sha256-v1` : LF, trailing spaces par ligne supprimés, blancs extérieurs supprimés,
SHA-256 UTF-8.

### Configuration

`paper-control-plane-config-v1` sérialise le modèle Pydantic en JSON canonique trié pour calculer
`configuration_digest`.

### Expérience v4

```text
SHA256(canonical JSON {
  experiment_protocol_version = paper-experiment-v4,
  strategy_id,
  strategy_revision,
  strategy_prompt_digest,
  base_agent_contract_version,
  configuration_digest
})
```

Les digests v1/v2/v3 ne sont pas recalculés avec ces nouveaux champs.

## 6. Persistence

Schéma 18.9A :

```text
strategies
  PK strategy_id

strategy_revisions
  PK (strategy_id, strategy_revision)
  FK strategy_id -> strategies

campaigns
  PK campaign_id
  FK (strategy_id, strategy_revision) -> strategy_revisions

paper_runs
  campaign_id NULLABLE FK -> campaigns
  resumed_from_paper_run_id UNIQUE FK -> paper_runs
```

`campaign_id` est nullable afin de préserver les runs historiques 18.x.

## 7. Activation fraîche

```text
POST /campaigns/{id}/activate
-> vérifier moteur actif != RUNNING
-> charger Campaign + StrategyRevision
-> vérifier prompt digest + base contract version
-> vérifier absence de run antérieur pour cette campagne
-> fermer l'ancien runtime STOPPED éventuel
-> build_campaign_runtime(..., resume=False)
-> CampaignPaperRunLifecycle.initialize()
-> nouveau paper_run avec campaign_id
```

## 8. Reprise

```text
POST /campaigns/{id}/resume
-> même vérification de campagne/révision
-> exiger un run précédent de la même campaign_id
-> vérifier univers
-> restaurer current_portfolio_payload
-> clôturer parent si nécessaire
-> nouveau run + resumed_from_paper_run_id
```

Aucune décision, recherche, évaluation Risk, intention ou fill historique n'est réexécuté.

## 9. Ressources et ownership

Le Control Plane garde une `Database` d'infrastructure pour lire Strategy/Campaign et les surfaces
read-only. Chaque runtime actif possède ses ressources réseau et sa propre `Database`/pool vers la
même URL pour le cycle/audit. Lors d'un switch, le runtime actif est fermé avant remplacement ; la
base d'infrastructure reste vivante jusqu'au shutdown FastAPI.

Une activation/reprise pendant `TradingEngine.is_running` est refusée en 409.

## 10. Frontières de sécurité

- CampaignConfiguration : whitelist stricte et `extra=forbid` ;
- aucune clé API/URL DB dans Campaign ;
- secret-like StrategyPrompt refusé avant persistence ;
- erreurs de composition/initialisation retournées sous forme générique 503 ;
- erreurs de conflict/not-found exposent uniquement une cause opératoire non sensible ;
- tools restent read-only et n'ont aucune dépendance Risk/Broker ;
- Risk/Broker ne sont jamais appelés depuis le Control Plane.

## 11. API paper-runs

La réponse expose désormais :

```text
campaign_id
resumed_from_paper_run_id
recovery_version
```

en plus des champs historiques et de `execution_universe`.

## 12. Migration

Cible canonique PostgreSQL :

```powershell
alembic -c backend/alembic.ini upgrade head
```

Le test réel de migration doit être effectué sur une base PostgreSQL disponible avant intégration.
