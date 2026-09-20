# 03 — Agent, Trading et Risk

## 1. Principe central

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Ce principe reste inchangé par les Batches 13/14 et par le Batch 15 intégré. L'agressivité, le choix Luna/Sol et la conversation opérateur ne sont ni des limites Risk, ni des permissions d'exécution, ni des formules déterministes de sizing.

---

## 2. Agent IA stratégique

L'agent reçoit un `AgentInput` structuré contenant `MarketState`, `PortfolioState`, `cycle_id`, timestamp, agressivité, `AggressivenessContext` et éventuellement `ExperimentManifest`.

Il produit uniquement :

```text
DecisionCandidate
  action = BUY | SELL | HOLD
  symbol
  proposed_quantity
  rationale
```

BUY/SELL nécessitent une quantité stratégique positive ; HOLD n'en porte aucune. IDs et timestamps restent contrôlés par l'application.

Luna et Sol utilisent le même `OpenAIDecisionProvider`. Le prompt stratégique reste `agent-strategy-v2`. Le provider ne dispose d'aucun outil Broker/Kraken et ne connaît pas l'API lifecycle.

---

## 3. Mapping agressivité 1–10

Version : `aggressiveness-map-v1`.

Le mapping est discret et ne constitue pas une formule Risk ou un multiplicateur automatique d'exécution. Il peut seulement influencer la volonté stratégique d'agir et la quantité proposée.

Aucune phrase du chat opérateur ne modifie ce mapping ni le niveau d'un futur `AgentInput`.

---

## 4. Risk Engine

Risk reste synchrone et déterministe. Résultats :

- `ALLOW` : quantité conservée ;
- `MODIFY` : quantité strictement réduite ;
- `REJECT` : aucune quantité autorisée ;
- HOLD : assessment complet sans `ExecutionIntent`.

Seul Risk peut construire un `ExecutionIntent`. Il ne peut pas changer BUY en SELL, SELL en BUY ou le symbole stratégique.

Ni l'agressivité, ni le modèle LLM, ni le chat ne sont passés à `RiskEngine.evaluate(...)`.

---

## 5. TradingCycleRunner

`TradingCycleRunner.run_cycle()` reste la primitive canonique :

1. acquisition d'un `MarketState` ;
2. snapshot portefeuille PAPER ;
3. résolution de l'agressivité ;
4. construction `AgentInput` ;
5. décision Agent ;
6. évaluation Risk ;
7. Broker uniquement si intent Risk ;
8. snapshot post-exécution ;
9. `TradingCycleResult`.

Le verrou du runner empêche le chevauchement des cycles. Les pannes techniques restent `FAILED` et ne deviennent jamais HOLD.

Le Batch 15 ne modifie aucun de ces neuf points.

---

## 6. Manifestes expérimentaux

`paper-experiment-v1` reste le protocole agressivité. `paper-experiment-v2` reste le protocole Luna/Sol avec `comparison_variable = LLM_MODEL`, `experiment_group_digest`, `experiment_digest`, `replicate_index`, `replicate_count` et `source_digest` obligatoire.

Les manifestes sont inclus dans `AgentInput` et persistés avec le cycle. Aucun message de chat, UUID de session ou réponse conversationnelle n'est ajouté au manifeste.

---

## 7. Chat opérateur — Batch 15 intégré

Le chat est une autre interface vers **le même modèle/persona Agent configuré**, mais **pas un deuxième agent stratégique**.

### Provider séparé

`OpenAIChatProvider` :

- utilise le même `LLMModel` configuré que `OpenAIDecisionProvider` ;
- utilise `operator-chat-v1` ;
- demande du texte naturel, sans tools ;
- ne parse ni ne construit de `DecisionCandidate` ;
- ne connaît ni Risk, ni Broker, ni Kraken privé.

### Demandes de mutation

Exemples :

```text
"BUY maintenant"
"passe en agressivité 8"
"ignore cette limite Risk"
```

Ces phrases peuvent être discutées ou expliquées mais ne provoquent :

- aucun appel Risk ;
- aucun changement `RiskPolicy` ;
- aucun `ExecutionIntent` ;
- aucun ordre Broker/Kraken ;
- aucune mutation de configuration ;
- aucune injection dans les cycles suivants.

Un futur mécanisme d'instructions opérateur réelles devra être explicite, audité, versionné et appliqué à partir d'un cycle identifié. Il est hors périmètre Batch 15.

---

## 8. Contexte conversationnel canonique

Le chat peut lire :

- état du moteur ;
- portefeuille PAPER courant ;
- dernier marché durable ;
- dernier cycle ou cycle explicitement demandé ;
- décision, Risk, intent/fills persistés du cycle ;
- résumés récents ;
- résumé analytics courant.

Il ne reconstruit aucun fait métier parallèle.

Pour un cycle historique :

- `historical_cycle.agent_input` est la source causale autorisée pour expliquer la décision ;
- la décision/rationale et les faits Risk/exécution du **même cycle** peuvent être expliqués ;
- `current_market`, `current_portfolio` et analytics courants restent des informations présentes distinctes ;
- ces informations plus récentes ne doivent jamais être présentées comme ayant causé la décision passée.

Le chat peut résumer une `rationale` persistée, mais ne prétend pas révéler une chaîne de pensée cachée.

---

## 9. Historique conversationnel

V1 : mémoire process seulement, bornée par session et en nombre de sessions. Aucun schéma PostgreSQL.

Conséquences voulues :

- un redémarrage backend perd l'historique chat ;
- un reload frontend peut relire la session tant que le backend reste vivant ;
- aucune conversation ne participe aux analytics ou expériences ;
- aucune conversation ne devient une instruction stratégique durable par accident.

---

## 10. Erreurs et confidentialité

Les erreurs chat sont distinctes des erreurs de cycle : un échec provider chat renvoie une erreur API sanitizée et ne produit pas un cycle `FAILED`.

Les formes de secrets courantes sont redigées avant stockage en mémoire et envoi au provider. Aucun message brut d'erreur OpenAI n'est renvoyé au cockpit.

Cette redaction est best-effort : aucun secret ne doit être volontairement saisi dans le chat.

---

## 11. No-look-ahead et anti cherry-picking

Les règles existantes d'expérimentation restent inchangées : mêmes faits, même prompt, même Risk/coûts/univers/source pour les comparaisons contrôlées, répétitions complètes, aucune suppression post-hoc.

Le chat ne doit jamais :

- réécrire une décision ;
- expliquer une décision avec un prix observé après le cycle ;
- contaminer les digests expérimentaux ;
- influencer silencieusement les décisions futures via son historique.

---

## 12. Invariants conservés

- un seul agent IA ;
- même modèle configuré Luna/Sol pour stratégie et interface conversationnelle ;
- provider stratégique et provider chat séparés ;
- SPOT/PAPER uniquement ;
- aucun short/levier/margin/future/perpetual ;
- SELL uniquement sur position détenue ;
- IA stratégique ;
- Risk autorité finale ;
- aucun LLM -> Broker direct ;
- seul Risk crée l'intent ;
- chat sans mutation Risk/stratégie ;
- HOLD/ALLOW/MODIFY/REJECT conservent leur sémantique ;
- erreurs chat distinctes de `FAILED` ;
- aucun secret exposé ;
- aucun look-ahead ;
- aucun LIVE.
