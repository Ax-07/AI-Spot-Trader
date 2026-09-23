# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **PAPER** sur Kraken, pilotée
par **un seul Agent IA stratégique**. L'Agent recherche, sélectionne un marché exécutable puis
propose `BUY`, `SELL` ou `HOLD`. Le **Risk Engine déterministe** conserve l'autorité finale : seul
Risk peut produire un `ExecutionIntent`, ensuite exécuté par le `PaperBroker`.

> Objectif expérimental : rechercher une performance élevée, avec une cible de travail de +4 %/jour.
> Ce n'est ni une promesse ni une garantie de rendement.

## Référence auditée — Batch 18.9B

```text
repository : Ax-07/AI-Spot-Trader
branche    : main
HEAD       : efe5a0f162a69e50bd6e5f5cd7aa61039792e911
code       : 11a04be33bf209552e6337e28318d039b775b264
```

Le HEAD `efe5a0f` finalise documentairement le Batch 18.9A ; le dernier commit code intégré reste
`11a04be` (`feat: add PAPER control plane`).

Le Batch 18.9B livré avec ce patch ajoute le cockpit frontend du Control Plane. Il n'est pas encore
intégré à GitHub tant que l'opérateur ne l'a pas extrait, validé, committé et poussé.

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
- aucun secret dans les prompts, Campaigns, réponses UI ou fichiers versionnés ;
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

Le frontend n'appartient pas à cette chaîne d'exécution.

## Control Plane backend — Batch 18.9A

### Strategy / StrategyRevision

`Strategy` porte l'identité et le nom. `StrategyRevision` est immuable et contient le texte
stratégique opérateur, son digest SHA-256, la version du contrat Agent protégé et son timestamp.
Modifier le texte crée une nouvelle révision. Renommer la Strategy ne modifie aucune révision.

### Contrat Agent protégé

Les runtimes de Campaign composent :

```text
contrat applicatif protégé
+ stratégie opérateur éditable
+ contexte d'agressivité canonique
```

L'input dynamique (`MarketSelectionInput` ou `AgentInput`) est séparé. Le preview ne l'invente pas.

### Campaign

Une `Campaign` est un snapshot immuable non sensible : modèle, agressivité, cadence, capital,
univers SPOT/PERP, coûts, levier/marge, limites Risk, deadlines, stratégie/révision et digests.

`OPENAI_API_KEY`, `DATABASE_URL` et les futurs secrets privés Kraken/LIVE restent exclusivement
serveur.

### Campaign vs paper_run

```text
Campaign = identité configuration/stratégie expérimentale
paper_run = lifetime d'exécution/recovery
```

Une reprise conserve `campaign_id`, crée un nouveau `paper_run_id`, renseigne
`resumed_from_paper_run_id` et restaure le ledger sans replay historique.

## Cockpit Control Plane — Batch 18.9B

Le nouveau panneau frontend permet de :

- créer, lister, renommer et archiver des Strategies ;
- consulter les révisions jusqu'à `latest_revision` ;
- créer une nouvelle StrategyRevision immuable ;
- comparer deux révisions via l'API backend ;
- prévisualiser le prompt canonique en distinguant contrat Agent protégé, stratégie opérateur,
  contexte d'agressivité et input dynamique futur ;
- créer une Campaign PAPER SPOT et/ou PERPETUAL ;
- choisir GPT-5.6 Luna ou Sol ;
- configurer agressivité, cadence, capital et actif de règlement ;
- configurer frais, spread, slippage ;
- configurer les champs Risk exposés par `CampaignConfiguration` ;
- configurer le levier PERPETUAL déterministe avec marge `ISOLATED` ;
- visualiser les digests et identités expérimentales ;
- déclencher activation fraîche ou reprise explicite ;
- piloter `run-cycle`, `start`, `stop` via les routes moteur canoniques ;
- voir Campaign active, `campaign_id`, `paper_run_id`, `resumed_from_paper_run_id` et
  `recovery_version` ;
- afficher les refus backend 409/422/503 sans les contourner.

Le cockpit ne calcule aucun signal, aucune décision, aucune autorisation Risk et aucun ordre. Les
valeurs du builder sont envoyées au modèle Pydantic canonique, qui conserve l'autorité de
validation.

Le nouveau panneau ne stocke ni prompt, ni Campaign, ni paramètres Risk dans `localStorage` ou
`sessionStorage`. Fermer le frontend n'envoie jamais `stop` au backend.

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

Commandes moteur :

```text
POST /api/v1/engine/run-cycle
POST /api/v1/engine/start
POST /api/v1/engine/stop
```

`/api/v1/paper-runs` expose `campaign_id`, `resumed_from_paper_run_id` et `recovery_version`.

## Persistence PostgreSQL

```text
0001_create_audit_journal
-> 0002_add_paper_runs
-> 0003_agent_tool_traces
-> 0004_multi_market_selection
-> 0005_paper_run_recovery
-> 0006_paper_control_plane
```

Aucune migration backend n'est ajoutée par le Batch 18.9B.

## Validation du patch 18.9B

Exécuté par ChatGPT :

```text
harness source frontend : 50 assertions passées
Node strip-types syntax checks : OK
typecheck ciblé avec stubs de dépendances : OK
```

À exécuter localement avec les dépendances frontend installées :

```powershell
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

Le backend n'est pas modifié par ce patch ; sa validation intégrée de référence reste celle de
18.9A (`504 passed`, Ruff OK, mypy OK, migration `0006` OK).

Après intégration de 18.9B, le prochain périmètre est le **Batch 18.9C — validation comportementale
réelle via frontend**.
