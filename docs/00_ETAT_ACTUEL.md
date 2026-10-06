# 00 — État actuel

## Référence de reprise — Batch 51.2 en validation locale, correctif audit Session à valider

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub intégré vérifié        : 7e2ce2821660c9be7f5ffdfe053244d56fae7986
Commit GitHub                      : fix: harden causal Ollama decision contract
Batch 51.1 intégré                 : aeaf04f — feat: add local Ollama LLM provider
Batch 51.1.1 intégré               : 7e2ce28 — fix: harden causal Ollama decision contract
Working tree connu après push      : propre (état utilisateur communiqué au lancement)
Batch 51.2                         : patch root-relative livré — non intégré
```

## État validé avant 51.2

Le même Agent stratégique peut utiliser OpenAI ou Ollama derrière `StructuredDecisionClient`. Le Structured Output multi-marché est causal : seuls les couples `(symbol, market_type)` présents dans `CycleDecisionPlanInput.market_states` sont admissibles. Ollama utilise `think:false` et aucune chaîne `thinking` n'est exposée dans l'audit.

Validation locale communiquée avant 51.2 : suite backend complète PASS, frontend typecheck PASS, frontend `92/92` PASS, `git diff --check` PASS et smoke réel `OLLAMA / qwen3.5:9b` PASS avec cycle `COMPLETED`, audit `provider=OLLAMA`, aucun appel OpenAI et aucun `thinking` exposé.

## Batch 51.2 — provider LLM par Session/Campaign

Patch livré :

- `CampaignConfiguration` accepte de façon additive `llm_provider`, `ollama_model`, `ollama_timeout_seconds` ;
- ces champs restent absents quand ils valent `null`, afin de préserver payload et digest des Campaigns legacy ;
- une nouvelle Session API doit choisir explicitement `OPENAI` ou `OLLAMA` ; une Session legacy peut rester en mode « hérité du runtime » lors d'une édition ;
- provider explicite Campaign > provider process ; `Settings.llm_provider` ne sert plus que de comportement legacy quand le snapshot ne contient pas le champ 51.2 ;
- `ollama_base_url`, secrets et timeout OpenAI restent process/infrastructure ;
- `ollama_model` reste une chaîne et ne modifie pas `LLMModel` Luna/Sol ;
- aucun fallback entre OpenAI et Ollama ;
- le chat opérateur reste disponible seulement lorsque le provider effectif de la Campaign est OpenAI ; Ollama chat reste hors périmètre ;
- le cockpit canonique `SimpleConfigurator` expose provider, modèle local et timeout transport ;
- `cycle_agent_timeout_seconds` reste l'enveloppe du stade Agent et doit être strictement supérieur au timeout Ollama effectif, sans prétendre garantir le budget d'une boucle multi-appels/tools.


## Smoke runtime 51.2 observé

Le smoke local du 6 octobre 2026 confirme un appel stratégique réel `STRATEGIC_MULTI_MARKET_PLAN` avec `provider=OLLAMA`, `model=qwen3.5:9b` et `status=SUCCESS`. Après redémarrage du backend, l’audit process-local a toutefois révélé que `cycle_id` était présent mais `session_id` absent. Le correctif 51.2 rattache désormais le contexte d’audit stratégique à `campaign.strategy_id` (identité Session) sans modifier le routage LLM ni la décision.

## Validation du patch 51.2 dans l'environnement ChatGPT

Exécuté :

```text
python -m py_compile sur les fichiers Python 51.2 : PASS
node --test --experimental-strip-types session-config-batch51_2.test.mjs : PASS — 9/9
```

Non exécutable ici faute de checkout/dépendances complets : suite backend repository, `pnpm typecheck`, suite frontend complète, smoke applicatif Ollama, `git diff --check` sur le vrai checkout.

## Invariants inchangés

Un seul Agent IA stratégique ; PAPER ; SPOT + PERPETUAL selon l'univers intégré ; Risk Engine déterministe avec autorité finale ; aucun LLM directement vers Broker/Kraken ; aucun fallback silencieux de provider ; aucun marché hors univers causal ; aucune chaîne de pensée détaillée persistée/exposée ; aucun secret dans Campaign/prompt/log/versioning ; frontend non requis par le moteur.
