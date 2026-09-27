# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié le 27 septembre 2026 : `b4f1e50f22164c7d019d11d930485733c01c6711` (`fix: restore paper perpetual session support`).
- `docs/00_ETAT_ACTUEL.md` était en retard d'un commit : il référençait encore `aa404e4` alors que le correctif PERPETUAL est désormais intégré à `main`.
- Le présent Batch inspecteur LLM est un **patch proposé au-dessus de `b4f1e50`, non intégré à GitHub**.

## État fonctionnel confirmé

- un seul Agent stratégique ;
- PAPER uniquement ;
- SPOT et PERPETUAL linéaire autorisés selon la configuration ;
- FUTURE daté non exécutable ;
- plan stratégique multi-marchés / multi-décisions ;
- Risk Engine déterministe avec autorité finale ;
- aucune sortie LLM ne déclenche directement un ordre.

## Batch inspecteur LLM proposé

Le patch ajoute une instrumentation en lecture seule à la frontière canonique `OpenAIResponsesClient`. Chaque appel Responses API réussi conserve, de façon bornée et best-effort, le payload exact réellement transmis (`model`, `instructions`, `input`, Structured Output, tools, `parallel_tool_calls`, `store`) ainsi que l'output fournisseur et le texte final lorsqu'il existe.

La corrélation est extraite des inputs canoniques (`cycle_id`, `discovery_id`) et complétée par un contexte asynchrone pour l'Operator Chat (`session_id`). Les tool loops produisent plusieurs entrées ordonnées : l'appel contenant le `function_call`, puis l'appel suivant contenant le `function_call_output` réellement renvoyé au modèle.

Rétention proposée : 200 appels maximum en mémoire du processus, 512 Kio maximum par entrée. Une panne de l'audit est ignorée à la frontière OpenAI afin de ne jamais perturber le moteur. Le cockpit ne fait que lire `/api/v1/llm-audit`.

## Anomalies de prompt confirmées mais non corrigées dans ce batch

1. `backend/src/ai_spot_trader/chat/prompt.py` affirme encore `Trading is SPOT only and PAPER only.` alors que SPOT + PERPETUAL linéaire sont supportés en PAPER.
2. `backend/src/ai_spot_trader/agent/strategy_client.py` contient `niveat={context.level}/10` au lieu de `niveau=...`.
3. `backend/src/ai_spot_trader/agent/prompt.py` indique encore que `FUTURE` daté « peut être découvrable », alors que l'invariant courant interdit FUTURE daté à la discovery et à l'exécution.

Ces incohérences sont documentées séparément afin que l'inspecteur permette d'observer les prompts réels avant une correction stratégique dédiée.

## Validation

Dans l'environnement ChatGPT, les nouveaux/modifiés fichiers Python ont été compilés syntaxiquement. Le checkout complet du repository et ses dépendances ne sont pas disponibles dans le conteneur ; `pytest`, le typecheck et le build frontend restent à exécuter localement après extraction.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer explicitement l'état intégré GitHub, les modifications locales fournies par l'opérateur et tout patch proposé non encore intégré.
