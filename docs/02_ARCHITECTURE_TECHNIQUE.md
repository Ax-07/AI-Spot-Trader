# 02 — Architecture technique

## 1. Objet

Ce document décrit l'architecture technique courante d'AI Spot Trader, incluant les Batches 10, 11 et 12 intégrés et le **patch Batch 13 préparé mais non intégré**. Les choix produit non figés restent explicitement séparés de l'architecture.

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
                                                     |
                                  +------------------+------------------+
                                  |                                     |
                                  v                                     v
                         audit query service                   analytics reducer
                                  |                                     |
                                  +------------------+------------------+
                                                     |
                                                     v
                                             FastAPI / cockpit
```

Le frontend n'est jamais l'ordonnanceur du moteur. PostgreSQL conserve des faits ; il ne produit aucune stratégie.

Le patch Batch 13 ajoute un protocole expérimental backend/domaine sans modifier ce flux de confiance.

---

## 3. Découpage backend

```text
backend/src/ai_spot_trader/
  agent/
  analytics/
    paper.py
  api/
  broker/
  core/
  domain/
    enums.py
    experiments.py
    models.py
    ports.py
    symbols.py
  experiments/
    __init__.py
    comparison.py
    protocol.py
  integrations/kraken/
  market/
  persistence/
  portfolio/
  risk/
  trading/
    engine.py
  main.py
```

Responsabilités :

- `domain.experiments` : mapping d'agressivité et identité/digest du protocole sans dépendance Risk/Broker ;
- `experiments.protocol` : construction du manifeste à partir des configurations injectées Risk/coûts ;
- `experiments.comparison` : comparaison factuelle de rapports Batch 12 sans recalcul analytics ;
- `analytics` : calculs PAPER purs et déterministes dérivés des faits durables ;
- `domain` : contrats canoniques fournisseur-agnostiques ;
- `market` : construction déterministe du `MarketState` ;
- `portfolio` : ledger PAPER mémoire ;
- `agent` : décision stratégique structurée ;
- `risk` : autorité déterministe avant exécution ;
- `broker` : exécution PAPER uniquement après intent Risk ;
- `trading` : orchestration et boucle séquentielle ;
- `persistence` : écriture/lecture durable ;
- `api` : transport HTTP sans métier de trading ;
- `core.runtime` : dépendances process-locales et lifecycle explicite.

Le package Agent n'importe pas directement `risk` ou `broker`. Il dépend du mapping canonique sous `domain.experiments`, ce qui évite une inversion de dépendance via le protocole expérimental.

---

## 4. Flux de confiance canonique

```text
MarketDataSource.snapshot(symbol) ----+
                                      |
PaperPortfolioLedger.snapshot() ------+--> AgentInput
                                             |
                                             |  aggressiveness_context
                                             |  experiment_manifest?
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

L'agressivité n'est jamais transmise comme paramètre au Risk Engine.

---

## 5. Contrats expérimentaux Batch 13

### 5.1 `AggressivenessContext`

Le mapping `aggressiveness-map-v1` est discret et déterministe. Chaque niveau `1..10` produit :

```text
mapping_version
level
posture
strategic_instruction
```

Il ne contient aucun seuil Risk, indicateur, balance minimale, notional ou multiplicateur d'exécution.

### 5.2 `ExperimentManifest`

Le manifeste `paper-experiment-v1` est un modèle Pydantic strict persistable avec :

```text
protocol_version
experiment_digest
aggressiveness
llm_model
prompt_version
universe[]
risk_policy
paper_costs
analytics_version
source_id
source_digest?
window_start?
window_end?
```

Le digest SHA-256 utilise une sérialisation canonique : clés triées, `Decimal` sérialisés sans flottants, timestamps explicites et collections triées là où l'ordre n'est pas sémantique.

Le `comparison_identity` recalcule un digest des champs contrôlés **en excluant volontairement l'agressivité**. Deux runs ne peuvent donc être comparés que si le reste du protocole est identique.

### 5.3 Snapshots de configuration

`RiskPolicy` est projetée vers :

```text
max_order_notional
allowed_pairs
stale_after_seconds
allow_quantity_reduction
```

`PaperExecutionCostModel` est projeté vers :

```text
fee_rate
spread_bps
slippage_bps
```

Ces snapshots servent à l'identité expérimentale. Ils ne déplacent aucune logique Risk/Broker dans le package expérimental.

---

## 6. Agent et prompt Batch 13

Le prompt évolue vers `agent-strategy-v2`.

`OpenAIDecisionProvider` :

1. valide le symbole et la chronologie existante ;
2. résout `aggressiveness-map-v1` ;
3. normalise un ancien `AgentInput` sans contexte pour l'appel LLM ;
4. si un manifeste existe, vérifie son digest, son modèle, son prompt et son mapping ;
5. appelle le client structured-output canonique ;
6. revalide la décision comme avant.

Aucun tool-calling, aucun accès Risk/Broker/Kraken et aucun retry automatique n'est ajouté.

---

## 7. TradingCycleRunner Batch 13

Le runner canonique reste unique. Son constructeur accepte un `experiment_manifest` optionnel.

À la construction :

- le symbole reste validé en forme canonique ;
- l'agressivité est validée via `aggressiveness_context(...)` ;
- si un manifeste est présent, son digest doit être valide ;
- le niveau du manifeste doit correspondre au niveau du runner ;
- le symbole du runner doit appartenir à l'univers du manifeste.

Lors de chaque cycle, l'`AgentInput` contient le même contexte et le même manifeste. Aucun composant expérimental n'exécute un ordre.

Le reste du pipeline reste inchangé : Market -> Portfolio -> Agent -> Risk -> Broker -> post-portfolio.

---

## 8. Risk Engine inchangé

`RiskEngine` reste synchrone et déterministe. Il ne lit ni `AggressivenessContext` ni `ExperimentManifest`.

Les contrôles restent :

- symbole et correspondance marché ;
- whitelist optionnelle ;
- chronologie marché/portfolio ;
- fraîcheur optionnelle ;
- max notional optionnel ;
- rôles d'actifs ;
- balance quote ;
- solvabilité BUY avec coûts ;
- position SELL disponible.

La quantité stratégique peut être réduite ou rejetée exactement comme avant. Le niveau 10 ne crée aucune exception.

---

## 9. Persistance durable sans migration

Le journal Batch 09 persiste déjà `agent_input_payload` en JSON/JSONB et le `result_digest` est calculé à partir du résultat complet.

Conséquences Batch 13 :

- `aggressiveness_context` et `experiment_manifest` sont durables sans nouvelle colonne ;
- les niveaux différents sont explicitement distinguables dans les faits persistés ;
- changer le manifeste change naturellement le `result_digest` ;
- les anciens payloads restent valides car les deux champs sont optionnels ;
- aucune migration Alembic n'est requise.

Le writer durable ne connaît pas la sémantique du manifeste : il persiste le modèle canonique comme n'importe quel autre fait `AgentInput`.

---

## 10. Compatibilité analytics Batch 12

`AgentInput.model_validate_json(...)` accepte les deux champs optionnels Batch 13 ; le reducer `analytics.paper` continue donc à lire les mêmes faits.

Aucune formule P&L/drawdown/coût/exposition n'est modifiée.

`compare_aggressiveness_runs(...)` reçoit des objets `PaperAnalyticsReport` déjà produits et extrait uniquement les métriques existantes :

- gross/net P&L ;
- frais/spread/slippage ;
- drawdown ;
- exposition ;
- trades ;
- HOLD/REJECT/MODIFY/FAILED ;
- `daily` existant.

La comparaison ne recharge pas le journal, ne revalorise pas les positions et ne modifie pas `source_digest`.

---

## 11. No-look-ahead et protocole expérimental

Le manifeste peut identifier une source/dataset et une fenêtre, mais le `MarketState` réellement fourni au cycle reste la seule donnée de marché décisionnelle.

Pour une comparaison strictement appariée :

- même `source_id` ;
- même `source_digest` si dataset figé ;
- même fenêtre ;
- même univers ;
- même modèle/prompt ;
- même `RiskPolicy` ;
- mêmes coûts PAPER ;
- même version analytics.

Une comparaison de deux passages live successifs est possible descriptivement, mais ne permet pas d'attribuer proprement l'écart observé à l'agressivité seule puisque les faits marché diffèrent.

---

## 12. Reproductibilité et limite LLM

Trois identités sont distinguées :

1. `experiment_digest` : protocole/configuration ;
2. `result_digest` : faits réalisés d'un cycle ;
3. `PaperAnalyticsReport.source_digest` : séquence de cycles utilisée par les analytics.

Cette séparation évite de prétendre qu'un digest de protocole reproduit une sortie LLM.

Tant qu'aucun déterminisme fournisseur exact n'est garanti, même modèle + prompt + faits + manifeste peuvent produire des décisions différentes. Un futur protocole statistique pourra exécuter plusieurs répétitions contrôlées ; ce choix n'est pas inventé au Batch 13.

---

## 13. Runtime FastAPI

`create_app()` reste sans I/O externe et sans démarrage du trading à l'import.

Le lifespan et la surface moteur restent inchangés. Batch 13 n'ajoute aucune route de création/mutation d'expérience.

Aucune valeur produit de capital, paire, cadence, coûts ou RiskPolicy n'est inventée par FastAPI.

---

## 14. Frontend cockpit

Le cockpit Batch 11 n'est pas modifié.

Il continue d'afficher les ressources REST et analytics Batch 12. Il ne contient pas de mapping d'agressivité, de constructeur de manifeste ou de logique de comparaison métier.

Une future surface UI de lancement/inspection d'expériences nécessitera un contrat API dédié avant implémentation.

---

## 15. PostgreSQL et schéma

Le schéma reste :

```text
audit_cycles
  +-- audit_decisions
  +-- audit_risk_assessments
  +-- audit_execution_intents
         +-- audit_fills
```

Aucune migration Batch 13 n'est ajoutée.

---

## 16. Testabilité

Les tests Batch 13 ciblent :

- validation `1..10` et rejet hors plage ;
- mapping discret/versionné déterministe ;
- cohérence `AgentInput` niveau/contexte ;
- digest de manifeste stable ;
- digest distinct pour niveaux différents ;
- rejet d'un manifeste altéré ;
- comparaison refusée si RiskPolicy diffère ;
- invariance des résultats Risk vis-à-vis du niveau ;
- HOLD / ALLOW / MODIFY / REJECT ;
- lecture analytics Batch 12 d'un `AgentInput` enrichi ;
- validation provider modèle/prompt/manifeste avant appel LLM.

Validation réellement exécutée pendant préparation :

```text
pytest ciblé test_experiments.py + test_agent_provider.py : 47 passed
python -m py_compile fichiers Python du patch          : réussi
```

Ruff n'était pas disponible dans l'environnement de préparation. La suite backend complète, Ruff, mypy et `git diff --check` doivent être exécutés localement avant intégration.

---

## 17. Hors périmètre du patch Batch 13

- configuration de stratégie/Risk/agressivité par cockpit ;
- lancement d'expériences via FastAPI ;
- replay historique complet d'un flux marché depuis PostgreSQL ;
- seed/déterminisme exact du fournisseur LLM ;
- scanner multi-paires ;
- private Kraken ;
- LIVE ;
- recovery/reconciliation exactly-once ;
- bus temps réel/WebSocket ;
- moteur alternatif côté frontend.
