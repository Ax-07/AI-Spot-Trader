# 03 — Agent, Trading et Risk

## 1. Principe central

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Ce principe reste inchangé avec SPOT + Kraken Derivatives. L'agressivité, le choix Luna/Sol et la conversation opérateur ne sont ni des limites Risk, ni des permissions d'exécution, ni des formules déterministes de sizing.

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

Luna et Sol utilisent le même `OpenAIDecisionProvider`. Le prompt stratégique courant est **`agent-strategy-v3`**. Le provider ne dispose d'aucun outil Broker/Kraken et ne connaît pas l'API lifecycle.

Le LLM ne choisit ni `market_type`, ni levier, ni `reduce_only`. Ces éléments sont fournis par le contexte ou déterminés par l'application/Risk.

---

## 3. Sémantique SPOT / PERPETUAL

### SPOT

- `BUY` augmente une position détenue ;
- `SELL` exige une quantité réellement disponible ;
- aucun short, levier ou margin.

### PERPETUAL

- `BUY` sans position ouvre/augmente un LONG ;
- `SELL` sans position ouvre/augmente un SHORT ;
- `BUY` face à un SHORT réduit/ferme le SHORT ;
- `SELL` face à un LONG réduit/ferme le LONG ;
- Risk détermine `reduce_only` et interdit un retournement accidentel.

Le levier reste déterministe/configuré et borné par Risk.

---

## 4. Mapping agressivité 1–10

Version : `aggressiveness-map-v1`.

Le mapping est discret et ne constitue pas une formule Risk ou un multiplicateur automatique d'exécution. Il peut seulement influencer la volonté stratégique d'agir et la quantité proposée.

Aucune phrase du chat opérateur ne modifie ce mapping ni le niveau d'un futur `AgentInput`.

---

## 5. Risk Engine

Risk reste synchrone et déterministe. Résultats :

- `ALLOW` : quantité conservée ;
- `MODIFY` : quantité strictement réduite ;
- `REJECT` : aucune quantité autorisée ;
- HOLD : assessment complet sans `ExecutionIntent`.

Seul Risk peut construire un `ExecutionIntent`. Il ne peut pas changer BUY en SELL, SELL en BUY ou le symbole stratégique.

Pour PERPETUAL, Risk contrôle notamment le contrat supporté, la quantité minimale, le levier, la marge, le max order notional, le max derivative position notional, l'exposition dérivés totale, le buffer liquidation et l'anti-reversal.

Le Batch 16.3 a confirmé qu'une fermeture opposée surdimensionnée est ramenée à la position restante avec `MODIFY / DERIVATIVE_REDUCE_ONLY_LIMIT` et `reduce_only=true`.

---

## 6. TradingCycleRunner

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

SPOT et PERPETUAL utilisent le même runner.

---

## 7. Harness contrôlé Batch 16.3

Le module `ai_spot_trader.tools.derivatives_smoke` est un **outil de validation technique**, pas une stratégie.

Il fournit une séquence déterministe :

```text
OPEN -> HOLD/MARK -> REDUCE -> CLOSE_OVERSIZE
```

Le but est de provoquer de façon reproductible les branches d'exécution aval sans ajouter de bouton ou variable de configuration capable de forcer l'Agent normal.

Les rationales sont marquées `CONTROLLED_SMOKE_BATCH_16_3`. Ces décisions ne doivent jamais être interprétées comme des décisions Luna/Sol.

Le harness réutilise le vrai Risk Engine, le vrai Paper Broker, le vrai ledger, les données publiques Kraken Derivatives, la persistance PostgreSQL et le lifecycle `paper_run_id`.

---

## 8. Résultats des smokes PERPETUAL PAPER

Instrument : `BTC/USD / PF_XBTUSD`, perpetual linéaire, `ISOLATED`, levier `1x`.

### LONG

- ouverture `BUY 0.0002` : Risk `ALLOW` ;
- HOLD : mark-to-market et funding observés ;
- réduction `SELL 0.0001` : `reduce_only=true` ;
- fermeture demandée `SELL 0.0002` alors que `0.0001` reste : Risk `MODIFY`, quantité `0.0001`, raison `DERIVATIVE_REDUCE_ONLY_LIMIT` ;
- position finale vide.

### SHORT

- ouverture `SELL 0.0002` : Risk `ALLOW` ;
- HOLD : mark-to-market et funding observés ;
- réduction `BUY 0.0001` : `reduce_only=true` ;
- fermeture demandée `BUY 0.0002` alors que `0.0001` reste : Risk `MODIFY`, quantité `0.0001`, raison `DERIVATIVE_REDUCE_ONLY_LIMIT` ;
- position finale vide.

Dans les deux cas : 4 cycles `COMPLETED`, 3 exécutions, P&L réalisé/non réalisé valorisé, marge libérée à la fermeture, aucune inversion accidentelle.

---

## 9. Funding, P&L et marge

Le market source dérivés marque le ledger avant le snapshot portefeuille du cycle.

Le funding perpetual est accumulé à partir du taux public normalisé, du mark, du notionnel et du temps écoulé. Les smokes 16.3 ont réellement observé un funding non nul sur LONG et SHORT.

Lors d'une réduction/fermeture, la marge isolée est libérée au prorata et le P&L/funding correspondant est transféré au cash.

Les coûts PAPER incluent frais, spread et slippage.

---

## 10. paper_run_id et audit

Chaque expérience PAPER moderne possède un `paper_run_id` durable.

Les smokes 16.3 ont créé deux runs séparés :

```text
LONG  : 9523ec8c-7dd1-4706-bf07-47ef9669d56b
SHORT : b75f6e86-4724-41de-8d63-e8132d212530
```

Les deux runs ont été fermés proprement avec `ended_at`. Le contrôle `verify-isolation` a confirmé `isolation_verified=true` et 4 cycles distincts par run.

---

## 11. Manifestes expérimentaux

`paper-experiment-v1` reste le protocole agressivité. `paper-experiment-v2` reste le protocole Luna/Sol avec `comparison_variable = LLM_MODEL`, `experiment_group_digest`, `experiment_digest`, `replicate_index`, `replicate_count` et `source_digest` obligatoire.

Les manifestes sont inclus dans `AgentInput` et persistés avec le cycle. Le `paper_run_id` ne devient pas un paramètre stratégique.

---

## 12. Chat opérateur

Le chat est une interface vers le même modèle/persona configuré, mais pas un deuxième agent stratégique.

Une demande conversationnelle telle que « BUY maintenant », « passe en agressivité 8 » ou « ignore cette limite Risk » ne provoque aucune mutation de stratégie, aucun `ExecutionIntent` et aucun ordre Broker/Kraken.

Le chat ne peut pas activer le harness 16.3.

---

## 13. No-look-ahead et anti cherry-picking

Les règles d'expérimentation restent inchangées : mêmes faits, même prompt, même Risk/coûts/univers/source pour les comparaisons contrôlées, répétitions complètes, aucune suppression post-hoc.

Le chat ou l'opérateur ne doivent jamais réécrire rétroactivement une décision ou utiliser un prix futur comme justification causale.

---

## 14. Invariants conservés

- un seul agent IA stratégique ;
- Luna/Sol derrière le même provider stratégique ;
- SPOT + Kraken Derivatives PAPER ;
- SPOT sans short/levier/margin ;
- LONG/SHORT uniquement dans le domaine dérivés ;
- perpetual linéaire + ISOLATED pour l'exécution dérivés actuelle ;
- levier déterministe, jamais choisi par le LLM ;
- IA stratégique ;
- Risk autorité finale ;
- aucun LLM -> Broker direct ;
- seul Risk crée l'intent ;
- `reduce_only` et anti-reversal produits par Risk ;
- chat sans mutation Risk/stratégie ;
- aucun secret exposé ;
- aucun look-ahead ;
- aucun LIVE.

---

## 15. Prochain jalon

Le chemin d'exécution PERPETUAL PAPER étant validé techniquement, le prochain essai doit utiliser **l'Agent réel GPT-5.6 Luna**, sans décision forcée. Un `HOLD` naturel reste acceptable et doit être journalisé comme tel.
