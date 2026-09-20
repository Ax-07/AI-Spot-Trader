# 03 — Agent IA, trading et Risk Engine

## 1. Objet

Ce document fixe la frontière entre :

1. les calculs déterministes de contexte ;
2. la décision stratégique de l'agent IA ;
3. les règles déterministes de sécurité ;
4. l'orchestration PAPER ;
5. l'exécution PAPER.

Cette frontière est centrale pour éviter de transformer AI Spot Trader en bot algorithmique traditionnel.

---

## 2. Principe de décision

L'agent IA est l'unique décideur stratégique. Il choisit parmi `BUY`, `SELL`, `HOLD` et fournit la **quantité proposée** pour BUY/SELL.

Les systèmes déterministes peuvent calculer et présenter prix, statistiques, volatilité, exposition, P&L, contraintes et fraîcheur des données. Ils ne doivent pas décider silencieusement qu'un signal technique implique un BUY ou SELL.

Le Risk Engine reste déterministe et possède l'autorité finale d'autoriser, réduire ou refuser une proposition tradable.

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
```

Aucune sortie LLM ne déclenche directement un ordre. Le package Agent n'importe ni Risk, ni Broker, ni Kraken, ni FastAPI. Le package `trading` orchestre les frontières mais ne prend aucune décision stratégique.

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

Les snapshots imbriqués restent les contrats Pydantic canoniques. Le runner Batch 08 crée l'input seulement après avoir acquis les deux snapshots du cycle.

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

Le modèle doit produire exactement `agent_input.market_state.symbol`. Une décision pour un autre symbole est rejetée avant création d'un `DecisionCandidate` utilisable.

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

Le parsing refuse notamment : sortie vide, JSON invalide, constantes non standard, quantité fournie comme chaîne, champs inattendus, action inconnue, BUY/SELL sans quantité positive et HOLD avec quantité.

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

Le choix est porté par `LLMModel`. Le Batch 08 n'ajoute aucune sélection dynamique ni comparaison de performance.

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
```

Le `TradingCycleResult` conserve la décision et l'assessment pour que Batch 09 puisse les persister.

---

## 13. REJECT

Pour `RiskDecision.REJECT` :

- aucun intent ;
- aucun Broker ;
- aucun fill ;
- aucune mutation du ledger ;
- résultat technique `COMPLETED` avec décision et assessment conservés.

---

## 14. MODIFY

Pour `MODIFY`, seul l'`ExecutionIntent` créé par Risk est transmis au Broker.

L'orchestrateur vérifie que :

- l'action est inchangée ;
- le symbole est inchangé ;
- l'intent référence le bon assessment ;
- la quantité de l'intent est exactement `authorized_quantity`.

Il ne recalcule ni n'arrondit cette quantité.

---

## 15. ALLOW

Pour BUY/SELL autorisé :

```text
DecisionCandidate
 -> RiskAssessment
 -> ExecutionIntent créé par Risk
 -> Broker.execute(intent, same_market_state)
 -> Fill(s)
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

---

## 18. Agressivité

Valeur entière de 1 à 10, validée dans `Settings` et `AgentInput`.

Le mapping exact reste à décider. Le Batch 08 transmet la valeur à `AgentInput` sans coefficient, taille, seuil technique ou changement de stratégie déterministe.

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

---

## 20. Cohérence des snapshots Batch 08

Chaque cycle capture exactement :

1. un `MarketState` ;
2. un `PortfolioState` pré-cycle.

Ces objets sont placés dans `AgentInput`. Après validation de l'input, l'orchestrateur réutilise explicitement ces mêmes références : marché + portefeuille pour Risk, puis marché pour Broker.

Aucun refresh marché n'est autorisé avant l'exécution de cette décision.

Le verrou global du runner garantit qu'un autre cycle utilisant ce runner ne peut pas muter le ledger entre Risk et Broker.

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

Le résultat technique ne recopie que le type d'exception, pas son message brut.

---

## 23. Timeouts et incertitude d'exécution

Les attentes Market, Agent et Broker sont bornées avec `asyncio.timeout`, avec valeurs injectées et strictement positives.

Risk reste sans timeout artificiel.

Le Broker PAPER canonique exécute son calcul/mutation de manière synchrone après acquisition de son verrou. Le Batch 08 n'introduit donc aucune reprise automatique d'un intent après timeout.

Un futur broker réseau pouvant laisser une mutation incertaine nécessitera persistance, idempotence/réconciliation et politique dédiée ; ces sujets sont différés.

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

`start()` refuse les doubles démarrages. `stop()` réveille l'attente de cadence et attend la fin du cycle borné en cours. Le runtime FastAPI peut appeler `stop()` au shutdown.

---

## 25. Interfaces externes

Ports canoniques inchangés :

- `MarketDataSource.snapshot(symbol) -> MarketState` ;
- `MarketObservationSource.observation(symbol) -> MarketObservation` ;
- `LLMProvider.generate_decision(agent_input) -> DecisionCandidate` ;
- `Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]`.

Le Risk Engine reste une frontière interne synchrone. Le Batch 08 n'ajoute pas de port externe généraliste.

---

## 26. Tests Batch 08

La suite ciblée vérifie notamment : HOLD complet et passage Risk, BUY/SELL ALLOW, MODIFY exact, REJECT sans Broker, identité Market/Portfolio, corrélation `cycle_id`, clock/factory injectables, erreurs avant décision/Agent/Risk/Broker, timeouts Market/Agent/Broker, absence de refresh caché, sérialisation de cycles, double start impossible, stop pendant cadence, absence de tâche orpheline, absence de boucle serrée, portfolio post BUY/SELL et shutdown runtime.

Aucun réseau ni secret réel n'est requis.

---

## 27. Persistance et LIVE

Batch 09 ajoutera le journal durable. Batch 08 ne prétend pas offrir de reprise après crash.

Le LIVE reste hors périmètre : aucune API Kraken privée, aucune clé de trading, aucune permission de retrait et aucune exécution réelle.
