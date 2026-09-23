# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs
> et les décisions récentes nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Risk, SPOT sans short/levier, PERPETUAL avec protections déterministes, audit durable,
no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence code intégrée — Batch 18.9A

```text
Code intégré : 11a04be33bf209552e6337e28318d039b775b264
Commit       : feat: add PAPER control plane
```

Le Batch 18.9A est **intégré et validé**.

## Décisions historiques toujours actives

Les ADR 136 à 172 restent applicables : sélection et décision avec le même Agent, univers typé,
séparation research/execution, audit multi-marchés, analytics causal, protocoles v1/v2/v3,
recovery sans replay, retries uniquement sur frontières répétables et deadlines de stage comme
plafond absolu.

## Décisions Batch 18.9A — intégrées

### ADR-173 — StrategyRevision est immuable

**INTÉGRÉE.** `Strategy` porte l'identité et le nom. Tout changement du texte stratégique crée une
nouvelle `(strategy_id, strategy_revision)`. Les Campaigns référencent une révision exacte et son
digest. Renommer une Strategy ne modifie aucune révision.

### ADR-174 — Séparer contrat Agent protégé et stratégie opérateur

**INTÉGRÉE.** Le contrat `agent-contract-v1` protège PAPER, les schémas BUY/SELL/HOLD,
SPOT/PERPETUAL, les inputs structurés, l'absence d'appel direct Broker/Risk et l'autorité finale de
Risk. La StrategyRevision est ajoutée comme couche subordonnée et ne peut modifier ce contrat via
l'API.

Le texte historique `AGENT_SYSTEM_PROMPT`/`agent-strategy-v4` est conservé pour ne pas modifier les
manifestes v1/v2/v3.

### ADR-175 — Utiliser un digest déterministe du prompt opérateur

**INTÉGRÉE.** `strategy-prompt-sha256-v1` normalise CRLF/CR en LF, retire les espaces de fin de
ligne, retire les blancs extérieurs puis calcule SHA-256 sur UTF-8. Les motifs usuels de secret sont
refusés avant persistence sans réafficher leur valeur.

### ADR-176 — Campaign est un snapshot opérateur non sensible

**INTÉGRÉE.** `CampaignConfiguration` est une whitelist stricte. Elle snapshotte modèle,
agressivité, cadence, capital, univers, coûts, levier/marge, Risk et deadlines. Les paramètres
réseau/tools restent serveur. Aucun `OPENAI_API_KEY`, `DATABASE_URL` ou futur secret privé n'entre
dans Campaign.

### ADR-177 — `paper-experiment-v4` est une identité de Campaign additive

**INTÉGRÉE.** V4 dépend de `strategy_id`, `strategy_revision`, `strategy_prompt_digest`,
`base_agent_contract_version` et `configuration_digest`. Le digest de configuration couvre aussi
tous les paramètres PERPETUAL/Risk effectifs.

`paper-experiment-v1/v2/v3` restent inchangés ; aucun champ v4 n'est injecté rétroactivement dans
leurs anciens payloads/digests.

### ADR-178 — Distinguer Campaign et paper_run

**INTÉGRÉE.** `campaign_id` identifie un environnement immuable. `paper_run_id` identifie un
lifetime d'exécution. `paper_runs.campaign_id` est nullable pour les historiques. Une même Campaign
peut produire plusieurs runs successifs via `paper-ledger-recovery-v1`.

Une reprise ne cherche que le dernier run de la même Campaign, vérifie l'univers et restaure le
snapshot durable. Une nouvelle configuration/stratégie est une autre Campaign, jamais une reprise.

### ADR-179 — Le Control Plane possède le runtime, il ne remplace pas le moteur

**INTÉGRÉE.** `CampaignRuntimeManager` détient au plus un runtime actif et délègue aux primitives
existantes. `build_campaign_runtime()` assemble `TradingCycleRunner`, `AuditedTradingCycleRunner`,
`TradingEngine`, `RiskEngine` et `PaperBroker` existants.

Activation/reprise pendant `RUNNING` => conflit. Un runtime STOPPED peut être fermé proprement avant
remplacement. Les routes `/api/v1/engine/run-cycle|start|stop` restent canoniques.

### ADR-180 — Le preview utilise exactement la composition live

**INTÉGRÉE.** `compose_agent_instructions()` est appelée par l'adapter live
`StrategyInstructionsClient` et par `/api/v1/prompt-preview`. Le preview n'invente pas le futur
`MarketSelectionInput`/`AgentInput` : il indique seulement son type et retourne `dynamic_input=null`.

### ADR-181 — Exposer le lineage recovery déjà durable

**INTÉGRÉE.** `/api/v1/paper-runs` expose `campaign_id`, `resumed_from_paper_run_id` et
`recovery_version`. Les anciens runs restent compatibles avec `campaign_id=null`.

## Changelog — 2026-09-23 — Batch 18.9A intégré

Implémentation intégrée :

- migration `0006_paper_control_plane` ;
- modèles/store Strategy/Revision/Campaign ;
- prompt protégé + stratégie versionnée + digest ;
- CampaignConfiguration et v4 ;
- lifecycle campaign-scoped ;
- composition/runtime manager canoniques ;
- routes API Control Plane ;
- champs recovery/campaign sur paper-runs ;
- tests ciblés ;
- documentation 18.9A.

Validation ChatGPT initiale :

```text
py_compile des fichiers Python du patch : OK
pytest unitaires prompt/config/v4/adapter : 11 passed
```

Validation opérateur finale après Correctif 1 :

```text
pytest ciblé persistence : 1 passed
ruff check backend : All checks passed!
pytest backend : 504 passed, 2 warnings
mypy --config-file backend/pyproject.toml backend/src : Success, 89 source files
Alembic 0005_paper_run_recovery -> 0006_paper_control_plane sur PostgreSQL : OK
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Le Correctif 1 remplace la désérialisation Python stricte de `CampaignConfiguration` par une
validation JSON stricte adaptée aux payloads JSONB (`model_validate_json`) et corrige trois écarts
Ruff mécaniques. Aucun changement de schéma, migration, Risk, digest ou moteur n'est introduit par
ce correctif.

Commit d'intégration :

```text
11a04be33bf209552e6337e28318d039b775b264
feat: add PAPER control plane
```

Prochaine étape : Batch 18.9B dans une nouvelle discussion, dédié au cockpit frontend.
