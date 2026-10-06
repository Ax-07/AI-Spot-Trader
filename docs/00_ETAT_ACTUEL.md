# 00 — État actuel

## Référence de reprise — Batch 51.1 patch livré, intégration locale à valider

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub vérifié                : e5887da5e8e6ebf0fa739a041c0226a6fed940dd
Commit HEAD                        : feat: add strategic thesis observability
Batch 50.1                         : INTÉGRÉ ET VALIDÉ
Batch 50.2                         : INTÉGRÉ — feat: add strategic thesis observability
Batch 51.1                         : PATCH LIVRÉ — intégration/validation repository à faire
```

Les mentions précédentes indiquant que le Batch 50.2 restait « patch livré / intégration à faire » sont obsolètes : le HEAD GitHub courant contient bien l'observabilité des thèses stratégiques.

## Batch 51.1 — Provider LLM local / Ollama

Le patch 51.1 introduit une frontière explicite de transport LLM pour **le même Agent stratégique canonique**.

```text
StrategicThesisContextDecisionProvider
        ↓
MultiTimeframeDecisionProvider
        ↓
OpenAIMultiMarketDecisionProvider  (nom legacy conservé)
        ↓
StrategyInstructionsClient / StructuredDecisionClient
        ├── OpenAIResponsesClient
        └── OllamaStructuredDecisionClient
        ↓
validation Pydantic canonique
        ↓
Risk Engine
        ↓
PaperBroker
```

Configuration process/runtime :

```text
AI_SPOT_TRADER_LLM_PROVIDER=OPENAI | OLLAMA
AI_SPOT_TRADER_LLM_MODEL=gpt-5.6-luna | gpt-5.6-sol
AI_SPOT_TRADER_OLLAMA_BASE_URL=http://localhost:11434
AI_SPOT_TRADER_OLLAMA_MODEL=qwen3.5:9b
AI_SPOT_TRADER_OLLAMA_TIMEOUT_SECONDS=60
```

Règles 51.1 :

- `LLMProviderKind` distingue `OPENAI` et `OLLAMA` sans réutiliser le port domaine `LLMProvider` ;
- `LLMModel` reste Luna/Sol afin de préserver la sémantique et les snapshots Campaign existants ;
- le modèle Ollama est une chaîne configurable séparée ;
- `OPENAI_API_KEY` n'est requise que lorsque `LLM_PROVIDER=OPENAI` ;
- aucun fallback `OLLAMA -> OPENAI` ;
- le client Ollama utilise `/api/chat` avec JSON Schema via `format` ;
- la sortie locale traverse les mêmes parseurs/validations Pydantic que la sortie OpenAI ;
- les tools read-only réutilisent le registre et le budget existants ;
- le chat opérateur reste volontairement OpenAI-only en 51.1 et devient indisponible en mode LOCAL plutôt que de provoquer un fallback ;
- Risk, Broker, Radar, mémoire de thèse, multi-timeframe et stratégie restent inchangés.

L'observabilité LLM expose désormais provider, modèle, statut, type d'erreur et latence lorsque disponible, sans secret HTTP.

## Validation réalisée dans l'environnement ChatGPT

Exécuté réellement :

```text
python -m compileall (fichiers Python du patch)                    : PASS
harnais isolé Ollama MockTransport (structured + tools + réseau)   : PASS
harnais isolé OpenAI audit (SUCCESS/ERROR + latence)               : PASS
git diff --cached --check sur staging du patch root-relative       : PASS
```

Non exécuté ici faute de checkout complet du repository et de serveur Ollama local :

```text
python -m pytest -q
pnpm typecheck
pnpm test
git diff --check dans le repository réel
smoke/inférence réelle Ollama
```

## Invariants inchangés

Un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ; Risk Engine déterministe autorité finale ; aucune sortie LLM directement exécutable ; Radar informatif/priorisation ; même `CycleDecisionPlanInput`, même mémoire de thèse et même contexte multi-timeframe ; `BUY` / `SELL` / `HOLD` inchangés ; aucun look-ahead ; aucun secret versionné ; frontend non requis par le moteur.
