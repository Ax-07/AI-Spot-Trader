# AI Spot Trader

AI Spot Trader est une application expérimentale de **trading crypto SPOT pilotée par un agent IA unique**.

Le projet étudie jusqu'où un agent IA peut prendre des décisions de trading autonomes à partir d'un état de marché et de portefeuille structurés, tout en restant encadré par un **Risk Engine déterministe** qui conserve l'autorité finale avant toute exécution.

> **Statut :** le **Batch 15 — Chat opérateur avec l'Agent est intégré** sur GitHub `main` au commit fonctionnel `1c182b829c141c20be5cc8e62a3f8afa6f71b4d6` (`feat: add operator agent chat`), après validation locale complète. Le Batch 14 reste la référence précédente au commit fonctionnel `dc60033f60bf5d98a68e6131a9320e575d46cc8d`, suivi du commit documentaire `b2c74672744639f86c38e873f25d56c77f899c76`.

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
- Le chat opérateur est **informatif uniquement** : il ne modifie jamais silencieusement la stratégie et n'est jamais injecté dans les cycles suivants.

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

Le Batch 15 ajoute un chemin conversationnel **latéral et en lecture seule** :

```text
Cockpit Chat -> FastAPI /api/v1/chat -> OperatorChatService
                                      |-> faits canoniques runtime/audit/analytics
                                      `-> OpenAIChatProvider -> même LLMModel Luna/Sol

Ce chemin ne rejoint jamais Risk, Broker, Kraken privé ou ExecutionIntent.
```

## Agent IA

Le port canonique reste :

```python
LLMProvider.generate_decision(agent_input: AgentInput) -> DecisionCandidate
```

Le fournisseur ne produit que `action`, `symbol`, `proposed_quantity` et `rationale`. Les IDs et timestamps restent sous contrôle applicatif. GPT-5.6 Luna est le modèle initial ; Sol reste sélectionnable par configuration.

### Agressivité — Batch 13 intégré

Le Batch 13 fixe une interprétation **discrète et versionnée** des niveaux `1..10` sous `aggressiveness-map-v1`. Chaque niveau fournit un `AggressivenessContext` explicite (posture + instruction stratégique) transmis dans `AgentInput`.

L'agressivité peut influencer uniquement la **volonté stratégique d'agir** et la **quantité proposée par l'Agent**. Elle ne modifie jamais `RiskPolicy`, les balances, les positions détenues, la solvabilité BUY, les contraintes temporelles, les coûts PAPER ou l'autorité finale de Risk.

Le prompt Agent devient `agent-strategy-v2`. Une expérience contrôlée peut attacher à chaque `AgentInput` un `ExperimentManifest` `paper-experiment-v1`. Les comparaisons d'agressivité réutilisent directement les rapports `paper-analytics-v1` du Batch 12 : aucun classement automatique n'est produit.

### Comparaison Luna / Sol — Batch 14 intégré

Le Batch 14 conserve `paper-experiment-v1` pour l'axe agressivité et introduit `paper-experiment-v2` pour une expérience dont **le modèle LLM est l'unique variable contrôlée**.

`paper-experiment-v2` ajoute `comparison_variable = LLM_MODEL`, `experiment_group_digest`, `replicate_index` et `replicate_count`. `source_digest` devient obligatoire afin d'identifier un dataset/snapshot figé. `compare_model_runs(...)` réutilise directement `PaperAnalyticsReport` (`paper-analytics-v1`) et ne produit ni score composite, ni classement, ni « meilleur modèle » automatique.

### Chat opérateur — Batch 15 intégré

Le Batch 15 ajoute une interface conversationnelle vers **le même modèle Agent configuré** (`LLMModel.LUNA` ou `LLMModel.SOL`) sans créer un deuxième agent stratégique.

Contrat :

- provider conversationnel distinct de `OpenAIDecisionProvider` ;
- prompt conversationnel versionné `operator-chat-v1` ;
- historique borné et process-local pour la V1 ;
- `POST /api/v1/chat/messages` pour envoyer un message ;
- `GET /api/v1/chat/sessions/{session_id}` pour relire l'historique de la session ;
- lecture des faits canoniques du runtime, du journal et des analytics ;
- contexte d'un cycle historique chargé depuis son `AgentInput` persisté exact ;
- état courant étiqueté séparément et interdit comme justification rétroactive d'une décision historique ;
- aucune instruction conversationnelle n'est ajoutée à `AgentInput` ni au manifeste expérimental ;
- « BUY maintenant », « agressivité 8 » ou « ignore Risk » restent conversationnels et ne déclenchent aucune mutation.

L'historique chat n'est pas persisté en PostgreSQL dans cette V1. Cette décision minimise les risques de contamination des digests expérimentaux et maintient une séparation explicite entre conversation et faits de trading.

## Trading PAPER canonique

`TradingCycleRunner.run_cycle()` exécute exactement un cycle et `TradingEngine` répète cette primitive séquentiellement. Un seul `MarketState` est partagé entre Agent, Risk et Broker pour le cycle, et un seul `PortfolioState` pré-cycle est partagé entre Agent et Risk.

- HOLD traverse Risk et produit un résultat complet sans intent.
- REJECT est une issue métier normale sans Broker.
- MODIFY utilise exactement la quantité autorisée par Risk.
- ALLOW transmet l'intent produit par Risk.
- Les erreurs Market/Portfolio/Agent/Risk/Broker restent des cycles `FAILED`, jamais des HOLD synthétiques.
- Les erreurs de chat restent des erreurs HTTP/chat séparées et ne marquent aucun cycle `FAILED`.

## Persistance durable — Batch 09 intégré

Le package `ai_spot_trader.persistence` utilise SQLAlchemy async, PostgreSQL et Alembic. `AuditedTradingCycleRunner` persiste le `TradingCycleResult` après le runner canonique sans dupliquer l'orchestration.

Le schéma `0001_audit_journal` conserve `audit_cycles`, `audit_decisions`, `audit_risk_assessments`, `audit_execution_intents` et `audit_fills`.

Le graphe est transactionnel et idempotent par `cycle_id`. La persistance ne garantit pas encore un exactly-once global entre la mutation du ledger PAPER mémoire et le commit PostgreSQL ; la reconstruction/réconciliation après crash reste différée.

Les Batches 13/14 n'ajoutent pas de table ni de migration. Le Batch 15 n'ajoute également **aucune migration** : les messages chat restent en mémoire et ne participent ni au `result_digest`, ni aux digests expérimentaux, ni aux analytics historiques.

## API FastAPI

La façade REST versionnée `/api/v1` expose notamment :

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
- `GET /api/v1/analytics`
- `POST /api/v1/chat/messages` — Batch 15 intégré
- `GET /api/v1/chat/sessions/{session_id}` — Batch 15 intégré

Les routes chat n'exposent aucune méthode de mutation Risk/Broker/stratégie et leurs erreurs fournisseur sont sanitizées (`502`) sans fuite du message brut.

## Frontend cockpit

Le cockpit affiche l'état backend/moteur, portefeuille, marché durable, cycles, décisions, Risk, exécutions/fills, erreurs sanitizées et analytics PAPER.

Le Batch 15 ajoute un panneau Chat séparé. Le navigateur ne possède aucun chemin chat vers `startEngine`, `stopEngine`, Risk, Broker ou Kraken. Recharger/fermer le frontend n'arrête donc pas le moteur backend ; une session chat mémoire peut en revanche expirer si le **backend** redémarre, ce qui est intentionnel en V1.

## Analytics PAPER — Batch 12 intégré

Le reducer analytics reste **pur, déterministe et en lecture seule** au-dessus du journal durable. Les coûts sont lus dans les fills persistés, chaque point est valorisé au `MarketState` durable du même cycle et la reproductibilité des métriques repose sur `paper-analytics-v1` + digest des `result_digest`.

Le chat peut lire un résumé analytics courant, mais ce résumé n'est jamais utilisé comme cause d'une décision historique et les messages chat ne modifient aucune métrique.

## Validation

### Batch 14 intégré

```text
pytest backend                          : 266 tests passés, 2 warnings externes
ruff check backend                      : All checks passed
mypy backend/src backend/tests          : 81 fichiers sans erreur
git diff --check                        : aucune erreur, warnings LF -> CRLF uniquement
commit/push                             : dc60033f60bf5d98a68e6131a9320e575d46cc8d
working tree après push                 : propre
```

### Batch 15 intégré

Le Batch 15 ajoute des tests dédiés couvrant l'activité moteur pendant le chat, Luna/Sol, absence de chemin Risk/Broker/Kraken/`ExecutionIntent`, non-contamination de `AgentInput`, requêtes BUY/Risk non exécutables, no-look-ahead historique, erreurs chat séparées, historique borné et absence de lifecycle moteur dans le frontend Chat.

Validation locale finale confirmée le 21 septembre 2026 :

```text
pytest backend                          : 277 tests passés, 2 warnings externes
ruff check backend                      : All checks passed
mypy backend/src backend/tests          : 89 fichiers sans erreur
pnpm lint                               : réussi
pnpm typecheck                          : réussi
pnpm build                              : réussi
git diff --check                        : aucune erreur, warnings LF -> CRLF uniquement
commit/push fonctionnel                 : 1c182b829c141c20be5cc8e62a3f8afa6f71b4d6
```

Le correctif frontend final a supprimé l'unique erreur ESLint `react-hooks/set-state-in-effect` dans `use-chat.ts` avant le commit fonctionnel.

## Sécurité

- Aucun secret ou clé API réel ne doit être versionné, journalisé ou renvoyé par l'API.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- PAPER et LIVE restent explicitement séparés.
- Toute exécution doit continuer à passer par Risk.
- Le chat redige les formes de secrets courantes avant de conserver le message en mémoire et n'expose pas les erreurs brutes du fournisseur.
- Le bind API par défaut reste local (`127.0.0.1`). Toute exposition distante des commandes lifecycle/chat devra être protégée explicitement avant usage.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et développement. Il ne constitue pas un conseil financier et ne garantit aucun résultat de trading. La cible expérimentale de +4 %/jour reste une métrique de recherche, jamais une promesse.
