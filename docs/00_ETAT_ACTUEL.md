# 00 — État actuel

## Référence de reprise — Batch 51.1.1 patch correctif livré, validation locale à faire

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub intégré vérifié        : e5887da5e8e6ebf0fa739a041c0226a6fed940dd
Commit GitHub                      : feat: add strategic thesis observability
État local de départ               : aeaf04f49aa103ad55410dbbdc60d37ed23ee060
Parent de aeaf04f                  : e5887da5e8e6ebf0fa739a041c0226a6fed940dd
Working tree au lancement          : propre
Batch 51.1                         : commit local préservé
Batch 51.1.1                       : patch correctif livré — intégration/validation à faire
```

## Batch 51.1.1 — durcissement du contrat Ollama

Le smoke réel `OLLAMA / qwen3.5:9b` a confirmé le transport Structured Output mais a révélé qu'un modèle local pouvait inventer des marchés : le schema statique contraignait `market_type` mais pas le couple exact `(symbol, market_type)`. Le contrôle métier Agent refusait correctement le plan hors univers causal.

Le correctif conserve ce contrôle et ajoute une première barrière structurée :

```text
CycleDecisionPlanInput.market_states
        ↓
build_strategic_plan_schema(...)
        ↓
StructuredDecisionClient
        ↓
OpenAIResponsesClient OU OllamaStructuredDecisionClient
        ↓
Pydantic
        ↓
contrôle métier Agent
        ↓
Risk Engine
```

Décisions 51.1.1 :

- schema dynamique lié aux couples exacts `symbol + market_type` ;
- BUY/SELL conservent `proposed_quantity > 0`, HOLD conserve `null` ;
- `thesis_update` reste inchangé ;
- contrôle métier post-LLM conservé fail-closed ;
- Ollama structuré envoie `think: false` ;
- `message.content` est la seule sortie décisionnelle ;
- toute clé `thinking` reçue est supprimée avant audit public ;
- `LLM audit SUCCESS` décrit le succès transport/provider, pas l'acceptation canonique du plan Agent ;
- `cycle_agent_timeout_seconds` doit dépasser le budget transport `ollama_timeout_seconds` réellement nécessaire ; aucune grosse valeur n'est hardcodée globalement.

## Validation

Exécuté dans l'environnement ChatGPT pour 51.1.1 :

```text
python -m py_compile sur les fichiers Python créés/modifiés : PASS
```

À exécuter dans le checkout réel après extraction :

```powershell
Push-Location backend
python -m pytest -q
Pop-Location

Push-Location frontend
pnpm typecheck
pnpm test
Pop-Location

git diff --check
git status --short
```

Le vrai smoke Ollama `qwen3.5:9b` reste à refaire localement. Un audit LLM `SUCCESS` ne suffit pas à déclarer le cycle Agent réussi.

## Invariants inchangés

Un seul Agent IA stratégique ; PAPER ; SPOT + PERPETUAL selon l'univers causal ; aucun LIVE ; aucune sortie LLM directement exécutable ; aucun fallback Ollama vers OpenAI ; aucune chaîne de pensée détaillée persistée/exposée ; Risk Engine déterministe avec autorité finale ; frontend non requis par le moteur ; aucun secret versionné.
