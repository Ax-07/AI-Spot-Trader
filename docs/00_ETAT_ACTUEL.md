# 00 — État actuel

## Référence de reprise — Batch 51.3 livré, non intégré

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub intégré vérifié        : 36491d4caf1fcc3bb4a2ceb5e3bc418e566ee598
Commit GitHub                      : feat: configure LLM provider per session
Batch 51.1 intégré                 : aeaf04f — feat: add local Ollama LLM provider
Batch 51.1.1 intégré               : 7e2ce28 — fix: harden causal Ollama decision contract
Batch 51.2 intégré                 : 36491d4 — feat: configure LLM provider per session
Working tree connu au lancement    : propre (état utilisateur communiqué)
Batch 51.3                         : patch root-relative livré — non intégré
```

## État intégré validé

Le même Agent stratégique utilise `OPENAI` ou `OLLAMA` derrière `StructuredDecisionClient`, sans fallback inter-provider. Le provider stratégique est configurable et persistant par Session/Campaign depuis 51.2 ; les snapshots legacy sans champ 51.2 héritent encore du provider process.

Ollama réel a été validé avec `qwen3.5:9b` : cycle `COMPLETED`, audit `STRATEGIC_MULTI_MARKET_PLAN`, `provider=OLLAMA`, `status=SUCCESS`, `session_id` et `cycle_id` corrélés. Le Structured Output reste causal, `think:false` reste actif et aucune chaîne `thinking` n'est exposée.

Validation locale communiquée pour 51.2 : backend complet PASS, frontend typecheck PASS, frontend `101/101` PASS.

## Batch 51.3 — observabilité live Ollama

Patch livré :

- `OllamaStructuredDecisionClient` journalise chaque tentative HTTP réelle `/api/chat` au départ ;
- chaque tentative possède un `call_id` éphémère et un numéro `attempt`, ce qui distingue les tool rounds et les retries sans nouvel identifiant persistant ;
- succès et erreurs exposent uniquement provider, modèle, Session, cycle, `call_id`, tentative, latence et type d'erreur ;
- les retries restent ceux de `ai_spot_trader.retry` et leur sémantique n'est pas modifiée ;
- après retour d'un `CycleDecisionPlan` déjà validé par le provider stratégique canonique, un log `agent_plan_completed` expose uniquement le nombre de décisions et les compteurs BUY/SELL/HOLD ;
- aucun prompt, historique, réponse brute, `thinking`, rationale détaillée, secret ou URL n'est ajouté aux logs ;
- les helpers de logging sont best-effort : une défaillance de logging ne modifie jamais la décision ni l'exécution.

Exemples attendus :

```text
llm_request_started provider=OLLAMA model=qwen3.5:9b session_id=<uuid> cycle_id=<uuid> call_id=<id> attempt=1
llm_request_succeeded provider=OLLAMA model=qwen3.5:9b session_id=<uuid> cycle_id=<uuid> call_id=<id> attempt=1 latency_ms=12345
llm_request_failed provider=OLLAMA model=qwen3.5:9b session_id=<uuid> cycle_id=<uuid> call_id=<id> attempt=1 error_type=LLMTimeoutError latency_ms=30000
agent_plan_completed session_id=<uuid> cycle_id=<uuid> decisions=6 buy=0 sell=0 hold=6
```

## Validation 51.3

Exécuté dans l'environnement de livraison ChatGPT :

```text
python -m py_compile sur les 3 fichiers Python 51.3 : PASS
pytest ciblé 51.3 dans un harness isolé              : PASS — 8/8
contrôle des espaces finaux des fichiers livrés       : PASS
```

Le pytest ciblé exécute les modules modifiés avec des dépendances minimales simulées ; il ne remplace pas la suite repository. La suite backend complète, `pnpm typecheck`, `pnpm test`, `git diff --check` sur le vrai checkout et le smoke Ollama réel restent à rejouer localement après extraction.

## Invariants inchangés

Un seul Agent IA stratégique ; PAPER ; SPOT + PERPETUAL selon l'univers intégré ; Risk Engine déterministe avec autorité finale ; aucun LLM directement vers Broker/Kraken ; aucun fallback silencieux de provider ; aucun marché hors univers causal ; aucune chaîne de pensée détaillée persistée/exposée ; aucun secret dans Campaign/prompt/log/versioning ; frontend non requis par le moteur.
