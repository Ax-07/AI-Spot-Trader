# 00 — État actuel

## Référence de reprise — Batch 51.7 préparé, non intégré

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub intégré vérifié        : 9fd8054213c2c6c7eb2e8429f288b1443ef70b94
Commit GitHub                      : docs: close batch 51.5 Ollama grounding validation
Batch 51.1 intégré                 : aeaf04f — feat: add local Ollama LLM provider
Batch 51.1.1 intégré               : 7e2ce28 — fix: harden causal Ollama decision contract
Batch 51.2 intégré                 : 36491d4 — feat: configure LLM provider per session
Batch 51.3 intégré                 : 5d24185 — feat: add live Ollama agent observability
Batch 51.4 intégré                 : 566e0ca — fix: restore automatic candle-close agent cycles
Batch 51.5 intégré                 : 6cbae55 — fix: ground strategic reasoning and sizing
Batch 51.7                         : patch préparé — non intégré
```

Le HEAD `6cbae55` encore présent dans cette mémoire courte avant le Batch 51.7 était obsolète : `9fd8054` est le HEAD GitHub `main` réellement audité. Le commit `9fd8054` clôt documentairement la validation 51.5 et ne modifie pas le runtime stratégique.

## État intégré confirmé

Le même Agent stratégique utilise `OPENAI` ou `OLLAMA` derrière `StructuredDecisionClient`, sans fallback inter-provider. Le provider stratégique est configurable et persistant par Session/Campaign. Le Risk Engine déterministe conserve l'autorité finale ; aucune sortie LLM ne déclenche directement Broker/Kraken.

Depuis 51.4, CANDLE_CLOSE utilise la frontière UTC comme trigger du scheduler et délègue la causalité des données aux services du cycle via `history_as_of()`.

Depuis 51.5, le plan multi-marchés renforce le grounding factuel et la cohérence quantitative de `proposed_quantity` sans ajouter de moteur de sizing stratégique déterministe. Le contexte Ollama `8192` reste une recommandation opérationnelle locale validée pour `qwen3.5:9b` sur RTX 3060 Ti, pas une limite Risk.

## Batch 51.7 — patch préparé

Le patch ajoute une seule régénération corrective pour les sorties stratégiques Ollama invalides et récupérables. La validation reste stricte : aucun JSON, signe de quantité, doublon, dépassement de cardinalité ou `thesis_update` n'est réparé par le backend. Le même Agent Ollama régénère intégralement le plan avec un feedback contractuel minimal ; une seconde sortie invalide reste `FAILED` avant Risk/Broker.

Les erreurs réseau/HTTP Ollama continuent d'utiliser exclusivement le retry transport existant. Les violations internes/causales telles qu'une horloge invalide ne déclenchent aucun retry contractuel. OpenAI conserve un seul appel stratégique par défaut et ne reçoit aucun coût supplémentaire du Batch 51.7.

Détail : `docs/51_7_ROBUSTESSE_STRUCTURED_OUTPUT_OLLAMA.md`.

## Validation du patch 51.7 dans l'environnement de livraison

```text
python -m py_compile fichiers Python modifiés/créés          : PASS
harness isolé classification/régénération                    : PASS
contrôle lignes > 100 / espaces finaux                       : PASS
```

La suite backend complète, les tests repository ciblés et `git diff --check` sur le vrai checkout restent à exécuter localement après extraction.

## Invariants inchangés

Un seul Agent IA stratégique ; l'IA conserve la décision stratégique ; Risk Engine déterministe avec autorité finale ; aucune sortie LLM directement vers Broker/Kraken ; PAPER pour les premiers usages ; BUY / SELL / HOLD ; aucun fallback inter-provider silencieux ; grounding causal conservé ; aucune réparation déterministe de stratégie ; aucune chaîne de pensée détaillée exposée ; aucun secret dans prompts, logs ou fichiers versionnés ; frontend non requis pour maintenir le moteur en marche.
