# Batch 51.7 — Robustesse des Structured Outputs Ollama

## Statut

Patch préparé sur le HEAD GitHub `main` audité :

```text
9fd8054213c2c6c7eb2e8429f288b1443ef70b94
docs: close batch 51.5 Ollama grounding validation
```

Ce batch n'est pas déclaré intégré tant que le patch n'a pas été extrait, validé localement et commité par l'opérateur.

## Diagnostic

Le transport Ollama peut terminer correctement (`HTTP 200`, enveloppe provider valide) alors que `message.content` ne respecte pas le contrat stratégique strict : JSON invalide, action/quantité invalide, décision hors univers causal, doublon `symbol + market_type`, cardinalité supérieure à `max_decisions_per_cycle` ou thèse structurée obligatoire absente.

Le fail-closed existant est correct et doit être conservé. Le problème est qu'une erreur de génération récupérable du modèle local faisait échouer directement le cycle sans donner au même Agent une unique occasion de régénérer un plan conforme.

L'audit confirme que le retry réseau/HTTP appartient à `OllamaStructuredDecisionClient`, tandis que la validation Pydantic et les invariants de plan appartiennent à `OpenAIMultiMarketDecisionProvider` dans `agent/planner.py`. Le retry contractuel est donc placé au niveau du planner et non dans le transport Ollama.

## Décision

### Une régénération corrective Ollama maximum

Le flux devient :

```text
appel stratégique Ollama
        |
        v
sortie LLM
        |
        v
validation stricte
   |           |
 valide     violation LLM récupérable
   |           |
   v           v
 suite       1 régénération maximum
               |
               v
          validation stricte
             |       |
          valide   invalide
             |       |
             v       v
           suite   FAILED
```

La régénération utilise le même provider Ollama, le même modèle, le même `CycleDecisionPlanInput`, le même schéma causal et le même contexte Session/cycle. Aucun fallback Ollama → OpenAI n'est introduit.

OpenAI conserve zéro régénération contractuelle automatique dans ce batch. Le choix est explicite : le besoin observé concerne le modèle local et aucun coût API supplémentaire n'est ajouté silencieusement.

### Classification des erreurs

Une sous-classe dédiée `RecoverableLLMContractViolationError` distingue les violations post-Pydantic imputables à la réponse du modèle des invariants internes de l'application.

Sont récupérables pour la régénération Ollama :

- sortie vide / JSON invalide ;
- action invalide ;
- combinaison action / `proposed_quantity` invalide ;
- liste de décisions structurellement invalide ;
- `thesis_update` structurellement invalide ;
- dépassement de `max_decisions_per_cycle` ;
- marché hors univers causal ;
- doublon `symbol + market_type` ;
- mise à jour/revue de thèse obligatoire absente.

Ne déclenchent pas de retry contractuel :

- erreur réseau/HTTP/provider avant sortie stratégique ;
- horloge naïve ou antérieure au `CycleDecisionPlanInput` ;
- trace tool temporellement impossible ;
- univers causal interne non exécutable ;
- erreur interne de composition ou de contexte.

Les erreurs réseau transitoires restent exclusivement gérées par `retry_async()` dans le transport Ollama.

### Aucun repair déterministe

Le backend ne transforme jamais la réponse précédente. En particulier il ne fait pas :

```text
-0.15 -> 0.15
```

Il ne déduplique pas le plan, ne tronque pas les décisions excédentaires et ne convertit aucune action en HOLD. La sortie fautive est rejetée ; le modèle régénère intégralement une nouvelle sortie.

### Feedback correctif

La deuxième génération reçoit uniquement un bloc `contract_regeneration` ajouté à l'input causal. Ce bloc contient :

- une version de protocole ;
- `attempt=1` ;
- une catégorie sûre de violation ;
- une instruction de régénération intégrale ;
- les contraintes contractuelles minimales à respecter.

La réponse brute précédente n'est jamais réinjectée. Aucun secret, aucune chaîne de pensée et aucune décision « attendue » n'est fournie au modèle.

## Observabilité

Les appels transport continuent de produire leurs propres `call_id`. La tentative initiale et la tentative corrective restent corrélées par le même `session_id` et `cycle_id` via `llm_audit_context`.

Le planner ajoute des événements best-effort sans contenu décisionnel brut :

```text
agent_contract_regeneration_started   provider=OLLAMA session_id=... cycle_id=... attempt=1 max_attempts=1 reason=...
agent_contract_regeneration_succeeded provider=OLLAMA session_id=... cycle_id=... attempt=1
agent_contract_regeneration_failed    provider=OLLAMA session_id=... cycle_id=... attempt=1 reason=...
```

Le deuxième appel apparaît aussi comme un enregistrement LLM audit distinct. Son input contient le marqueur `contract_regeneration`, ce qui permet à l'Inspecteur LLM de distinguer la tentative corrective sans modifier son modèle de données.

## Fichiers du batch

```text
backend/src/ai_spot_trader/agent/errors.py
backend/src/ai_spot_trader/agent/planner.py
backend/tests/test_batch51_7_contract_regeneration.py
docs/00_ETAT_ACTUEL.md
docs/10_DECISIONS_ET_CHANGELOG.md
docs/51_7_ROBUSTESSE_STRUCTURED_OUTPUT_OLLAMA.md
```

## Tests ajoutés

Le test dédié couvre :

1. première sortie valide → un seul appel ;
2. JSON invalide puis valide → une régénération ;
3. SELL négatif puis valide → une régénération ;
4. doublon puis valide → une régénération ;
5. dépassement de cardinalité puis valide → une régénération ;
6. deux sorties invalides → échec après exactement deux appels ;
7. épuisement du retry → cycle FAILED, aucun appel Risk/Broker ;
8. violation d'horloge interne → aucun retry contractuel ;
9. erreur réseau → aucun retry contractuel ;
10. modèle OpenAI → aucun appel supplémentaire ;
11. logs correctifs sûrs et corrélés ;
12. transport Ollama réel mocké → deux enregistrements audit corrélés, dont un marqué `contract_regeneration`.

Le test 51.7 de runner vérifie explicitement le garde-fou fail-closed après épuisement de la correction : `decision_plan` reste absent et Risk/Broker ne sont pas appelés.

## Validation de livraison

Exécuté dans l'environnement de livraison :

```text
python -m py_compile backend/src/ai_spot_trader/agent/errors.py                         : PASS
python -m py_compile backend/src/ai_spot_trader/agent/planner.py                        : PASS
python -m py_compile backend/tests/test_batch51_7_contract_regeneration.py               : PASS
harness isolé classification/régénération                                                 : PASS
contrôle lignes Python > 100 caractères                                                   : PASS
contrôle espaces finaux                                                                    : PASS
```

Le checkout complet du repository n'est pas disponible dans cet environnement ; la suite `pytest` repository et `git diff --check` ne sont donc pas déclarés exécutés ici.

## Validation locale obligatoire après extraction

```powershell
Push-Location backend
pytest -q tests/test_batch51_7_contract_regeneration.py tests/test_multi_market_provider.py tests/test_batch51_1_1_ollama_contract.py tests/test_batch51_3_ollama_live_logging.py
pytest -q
Pop-Location
git diff --check
git status --short
```

## Invariants préservés

- un seul Agent IA stratégique ;
- BUY / SELL / HOLD restent les seules actions ;
- l'IA conserve la décision stratégique ;
- le Risk Engine déterministe garde l'autorité finale ;
- aucune sortie LLM invalide n'atteint Risk/Broker ;
- aucune réparation stratégique déterministe ;
- aucune boucle de retry non bornée ;
- aucun fallback inter-provider ;
- grounding causal 51.5 conservé ;
- aucune chaîne de pensée détaillée exposée ;
- aucun secret dans le feedback, les logs ou l'audit.

Le principe reste : **l'IA propose. Le contrat valide. Le Risk Engine autorise, modifie ou refuse.**
