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

Luna et Sol utilisent le même `OpenAIDecisionProvider`. Le prompt stratégique courant est **`agent-strategy-v4`**. Les instructions humaines sont en français, les valeurs techniques `BUY`/`SELL`/`HOLD` et `SPOT`/`PERPETUAL`/`FUTURE` restent inchangées, et `rationale` doit être rédigé en français. Le provider ne dispose d'aucun outil Broker/Kraken et ne connaît pas l'API lifecycle.

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

## 4. Contexte marché transmis à l'Agent

`MarketState.context` est un contexte **descriptif et déterministe**, jamais un signal de trading. Le `MarketStateBuilder` calcule actuellement des fenêtres 5 min / 30 min avec fraîcheur, prix de début/fin, min/max, range, rendement et volatilité réalisée.

Pour SPOT, ce contexte est construit à partir de l'historique OHLC public Kraken et du ticker courant.

Le Batch 16.5 applique le même pipeline à PERPETUAL à partir des bougies publiques Kraken Futures Charts `mark` en `1m`. Les bougies sont normalisées en `MarketObservation` puis passées au même builder ; aucune logique statistique parallèle n'est créée.

Règles causales :

- le ticker mark courant fournit `last_price` et la fraîcheur ;
- les statistiques utilisent uniquement des bougies clôturées strictement avant le timestamp du ticker ;
- une bougie en cours ou future n'est jamais incluse ;
- le `statistics_as_of` reste ancré sur la dernière clôture historique réellement disponible ;
- `DerivativeMarketContext` conserve en parallèle instrument, mark, index et funding courant.

Ces observations peuvent éclairer Luna, mais elles ne produisent jamais elles-mêmes BUY, SELL ou HOLD.

Validation réelle Batch 16.5 : le cycle `c097f3fc-4954-4985-a364-f6ffe99b24e6` du run `8bbfe6a5-a5d5-4c32-96dc-eb9c5e4113d2` est `COMPLETED` avec un vrai `AgentInput.market_state.context` non nul. Les fenêtres 5 min et 30 min étaient complètes, avec 6 et 31 observations, et le contexte dérivé mark/index/funding restait présent.

---

## 5. Mapping agressivité 1–10

Version : `aggressiveness-map-v1`.

Le mapping est discret et ne constitue pas une formule Risk ou un multiplicateur automatique d'exécution. Il peut seulement influencer la volonté stratégique d'agir et la quantité proposée.

Aucune phrase du chat opérateur ne modifie ce mapping ni le niveau d'un futur `AgentInput`.

---

## 6. Risk Engine

Risk reste synchrone et déterministe. Résultats :

- `ALLOW` : quantité conservée ;
- `MODIFY` : quantité strictement réduite ;
- `REJECT` : aucune quantité autorisée ;
- HOLD : assessment complet sans `ExecutionIntent`.

Seul Risk peut construire un `ExecutionIntent`. Il ne peut pas changer BUY en SELL, SELL en BUY ou le symbole stratégique.

Pour PERPETUAL, Risk contrôle notamment le contrat supporté, la quantité minimale, le levier, la marge, le max order notional, le max derivative position notional, l'exposition dérivés totale, le buffer liquidation et l'anti-reversal.

Le Batch 16.3 a confirmé qu'une fermeture opposée surdimensionnée est ramenée à la position restante avec `MODIFY / DERIVATIVE_REDUCE_ONLY_LIMIT` et `reduce_only=true`.

---

## 7. TradingCycleRunner

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

## 8. Harness contrôlé Batch 16.3

Le module `ai_spot_trader.tools.derivatives_smoke` est un **outil de validation technique**, pas une stratégie.

Il fournit une séquence déterministe :

```text
OPEN -> HOLD/MARK -> REDUCE -> CLOSE_OVERSIZE
```

Le but est de provoquer de façon reproductible les branches d'exécution aval sans ajouter de bouton ou variable de configuration capable de forcer l'Agent normal.

Les rationales sont marquées `CONTROLLED_SMOKE_BATCH_16_3`. Ces décisions ne doivent jamais être interprétées comme des décisions Luna/Sol.

Le harness réutilise le vrai Risk Engine, le vrai Paper Broker, le vrai ledger, les données publiques Kraken Derivatives, la persistance PostgreSQL et le lifecycle `paper_run_id`.

---

## 9. Résultats des smokes PERPETUAL PAPER

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

## 10. Premier run Agent réel — Batch 16.4

Le premier run GPT-5.6 Luna réel en PERPETUAL PAPER a été exécuté via la composition normale, sans harness et sans décision forcée.

`paper_run_id = 36fe73e0-f52f-4e27-995b-c5c848f46da2`, `BTC/USD / PF_XBTUSD`, `ISOLATED`, levier `1x`, agressivité `2`, capital `1000 USD` :

- 4 cycles `COMPLETED` ;
- 4 décisions Luna `HOLD` ;
- 0 `FAILED` ;
- 4 Risk `ALLOW / HOLD_NO_EXECUTION` ;
- 0 `ExecutionIntent`, fill ou trade ;
- exposition finale `0`, P&L `0`, portefeuille final `1000 USD` ;
- run clôturé durablement avec `ended_at`.

L'audit du vrai `AgentInput` a montré `market_state.context = null`. Les rationales Luna indiquaient un manque de contexte directionnel ; avec agressivité `2`, les quatre HOLD sont cohérents et ne constituent pas un échec du pipeline.

---

## 11. Validation comportementale Luna — Batch 16.6

Le run final du Batch 16.6 utilise la composition normale, GPT-5.6 Luna et le contexte PERPETUAL enrichi, sans harness, sans décision forcée, sans modification du prompt et sans augmentation artificielle de l'agressivité.

Run : `c9443243-57ca-43de-9356-adc1e6fe3226`, `BTC/USD / PF_XBTUSD`, `ISOLATED`, levier `1x`, agressivité `2`, capital `1000 USD`.

Résultats :

- 8 cycles `COMPLETED`, 0 `FAILED` ;
- `market_state.context` non nul sur les 8 cycles ;
- fenêtre 5 min complète sur les 8 cycles, 6 observations ;
- fenêtre 30 min complète sur les 8 cycles, 31 observations ;
- fraîcheur comprise entre `1.021449 s` et `1.110151 s` ;
- vérification causale `true` sur les 8 cycles : aucune dernière observation statistique n'est égale ou postérieure au timestamp Derivatives courant ;
- rendements 5m observés allant de `0.001382112552274408121158548` à `0.004277054732762370494098960` ;
- rendements 30m observés allant de `0.000595245832287674415770980` à `0.004189253453471024976633082` ;
- funding courant positif sur les 8 cycles affichés ;
- 8 décisions naturelles `HOLD`, sans quantité proposée ;
- 8 Risk `ALLOW`, aucun `ExecutionIntent`, fill ou trade.

Les rationales Luna restent alignées avec les faits présents dans l'`AgentInput` : posture très conservatrice liée à l'agressivité `2`, rendements 5m/30m positifs mais jugés insuffisants, absence de position existante et, lorsqu'il est cité, funding positif. Aucun indicateur technique, news, carnet d'ordres ou autre donnée absente n'a été observé dans ces rationales.

Le run n'a produit aucun BUY ou SELL naturel. Ce résultat est conservé tel quel : il ne justifie ni changement de prompt, ni hausse artificielle de l'agressivité, ni règle déterministe destinée à provoquer un trade.

Risk conserve bien l'autorité finale : chaque HOLD a été évalué `ALLOW` sans intent, conformément au contrat canonique.

---

## 12. Funding, P&L et marge

Le market source dérivés marque le ledger avant le snapshot portefeuille du cycle.

Le funding perpetual est accumulé à partir du taux public normalisé, du mark, du notionnel et du temps écoulé. Les smokes 16.3 ont réellement observé un funding non nul sur LONG et SHORT.

Lors d'une réduction/fermeture, la marge isolée est libérée au prorata et le P&L/funding correspondant est transféré au cash.

Les coûts PAPER incluent frais, spread et slippage.

Sur le run 16.6, aucune position n'ayant été ouverte : capital initial/final `1000 USD`, P&L brut/net `0`, frais `0`, spread `0`, slippage `0`, funding P&L `0`, exposition `0`, drawdown `0`, `trade_count=0`.

---

## 13. paper_run_id et audit

Chaque expérience PAPER moderne possède un `paper_run_id` durable.

Les smokes 16.3 ont créé deux runs séparés :

```text
LONG  : 9523ec8c-7dd1-4706-bf07-47ef9669d56b
SHORT : b75f6e86-4724-41de-8d63-e8132d212530
```

Les deux runs ont été fermés proprement avec `ended_at`. Le contrôle `verify-isolation` a confirmé `isolation_verified=true` et 4 cycles distincts par run.

Le run Luna 16.4 `36fe73e0-f52f-4e27-995b-c5c848f46da2` a lui aussi été clôturé durablement.

Pour le Batch 16.6, le run propre `c9443243-57ca-43de-9356-adc1e6fe3226` contient exactement 8 cycles et n'a aucun `cycle_id` commun avec le run de référence Batch 16.5. Il a été clôturé avec `ended_at = 2026-09-22 08:41:03.924351 UTC`.

Un essai précédent a réutilisé le run Batch 16.5 faute de redémarrage complet du backend. Les lignes créées restent dans l'audit durable et ne sont pas supprimées ; elles ne sont pas utilisées comme preuve de l'isolation du Batch 16.6.

---

## 14. Manifestes expérimentaux

`paper-experiment-v1` reste le protocole agressivité. `paper-experiment-v2` reste le protocole Luna/Sol avec `comparison_variable = LLM_MODEL`, `experiment_group_digest`, `experiment_digest`, `replicate_index`, `replicate_count` et `source_digest` obligatoire.

Les manifestes sont inclus dans `AgentInput` et persistés avec le cycle. Le `paper_run_id` ne devient pas un paramètre stratégique.

---

## 15. Chat opérateur

Le chat est une interface vers le même modèle/persona configuré, mais pas un deuxième agent stratégique.

Une demande conversationnelle telle que « BUY maintenant », « passe en agressivité 8 » ou « ignore cette limite Risk » ne provoque aucune mutation de stratégie, aucun `ExecutionIntent` et aucun ordre Broker/Kraken.

Le chat ne peut pas activer le harness 16.3.

---

## 16. No-look-ahead et anti cherry-picking

Les règles d'expérimentation restent inchangées : mêmes faits, même prompt, même Risk/coûts/univers/source pour les comparaisons contrôlées, répétitions complètes, aucune suppression post-hoc.

Le contexte PERPETUAL respecte la même causalité : une bougie mark n'est statistiquement visible qu'après sa clôture. Le timestamp du ticker courant borne explicitement l'historique admissible.

Le Batch 16.6 conserve les 8 HOLD naturels et l'essai initial non isolé dans l'audit au lieu de sélectionner uniquement des cycles favorables. Le run propre final a été évalué intégralement.

Le chat ou l'opérateur ne doivent jamais réécrire rétroactivement une décision ou utiliser un prix futur comme justification causale.

---

## 17. Invariants conservés

- un seul agent IA stratégique ;
- Luna/Sol derrière le même provider stratégique ;
- SPOT + Kraken Derivatives PAPER ;
- SPOT sans short/levier/margin ;
- LONG/SHORT uniquement dans le domaine dérivés ;
- perpetual linéaire + ISOLATED pour l'exécution dérivés actuelle ;
- levier déterministe, jamais choisi par le LLM ;
- contexte marché déterministe descriptif, jamais signal d'action ;
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

## 18. Prochain jalon

Le Batch 16.6 confirme le fonctionnement naturel de GPT-5.6 Luna avec le contexte PERPETUAL enrichi sur un run isolé de 8 cycles, sans changement de code. Aucun BUY/SELL n'a été observé et aucun mécanisme ne doit être ajouté pour en provoquer un. Toute nouvelle expérimentation, robustesse Derivatives ou enrichissement de données doit rester un batch distinct et être justifié par un besoin mesuré.

La localisation `agent-strategy-v4` est un changement de langue du contrat explicatif ; elle ne modifie ni le schéma structuré, ni les responsabilités Agent/Risk, ni les règles d'exécution.
