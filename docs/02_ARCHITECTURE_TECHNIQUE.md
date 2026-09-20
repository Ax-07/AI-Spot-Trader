# 02 — Architecture technique

## 1. Objet

Ce document décrit l'architecture technique courante d'AI Spot Trader, incluant le Batch 10 intégré et le patch Batch 11 proposé pour validation. Les choix produit non figés restent explicitement séparés de l'architecture.

---

## 2. Vue d'ensemble

```text
+--------------------------+
| Frontend cockpit         |
| Next.js / TS / shadcn    |
+------------+-------------+
             |
      /backend/* rewrite
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

L'API ne peut ni créer `DecisionCandidate`, ni appeler le LLM, ni construire `RiskAssessment`/`ExecutionIntent`, ni appeler le Broker pour contourner le runner. Le frontend ne peut pas non plus effectuer ces opérations.

---

## 5. Runtime FastAPI intégré au Batch 10

`create_app()` reste sans I/O externe et sans démarrage du trading à l'import.

Le lifespan construit un `AppRuntime` avec, selon l'injection :

- un `ControllableTradingEngine` ;
- un `PortfolioSnapshotSource` ;
- un `CycleAuditReader` ;
- éventuellement un `Database` possédé par l'application si `database_url` est configurée.

Aucune valeur produit de capital, paire, cadence, coûts ou RiskPolicy n'est inventée par FastAPI. Sans moteur ou portefeuille injecté, les endpoints associés restent explicitement non configurés.

À l'arrêt, `AppRuntime.close()` demande l'arrêt coopératif du moteur configuré puis ferme la DB qu'il possède. Fermer un client ou le frontend n'appelle pas ce lifecycle process.

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

Le recovery/rebuild du ledger reste hors Batch 10 et hors Batch 11.

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

Le frontend Batch 11 reflète ces modèles avec des types TypeScript dédiés. Il n'ajoute aucun champ métier et se limite au formatage d'affichage des UUID, timestamps et `Decimal` sérialisés.

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

Le cockpit distingue explicitement 404, 503, erreurs réseau et erreurs API génériques. Il n'affiche aucune stack trace.

---

## 12. Lifecycle DB

Si un `CycleAuditReader` est injecté, FastAPI ne crée pas de DB.

Sinon, lorsque `AI_SPOT_TRADER_DATABASE_URL` est présente, le lifespan construit `Database` et `SqlAlchemyCycleAuditQueryService`. La création de l'engine SQLAlchemy ne lance ni migration ni requête au startup. Le pool est disposé au shutdown.

Les migrations restent gérées exclusivement par Alembic. Le Batch 10 ne nécessite aucune migration supplémentaire au-dessus de `0001_audit_journal` et le Batch 11 ne modifie pas la base.

---

## 13. WebSocket

Aucun WebSocket n'est introduit au Batch 10 ni dans le patch Batch 11.

Motifs :

- aucune source d'événements runtime canonique n'existe encore ;
- diffuser en WebSocket des polls DB ajouterait peu de valeur ;
- il faut éviter une seconde source d'état parallèle à PostgreSQL/`TradingEngine` ;
- REST suffit au premier cockpit.

Un WebSocket sera réévalué lorsque le besoin de fréquence, le modèle d'abonnement et la source d'événements auront été définis.

---

## 14. Frontend cockpit — Batch 11 proposé

Découpage proposé :

```text
frontend/src/
  app/
    page.tsx
    globals.css
  components/
    cockpit/
      cockpit-dashboard.tsx
    ui/
      badge.tsx
      button.tsx
      card.tsx
  hooks/
    use-cockpit.ts
  lib/
    api/
      client.ts
      format.ts
      types.ts
    utils.ts
```

### 14.1 Couche HTTP

`frontend/src/lib/api/client.ts` est l'unique point d'accès REST du cockpit.

Le navigateur appelle :

```text
/backend/health
/backend/api/v1/engine
/backend/api/v1/portfolio
/backend/api/v1/...
```

`next.config.ts` réécrit ces routes vers :

```text
AI_SPOT_TRADER_BACKEND_URL
```

La valeur locale par défaut est `http://127.0.0.1:8000`. Cette adresse n'est pas sensible et n'est pas exposée par une variable `NEXT_PUBLIC_*`.

### 14.2 CORS

Le rewrite same-origin évite d'introduire une politique CORS backend pour le développement standard. Un déploiement séparant réellement les origines pourra revoir cette décision avec une politique CORS explicite, mais le Batch 11 n'élargit pas la surface backend.

### 14.3 Polling

`useCockpit` déclenche une lecture toutes les 10 secondes lorsque `document.visibilityState === "visible"`, plus une actualisation manuelle.

Le polling :

- est borné ;
- est exclusivement présentatif ;
- ne crée aucune tâche de trading ;
- ne règle aucune cadence moteur ;
- n'est pas requis pour la survie du backend.

### 14.4 Commandes lifecycle

Start/Stop appellent uniquement les routes Batch 10. Les boutons sont désactivés pendant une requête et selon l'état `configured/status` renvoyé par le backend.

Aucun `ExecutionIntent`, décision ou fill n'est construit dans le navigateur.

### 14.5 États UI

Chaque ressource peut être :

```text
loading
ready
empty
unavailable
error
```

Correspondances principales :

- 404 -> `empty` ;
- 503 -> `unavailable` ;
- erreur réseau -> `error` ;
- liste 200 avec `items=[]` -> `ready` + état vide métier.

### 14.6 Affichage

Le cockpit privilégie les champs structurés de premier niveau : état moteur, action, statut Risk, symbole, timestamps, balances, positions et nombre de fills.

Les payloads JSON canoniques détaillés ne sont pas utilisés pour produire une logique parallèle ni exposés comme dumps bruts par défaut.

---

## 15. PostgreSQL et schéma

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

## 16. Testabilité

Les routes sont testables avec des fakes injectés, sans OpenAI, Kraken ou PostgreSQL réel.

Un test séparé du query service utilise `sqlite+aiosqlite:///:memory:` pour vérifier les requêtes SQLAlchemy offline. La validation PostgreSQL reste une validation d'intégration locale distincte.

Le startup FastAPI ne doit déclencher ni cycle, ni réseau, ni migration.

Le frontend Batch 11 ne doit exiger aucun backend actif pour compiler. Les validations attendues sont :

```text
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
git diff --check
```

Aucune requête réelle OpenAI ou Kraken n'est nécessaire.

---

## 17. Hors périmètre Batch 11

- analytics P&L/drawdown complets ;
- configuration de stratégie/Risk/agressivité par cockpit ;
- private Kraken ;
- LIVE ;
- auth complexe ;
- scanner multi-paires ;
- recovery/reconciliation exactly-once ;
- bus temps réel/WebSocket ;
- moteur alternatif côté frontend ;
- écriture directe PostgreSQL depuis le frontend.
