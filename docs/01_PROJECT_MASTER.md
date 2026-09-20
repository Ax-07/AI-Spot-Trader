# 01 — Project Master

## 1. Rôle de ce document

Ce document est la spécification fonctionnelle et architecturale principale d'**AI Spot Trader**. Les détails spécialisés sont complétés par `02_ARCHITECTURE_TECHNIQUE.md`, `03_AGENT_TRADING_RISK.md`, `09_ROADMAP_DEVELOPPEMENT.md` et `10_DECISIONS_ET_CHANGELOG.md`.

Statuts utilisés : **Confirmé**, **Proposé**, **À décider** et **Hors périmètre pour l'instant**.

---

## 2. Vision et invariants

**Confirmé.** AI Spot Trader est une application expérimentale de trading crypto **SPOT** pilotée par **un agent IA unique**. L'agent conserve la décision stratégique ; les composants déterministes construisent le contexte, imposent les contraintes de risque, exécutent en PAPER, persistent les faits et mesurent les résultats.

Invariants principaux :

- Kraken est l'exchange initial ;
- SPOT uniquement : aucun short, levier, margin, future ou perpetual ;
- actions stratégiques `BUY`, `SELL`, `HOLD` ;
- aucune vente d'un actif non détenu ;
- GPT-5.6 Luna pour les premiers essais, Sol sélectionnable par configuration ;
- Risk Engine déterministe avec autorité finale ;
- aucune sortie LLM ne déclenche directement une exécution ;
- premières versions exclusivement en PAPER ;
- frais, spread et slippage pris en compte ;
- toutes les décisions, y compris `HOLD`, sont journalisables durablement ;
- les erreurs techniques restent distinctes des décisions métier ;
- aucun secret dans Git, prompts ou logs ;
- aucun look-ahead ;
- frontend indépendant du moteur backend ;
- un seul cycle de trading à la fois ;
- la persistance observe les faits métier, elle ne crée aucune stratégie.

La cible expérimentale de **+4 %/jour** reste une métrique de recherche très agressive, jamais une garantie, une hypothèse de rendement attendu ou une obligation de forcer des trades.

---

## 3. Périmètre V0 / V1

### V0 — socle expérimental

V0 est atteinte lorsque le backend peut, sans frontend obligatoire :

1. recevoir des données publiques Kraken ;
2. construire un `MarketState` cohérent ;
3. maintenir un `PortfolioState` PAPER ;
4. obtenir une décision structurée de l'agent Luna ;
5. soumettre toute proposition au Risk Engine, y compris HOLD ;
6. produire `ALLOW`, `MODIFY` ou `REJECT` ;
7. simuler l'exécution autorisée via le Paper Broker ;
8. mettre à jour le portefeuille ;
9. répéter le cycle de manière autonome et séquentielle ;
10. journaliser durablement les cycles ;
11. exposer suffisamment d'état via FastAPI.

Le Batch 08 réalise le point 9. Le Batch 09 réalise le socle durable du point 10. Le Batch 10 doit traiter le point 11.

### V1 — cockpit et expérimentation instrumentée

V1 ajoute le cockpit Next.js/shadcn, historique, analytics P&L/drawdown/coûts/exposition, replay reproductible, expérimentations d'agressivité et comparaison Luna/Sol. Le LIVE n'est pas une condition de V1.

---

## 4. Architecture et flux de confiance

**Confirmé :** backend Python + `asyncio` + FastAPI + Pydantic ; persistance PostgreSQL + SQLAlchemy async + Alembic ; frontend Next.js + TypeScript + shadcn/ui + Tailwind ; REST/WebSocket selon le besoin.

```text
MarketDataSource
      |
      v
MarketState -----+
                 |
PortfolioState --+--> AgentInput --> Agent IA --> DecisionCandidate
                                             |
                                             v
                                        Risk Engine
                                     /       |       \
                                 REJECT    MODIFY    ALLOW
                                     \       |       /
                                             v
                                       RiskAssessment
                                             |
                              ExecutionIntent si tradable
                                             |
                              même MarketState du cycle
                                             |
                                             v
                                       Paper Broker
                                             |
                                  Fill(s) + PortfolioState
                                             |
                                             v
                                      TradingCycleResult
                                             |
                                             v
                                  durable audit persistence
```

Principe absolu : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Le package Agent ne possède aucun chemin direct vers Risk, Broker, Kraken, FastAPI ou une base de données. Le package d'orchestration relie explicitement les composants canoniques sans réimplémenter leur métier. La persistance ne décide rien et ne modifie aucun artefact métier.

---

## 5. Contrats de domaine canoniques

Les frontières critiques utilisent des modèles Pydantic stricts avec champs supplémentaires interdits, UUID explicites et timestamps timezone-aware normalisés UTC.

### Marché et portefeuille

- `MarketObservation` : fait marché fournisseur-agnostique minimal ;
- `MarketState` : snapshot déterministe, symbole canonique, dernier prix et contexte optionnel ;
- `MarketContext` : fraîcheur descriptive et fenêtres multi-horizon ;
- `PortfolioState` : snapshot PAPER avec `balances` et `positions` disjoints ;
- `AssetBalance` : actif de règlement disponible ;
- `AssetPosition` : quantité détenue et quantité disponible à la vente.

### Agent, Risk et exécution

`AgentInput` contient `cycle_id`, `created_at`, les deux snapshots et `aggressiveness`.

`DecisionCandidate` contient :

```text
decision_id
cycle_id
created_at
action = BUY | SELL | HOLD
symbol
proposed_quantity?   # obligatoire pour BUY/SELL, interdite pour HOLD
rationale?
```

Le sizing initial est **stratégique** : le Risk Engine ne choisit pas arbitrairement une taille de départ.

`RiskAssessment` contient :

```text
risk_assessment_id
cycle_id
decision_id
assessed_at
status = ALLOW | MODIFY | REJECT
requested_quantity?
authorized_quantity?
evaluated_limits[]
reasons[]
```

`MODIFY` réduit strictement la quantité demandée. `REJECT` n'autorise aucune quantité. HOLD produit un assessment auditable sans intent.

`ExecutionIntent` reste uniquement PAPER, BUY/SELL, et n'existe que si le Risk Engine autorise une quantité strictement positive. Seul le Risk Engine le construit.

`Fill` reste le fait d'exécution PAPER auditable avec contexte de pricing, prix de référence, prix exécuté, notional, frais, spread et slippage.

La couche SQLAlchemy n'introduit pas de seconde représentation métier : ses records sont des structures de persistance qui conservent les objets canoniques sous forme JSON/JSONB et leurs clés de corrélation.

---

## 6. Market State

### Confirmé au Batch 04

`MarketStateBuilder` est mono-symbole, déterministe et mémoire. Il garde un historique borné, impose un ordre temporel strict et construit les horizons descriptifs configurés.

Pour un snapshot à `T`, seules les observations `observed_at <= T` sont utilisées. Le seuil technique de stale du Market State reste distinct de la politique métier Risk.

Le runner consomme `MarketDataSource.snapshot(symbol)` exactement une fois par cycle. Aucun refresh caché n'est permis ensuite pour cette décision.

---

## 7. Portfolio State et Paper Broker

### Confirmé au Batch 05

`balances` est la source canonique des actifs de règlement ; `positions` est la source canonique des actifs détenus/vendables. Les rôles sont uniques et non chevauchants.

`PaperPortfolioLedger` reçoit un état initial explicitement injecté. Aucun capital PAPER, devise de référence ou univers produit n'est imposé globalement. Les mutations sont copy-on-write et atomiques.

`PaperBroker` reçoit explicitement `ExecutionIntent` et `MarketState` :

```text
Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]
```

Il ne consulte jamais Kraken. Une fois son verrou acquis, le chemin de calcul/mutation PAPER est synchrone et atomique du point de vue asyncio : le fill est construit puis la mutation ledger est appliquée sans `await` intermédiaire.

Le calcul des coûts est factorisé dans `estimate_paper_execution` et partagé par Risk et le Paper Broker. `PaperExecutionCostModel` reste injecté : `fee_rate`, `spread_bps`, `slippage_bps`.

---

## 8. Risk Engine — intégré au Batch 06

Le package canonique est `ai_spot_trader.risk`. Le moteur est synchrone, déterministe, sans FastAPI, Kraken, LLM ou I/O réseau. Il ne mute ni `MarketState` ni `PortfolioState` et n'exécute jamais lui-même un ordre.

`RiskPolicy` reste explicitement injectée. Elle peut porter :

- `max_order_notional` optionnel ;
- `allowed_pairs` optionnel ;
- `stale_after` métier optionnel ;
- `allow_quantity_reduction` explicite.

Contrôles actuels : symbole, chronologie, whitelist optionnelle, fraîcheur métier optionnelle, max notional, balance quote, solvabilité BUY avec coûts PAPER, position SELL disponible et rôles d'actifs.

`MODIFY` ne change jamais BUY↔SELL ou le symbole et n'augmente jamais la taille stratégique.

HOLD traverse Risk et produit `ALLOW + HOLD_NO_EXECUTION`, sans `ExecutionIntent`.

---

## 9. Agent IA — intégré au Batch 07

Le port canonique reste :

```text
LLMProvider.generate_decision(AgentInput) -> DecisionCandidate
```

Le modèle fournisseur ne produit que `action`, `symbol`, `proposed_quantity`, `rationale`. `decision_id`, `cycle_id` et `created_at` restent sous contrôle de l'application.

L'Agent est limité au symbole de `agent_input.market_state.symbol`. Une sortie divergente est rejetée avant création d'un `DecisionCandidate` utilisable.

L'adapter OpenAI utilise la Responses API et un JSON Schema strict. La réponse est parsée et revalidée localement sans réparation stratégique silencieuse. Le prompt versionné est `agent-luna-v1`.

Aucun retry automatique n'est implémenté : transport, enveloppe fournisseur, sortie structurée invalide et violation du contrat Agent restent des erreurs explicites.

---

## 10. Chronologie et no look-ahead

Un cycle valide respecte :

```text
MarketState.as_of <= AgentInput.created_at
PortfolioState.as_of <= AgentInput.created_at
AgentInput.created_at <= DecisionCandidate.created_at
DecisionCandidate.created_at <= RiskAssessment.assessed_at
RiskAssessment.assessed_at = ExecutionIntent.created_at   # si intent
MarketState.as_of <= Fill.filled_at                       # si fill
```

Le runner crée `AgentInput.created_at` après acquisition des deux snapshots. Les composants Agent et Risk conservent également leurs propres contrôles temporels.

Le même `MarketState` imbriqué dans `AgentInput` est réutilisé pour Risk puis, si autorisé, pour le Broker. Le même `PortfolioState` pré-cycle est réutilisé pour Agent et Risk.

La persistance enregistre les timestamps produits ; elle ne les recalcule pas et ne réécrit pas les décisions a posteriori.

---

## 11. Orchestration autonome — Batch 08 intégré

### Primitive un-cycle

`TradingCycleRunner.run_cycle()` exécute exactement un cycle PAPER pour un symbole explicite. Il dépend des ports/composants canoniques existants et injecte :

- `MarketDataSource` ;
- `PaperPortfolioLedger` ;
- `LLMProvider` ;
- `RiskEngine` ;
- `Broker` ;
- symbole ;
- agressivité ;
- `Clock` ;
- factory `cycle_id` ;
- timeouts Market/Agent/Broker.

Un verrou `asyncio.Lock` interne couvre l'intégralité du cycle. Les appels manuels et la boucle autonome partageant le même runner ne peuvent donc pas modifier le ledger entre le snapshot pré-cycle, Risk et l'exécution.

### Résultat de cycle

`TradingCycleResult` est une dataclass immuable interne d'orchestration. Elle conserve les artefacts canoniques réellement atteints : `AgentInput`, `DecisionCandidate`, `RiskAssessment`, `ExecutionIntent`, fills et snapshot portfolio post-exécution.

HOLD et REJECT restent des cycles `COMPLETED`. Les pannes techniques restent `FAILED`.

### Timeouts et boucle

Market, Agent et Broker sont entourés d'`asyncio.timeout`. Risk reste synchrone et déterministe, sans timeout artificiel.

`TradingEngine` répète le même runner séquentiellement :

```text
cycle terminé -> attente cadence -> cycle suivant
```

La cadence est injectée et `> 0`. `start()` refuse une seconde loop et `stop()` est coopératif.

---

## 12. Runtime FastAPI et composition

`AppRuntime` peut recevoir un moteur implémentant uniquement `stop()` comme dépendance de lifecycle. `close()` pose le signal global de shutdown puis attend le moteur configuré.

`create_app(..., trading_engine=...)` permet cette composition sans lancer le moteur. L'import du module, le healthcheck et les tests d'application ne provoquent aucun appel OpenAI/Kraken et aucune boucle réelle.

Le Batch 10 doit ajouter les routes de contrôle utiles sans rendre le frontend propriétaire du lifecycle du moteur.

---

## 13. Persistance durable — Batch 09 intégré

### Choix techniques

Le Batch 09 retient :

- PostgreSQL comme base durable ;
- SQLAlchemy 2 en mode asynchrone ;
- `asyncpg` comme driver PostgreSQL ;
- Alembic pour les migrations ;
- `aiosqlite` uniquement pour les tests de persistance offline.

La migration initiale est `0001_audit_journal`.

### Frontière de persistance

`CycleAuditWriter` est le port minimal du journal durable :

```text
record(TradingCycleResult) -> bool
```

`AuditedTradingCycleRunner` enveloppe un runner canonique :

```text
delegate.run_cycle()
        |
        v
TradingCycleResult
        |
        v
audit_writer.record(result)
        |
        v
même TradingCycleResult retourné
```

Cette couche ne connaît ni stratégie, ni Kraken, ni calcul Risk. Elle ne crée jamais de `DecisionCandidate`, `RiskAssessment`, `ExecutionIntent` ou `Fill`.

### Schéma du journal

Tables initiales :

- `audit_cycles` ;
- `audit_decisions` ;
- `audit_risk_assessments` ;
- `audit_execution_intents` ;
- `audit_fills`.

`alembic_version` est gérée par Alembic.

Le cycle enregistre notamment :

- `cycle_id` ;
- statut technique ;
- métadonnées d'erreur sanitizées ;
- IDs des snapshots disponibles ;
- timestamps utiles ;
- `AgentInput` complet en JSON/JSONB ;
- snapshot portfolio post-cycle éventuel.

Les objets métier aval sont stockés dans leurs tables corrélées avec leur payload canonique.

### HOLD, REJECT, MODIFY et ALLOW

- HOLD : cycle + décision + assessment, aucun intent/fill.
- REJECT : cycle + décision + assessment, aucun intent/fill.
- MODIFY : cycle + décision + assessment + intent Risk + fill(s).
- ALLOW tradable : cycle + décision + assessment + intent Risk + fill(s).
- FAILED : le cycle et tous les artefacts atteints avant la panne sont conservés.

### Idempotence et transactions

L'identité durable est `cycle_id`.

Une empreinte SHA-256 déterministe du résultat complet permet :

- replay exact : aucune double écriture, `record()` retourne `False` ;
- même `cycle_id` avec faits différents : `CycleAuditConflictError`.

Chaque graphe est écrit dans une transaction SQLAlchemy unique. Un échec force un rollback complet.

### Lifecycle DB

`Database` possède explicitement l'`AsyncEngine` et la session factory. `close()` dispose les connexions.

`create_schema_for_tests()` existe uniquement pour les tests isolés ; le runtime réel doit utiliser Alembic.

### PostgreSQL de développement

`docker-compose.yml` fournit PostgreSQL 18 avec volume persistant et healthcheck. La base a été réellement démarrée et la migration `0001_audit_journal` appliquée avec succès pendant la validation Batch 09.

### Reprise après crash

Le Batch 09 fournit un **socle de reprise**, pas une garantie exactly-once bout-en-bout.

Le `PaperPortfolioLedger` reste mémoire. Si le Broker PAPER mute le ledger puis que le processus tombe avant le commit du journal, la base ne peut pas prouver à elle seule quel état mémoire était effectif.

La future reprise devra décider explicitement :

- comment reconstruire le ledger depuis un état durable ;
- comment traiter un cycle partiellement observé ;
- comment réconcilier portefeuille, intents et fills ;
- quelles opérations peuvent être rejouées sans double effet.

Aucun replay automatique d'un intent n'est introduit au Batch 09.

---

## 14. Sécurité et séparation PAPER / LIVE

`ExecutionMode` ne contient que `PAPER`. Le LIVE reste non représentable et nécessitera une décision dédiée. Aucune clé Kraken privée n'est requise.

Le provider OpenAI ne dispose d'aucun outil d'exécution et ne connaît ni Broker ni Kraken. L'orchestrateur n'interprète jamais `rationale` comme commande.

La base PostgreSQL ne doit recevoir aucun secret. `database_url` est chargée depuis l'environnement via `SecretStr`.

---

## 15. Stratégie de tests

Les tests restent déterministes et offline autant que possible.

Batch 09 ajoute des tests SQLite async pour :

- HOLD sans intent/fill ;
- REJECT sans intent/fill ;
- ALLOW avec graphe complet ;
- MODIFY avec graphe complet ;
- conservation des IDs/snapshots/status ;
- erreur technique sanitizée ;
- replay exact idempotent ;
- wrapper `AuditedTradingCycleRunner` ;
- rollback atomique en cas d'échec.

Validation locale confirmée :

- `pytest backend` : **209 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **63 fichiers sans erreur** ;
- `git diff --check` : aucune erreur.

Validation PostgreSQL réelle :

- conteneur healthy ;
- migration Alembic réussie ;
- tables et version Alembic vérifiées via `psql`.

---

## 16. Questions ouvertes prioritaires

- capital PAPER et devise de référence produit ;
- univers initial de paires ;
- valeur produit de cadence ;
- valeurs produit des limites Risk ;
- mapping agressivité 1–10 ;
- valeurs de référence fee/spread/slippage ;
- exposition portefeuille avancée ;
- frontière de journée et données P&L ;
- politique de rétention du journal ;
- reconstruction du ledger et réconciliation après crash ;
- conditions futures d'un éventuel LIVE.

Ces choix doivent être consignés dans `10_DECISIONS_ET_CHANGELOG.md` lorsqu'ils deviennent canoniques.
