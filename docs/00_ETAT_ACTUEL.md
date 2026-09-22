# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité avant Batch 18.1 : `ca5077af00293ccca9794132ee0dd53a5b339911` (`docs: finalize Batch 17 integration`).
- Tag de restauration officiel : `baseline-batch17`, vérifié sur le même commit `ca5077af00293ccca9794132ee0dd53a5b339911`.
- Batch 17 fonctionnel : `25efe21194a61140c426a47c261f74f76799e4ea` (`fix: harden Kraken derivatives paper metadata`).
- Prompt stratégique : `agent-strategy-v4`.

## Batch 18.1 — patch proposé, non intégré

Objectif : donner à l'unique Agent stratégique un petit socle de recherche marché **read-only** piloté par function calling OpenAI, sans créer de second agent, scanner, ranking, score d'opportunité ou voie d'exécution parallèle.

Le patch proposé ajoute :

- `MarketResearchService`, frontière provider-agnostic de recherche factuelle ;
- deux tools uniquement : `list_markets` et `get_market_snapshot` ;
- réutilisation des adapters Kraken publics et du `MarketStateBuilder` existants ;
- boucle Responses API explicite avec `store=false`, functions strictes et replay causal des `function_call` / `function_call_output` ;
- budgets purement techniques : nombre max d'appels, timeout par tool et taille max de résultat ;
- traces de recherches normalisées, sanitizées et digestées ;
- persistance des traces au niveau du cycle, y compris si l'Agent échoue après avoir déjà utilisé un tool ;
- migration `0003_agent_tool_traces` ajoutant `audit_cycles.agent_tool_traces_payload` ;
- inclusion des traces dans le digest durable du cycle.

La recherche peut porter sur d'autres symboles, mais **Batch 18.1 ne change pas le symbole exécutable** :

```text
DecisionCandidate.symbol == AgentInput.market_state.symbol == paper_symbol du cycle
```

Le `MarketState` transmis à Risk/Broker reste celui acquis par le runner canonique pour le `paper_symbol`. Le vrai choix multi-symbole exécutable est réservé au Batch 18.2.

## Frontières conservées

- un seul Agent stratégique ;
- SPOT + Derivatives en PAPER uniquement ;
- aucun short SPOT ;
- LONG/SHORT uniquement dans le domaine Derivatives compatible ;
- le LLM ne choisit ni levier ni `reduce_only` ;
- seul Risk peut créer un `ExecutionIntent` ;
- aucun tool -> Risk/Broker et aucun LLM -> Broker ;
- aucune API Kraken privée ni LIVE ;
- `PortfolioState` complet reste fourni à l'Agent ;
- aucune donnée postérieure à la décision finale ;
- HOLD reste un résultat stratégique valide.

## Choix d'architecture importants

Les sources de recherche Kraken sont **distinctes des sources de trading** afin qu'une exploration de marché ne modifie ni le cache causal du source principal ni le ledger. Le source Derivatives de recherche n'a aucun `market_sink`.

`list_markets` peut exposer des métadonnées SPOT, PERPETUAL et FUTURE. `get_market_snapshot` est volontairement limité à SPOT/PERPETUAL en 18.1 : le mapping Derivatives exécutable actuel privilégie le perpetual linéaire en cas de collision de symbole canonique, donc prétendre fournir un snapshot FUTURE générique serait trompeur.

## Validation exécutée par ChatGPT sur le patch

Dans l'environnement de livraison partiel :

```text
pytest ciblé Batch 18.1 + non-régressions OpenAI/config : 47 passed
python -m compileall sur code/test/migration modifiés        : OK
```

`ruff` et `mypy` ne sont pas installés dans cet environnement. La suite complète du repository et les validations Git doivent donc être exécutées localement après extraction.

## Prochaine étape

1. appliquer le ZIP Batch 18.1 à la racine ;
2. exécuter la migration Alembic et la validation locale complète ;
3. intégrer seulement après validation ;
4. traiter séparément le Batch 18.2 pour sélectionner causalement le marché exécutable avant Risk/Broker.
