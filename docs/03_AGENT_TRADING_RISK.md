# 03 — Agent IA, trading et Risk Engine

## 1. Objet

Ce document fixe la frontière entre :

1. les calculs déterministes de contexte ;
2. la décision stratégique de l'agent IA ;
3. les règles déterministes de sécurité ;
4. l'orchestration PAPER ;
5. l'exécution PAPER ;
6. la persistance durable des faits de cycle.

Cette frontière est centrale pour éviter de transformer AI Spot Trader en bot algorithmique traditionnel.

---

## 2. Principe de décision

L'agent IA est l'unique décideur stratégique. Il choisit parmi `BUY`, `SELL`, `HOLD` et fournit la **quantité proposée** pour BUY/SELL.

Les systèmes déterministes peuvent calculer et présenter prix, statistiques, volatilité, exposition, P&L, contraintes et fraîcheur des données. Ils ne doivent pas décider silencieusement qu'un signal technique implique un BUY ou SELL.

Le Risk Engine reste déterministe et possède l'autorité finale d'autoriser, réduire ou refuser une proposition tradable.

La persistance conserve ce qui s'est produit ; elle ne décide jamais de ce qui doit se produire.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

---

## 3. Chaîne de décision canonique

```text
MarketState + PortfolioState + aggressiveness
                  |
                  v
             AgentInput
                  |
                  v
          Agent Luna/Sol
                  |
                  v
         DecisionCandidate
   action + proposed_quantity
                  |
                  v
            Risk Engine
         /       |        \
     REJECT    MODIFY      ALLOW
         |        |          |
         |        +----------+
         |                   |
         |          ExecutionIntent PAPER
         |                   |
         |          same MarketState pricing
         |                   |
         |                   v
         |             Paper Broker
         |                   |
         +-------------------+
                  |
          TradingCycleResult
                  |
                  v
       Audit persistence PostgreSQL
```

Aucune sortie LLM ne déclenche directement un ordre. Le package Agent n'importe ni Risk, ni Broker, ni Kraken, ni FastAPI, ni persistance. Le package `trading` orchestre les frontières mais ne prend aucune décision stratégique.

---

## 4. AgentInput

```text
AgentInput
- cycle_id
- created_at
- market_state
- portfolio_state
- aggressiveness (1..10)
```

Les snapshots imbriqués restent les contrats Pydantic canoniques. Le runner crée l'input seulement après avoir acquis les deux snapshots du cycle.

### No look-ahead côté Agent

Avant tout appel LLM :

```text
market_state.as_of    <= agent_input.created_at
portfolio_state.as_of <= agent_input.created_at
```

Une violation empêche l'appel fournisseur. Aucun lookup Kraken, refresh de prix ou enrichissement réseau n'est réalisé par l'agent.

---

## 5. DecisionCandidate et sizing stratégique

```text
DecisionCandidate
- decision_id
- cycle_id
- created_at
- action = BUY | SELL | HOLD
- symbol
- proposed_quantity?   # obligatoire BUY/SELL, interdite HOLD
- rationale?
```

Conséquences :

- BUY et SELL sans quantité sont invalides ;
- HOLD avec une quantité est invalide ;
- Risk peut réduire une quantité uniquement si sa policy l'autorise ;
- Risk ne peut jamais augmenter la taille proposée ;
- Risk ne peut jamais changer action ou symbole ;
- l'orchestrateur ne recalcule jamais la quantité ;
- `rationale` reste une donnée d'audit, jamais une commande.

---

## 6. Frontière fournisseur LLM

Le modèle n'est pas autorisé à inventer les métadonnées techniques. Son JSON contient uniquement :

```text
action
symbol
proposed_quantity
rationale
```

`decision_id`, `cycle_id` et `created_at` appartiennent à l'application : factory UUID injectable, `cycle_id` recopié de l'input et `Clock` injectable.

Le modèle doit produire exactement `agent_input.market_state.symbol`.

---

## 7. Validation structurée LLM

Le JSON Schema OpenAI strict autorise uniquement :

```text
{
  action: BUY | SELL | HOLD,
  symbol: string,
  proposed_quantity: number | null,
  rationale: string | null
}
```

Les quatre propriétés sont requises, `additionalProperties=false`, puis la réponse est revalidée localement.

Aucune réparation silencieuse n'est tentée.

---

## 8. Prompt `agent-luna-v1`

Le prompt système rappelle :

- SPOT uniquement ;
- PAPER uniquement ;
- BUY / SELL / HOLD ;
- aucun short, levier, margin, future ou perpetual ;
- ne pas vendre plus que détenu ;
- BUY/SELL avec quantité positive ;
- HOLD sans quantité ;
- agressivité 1–10 comme contexte, sans mapping définitif ;
- cible expérimentale +4 %/jour sans obligation de trader ;
- aucune garantie de rendement ;
- aucune donnée absente inventée ;
- décision fondée uniquement sur l'`AgentInput` reçu ;
- symbole limité au `MarketState` fourni ;
- aucune instruction d'exécution, de broker, de Kraken ou de tool-calling.

Le prompt ne contient aucun secret.

---

## 9. OpenAI / Luna / Sol

La même implémentation `OpenAIDecisionProvider` supporte :

```text
Luna = gpt-5.6-luna
Sol  = gpt-5.6-sol
```

Le choix est porté par `LLMModel`.

---

## 10. Erreurs Agent

Erreurs séparées :

- `LLMTransportError` : réseau ou HTTP ;
- `LLMProviderError` : réponse fournisseur incomplète, refusée ou enveloppe inutilisable ;
- `LLMOutputValidationError` : sortie JSON/stratégique invalide ;
- `AgentContractViolationError` : invariant d'application violé.

Une erreur Agent termine techniquement le cycle avant Risk/Broker. Elle n'est jamais transformée en HOLD et ne déclenche aucun retry immédiat du même cycle.

---

## 11. Risk Engine

`RiskPolicy` peut porter :

```text
max_order_notional?
allowed_pairs?
stale_after?
allow_quantity_reduction = false
```

Risk vérifie indépendamment symbole, chronologie, whitelist, fraîcheur, max notional, cash BUY, position SELL et rôles d'actifs.

### Sémantique

- `ALLOW` : proposition acceptée ;
- `MODIFY` : quantité strictement réduite ;
- `REJECT` : aucun `ExecutionIntent` ;
- `HOLD` : `ALLOW + HOLD_NO_EXECUTION`, aucun intent.

REJECT est un résultat métier normal, pas une exception technique.

---

## 12. HOLD

HOLD suit obligatoirement :

```text
Agent
 -> DecisionCandidate(HOLD)
 -> Risk Engine
 -> RiskAssessment(ALLOW + HOLD_NO_EXECUTION)
 -> aucun ExecutionIntent
 -> aucun Broker
 -> journal durable du cycle/décision/assessment
```

La persistance Batch 09 vérifie que HOLD ne crée ni intent ni fill.

---

## 13. REJECT

Pour `RiskDecision.REJECT` :

- aucun intent ;
- aucun Broker ;
- aucun fill ;
- aucune mutation du ledger ;
- résultat technique `COMPLETED` avec décision et assessment conservés ;
- journal durable du cycle/décision/assessment.

---

## 14. MODIFY

Pour `MODIFY`, seul l'`ExecutionIntent` créé par Risk est transmis au Broker.

L'orchestrateur vérifie que :

- l'action est inchangée ;
- le symbole est inchangé ;
- l'intent référence le bon assessment ;
- la quantité de l'intent est exactement `authorized_quantity`.

Le journal conserve la décision originale, l'assessment MODIFY, l'intent Risk et les fills réellement retournés.

---

## 15. ALLOW

Pour BUY/SELL autorisé :

```text
DecisionCandidate
 -> RiskAssessment
 -> ExecutionIntent créé par Risk
 -> Broker.execute(intent, same_market_state)
 -> Fill(s)
 -> audit durable
```

Il n'existe aucun autre chemin d'exécution.

---

## 16. Paper Broker et portefeuille

`PaperBroker` reste l'unique composant qui réalise le fill et mute le `PaperPortfolioLedger`.

```text
Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]
```

Le Broker reçoit le même `MarketState` que celui présenté à l'Agent et à Risk pour le cycle. Il n'effectue aucun lookup Kraken caché.

Le snapshot portfolio post-trade n'est pris qu'après retour de fills valides.

---

## 17. Frais, spread et slippage

`PaperExecutionCostModel` reste la source des coûts PAPER déterministes : `fee_rate`, `spread_bps`, `slippage_bps`.

Risk utilise la même estimation de coût que le Paper Broker pour la solvabilité BUY. Tous les calculs financiers utilisent `Decimal`.

Les fills persistés conservent prix de référence, prix exécuté, notional, frais, spread et slippage via leur payload canonique.

---

## 18. Agressivité

Valeur entière de 1 à 10, validée dans `Settings` et `AgentInput`.

Le mapping exact reste à décider. L'orchestrateur transmet la valeur à `AgentInput` sans coefficient, taille, seuil technique ou changement de stratégie déterministe.

La persistance ne l'interprète pas.

---

## 19. Identifiants, timestamps et audit

Un cycle complet peut relier :

```text
cycle_id
market_state_id
portfolio_state_id
decision_id
risk_assessment_id
execution_id
fill_id(s)
```

Frontière temporelle :

```text
market_state.as_of    <= agent_input.created_at
portfolio_state.as_of <= agent_input.created_at
agent_input.created_at <= decision_candidate.created_at
                         <= risk_assessment.assessed_at
                         == execution_intent.created_at  # si intent
market_state.as_of <= fill.filled_at                    # si fill
```

Le `cycle_id` vient d'une factory injectable au runner. Le LLM ne l'invente jamais.

Le journal utilise `cycle_id` comme identité principale du graphe durable.

---

## 20. Cohérence des snapshots

Chaque cycle capture exactement :

1. un `MarketState` ;
2. un `PortfolioState` pré-cycle.

Ces objets sont placés dans `AgentInput`. Après validation de l'input, l'orchestrateur réutilise explicitement ces mêmes références : marché + portefeuille pour Risk, puis marché pour Broker.

Le journal conserve l'`AgentInput` complet et le snapshot post-cycle s'il existe.

---

## 21. Résultat technique du cycle

`TradingCycleResult` est un conteneur d'orchestration mémoire et non un contrat métier parallèle.

Il peut conserver selon l'étape :

- `cycle_id` ;
- `AgentInput` ;
- `DecisionCandidate` ;
- `RiskAssessment` ;
- `ExecutionIntent` éventuel ;
- fills ;
- `PortfolioState` post-exécution ;
- métadonnée de panne technique éventuelle.

HOLD et REJECT sont `COMPLETED`. Une panne technique est `FAILED`.

Batch 09 persiste ce résultat tel qu'il a été produit.

---

## 22. Politique d'erreur du cycle

### Avant décision

Une erreur Market/Portfolio/Input empêche Agent, Risk et Broker selon l'étape atteinte.

### Agent

Une erreur fournisseur, transport, parsing ou contrat empêche Risk et Broker. Pas de HOLD synthétique.

### Risk

Une exception technique Risk empêche le Broker. Elle reste distincte d'un `REJECT` métier.

### Broker

Une erreur Broker est conservée comme échec explicite. Aucun fill synthétique n'est créé.

Le résultat technique ne recopie que le type d'exception, pas son message brut. Le journal durable reprend cette métadonnée sanitizée.

---

## 23. Timeouts et incertitude d'exécution

Les attentes Market, Agent et Broker sont bornées avec `asyncio.timeout`, avec valeurs injectées et strictement positives.

Risk reste sans timeout artificiel.

Le Broker PAPER canonique exécute son calcul/mutation de manière synchrone après acquisition de son verrou.

Un futur broker réseau pouvant laisser une mutation incertaine nécessitera une politique dédiée de réconciliation.

---

## 24. Boucle autonome

`TradingEngine` répète un seul runner :

```text
cycle N complet
    |
attente cadence ou stop
    |
cycle N+1
```

Il n'existe aucun cycle de rattrapage concurrent. Une erreur de cycle est isolée puis la cadence normale est respectée avant de retenter un nouveau cycle.

`start()` refuse les doubles démarrages. `stop()` réveille l'attente de cadence et attend la fin du cycle borné en cours.

---

## 25. Frontière de persistance Batch 09

`AuditedTradingCycleRunner` est un wrapper, pas un nouvel orchestrateur :

```text
TradingCycleRunner
      |
      v
TradingCycleResult
      |
      v
SqlAlchemyCycleAuditRepository
```

La persistance :

- ne modifie pas le résultat ;
- ne réévalue pas Risk ;
- ne reconstruit pas un intent ;
- ne synthétise pas de fill ;
- ne transforme pas une erreur en HOLD ;
- ne rejoue pas automatiquement un intent.

Une panne de persistance est une panne technique et doit rester visible.

---

## 26. Idempotence métier du journal

Le repository calcule une empreinte déterministe du résultat complet.

- premier `cycle_id` : écriture ;
- replay strictement identique : no-op ;
- même `cycle_id` avec contenu différent : conflit explicite.

Cette politique prévient les doubles écritures du journal. Elle ne garantit pas à elle seule un exactly-once d'exécution.

---

## 27. Reprise après crash

Le ledger PAPER reste mémoire au Batch 09.

Il existe donc encore une fenêtre :

```text
PaperBroker mutate le ledger
        |
crash
        |
journal durable pas encore commité
```

La persistance apporte les données nécessaires à une future réconciliation, mais elle ne peut pas garantir que cette fenêtre n'existe pas.

La prochaine architecture de reprise devra être décidée sans rejouer post-hoc les décisions de l'IA.

---

## 28. Interfaces externes

Ports canoniques métier inchangés :

- `MarketDataSource.snapshot(symbol) -> MarketState` ;
- `MarketObservationSource.observation(symbol) -> MarketObservation` ;
- `LLMProvider.generate_decision(agent_input) -> DecisionCandidate` ;
- `Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]`.

Port de persistance ajouté :

- `CycleAuditWriter.record(TradingCycleResult) -> bool`.

Risk reste une frontière interne synchrone.

---

## 29. Tests Batch 09

La suite de persistance vérifie notamment :

- HOLD durable sans intent/fill ;
- REJECT durable sans intent/fill ;
- ALLOW et MODIFY avec relation complète ;
- conservation des IDs de snapshots ;
- erreurs techniques sanitizées ;
- replay idempotent ;
- rollback transactionnel ;
- wrapper audité ;
- lifecycle de la DB.

La suite standard utilise SQLite async mémoire et reste indépendante d'un service PostgreSQL externe.

Une validation séparée réelle a appliqué la migration Alembic sur PostgreSQL 18 sous Docker Desktop et vérifié les tables créées.

---

## 30. Persistance et LIVE

Le journal durable reste PAPER uniquement.

Le LIVE reste hors périmètre : aucune API Kraken privée, aucune clé de trading, aucune permission de retrait et aucune exécution réelle.
