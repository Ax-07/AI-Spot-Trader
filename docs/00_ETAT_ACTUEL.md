# 00 — État actuel

## Référence de reprise — Batch 51.5 préparé, non intégré

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub intégré vérifié        : e0ddeba3d5170a53d0796f0345af1c5912ee8259
Commit GitHub                      : docs: sync documentation after batch 51.4 integration
Batch 51.1 intégré                 : aeaf04f — feat: add local Ollama LLM provider
Batch 51.1.1 intégré               : 7e2ce28 — fix: harden causal Ollama decision contract
Batch 51.2 intégré                 : 36491d4 — feat: configure LLM provider per session
Batch 51.3 intégré                 : 5d24185 — feat: add live Ollama agent observability
Batch 51.4 intégré                 : 566e0ca — fix: restore automatic candle-close agent cycles
Batch 51.5                         : patch préparé — non intégré
```

L'ancienne référence `566e0ca` comme HEAD courant était obsolète : `e0ddeba` est le HEAD GitHub réellement audité au démarrage du Batch 51.5. Le commit `e0ddeba` est une synchronisation documentaire post-51.4 et ne change pas le code runtime de 51.4.

## État intégré confirmé

Le même Agent stratégique utilise `OPENAI` ou `OLLAMA` derrière `StructuredDecisionClient`, sans fallback inter-provider. Le provider stratégique est configurable et persistant par Session/Campaign. Ollama réel a été validé avec `qwen3.5:9b` ; les logs 51.3 exposent le départ, le succès/échec et la latence d'un appel ainsi que le résumé BUY/SELL/HOLD du plan validé, sans prompt, réponse brute, `thinking` ou secret.

Le moteur PAPER supporte SPOT et PERPETUAL selon l'univers intégré. Le Market Attention Radar reste déterministe/informatif ; le même Agent conserve BUY/SELL/HOLD ; le Risk Engine garde l'autorité finale. Le frontend reste un cockpit et n'est pas requis pour maintenir le moteur en marche.

Depuis 51.4, CANDLE_CLOSE utilise la frontière UTC comme trigger du scheduler. La causalité des données reste appliquée dans les services consommateurs via `history_as_of()` ; le scheduler ne pré-résout plus Radar et ne bloque plus le cycle sur les candles des marchés bootstrap.

## Batch 51.5 — grounding factuel et sizing stratégique

Le benchmark Ollama canonique est suffisamment rapide ; le problème courant est la qualité du raisonnement stratégique. Le contrat multi-marchés 51.5 est renforcé sans modifier l'autorité du Risk Engine :

- une affirmation factuelle de rationale/thèse doit provenir de l'input causal ou d'un tool read-only du même appel ;
- les connaissances générales du modèle ne sont pas une source de faits pour la décision ;
- un prix isolé ne permet pas de déduire tendance, momentum, volatilité, consolidation/breakout, ratio inter-actifs ou faits fondamentaux ;
- le prompt reçoit des références arithmétiques de sizing calculées uniquement à partir du portefeuille et des prix fournis ;
- `proposed_quantity` est explicitement une quantité d'actif de base ;
- toute mention de pourcentage doit être cohérente avec `quantity × price` et une référence effectivement fournie ;
- pour un SELL SPOT, la quantité proposée ne doit pas excéder la quantité de base disponible ;
- ces références ne sont pas des recommandations d'allocation et ne constituent aucune limite Risk.

Cas de régression principal : `0.1 BTC × 98 250 EUR = 9 825 EUR`, soit `98,25 %` de `10 000 EUR`, et non `1 %`.

Détail : `docs/51_5_GROUNDING_SIZING_OLLAMA.md`.

## Invariants inchangés

Un seul Agent IA stratégique ; PAPER ; SPOT + PERPETUAL selon l'univers intégré ; Risk Engine déterministe avec autorité finale ; aucun LLM directement vers Broker/Kraken ; aucun fallback silencieux de provider ; aucune donnée future dans les contextes causaux ; aucune chaîne de pensée détaillée persistée/exposée ; aucun secret dans Campaign/prompt/log/versioning ; frontend non requis par le moteur.

## Validation du patch 51.5

Exécuté dans l'environnement de livraison :

```text
python -m py_compile (3 fichiers Python)                 : PASS
pytest standalone du helper grounding/sizing             : PASS — 5/5
contrôle statique d'intégration StrategyInstructionsClient: PASS
reconstruction du strategy_client.py de base / Git blob   : PASS
contrôle lignes nouvelles <= 100 / espaces finaux         : PASS
```

La suite repository complète, Ruff et le benchmark Ollama réel ne sont pas déclarés exécutés ici. Ils doivent être rejoués localement après extraction avant intégration.
