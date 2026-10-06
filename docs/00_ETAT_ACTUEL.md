# 00 — État actuel

## Référence de reprise — Batch 51.4 livré, non intégré

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub intégré vérifié        : 5d24185ac1eefe9be3c21e31e62831228c73fea9
Commit GitHub                      : feat: add live Ollama agent observability
Batch 51.1 intégré                 : aeaf04f — feat: add local Ollama LLM provider
Batch 51.1.1 intégré               : 7e2ce28 — fix: harden causal Ollama decision contract
Batch 51.2 intégré                 : 36491d4 — feat: configure LLM provider per session
Batch 51.3 intégré                 : 5d24185 — feat: add live Ollama agent observability
Batch 51.4                         : patch root-relative livré — non intégré
```

## État intégré confirmé

Le même Agent stratégique utilise `OPENAI` ou `OLLAMA` derrière `StructuredDecisionClient`, sans fallback inter-provider. Le provider stratégique est configurable et persistant par Session/Campaign. Ollama réel a été validé avec `qwen3.5:9b` ; les logs 51.3 exposent le départ, le succès/échec et la latence d'un appel ainsi que le résumé BUY/SELL/HOLD du plan validé, sans prompt, réponse brute, `thinking` ou secret.

Le moteur PAPER supporte SPOT et PERPETUAL selon l'univers intégré. Le Market Attention Radar reste déterministe/informatif ; le même Agent conserve BUY/SELL/HOLD ; le Risk Engine garde l'autorité finale. Le frontend reste un cockpit et n'est pas requis pour maintenir le moteur en marche.

## Diagnostic Batch 51.4 — scheduler CANDLE_CLOSE

Diagnostic confirmé sur le HEAD `5d24185` :

- `ScheduledTradingEngine` attendait `CandleCloseReadinessGate` avant d'entrer dans le cycle ;
- le gate exigeait une candle finale exacte pour **tous** les marchés reçus ;
- `campaign_composition.py` lui fournissait `paper_executable_markets` ;
- pour une Campaign Radar dynamique, ces marchés sont le bootstrap et ne représentent pas forcément l'univers stratégique réellement résolu dans `DynamicMarketTradingCycleRunner` ;
- toute exception `history_as_of()` sur un seul bootstrap faisait retourner `False` au gate ;
- l'erreur restait invisible dans la boucle et la frontière pouvait être dépassée puis abandonnée sans aucun appel Agent ;
- le warning réel `Kraken payload validation failed operation=OHLC stage=OHLC_NUMERIC` est compatible avec ce mécanisme de blocage ;
- le run manuel contourne le scheduler et appelle directement le runner, ce qui explique qu'il fonctionne alors que la Session `RUNNING` ne déclenche rien automatiquement.

## Décision Batch 51.4

En CANDLE_CLOSE, la frontière UTC de la timeframe devient le **trigger du scheduler**. Le scheduler ne pré-résout plus Radar et ne bloque plus le cycle sur les candles des marchés bootstrap.

La causalité reste assurée dans les services canoniques consommateurs : `CandleStreamService.history_as_of()` n'expose que des observations disponibles à `as_of`, refuse les finals futurs et backfill de façon causale. Les contextes stratégiques conservent leur sémantique existante `AVAILABLE` / `PARTIAL` / `MISSING`; une erreur technique provider suit le chemin d'échec canonique du cycle au lieu d'être transformée en attente silencieuse pré-cycle.

`CandleCloseReadinessGate` reste disponible uniquement comme helper de diagnostic/test sur un ensemble de marchés explicite ; il n'est plus composé dans le scheduler de Campaign.

Le scheduler conserve : grille UTC, une exécution max par frontière, aucune rafale de catch-up, reprise à la prochaine frontière future après un cycle long ou un réveil tardif, run manuel et arrêt interruptible.

## Observabilité/runtime logging 51.4

La configuration runtime normale rend visibles à INFO :

```text
ai_spot_trader.agent.ollama
ai_spot_trader.agent.planner
ai_spot_trader.trading.cadence
```

`httpx` et `httpcore` restent à WARNING. `ai_spot_trader.integrations.kraken` reste à WARNING : les requêtes normales ne spamment pas le terminal, mais `OHLC_NUMERIC` et autres warnings/errors Kraken restent visibles.

Le scheduler journalise uniquement des événements bornés : prochaine clôture, frontière atteinte, readiness temporelle validée/déléguée au cycle, démarrage/fin du cycle auto et frontières sautées. Aucun polling à 0,5 s n'est journalisé.

## Timeouts Ollama

Le HEAD intégré utilise actuellement `ollama_timeout_seconds=60` par défaut process, alors que le configurateur utilisait `cycle_agent_timeout_seconds=35` pour une nouvelle Session : cette combinaison est incohérente avec la validation existante `Agent > transport` et avec la latence réelle observée de `qwen3.5:9b` (~27–31 s par appel).

Batch 51.4 conserve la validation stricte backend existante et ajoute une recommandation UX dérivée : lorsqu'un passage vers Ollama rencontre un timeout Agent absent/invalide/inférieur ou égal au transport, le cockpit propose automatiquement `2 × timeout transport` (60 → 120 s). Une valeur Agent déjà supérieure est conservée. Cette recommandation n'est pas une garantie pour une tool-loop multi-appels et n'introduit pas de couple 120/300 codé en dur.

## Validation 51.4 dans l'environnement de livraison

Exécuté sur les fichiers livrés :

```text
python -m py_compile (6 fichiers Python)                    : PASS
pytest scheduler dans harness isolé                         : PASS — 26/26
pytest configuration logging runtime                        : PASS — 2/2
node tests session-config 51.2 + 51.4                       : PASS — 11/11
parse/transpile TypeScript ciblé session-config + TSX       : PASS
contrôle espaces finaux / arborescence de livraison         : PASS
```

Le clone complet du repository n'était pas disponible dans l'environnement d'exécution ; la suite repository complète `pytest`, `pnpm typecheck`, `pnpm test`, `git diff --check` et le smoke réel d'une Session Ollama CANDLE_CLOSE restent à rejouer localement après extraction du ZIP.

## Invariants inchangés

Un seul Agent IA stratégique ; PAPER ; SPOT + PERPETUAL selon l'univers intégré ; Risk Engine déterministe avec autorité finale ; aucun LLM directement vers Broker/Kraken ; aucun fallback silencieux de provider ; aucune donnée future dans les contextes causaux ; aucune chaîne de pensée détaillée persistée/exposée ; aucun secret dans Campaign/prompt/log/versioning ; frontend non requis par le moteur.
