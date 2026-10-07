# 00 — État actuel

## Référence de reprise — Batch 51.5 intégré et validé

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub intégré vérifié        : 6cbae5535fbc480b73ffa06cd876ab48be22094d
Commit GitHub                      : fix: ground strategic reasoning and sizing
Batch 51.1 intégré                 : aeaf04f — feat: add local Ollama LLM provider
Batch 51.1.1 intégré               : 7e2ce28 — fix: harden causal Ollama decision contract
Batch 51.2 intégré                 : 36491d4 — feat: configure LLM provider per session
Batch 51.3 intégré                 : 5d24185 — feat: add live Ollama agent observability
Batch 51.4 intégré                 : 566e0ca — fix: restore automatic candle-close agent cycles
Batch 51.5 intégré                 : 6cbae55 — fix: ground strategic reasoning and sizing
```

Le HEAD `e0ddeba` mentionné avant intégration de 51.5 est obsolète : `6cbae55` est désormais le HEAD GitHub intégré audité. Son parent direct est `e0ddeba3d5170a53d0796f0345af1c5912ee8259`.

## État intégré confirmé

Le même Agent stratégique utilise `OPENAI` ou `OLLAMA` derrière `StructuredDecisionClient`, sans fallback inter-provider. Le provider stratégique est configurable et persistant par Session/Campaign. Le Risk Engine déterministe conserve l'autorité finale ; aucune sortie LLM ne déclenche directement Broker/Kraken.

Depuis 51.4, CANDLE_CLOSE utilise la frontière UTC comme trigger du scheduler et délègue la causalité des données aux services du cycle via `history_as_of()`.

Depuis 51.5, le plan multi-marchés renforce le grounding factuel et la cohérence quantitative de `proposed_quantity` sans ajouter de moteur de sizing stratégique déterministe. Une rationale/thèse ne doit présenter comme faits que des éléments présents dans l'input causal ou issus d'un tool read-only du même appel. Les références `SIZING_FACTS` restent descriptives ; elles ne sont ni des cibles d'allocation ni des limites Risk.

## Validation 51.5 confirmée par l'opérateur

```text
Tests ciblés 51.5 + contrats associés        : PASS — 39 tests
Suite backend complète `pytest -q`            : PASS — 100 %
Smoke Ollama grounding factuel qwen3.5:9b     : PASS — 15.11 s
Smoke Ollama sizing/structured output         : PASS — 28.57 s
Fail-closed sorties JSON/contractuelles        : PASS observé
```

Le smoke sizing a confirmé qu'avec `10 000 EUR`, une cible arithmétique de `1 %` et `BTC/EUR = 98 250`, la quantité `0.0010178117048346 BTC` correspond pratiquement à `100 EUR`, soit `1 %` du cash. Le BUY était imposé uniquement pour tester le contrat ; aucun signal de marché absent n'a été présenté comme observé.

Pour `qwen3.5:9b` sur la machine locale testée, le contexte Ollama recommandé est `8192`. Les essais à `4096` ont produit plusieurs JSON tronqués/incomplets ; `8192` a permis les smokes validés. Cette valeur est une recommandation opérationnelle locale, pas une règle universelle ni une limite du Risk Engine. `ollama ps` a observé environ `12 % CPU / 88 % GPU` sur RTX 3060 Ti.

Détail : `docs/51_5_GROUNDING_SIZING_OLLAMA.md`.

## Invariants inchangés

Un seul Agent IA stratégique ; l'IA conserve la décision stratégique ; Risk Engine déterministe avec autorité finale ; aucune sortie LLM directement vers Broker/Kraken ; PAPER pour les premiers usages ; BUY / SELL / HOLD ; aucun fait inventé depuis la mémoire générale du modèle ; aucune chaîne de pensée détaillée exposée ; aucun secret dans prompts, logs ou fichiers versionnés ; frontend non requis pour maintenir le moteur en marche.
