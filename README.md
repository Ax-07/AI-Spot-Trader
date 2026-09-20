# AI Spot Trader

AI Spot Trader est une application expérimentale de **trading crypto SPOT pilotée par un agent IA unique**.

Le projet étudie jusqu'où un agent IA peut prendre des décisions de trading autonomes à partir d'un état de marché et de portefeuille structurés, tout en restant encadré par un **Risk Engine déterministe** qui conserve l'autorité finale avant toute exécution.

> **Statut :** GitHub `main` a été resynchronisé au HEAD `cab3920d4d924d785b0a54c06b51066ccc949eb0` (`docs: record Batch 11 integration`). Le Batch 11 reste intégré fonctionnellement au commit `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7`. Le **patch Batch 12 — Analytics et expérimentation reproductible est préparé mais non intégré** tant que la validation locale, le commit et le push ne sont pas confirmés.

## Principes

- Exchange initial : **Kraken**.
- Trading **SPOT uniquement**.
- Aucun short, levier, margin, future ou perpetual.
- Actions stratégiques : `BUY`, `SELL`, `HOLD`.
- Impossible de vendre un actif non détenu.
- Un seul agent IA conserve la décision stratégique.
- Le Risk Engine déterministe autorise, réduit ou refuse une proposition.
- Seul Risk peut produire un `ExecutionIntent`.
- Aucune sortie LLM ne déclenche directement un Broker ou un ordre Kraken.
- Les premières versions restent exclusivement en **PAPER**.
- Frais, spread et slippage restent explicitement mesurables.
- Toutes les décisions, y compris HOLD et REJECT, sont auditables.
- Les erreurs techniques restent distinctes des décisions métier.
- Aucun secret dans prompts, logs, réponses API ou fichiers versionnés.
- Aucun look-ahead ni réécriture post-hoc.

Principe central : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Architecture

Le backend constitue l'application de trading. Le frontend est uniquement un cockpit de contrôle et de visualisation : fermer ou redémarrer le frontend ne doit jamais arrêter le moteur.

Stack :

- backend : Python, `asyncio`, FastAPI, Pydantic ;
- persistance : PostgreSQL, SQLAlchemy 2 async, `asyncpg`, Alembic ;
- frontend : Next.js, TypeScript, shadcn/ui, Tailwind CSS ;
- communication : REST tant qu'aucun besoin réel et bus d'événements canonique ne justifient un WebSocket ;
- Kraken et le fournisseur LLM restent derrière des interfaces dédiées.

```text
Kraken public data
        |
        v
   MarketState --------+
                       |
 PortfolioState -------+--> AgentInput --> Agent Luna/Sol
                                          BUY / SELL / HOLD
                                                  |
                                                  v
                                             Risk Engine
                                      ALLOW / MODIFY / REJECT
                                                  |
                            HOLD/REJECT -----------+--- tradable
                            aucun Broker                 |
                                                      v
                                             ExecutionIntent
                                               créé par Risk
                                                      |
                                                      v
                                               Paper Broker
                                                      |
                                             Fill(s) + ledger
                                                      |
                                                      v
                                            TradingCycleResult
                                                      |
                                                      v
                                     AuditedTradingCycleRunner
                                                      |
                                                      v
                                      PostgreSQL audit journal
                                                      |
                                                      v
                              durable read/query + analytics reducer
                                                      |
                                                      v
                                       FastAPI REST / analytics
                                                      |
                                                      v
                                          Next.js cockpit
```

## Agent IA

Le port canonique reste :

```python
LLMProvider.generate_decision(agent_input: AgentInput) -> DecisionCandidate
```

Le fournisseur ne produit que `action`, `symbol`, `proposed_quantity` et `rationale`. Les IDs et timestamps restent sous contrôle applicatif. GPT-5.6 Luna est le modèle initial ; Sol reste sélectionnable par configuration.

L'agressivité est un entier de 1 à 10. Son mapping produit exact n'est pas encore figé et n'est pas inventé par l'API ni par le cockpit.

## Trading PAPER canonique

`TradingCycleRunner.run_cycle()` exécute exactement un cycle et `TradingEngine` répète cette primitive séquentiellement. Un seul `MarketState` est partagé entre Agent, Risk et Broker pour le cycle, et un seul `PortfolioState` pré-cycle est partagé entre Agent et Risk.

- HOLD traverse Risk et produit un résultat complet sans intent.
- REJECT est une issue métier normale sans Broker.
- MODIFY utilise exactement la quantité autorisée par Risk.
- ALLOW transmet l'intent produit par Risk.
- Les erreurs Market/Portfolio/Agent/Risk/Broker restent des cycles `FAILED`, jamais des HOLD synthétiques.

## Persistance durable — Batch 09 intégré

Le package `ai_spot_trader.persistence` utilise SQLAlchemy async, PostgreSQL et Alembic. `AuditedTradingCycleRunner` persiste le `TradingCycleResult` après le runner canonique sans dupliquer l'orchestration.

Le schéma `0001_audit_journal` conserve :

- `audit_cycles` ;
- `audit_decisions` ;
- `audit_risk_assessments` ;
- `audit_execution_intents` ;
- `audit_fills`.

Le graphe est transactionnel et idempotent par `cycle_id`. La persistance ne garantit pas encore un exactly-once global entre la mutation du ledger PAPER mémoire et le commit PostgreSQL ; la reconstruction/réconciliation après crash reste différée.

## API FastAPI — Batch 10 intégré

Le Batch 10 expose une façade REST versionnée `/api/v1` sans seconde logique de trading.

### Observation

- `GET /health`
- `GET /api/v1/engine`
- `GET /api/v1/portfolio`
- `GET /api/v1/cycles`
- `GET /api/v1/cycles/latest`
- `GET /api/v1/cycles/{cycle_id}`
- `GET /api/v1/decisions`
- `GET /api/v1/risk-assessments`
- `GET /api/v1/executions`
- `GET /api/v1/errors/latest`
- `GET /api/v1/market/latest`

Les listes utilisent `limit`, `offset`, un ordre déterministe `asc|desc` et des filtres simples. Les routes ne requêtent pas directement les modèles SQLAlchemy : `SqlAlchemyCycleAuditQueryService` fournit une frontière de lecture dédiée.

### Lifecycle

- `POST /api/v1/engine/start`
- `POST /api/v1/engine/stop`

Ces commandes appellent uniquement le `TradingEngine` canonique injecté dans le runtime. FastAPI ne démarre jamais automatiquement le moteur. Si aucun moteur n'est injecté, l'API l'indique explicitement au lieu d'inventer une configuration de capital, paire ou cadence.

### Portefeuille et marché

Le portefeuille courant vient du `PaperPortfolioLedger` injecté. Le dernier marché exposé par l'API d'audit est le dernier `MarketState` durable déjà utilisé par un cycle ; l'endpoint ne déclenche aucun refresh Kraken.

### Erreurs et DB

Les erreurs techniques sont exposées sous forme sanitizée (`stage`, `error_type`, `timed_out`) sans message brut potentiellement sensible.

Lorsque `AI_SPOT_TRADER_DATABASE_URL` est configurée et qu'aucun reader n'est injecté, FastAPI crée le `Database` et le query service pendant son lifespan, sans requête automatique et sans démarrer le trading. La connexion est disposée à l'arrêt. Une DB absente ou indisponible produit une erreur API générique sans fuite d'URL ou de secret.

## Frontend cockpit — Batch 11 intégré

Le Batch 11 remplace le bootstrap technique du Batch 01 par un cockpit de contrôle/observation PAPER.

Il affiche notamment :

- disponibilité FastAPI et audit store ;
- état `RUNNING` / `STOPPED` / `UNAVAILABLE` ;
- Start/Stop via les endpoints Batch 10 uniquement ;
- portefeuille PAPER ;
- dernier marché durable ;
- cycles récents ;
- décisions BUY/SELL/HOLD ;
- résultats Risk ALLOW/MODIFY/REJECT ;
- executions/intents et fills ;
- dernière erreur technique sanitizée.

Le navigateur n'appelle pas directement FastAPI sur une autre origine. Next.js expose un chemin same-origin `/backend/*` et le réécrit vers l'adresse configurée côté serveur :

```text
browser -> /backend/api/v1/... -> Next.js rewrite -> FastAPI
```

Configuration locale :

```powershell
Copy-Item frontend\.env.example frontend\.env.local
# puis ajuster AI_SPOT_TRADER_BACKEND_URL si FastAPI n'écoute pas sur http://127.0.0.1:8000
```

Le polling du cockpit est borné à 10 secondes et suspendu lorsque l'onglet n'est pas visible. Il sert uniquement à l'affichage et ne devient jamais l'ordonnanceur du moteur.

Le frontend ne contient aucun appel OpenAI/Kraken, aucune `RiskPolicy`, aucune création de décision ou d'`ExecutionIntent`, aucune simulation de fill et aucun LIVE.


## Analytics PAPER — Batch 12 patch à valider

Le patch Batch 12 ajoute un reducer analytics **pur, déterministe et en lecture seule** au-dessus du journal durable existant. Aucune migration n'est requise et aucune décision de trading n'est recalculée ou modifiée.

Conventions proposées par le patch :

- source canonique : faits immuables du journal PostgreSQL (`AgentInput`, décision/Risk, fills, portfolio post-cycle) ;
- P&L net : equity marquée au prix durable du cycle moins l'equity initiale durable ;
- P&L brut : P&L net + frais + spread + slippage cumulés ;
- coûts : sommes des valeurs effectivement persistées dans les fills, jamais réestimées avec une configuration courante ;
- drawdown : calculé sur l'equity nette marquée ;
- exposition : valeur des positions au prix durable du cycle rapportée à l'equity lorsque celle-ci est positive ;
- trade : exécution effectivement fillée ; HOLD et REJECT sont comptés séparément ;
- cycles `FAILED` : comptés séparément et valorisés uniquement lorsque les faits marché/portefeuille nécessaires sont durables ;
- frontière quotidienne : **UTC** ;
- historique : chaque point utilise uniquement le `MarketState` durable du cycle concerné, sans dernier prix futur ;
- reproductibilité : `calculation_version` + SHA-256 de la séquence durable `(cycle_id, result_digest)` ;
- incohérence de continuité ou actif non valorisable : erreur explicite plutôt qu'une métrique inventée.

L'API proposée ajoute `GET /api/v1/analytics`. Le cockpit affiche P&L, coûts, drawdown, exposition, activité et performances quotidiennes sans recalcul métier dans le navigateur. La reproduction d'une **décision LLM** sous protocole expérimental complet (modèle/prompt/RiskPolicy/configuration) n'est pas prétendue par ce batch et reste du ressort des Batches 13/14.

## PostgreSQL local

Depuis la racine du repository :

```powershell
docker compose up -d
$env:AI_SPOT_TRADER_DATABASE_URL="postgresql+asyncpg://ai_spot_trader:local_dev_password@localhost:5432/ai_spot_trader"
backend\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

Le mot de passe versionné dans `docker-compose.yml` est uniquement une valeur locale de développement.

## Validation

Batch 11 validé localement puis intégré sur `main` au commit `d3f41a3b9df6a69018508a4dc5c8a7286cbbced7`.

```text
pnpm --dir frontend lint       réussi
pnpm --dir frontend typecheck  réussi
pnpm --dir frontend build      réussi — Next.js 16.3.3, route / statique compilée
git diff --check               aucune erreur ; warnings LF -> CRLF uniquement
```

Smoke test runtime confirmé : backend accessible, moteur non configuré, ressources vides/indisponibles affichées sans crash ni fuite d'erreur brute, puis backend arrêté avec bascule propre du cockpit vers l'état indisponible. Le working tree était propre après commit/push.

La dernière validation backend intégrée reste celle du Batch 10 : **222 tests**, Ruff OK et mypy sans erreur sur 70 fichiers.


### Validation du patch Batch 12 dans cet environnement

Exécuté pendant la préparation du patch :

```text
pytest ciblé backend/tests/test_analytics.py : 6 tests réussis
```

La suite backend complète, Ruff, mypy, lint/typecheck/build frontend et le smoke test PostgreSQL/runtime doivent encore être exécutés localement dans le repository complet avant toute intégration. Le Batch 12 ne doit donc pas être marqué intégré à ce stade.

## Sécurité

- Aucun secret ou clé API réel ne doit être versionné, journalisé ou renvoyé par l'API.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- PAPER et LIVE restent explicitement séparés.
- Toute exécution doit continuer à passer par Risk.
- Le bind API par défaut reste local (`127.0.0.1`). Toute exposition distante des commandes lifecycle devra être protégée explicitement avant usage.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et développement. Il ne constitue pas un conseil financier et ne garantit aucun résultat de trading. La cible expérimentale de +4 %/jour reste une métrique de recherche, jamais une promesse.
