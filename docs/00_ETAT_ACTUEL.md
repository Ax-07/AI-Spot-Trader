# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié le 27 septembre 2026 : `5fdd9a32bce45deda30c652b6b6f8c59e4996559` (`fix: refresh paper marks before trading starts`).
- Le document intégré était en retard de deux commits : l'inspecteur LLM `7846d89` et le correctif de rafraîchissement initial des marks `5fdd9a3` sont désormais intégrés à `main`.
- Le présent recalibrage des prompts stratégiques est un **patch proposé au-dessus de `5fdd9a3`, non intégré à GitHub**.

## État fonctionnel confirmé

- un seul Agent stratégique ;
- PAPER uniquement ;
- SPOT et PERPETUAL linéaire autorisés selon la configuration ;
- FUTURE daté interdit ;
- plan stratégique multi-marchés / multi-décisions ;
- Risk Engine déterministe avec autorité finale et évaluation séquentielle ;
- aucune sortie LLM ne déclenche directement un ordre ;
- inspecteur LLM en lecture seule intégré ;
- rafraîchissement initial des marks PAPER terminé avant le démarrage des cycles.

## Recalibrage de prompt proposé

Le chemin Session/Campaign courant ne doit plus injecter la cible expérimentale `+4 %/jour` dans les instructions du LLM. Cette cible reste documentée comme objectif expérimental non garanti du projet.

L'agressivité reste un contexte stratégique 1–10. Le mapping durable historique `aggressiveness-map-v1` reste intact pour les manifests/replays ; les prompts courants utilisent `aggressiveness-map-v2`. Les niveaux élevés augmentent l'initiative, la volonté d'agir et la rotation potentielle, mais n'impliquent jamais une quantité maximale. Le sizing proposé reste proportionné à la qualité/conviction de la thèse, aux faits fournis, aux coûts et au capital déjà exposé.

Le contrat courant rappelle explicitement que la qualité de la thèse prime sur la fréquence des trades, qu'aucun trade ne doit être produit pour créer de l'activité ou poursuivre une cible de rendement, et que `HOLD` reste valide lorsque la thèse n'est pas suffisamment défendable.

La section d'agressivité est rendue par un helper canonique partagé ; le typo `niveat=` disparaît au profit de `niveau=`. Les garde-fous SPOT/PERPETUAL, `management_mode`, quantité BUY/SELL positive, HOLD `null`, contrôle Risk du levier/marge/exposition/liquidation/`reduce_only` et causalité multi-décisions restent inchangés.

`AGENT_SYSTEM_PROMPT` / `agent-strategy-v4` reste volontairement figé pour les protocoles expérimentaux historiques v1/v2/v3 et leurs replays ; le recalibrage cible les instructions canoniques actuelles composées par `StrategyInstructionsClient`.

## SCALP / fraîcheur

Audit confirmé sans modification de politique : Risk possède déjà un contrôle de fraîcheur (`MARKET_FRESHNESS_UNAVAILABLE` / `MARKET_DATA_STALE`) et `kraken_stale_after_seconds` reste optionnel avec `None` par défaut. Au HEAD audité, la `RiskPolicy` des Campaigns ne renseigne toutefois pas `stale_after`, donc ce rejet Risk n'est pas activé par défaut sur ce chemin. Le style SCALP reste un style minute/intraday supporté ; aucun argument ne justifie de le supprimer dans ce batch.

Un durcissement spécifique SCALP doit rester un batch séparé, précédé d'une mesure réelle de la latence `MarketState -> LLM -> Risk` afin de fixer une politique de fraîcheur sur des données observées plutôt que sur une hypothèse.

## Validation du patch proposé

Dans l'environnement ChatGPT, les fichiers Python modifiés ont été compilés syntaxiquement. Un smoke contractuel isolé vérifie la conservation du v1 historique, le mapping LLM v2, l'absence de `+4 %/jour` dans le contrat courant, `niveau=10/10`, le remplacement du contexte d'agressivité dans l'input réellement transmis et la présence des garde-fous multi-marchés. Un `pytest` isolé de `test_control_plane_prompt.py` a produit `7 passed`.

Le checkout complet du repository et ses dépendances n'étant pas disponibles dans le conteneur, les tests ciblés du vrai backend et le `pytest` complet restent à exécuter localement après extraction du ZIP.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer explicitement l'état intégré GitHub, les modifications locales fournies par l'opérateur et tout patch proposé non encore intégré.
