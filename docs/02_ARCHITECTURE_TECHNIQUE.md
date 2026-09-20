# 02 — Architecture technique

## 1. Objet

Ce document décrit l'architecture technique courante d'AI Spot Trader, incluant le Batch 10 intégré. Les choix produit non figés restent explicitement séparés de l'architecture.

---

## 2. Vue d'ensemble

```text
+--------------------------+
| Frontend cockpit         |
| Next.js / TS / shadcn    |
+------------+-------------+
             |
            REST
             |
+------------v-------------+
| FastAPI API              |
| observation + lifecycle  |
+------+-------------------+
       |               |
       |               +------------------------------+
       v                                              v
TradingEngine / ledger                    CycleAuditReader
canonique PAPER                           query service SQLAlchemy
       |                                              |
       v                                              v
Agent -> Risk -> Paper Broker                     PostgreSQL
       |
       v
TradingCycleResult -> AuditedTradingCycleRunner -> journal durable
```

Le frontend n'est jamais l'ordonnanceur du moteur. PostgreSQL conserve des faits ; il ne produit aucune stratégie.

---

## 3. Découpage backend

```text
backend/src/ai_spot_trader/
  agent/
  api/
    routes/
      audit.py
      engine.py
      health.py
      portfolio.py
    schemas.py
  broker/
  core/
    clock.py
    config.py
    runtime.py
  domain/
  integrations/kraken/
  market/
  persistence/
    audit.py
    db.py
    models.py
    query.py
    repository.py
  portfolio/
  risk/
  trading/
    engine.py
  main.py
```

Responsabilités :

- `domain` : contrats canoniques fournisseur-agnostiques ;
- `market` : construction déterministe du `MarketState` ;
- `portfolio` : ledger PAPER mémoire ;
- `agent` : décision stratégique structurée ;
- `risk` : autorité déterministe avant exécution ;
- `broker` : exécution PAPER uniquement après intent Risk ;
- `trading` : orchestration et boucle séquentielle ;
- `persistence.repository` : écriture durable du résultat ;
- `persistence.query` : lecture durable pour l'API ;
- `api` : transport HTTP et modèles de réponse, sans métier de trading ;
- `core.runtime` : dépendances process-locales et lifecycle explicite.

---

## 4. Flux de confiance canonique

```text
MarketDataSource.snapshot(symbol) ----+
                                      |
PaperPortfolioLedger.snapshot() ------+--> AgentInput
                                             |
                                             v
                                      DecisionCandidate
                                             |
                                             v
                                        RiskEngine
                                      /      |      \
                                  REJECT  MODIFY  ALLOW
                                      \      |      /
                                             v
                                      RiskAssessment
                                             |
                                      ExecutionIntent
                                       si tradable
                                             |
                                             v
                                       PaperBroker
                                             |
                                             v
                                      Fill(s) + ledger
                                             |
                                             v
                                    TradingCycleResult
                                             |
                                             v
                                  audit persistence
```

L'API ne peut ni créer `DecisionCandidate`, ni appeler le LLM, ni construire `RiskAssessment`/`ExecutionIntent`, ni appeler le Broker pour contourner le runner.

---

## 5. Runtime FastAPI intégré au Batch 10

`create_app()` reste sans I/O externe et sans démarrage du trading à l'import.

Le lifespan construit un `AppRuntime` avec, selon l'injection :

- un `ControllableTradingEngine` ;
- un `PortfolioSnapshotSource` ;
- un `CycleAuditReader` ;
- éventuellement un `Database` possédé par l'application si `database_url` est configurée.

Aucune valeur produit de capital, paire, cadence, coûts ou RiskPolicy n'est inventée par FastAPI. Sans moteur ou portefeuille injecté, les endpoints associés restent explicitement non configurés.

À l'arrêt, `AppRuntime.close()` demande l'arrêt coopératif du moteur configuré puis ferme la DB qu'il possède. Fermer un client ou le futur frontend n'appelle pas ce lifecycle process.

---

## 6. Surface moteur

Le protocole HTTP ne connaît qu'une surface lifecycle/observation étroite :

```text
is_running
last_result
last_unexpected_error_type
start()
stop()
```

`POST /api/v1/engine/start` ne crée aucune tâche alternative : il délègue à `TradingEngine.start()`.

`POST /api/v1/engine/stop` délègue à `TradingEngine.stop()` et reste idempotent lorsque le moteur est déjà arrêté.

Un verrou de commande dans `AppRuntime` sérialise start/stop côté API. Le verrou de cycle du moteur reste la protection canonique du trading.

---

## 7. Portefeuille

`GET /api/v1/portfolio` appelle uniquement `snapshot()` sur le ledger PAPER injecté. Cette lecture :

- ne déclenche aucune exécution ;
- ne reconstruit pas le ledger depuis PostgreSQL ;
- ne modifie pas le portefeuille ;
- conserve les contrats PAPER existants.

Le recovery/rebuild du ledger reste hors Batch 10.

---

## 8. Query service durable

`SqlAlchemyCycleAuditQueryService` sépare FastAPI des records ORM.

```text
FastAPI route
    |
    v
CycleAuditReader
    |
    v
SqlAlchemyCycleAuditQueryService
    |
    v
AsyncSession
    |
    v
audit_* tables
```

Il expose :

- historique paginé des cycles ;
- détail d'un cycle ;
- dernier cycle ;
- décisions ;
- assessments Risk ;
- intents + fills ;
- dernière erreur technique ;
- dernier `MarketState` déjà enregistré dans un `AgentInput`.

Les routes ne manipulent pas les modèles SQLAlchemy.

---

## 9. Pagination, ordre et filtres

Les collections utilisent :

- `limit` : 1 à 100 ;
- `offset` : entier >= 0 ;
- `order=asc|desc` ;
- ordre secondaire déterministe par UUID ;
- filtres adaptés à la ressource : statut cycle, action, statut Risk, symbole.

Le `total` est calculé sur l'ensemble filtré avant pagination.

---

## 10. Modèles HTTP

Les réponses possèdent des modèles Pydantic dédiés sous `api/schemas.py` afin d'éviter de coupler le contrat HTTP aux classes ORM.

Les payloads JSON/JSONB canoniques du journal sont rendus comme faits enregistrés. L'API n'en déduit aucune nouvelle décision.

Les IDs et timestamps durables sont conservés.

---

## 11. Erreurs techniques et sécurité

Le moteur et le journal ne conservent dans l'API que les métadonnées d'erreur sanitizées nécessaires :

```text
stage
error_type
timed_out
```

Aucun message brut d'exception, stack trace, DSN, SecretStr ou secret fournisseur n'est renvoyé au cockpit.

Comportements HTTP :

- ressource absente : 404 ;
- moteur/portfolio/store non configuré : 503 explicite ;
- store configuré mais indisponible : 503 générique ;
- payload durable incohérent : 500 générique ;
- paramètres invalides : validation FastAPI 422 ;
- start dupliqué : 409.

---

## 12. Lifecycle DB

Si un `CycleAuditReader` est injecté, FastAPI ne crée pas de DB.

Sinon, lorsque `AI_SPOT_TRADER_DATABASE_URL` est présente, le lifespan construit `Database` et `SqlAlchemyCycleAuditQueryService`. La création de l'engine SQLAlchemy ne lance ni migration ni requête au startup. Le pool est disposé au shutdown.

Les migrations restent gérées exclusivement par Alembic. Le Batch 10 ne nécessite aucune migration supplémentaire au-dessus de `0001_audit_journal`.

---

## 13. WebSocket

Aucun WebSocket n'est introduit au Batch 10.

Motifs :

- aucune source d'événements runtime canonique n'existe encore ;
- diffuser en WebSocket des polls DB ajouterait peu de valeur ;
- il faut éviter une seconde source d'état parallèle à PostgreSQL/`TradingEngine` ;
- le futur cockpit peut d'abord consommer REST.

Un WebSocket sera réévalué lorsque le besoin de fréquence, le modèle d'abonnement et la source d'événements auront été définis.

---

## 14. PostgreSQL et schéma

Le schéma du Batch 09 est réutilisé tel quel :

```text
audit_cycles
  +-- audit_decisions
  +-- audit_risk_assessments
  +-- audit_execution_intents
         +-- audit_fills
```

Le journal garde les snapshots JSON disponibles et les colonnes indexables utiles. L'API ne modifie pas ce schéma pour simplifier ses routes.

---

## 15. Testabilité

Les routes sont testables avec des fakes injectés, sans OpenAI, Kraken ou PostgreSQL réel.

Un test séparé du query service utilise `sqlite+aiosqlite:///:memory:` pour vérifier les requêtes SQLAlchemy offline. La validation PostgreSQL reste une validation d'intégration locale distincte.

Le startup FastAPI ne doit déclencher ni cycle, ni réseau, ni migration.

---

## 16. Hors périmètre Batch 10

- frontend ;
- analytics P&L/drawdown complets ;
- configuration de stratégie/Risk/agressivité par API ;
- private Kraken ;
- LIVE ;
- auth complexe ;
- scanner multi-paires ;
- recovery/reconciliation exactement-once ;
- bus temps réel/WebSocket.
