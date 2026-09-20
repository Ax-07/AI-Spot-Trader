# 03 — Agent IA, trading et Risk Engine

## 1. Objet

Ce document fixe la frontière entre :

1. les calculs déterministes de contexte ;
2. la décision stratégique de l'agent IA ;
3. les règles déterministes de sécurité et d'exécution.

Cette frontière est centrale pour éviter de transformer AI Spot Trader en bot algorithmique traditionnel.

---

## 2. Principe de décision

### Confirmé

L'agent IA est l'unique décideur stratégique. Il choisit parmi `BUY`, `SELL`, `HOLD` et fournit la **quantité proposée** pour BUY/SELL.

Les systèmes déterministes peuvent calculer et présenter prix, statistiques, volatilité, exposition, P&L, contraintes et fraîcheur des données. Ils ne doivent pas décider silencieusement qu'un signal technique implique un BUY ou SELL.

Le Risk Engine reste déterministe et possède l'autorité finale d'autoriser, modifier ou refuser une proposition tradable.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

---

## 3. Chaîne de décision

### Confirmé après préparation du Batch 07

```text
MarketState + PortfolioState + aggressiveness
                  |
                  v
             AgentInput
                  |
                  v
       OpenAIDecisionProvider
                  |
    sortie structurée strictement validée
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
   aucun intent   +----------+
                  |
                  v
          ExecutionIntent PAPER
                  |
          MarketState pricing
                  |
                  v
            Paper Broker
```

Aucune sortie LLM ne déclenche directement un ordre. Le package Agent n'importe ni Risk, ni Broker, ni Kraken, ni FastAPI.

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

Le Batch 07 ne modifie pas ce contrat. Les snapshots imbriqués restent des modèles Pydantic stricts et les timestamps sont timezone-aware normalisés UTC.

### No look-ahead côté Agent

Avant tout appel LLM :

```text
market_state.as_of    <= agent_input.created_at
portfolio_state.as_of <= agent_input.created_at
```

Une violation est rejetée avant l'appel fournisseur. Aucun lookup Kraken, refresh de prix ou enrichissement réseau n'est réalisé par l'agent.

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

La taille proposée est portée par le contrat stratégique canonique. Conséquences :

- BUY et SELL sans quantité sont invalides ;
- HOLD avec une quantité est invalide ;
- le Risk Engine peut réduire une quantité uniquement si sa policy l'autorise ;
- le Risk Engine ne peut jamais augmenter la taille proposée ;
- le Risk Engine ne peut jamais changer l'action ou le symbole ;
- `rationale` reste une donnée d'audit, jamais une commande.

---

## 6. Frontière fournisseur du Batch 07

### Sortie autorisée du modèle

Le modèle n'est pas autorisé à inventer les métadonnées techniques. Son JSON contient uniquement :

```text
action
symbol
proposed_quantity
rationale
```

`decision_id`, `cycle_id` et `created_at` appartiennent à l'application :

- factory UUID injectable ;
- `cycle_id` recopié de l'input ;
- `Clock` injectable.

Cette décision conserve le port `LLMProvider` inchangé et évite un second contrat métier concurrent.

### Symbole

Le modèle doit produire exactement `agent_input.market_state.symbol`.

Une décision pour `ETH/EUR` à partir d'un `MarketState` `BTC/EUR` est rejetée avant création d'un `DecisionCandidate`. L'agent ne peut donc pas trader silencieusement un actif sans contexte marché fourni.

Le Risk Engine conserve son propre contrôle identique en aval : la défense est volontairement redondante, mais les responsabilités diffèrent.

---

## 7. Validation structurée LLM

### Structured Outputs

Le Batch 07 utilise un JSON Schema strict côté OpenAI :

```text
{
  action: BUY | SELL | HOLD,
  symbol: string,
  proposed_quantity: number | null,
  rationale: string | null
}
```

Les quatre propriétés sont requises, `additionalProperties=false`, puis la réponse est revalidée localement.

### Validation applicative

Le parsing :

- refuse les sorties vides ou JSON invalides ;
- préserve les nombres comme `Decimal` ;
- refuse les constantes JSON non standard ;
- refuse la coercition d'une chaîne `"0.01"` en quantité ;
- refuse les champs inattendus ;
- refuse une action inconnue ;
- exige quantité strictement positive pour BUY/SELL ;
- exige `null` pour la quantité de HOLD.

Aucune réparation silencieuse n'est tentée. Une réponse stratégique invalide ne produit pas de `DecisionCandidate` utilisable.

---

## 8. Prompt `agent-luna-v1`

Le prompt système est versionné et auditable. Il rappelle au modèle :

- SPOT uniquement ;
- PAPER uniquement ;
- BUY / SELL / HOLD ;
- aucun short ;
- aucun levier ;
- aucune margin ;
- aucun future/perpetual ;
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

La documentation OpenAI vérifiée lors du Batch 07 confirme :

```text
Luna = gpt-5.6-luna
Sol  = gpt-5.6-sol
```

Les deux modèles supportent la Responses API et les Structured Outputs. L'application utilise un provider unique paramétré par `LLMModel`; Sol ne nécessite pas un second agent.

Le Batch 07 ne compare pas leurs performances et n'introduit aucun mécanisme expérimental de sélection dynamique.

---

## 10. Adapter OpenAI et erreurs

`OpenAIResponsesClient` encapsule uniquement le transport Responses API. Il ne connaît pas le domaine Risk/Broker.

Erreurs séparées :

- `LLMTransportError` : réseau ou HTTP ;
- `LLMProviderError` : réponse fournisseur incomplète, refusée ou enveloppe inutilisable ;
- `LLMOutputValidationError` : sortie JSON/stratégique invalide ;
- `AgentContractViolationError` : invariant d'application violé, par exemple symbole ou chronologie.

Les erreurs transport ne reproduisent jamais le body de réponse distant ni les headers d'authentification afin de ne pas exposer de secret.

### Retry

Aucun retry n'est ajouté au Batch 07. Un appel échoue explicitement. Une stratégie bornée pourra être décidée plus tard si l'orchestration en a besoin.

---

## 11. Configuration et secrets

Configuration LLM pertinente :

```text
AI_SPOT_TRADER_LLM_MODEL=gpt-5.6-luna
AI_SPOT_TRADER_OPENAI_API_KEY=
AI_SPOT_TRADER_OPENAI_BASE_URL=https://api.openai.com/v1
AI_SPOT_TRADER_OPENAI_TIMEOUT_SECONDS=30
```

La clé est typée `SecretStr | None`. Elle reste absente par défaut afin que l'application et les tests puissent démarrer sans compte OpenAI. Un client réel exige une valeur non vide.

Aucun secret n'est présent dans `.env.example`, le prompt ou les tests.

---

## 12. Risk Engine

Le Risk Engine du Batch 06 reste inchangé.

```text
RiskPolicy
- max_order_notional?
- allowed_pairs?
- stale_after?
- allow_quantity_reduction = false
```

Il vérifie indépendamment symbole, chronologie, whitelist, fraîcheur, max notional, cash BUY, position SELL et rôles d'actifs. Il conserve l'autorité finale même si le prompt a demandé au LLM de respecter ces invariants.

### Sémantique

- `ALLOW` : proposition acceptée ;
- `MODIFY` : quantité strictement réduite ;
- `REJECT` : aucun `ExecutionIntent` ;
- `HOLD` : assessment auditable sans intent.

---

## 13. MODIFY et réductions autorisées

La réduction est désactivée par défaut. Lorsqu'elle est activée, Risk peut borner une quantité par max notional, cash BUY disponible ou quantité SELL disponible.

Risk ne peut jamais :

- augmenter la quantité ;
- changer l'action ;
- changer le symbole ;
- transformer HOLD en ordre ;
- choisir une autre opportunité.

---

## 14. ExecutionIntent et Paper Broker

`ExecutionIntent` reste PAPER, BUY/SELL uniquement et n'est construit qu'après Risk.

Le Paper Broker reste l'unique composant qui exécute et mute le portefeuille :

```text
Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]
```

Il n'existe aucun appel Broker depuis le package Agent.

---

## 15. Frais, spread et slippage

`PaperExecutionCostModel` reste la source des coûts PAPER déterministes : `fee_rate`, `spread_bps`, `slippage_bps`.

Le Risk Engine utilise l'estimation commune pour la solvabilité BUY et le Paper Broker utilise la même primitive pour le fill. Tous les calculs financiers utilisent `Decimal`.

---

## 16. Portfolio PAPER et invariants SPOT

`PortfolioState` distingue `balances` et `positions`.

Le prompt demande à l'agent de ne pas vendre plus que détenu, mais ce contrôle n'est pas transformé en stratégie déterministe parallèle : Risk et le Paper Broker gardent leurs vérifications canoniques de quantité disponible.

---

## 17. Agressivité

Valeur entière de 1 à 10, validée dans `Settings` et `AgentInput`.

Le mapping exact reste à décider. Le prompt la traite comme contexte sans fabriquer de coefficient ou de policy chiffrée. Aucune agressivité ne contourne les invariants absolus ou Risk.

---

## 18. Objectif quotidien +4 %

Cible expérimentale, jamais une garantie.

Le prompt précise explicitement que la cible n'impose pas de trade. Le système ne doit pas générer une position uniquement parce que la performance du jour est inférieure à +4 %.

---

## 19. Identifiants, timestamps et audit

Un cycle complet pourra relier :

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
```

Les IDs et timestamps techniques Agent sont injectables pour les tests/replays.

---

## 20. Interfaces externes

Ports canoniques :

- `MarketDataSource.snapshot(symbol) -> MarketState` ;
- `MarketObservationSource.observation(symbol) -> MarketObservation` ;
- `LLMProvider.generate_decision(agent_input) -> DecisionCandidate` ;
- `Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]`.

Le Batch 07 ne modifie aucun de ces ports.

---

## 21. Tests Batch 07

La suite Agent vérifie notamment : BUY/SELL/HOLD valides, quantités absentes/non positives, HOLD avec quantité, action inconnue, JSON invalide, champs supplémentaires, absence de coercition, symbole divergent, corrélation `cycle_id`, UUID/timestamp injectables, rationale conservée, prompt versionné, Luna/Sol par la même classe, erreurs transport/refus/incomplétude et absence d'import Risk/Broker/Kraken/FastAPI.

Les tests HTTP utilisent `httpx.MockTransport` ; aucun réseau ni secret réel n'est requis.

---

## 22. Comparaison Luna / Sol

Une future comparaison devra utiliser des `MarketState`, `PortfolioState`, `RiskPolicy`, coûts PAPER, mapping d'agressivité et versions de prompt/contracts comparables. Le Batch 07 fournit seulement la compatibilité architecturale commune.

---

## 23. Conditions minimales avant discussion LIVE

**Hors périmètre pour l'instant.** Le Batch 07 ne change rien à la politique LIVE : aucune API Kraken privée, aucune clé de trading, aucune permission de retrait et aucune exécution réelle.
