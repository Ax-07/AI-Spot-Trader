# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **PAPER** sur Kraken, pilotée
par **un seul Agent IA stratégique**. L'Agent recherche, sélectionne un marché exécutable puis
propose `BUY`, `SELL` ou `HOLD`. Le **Risk Engine déterministe** conserve l'autorité finale : seul
Risk peut produire un `ExecutionIntent`, ensuite exécuté par le `PaperBroker`.

> Objectif expérimental : rechercher une performance élevée, avec une cible de travail de +4 %/jour.
> Ce n'est ni une promesse ni une garantie de rendement.

## Référence code intégrée — Batch 18.9A

```text
repository : Ax-07/AI-Spot-Trader
branche    : main
code       : 11a04be33bf209552e6337e28318d039b775b264
commit     : feat: add PAPER control plane
```

Le Batch 18.9A — **Control Plane PAPER backend + stratégies éditables + campagnes persistantes** —
est intégré sur `main`.

Validation opérateur du Batch 18.9A :

```text
pytest backend : 504 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 89 source files
Alembic 0005_paper_run_recovery -> 0006_paper_control_plane sur PostgreSQL : OK
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

## Invariants

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- PAPER uniquement ;
- SPOT sans short, levier ni marge ;
- PERPETUAL linéaire LONG/SHORT, marge `ISOLATED` ;
- levier configuré/déterministe, jamais choisi par le LLM ;
- aucune sortie LLM -> Broker ;
- aucun tool -> Broker/Risk ;
- Risk autorise, modifie ou refuse et garde l'autorité finale ;
- aucun secret dans les prompts, campagnes, réponses API ou fichiers versionnés ;
- aucun replay LLM/Risk/Broker/Fill lors du recovery ;
- aucun look-ahead ;
- toutes les décisions, dont `HOLD`, restent auditables ;
- le backend reste indépendant du frontend.

Principe : **l'Agent propose. Le Risk Engine autorise, modifie ou refuse.**

## Pipeline canonique

```text
PortfolioState complet
        |
        v
MarketSelectionInput
        |
        v
OpenAIDecisionProvider (Agent unique)
        |\
        | +--> tools read-only Kraken publics
        v
MarketSelection (symbol + market_type + traces + digest)
        |
        v
RoutedExecutableMarketDataSource
        |
        v
MarketState canonique exact
        |
        v
AgentInput -> même Agent -> BUY / SELL / HOLD
        |
        v
RiskEngine -> ALLOW / MODIFY / REJECT
        |
        v
ExecutionIntent éventuel -> PaperBroker -> Fill
        |
        v
Audit PostgreSQL + ledger PAPER durable
```

Il n'existe ni second Agent, ni moteur parallèle, ni scanner déterministe qui choisit
l'opportunité à la place du LLM.

## Control Plane — Batch 18.9A

Le Control Plane ajoute trois concepts persistants.

### Strategy / StrategyRevision

`Strategy` porte l'identité et le nom d'une stratégie. `StrategyRevision` est immuable et contient
le texte stratégique opérateur, son digest SHA-256, la version du contrat Agent protégé et son
timestamp.

Le digest du prompt utilise la normalisation `strategy-prompt-sha256-v1` :

1. CRLF/CR -> LF ;
2. suppression des espaces de fin de ligne ;
3. suppression des blancs extérieurs ;
4. SHA-256 UTF-8 du texte normalisé.

Créer un nouveau texte crée une nouvelle révision. Renommer la stratégie ne change aucun digest.
Les révisions refusent des motifs de secrets connus au lieu de les recopier dans le prompt.

### Contrat Agent protégé + stratégie opérateur

Les runtimes de campagne composent les instructions dans cet ordre :

```text
contrat applicatif protégé
+ stratégie opérateur éditable
+ contexte d'agressivité canonique
```

L'input dynamique (`MarketSelectionInput` ou `AgentInput`) reste envoyé séparément et n'est jamais
inventé par l'API de preview.

Le contrat protégé impose toujours PAPER, BUY/SELL/HOLD structurés, les sémantiques SPOT/PERP,
l'absence d'accès Broker/Risk depuis le LLM/tools, l'autorité finale de Risk et l'interdiction
d'inventer des faits. Une stratégie « ignore Risk » n'ajoute aucun chemin d'exécution : elle reste
subordonnée au contrat et le pipeline déterministe demeure inchangé.

### Campaign

Une `Campaign` est un snapshot immuable de configuration opérateur non sensible :

- modèle Luna/Sol ;
- agressivité et cadence ;
- capital initial, actif de règlement et univers SPOT/PERP ;
- frais, spread, slippage ;
- levier/marge PERPETUAL ;
- limites Risk SPOT et PERPETUAL ;
- deadlines MARKET/AGENT/BROKER ;
- stratégie/révision/digest ;
- `configuration_digest` et `experiment_digest`.

`OPENAI_API_KEY`, `DATABASE_URL` et les futurs secrets privés Kraken/LIVE restent exclusivement
dans la configuration serveur et ne font pas partie du modèle Campaign.

## `paper-experiment-v4`

Le Control Plane introduit `paper-experiment-v4` comme identité de campagne. Son digest canonique
inclut au minimum :

```text
strategy_id
strategy_revision
strategy_prompt_digest
base_agent_contract_version
configuration_digest
```

Le `configuration_digest` couvre les paramètres structurels effectifs, notamment les limites Risk
PERPETUAL qui n'étaient pas toutes représentées par le snapshot Risk historique v3.

Les protocoles `paper-experiment-v1`, `v2` et `v3` ne sont pas réinterprétés ni migrés. Leur code de
validation et leurs anciens digests restent leur source de vérité historique.

## Campaign vs `paper_run`

```text
Campaign = identité configuration/stratégie expérimentale
paper_run = lifetime d'exécution/recovery
```

Une même campagne peut produire plusieurs `paper_run_id` successifs. Chaque reprise :

- conserve `campaign_id` ;
- crée un nouveau `paper_run_id` ;
- renseigne `resumed_from_paper_run_id` ;
- conserve `paper-ledger-recovery-v1` ;
- restaure le snapshot durable sans replay LLM/Risk/Broker/Fill.

Changer stratégie, révision ou configuration implique une **nouvelle campagne**. Une reprise ne
cherche que les runs de la campagne demandée et échoue fermée en cas d'incompatibilité.

## API Control Plane

Sous `/api/v1` :

```text
POST   /strategies
GET    /strategies
GET    /strategies/{strategy_id}
PATCH  /strategies/{strategy_id}
POST   /strategies/{strategy_id}/archive
POST   /strategies/{strategy_id}/revisions
GET    /strategies/{strategy_id}/revisions/{revision}
GET    /strategies/{strategy_id}/compare?left=1&right=2

POST   /campaigns
GET    /campaigns
GET    /campaigns/active
GET    /campaigns/{campaign_id}
POST   /campaigns/{campaign_id}/activate
POST   /campaigns/{campaign_id}/resume

POST   /prompt-preview
```

Les commandes moteur existantes restent canoniques :

```text
POST /api/v1/engine/run-cycle
POST /api/v1/engine/start
POST /api/v1/engine/stop
```

L'API `/api/v1/paper-runs` expose aussi `campaign_id`, `resumed_from_paper_run_id` et
`recovery_version`.

## Persistence PostgreSQL

Chaîne de migrations :

```text
0001_create_audit_journal
-> 0002_add_paper_runs
-> 0003_agent_tool_traces
-> 0004_multi_market_selection
-> 0005_paper_run_recovery
-> 0006_paper_control_plane
```

`0006_paper_control_plane` crée `strategies`, `strategy_revisions`, `campaigns` et ajoute le FK
nullable `paper_runs.campaign_id`. Les anciens runs restent valides avec `campaign_id = NULL`.

## Démarrage sans campagne active

Avec l'infrastructure serveur configurée (`DATABASE_URL`, migrations appliquées), FastAPI démarre
le Control Plane sans créer implicitement de campagne ni de run. Le moteur est alors
`UNAVAILABLE` jusqu'à activation/reprise explicite. `OPENAI_API_KEY` n'entre dans aucune Campaign ;
il est requis au moment de composer un runtime Agent réel.

## Validation

Commandes de validation de référence sous PowerShell :

```powershell
pytest backend
ruff check backend
mypy --config-file backend/pyproject.toml backend/src
alembic -c backend/alembic.ini upgrade head
git diff --check
git status --short
```

Le prochain périmètre est le Batch 18.9B : cockpit frontend de configuration SPOT/PERPETUAL,
reposant sur les contrats backend 18.9A intégrés. Le frontend reste un cockpit de contrôle ; sa
fermeture ne doit jamais arrêter le moteur backend.
