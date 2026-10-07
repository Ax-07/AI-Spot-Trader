# 00 — État actuel

## Référence de reprise — Batch 51.7 intégré et validé

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub intégré vérifié        : e1396dfc0ce01d583ed9769e4a461c92c3782c9d
Commit GitHub                      : fix: regenerate invalid Ollama strategic outputs once
Batch 51.1 intégré                 : aeaf04f — feat: add local Ollama LLM provider
Batch 51.1.1 intégré               : 7e2ce28 — fix: harden causal Ollama decision contract
Batch 51.2 intégré                 : 36491d4 — feat: configure LLM provider per session
Batch 51.3 intégré                 : 5d24185 — feat: add live Ollama agent observability
Batch 51.4 intégré                 : 566e0ca — fix: restore automatic candle-close agent cycles
Batch 51.5 intégré                 : 6cbae55 — fix: ground strategic reasoning and sizing
Clôture documentaire 51.5         : 9fd8054 — docs: close batch 51.5 Ollama grounding validation
Batch 51.7 intégré                 : e1396df — fix: regenerate invalid Ollama strategic outputs once
```

## État intégré confirmé

Le même Agent stratégique utilise `OPENAI` ou `OLLAMA` derrière `StructuredDecisionClient`, sans fallback inter-provider. Le provider stratégique est configurable et persistant par Session/Campaign. Le Risk Engine déterministe conserve l'autorité finale ; aucune sortie LLM ne déclenche directement Broker/Kraken.

Depuis 51.4, CANDLE_CLOSE utilise la frontière UTC comme trigger du scheduler et délègue la causalité des données aux services du cycle via `history_as_of()`.

Depuis 51.5, le plan multi-marchés renforce le grounding factuel et la cohérence quantitative de `proposed_quantity` sans ajouter de moteur de sizing stratégique déterministe. Le contexte Ollama `8192` reste une recommandation opérationnelle locale validée pour `qwen3.5:9b` sur RTX 3060 Ti, pas une limite Risk.

Depuis 51.7, une sortie stratégique Ollama invalide et récupérable peut déclencher exactement une régénération corrective par le même Agent. La validation reste stricte : aucun JSON, signe de quantité, doublon, dépassement de cardinalité ou `thesis_update` n'est réparé par le backend. Une seconde sortie invalide reste `FAILED` avant Risk/Broker.

Les erreurs réseau/HTTP Ollama continuent d'utiliser exclusivement le retry transport existant. Les violations internes/causales telles qu'une horloge invalide ne déclenchent aucun retry contractuel. OpenAI conserve un seul appel stratégique par défaut et ne reçoit aucun coût supplémentaire du Batch 51.7.

Détail : `docs/51_7_ROBUSTESSE_STRUCTURED_OUTPUT_OLLAMA.md`.

## Validation 51.7 confirmée par l'opérateur

```text
Tests ciblés 51.7 + contrats associés        : PASS — 52 tests
Suite backend complète `pytest -q`            : PASS — 100 %
`git diff --check`                            : PASS
```

Les seuls avertissements observés sont des dépréciations externes Starlette/httpx et anyio ainsi que les messages Windows LF → CRLF ; aucune erreur de test ou de whitespace n'a été remontée.

## Invariants inchangés

Un seul Agent IA stratégique ; l'IA conserve la décision stratégique ; Risk Engine déterministe avec autorité finale ; aucune sortie LLM directement vers Broker/Kraken ; PAPER pour les premiers usages ; BUY / SELL / HOLD ; aucun fallback inter-provider silencieux ; grounding causal conservé ; aucune réparation déterministe de stratégie ; aucune boucle de retry contractuel non bornée ; aucune chaîne de pensée détaillée exposée ; aucun secret dans prompts, logs ou fichiers versionnés ; frontend non requis pour maintenir le moteur en marche.
