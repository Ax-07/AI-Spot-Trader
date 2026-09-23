# 02 — Architecture technique

## 1. Référence

HEAD GitHub vérifié après intégration du Batch 18.7 :

```text
0886216324106d941c3df0e30f074e24dbe1d33a
feat: add bounded network retry resilience
```

Dernier commit code intégré :

```text
0886216324106d941c3df0e30f074e24dbe1d33a
feat: add bounded network retry resilience
```

Les Batches 18.6 et 18.7 sont intégrés sur `main`.

## 2. Modules concernés

```text
backend/src/ai_spot_trader/
  agent/
    provider.py            # même Agent + validation runtime des manifestes v3
    openai_client.py       # Responses API + retry transport pré-décision borné
    prompt.py              # contrat à deux phases, toujours agent-strategy-v4
  core/
    retry.py               # politique générique bornée, backoff + logs sanitaires
  domain/
    models.py              # contrats Agent/portfolio/expériences existants
  experiments/
    protocol.py            # builders v1/v2/v3
    comparison.py          # comparaisons Luna/Sol v2 ou v3, sans ranking
  market/
    execution.py           # routeur typé SPOT/PERPETUAL, fail-closed
  trading/
    engine.py              # orchestration canonique Agent -> Risk -> Broker
  portfolio/
    ledger.py              # ledger mémoire + restore(PortfolioState)
  persistence/
    models.py              # paper_runs + état durable de recovery
    runs.py                # handoff de session et reconstruction fail-closed
    repository.py          # cycle + current_portfolio_payload dans la même transaction
    audit.py               # checkpoint/rollback mémoire autour de l'audit durable
    analytics.py           # replay chain-aware des runs liés par recovery
  integrations/kraken/
    rest.py                # client SPOT public brut
    derivatives.py         # client Derivatives public brut + mark/funding execution
    websocket.py           # reconnect SPOT borné existant
    resilience.py          # retry REST read-only + classification transitoire/permanente
    market_data.py         # injecte le wrapper REST SPOT
  analytics/
    paper.py               # paper-analytics-v3 multi-marchés causal
  composition.py           # wrappers REST Derivatives + ledger/Risk/Broker/runtime
backend/alembic/versions/
  0005_paper_run_recovery.py
```

## 3. Flux runtime causal

```text
                         +-------------------------------+
                         | Kraken public research        |
                         | instances dédiées             |
                         +---------------+---------------+
                                         |
                                 MarketResearchService
                                         |
                                  ReadOnlyToolRegistry
                                         |
                                         v
PortfolioLedger -> MarketSelectionInput -> OpenAIDecisionProvider.select_market()
                                         |
                                         v
                                  MarketSelection
                                         |
                                         v
                         RoutedExecutableMarketDataSource
                           /                         \
                    execution SPOT            execution Derivatives
                           \                         /
                            +------> MarketState <---+
                                         |
PortfolioLedger ------------------------>| recapture complète
                                         v
                                     AgentInput
                                         |
                                         v
                         OpenAIDecisionProvider.generate_decision()
                                         |
                                         v
                                  DecisionCandidate
                                         |
                                         v
                                     RiskEngine
                                         |
                                  ExecutionIntent ?
                                         |
                                         v
                                    PaperBroker
```

Le Batch 18.7 ne modifie pas ce pipeline stratégique. Il agit uniquement sous les frontières
réseau read-only ou pré-décision.

## 4. Un seul Agent, deux phases

`OpenAIDecisionProvider` implémente :

```text
select_market(MarketSelectionInput) -> MarketSelection
generate_decision(AgentInput)       -> DecisionCandidate
```

Il s'agit du **même objet Agent**, du même modèle Luna/Sol et du même rôle stratégique. La phase
sélection peut utiliser le function calling borné. Le chemin causal final est un appel structuré
direct sans nouveaux tools ; il réutilise les traces de sélection.

## 5. Univers typé

`ExecutableMarket` est immuable :

```text
symbol: BASE/QUOTE
market_type: SPOT | PERPETUAL
```

`FUTURE` est refusé. L'univers est trié et dédupliqué de façon déterministe. En v3, ce tuple exact
fait partie de l'identité expérimentale.

## 6. Routeur d'exécution

`RoutedExecutableMarketDataSource` ne fait aucune sélection stratégique. Il reçoit le marché déjà
choisi et vérifie format, appartenance exacte, type supporté, cohérence du snapshot et, pour les
PERPETUAL, contrat linéaire réellement représenté. Une erreur provoque un échec technique, jamais
un HOLD artificiel.

Le routeur n'est pas une frontière de retry : rejouer un `snapshot()` PERPETUAL complet pourrait
répéter une mutation de mark/funding après un premier succès réseau. Les retries 18.7 restent donc
plus bas, sur les seules lectures REST publiques.

## 7. Séparation research / execution

Les sources research n'ont aucun `market_sink`; les sources execution sont appelées seulement après
`MarketSelection`. Une exploration PERPETUAL ne peut donc ni marquer le ledger ni accumuler du
funding.

## 8. Portfolio et Derivatives

Le runner capture un portefeuille complet avant la sélection puis le recapture après acquisition du
marché choisi. Cela garantit que mark, unrealized P&L et funding causaux d'une position dérivée
existante sont visibles par l'Agent final et Risk.

`PaperPortfolioLedger.restore(PortfolioState)` est intégré par le Batch 18.6. Il remplace
atomiquement les balances, positions SPOT et positions dérivées à partir d'un contrat déjà validé ;
il ne rejoue aucun fill.

## 9. Artefact MarketSelection

```text
selection_id
cycle_id
selected_at
symbol
market_type
rationale
tool_traces[]
selection_digest
```

Le digest couvre rationale et traces. Les traces viennent du registre contrôlé par l'application,
pas du LLM.

## 10. Protocole expérimental v3

`ExperimentManifest` conserve son identité historique pour v1/v2 et reçoit un champ optionnel
`agent_protocol`, omis de la sérialisation lorsqu'il est absent.

Pour `paper-experiment-v3`, `agent_protocol` contient l'univers typé, la version de sélection, les
phases tools et les bornes effectives. Le transport/retry 18.7 n'altère ni le contrat stratégique,
ni les digests historiques.

## 11. Identité de la capacité tools

`ReadOnlyToolRegistry.openai_tools` reste la source de définition réellement transmise au LLM.
Le digest et les bornes introduits par 18.5 restent inchangés.

## 12. Digests et groupes contrôlés

v1 et v2 continuent d'utiliser leurs payloads historiques. En v3, le digest du groupe exclut
seulement `llm_model` et `replicate_index`. Le recovery et la politique de retry transport ne
réinterprètent pas les manifestes historiques.

## 13. Validation avant appel LLM

Les contrôles v3 du runner et du provider restent inchangés. Le recovery se produit au démarrage du
runtime, avant tout cycle et donc avant tout nouvel appel stratégique.

Un retry Responses API est autorisé uniquement avant qu'une réponse exploitable n'ait produit une
`MarketSelection` ou un `DecisionCandidate`. Dans la boucle tools, chaque requête HTTP est retryée
individuellement ; les tools demeurent read-only et aucun retry n'entoure l'ensemble Agent/Risk.

## 14. Persistance de cycle et état de ledger

La migration intégrée `0005_paper_run_recovery` ajoute :

```text
paper_runs.resumed_from_paper_run_id UUID NULL UNIQUE
paper_runs.recovery_version          VARCHAR(64) NULL
paper_runs.initial_portfolio_payload JSONB NULL
paper_runs.current_portfolio_payload JSONB NULL
```

Pour les nouveaux runs recovery-v1, `initial_portfolio_payload` et `current_portfolio_payload` sont
renseignés dès la création.

`SqlAlchemyCycleAuditRepository.record_for_run()` met à jour `current_portfolio_payload` uniquement
pour un cycle `COMPLETED`, dans **la même transaction** que `audit_cycles`, décision, risk,
execution intent et fills. Pour un cycle sans exécution, le snapshot engagé est le
`AgentInput.portfolio_state`; pour un cycle exécuté, c'est `portfolio_state_after`.

Conséquence : il n'existe pas de fenêtre durable où le cycle est commit mais le snapshot de reprise
ne l'est pas, ou inversement.

## 15. Frontière mémoire/durable

`AuditedTradingCycleRunner` reçoit le ledger canonique et capture un checkpoint avant le delegate :

```text
preflight audit
-> checkpoint PortfolioState
-> TradingCycleRunner
   -> FAILED     : restore(checkpoint)
   -> COMPLETED  : conserver temporairement l'état muté
-> record PostgreSQL
   -> erreur     : restore(checkpoint) + latch fail-closed
   -> inserted=false : restore(checkpoint)
   -> commit OK  : garder l'état muté
```

Ainsi :

- un funding/mark observé dans un cycle `FAILED` n'avance pas silencieusement le ledger ;
- une mutation Broker dont l'audit n'est pas durable est annulée en mémoire ;
- un replay idempotent ne double pas l'exposition ;
- un cycle `COMPLETED` durable est l'unique frontière qui fait avancer l'état de reprise.

Le Batch 18.7 ne modifie pas cette frontière et n'ajoute aucun retry autour de l'audit.

## 16. Handoff de restart

La sémantique intégrée conserve l'invariant historique **un run par lifetime backend** :

```text
run A --shutdown/crash--> startup
                         |
                         v
             récupérer état durable de A
                         |
                         v
             créer run B (resumed_from=A)
                         |
                         v
             restore du même PaperPortfolioLedger
```

Le run parent n'est jamais réouvert ni modifié rétroactivement, à l'exception de `ended_at` si le
process précédent avait crashé sans fermeture propre.

Pour un parent `paper-ledger-recovery-v1`, la source de vérité est
`current_portfolio_payload`. Pour un run legacy antérieur à 18.6, une migration de reprise n'est
acceptée que si le dernier état est non ambigu et dérivable d'un cycle `COMPLETED`; un dernier
cycle `FAILED` legacy provoque un refus fail-closed.

Le nouvel univers exécutable doit être identique à celui du parent. Les balances de règlement,
inventaires SPOT et symboles PERPETUAL restaurés sont validés contre la configuration courante.

## 17. Ce qui n'est pas rejoué

Le recovery ne réémet jamais :

- `MarketSelection` ;
- appel LLM de décision ;
- `RiskAssessment` ;
- `ExecutionIntent` ;
- `Fill`.

Les identités historiques restent dans leurs tables. Le runtime repart uniquement du
`PortfolioState` durable.

## 18. SPOT et PERPETUAL restaurés

SPOT :

- cash disponible ;
- quantité/available des actifs détenus ;
- l'interdiction de vendre un actif non détenu reste portée par Ledger/Risk.

PERPETUAL :

- symbole et sens LONG/SHORT ;
- quantité et average entry price ;
- mark/notional ;
- realized/unrealized P&L ;
- levier et marge utilisée ;
- maintenance margin ;
- cumulative funding et `funding_updated_at` ;
- liquidation price telle que portée par le dernier snapshot durable.

Aucun calcul rétrospectif de décision n'est nécessaire.

## 19. Analytics et causalité

`paper-analytics-v3` garde ses calculs, mais la couche de persistance est consciente de la lignée de
recovery. `paper_analytics_for_run(run_id)` remonte `resumed_from_paper_run_id`, puis rejoue les
cycles de l'ancêtre le plus ancien jusqu'au run demandé. Les rows restent attachées à leurs
`paper_run_id` d'origine ; seule la lecture analytique suit explicitement la chaîne, ce qui
préserve frais, funding, P&L, drawdown et compteurs cumulés à travers les restarts.

## 20. Compatibilité et fail-closed

Compatibilité conservée :

```text
experiment_manifest = None
paper-experiment-v1
paper-experiment-v2
paper-experiment-v3
agent-strategy-v4
paper-ledger-recovery-v1
mode mono-marché legacy du TradingCycleRunner
composition PAPER multi-marché canonique
```

Le démarrage est refusé si l'état durable est invalide, incomplet ou incompatible. Le Batch 18.7
ne crée aucune architecture stratégique parallèle et ne change ni RiskPolicy, ni les règles de
PaperBroker.

## 21. Validation intégrée 18.6

```text
Alembic 0004_multi_market_selection -> 0005_paper_run_recovery sur PostgreSQL : OK
pytest ciblé recovery/persistence/trading/broker : 75 passed
pytest backend : 468 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

## 22. Politique de retry intégrée par 18.7

### Kraken public REST

Les seules opérations retryées sont les lectures publiques :

```text
SPOT        : AssetPairs, OHLC
Derivatives : instruments, ticker, mark history
```

Politique : 3 tentatives maximum, backoff exponentiel `0.25s -> 0.5s` borné à `1s`.

Retryable : timeout/transport, HTTP 408, HTTP 429, HTTP 5xx.

Non retryable : autre HTTP 4xx, JSON invalide, payload Kraken invalide, symbole/stale/invariant.

Le WebSocket SPOT conserve son mécanisme existant de reconnexion bornée ; il n'est pas enveloppé
par cette nouvelle politique.

### Responses API

Chaque POST `/responses` dispose de 2 tentatives maximum, backoff `0.5s`, uniquement pour
transport/timeout, 408, 429 ou 5xx. `store=false` reste utilisé. Une réponse HTTP reçue avec JSON ou
contrat provider invalide échoue sans retry.

Cette frontière est avant toute décision durable et ne permet jamais au LLM de déclencher Risk ou
Broker directement.

### Timeouts et deadline de stage

Les timeouts transport existants restent configurables (`kraken_rest_timeout_seconds=10s` et
`openai_timeout_seconds=30s` par défaut). Le runner conserve en parallèle ses deadlines de stage
`MARKET`, `AGENT` et `BROKER`. La deadline de stage est le plafond absolu : un retry ne la prolonge
jamais. Si une configuration fixe un timeout de stage inférieur ou égal au timeout transport, une
attente longue peut donc être interrompue par le runner avant qu'un retry transport soit possible.
C'est un fail-closed volontaire ; pour tester/rendre utile le retry de timeout, le timeout transport
doit être strictement inférieur au budget de stage disponible.

### Jitter

Aucun jitter n'est ajouté dans 18.7. Le runtime courant est mono-Agent et séquentiel ; un backoff
déterministe est suffisant et rend les tests strictement reproductibles. Une réévaluation pourra
être faite si plusieurs runtimes concurrents sont réellement déployés.

## 23. Observabilité intégrée par 18.7

Les erreurs réseau finales sont classées sans corps de réponse ni secret :

```text
KrakenTimeoutError / LLMTimeoutError
KrakenNetworkError / LLMNetworkError
KrakenRateLimitError / LLMRateLimitError
KrakenServerError / LLMServerError
KrakenHTTPError / LLMHTTPError
```

Ces types remontent jusqu'à `TradingCycleFailure.error_type`, déjà persisté par l'audit. Les types
Timeout héritent aussi de `TimeoutError`, donc `failure_timed_out` reste vrai sans migration.

Les retries journalisent uniquement : opération logique, tentative, budget, type d'erreur, statut
HTTP éventuel et délai. Aucun prompt, payload Kraken/OpenAI, URL avec paramètres, token ou secret
n'est écrit par cette couche.

Il n'existe pas encore de backend métriques dédié dans le repository ; 18.7 n'introduit donc pas
Prometheus/OpenTelemetry en parallèle. Les logs structurés et les failures durables constituent la
surface d'observabilité de ce batch.

## 24. Hors périmètre 18.7

Pas de retry Risk/Broker/persistance, pas de retry du `snapshot()` exécutable complet, pas de
scanner/ranking/opportunity score, pas de nouvelle donnée research, pas de changement de stratégie,
pas de migration, pas de multi-quote/FX, pas de FUTURE daté et pas de LIVE.
