# Batch 51.5 — Grounding factuel et sizing stratégique Ollama

## Statut

Patch préparé sur le HEAD GitHub intégré audité :

```text
e0ddeba3d5170a53d0796f0345af1c5912ee8259
docs: sync documentation after batch 51.4 integration
```

Ce batch n'est pas déclaré intégré tant qu'il n'a pas été appliqué, validé localement et commité par l'opérateur.

## Contexte

Le benchmark canonique Ollama réel avec `qwen3.5:9b`, `OllamaStructuredDecisionClient`, `StrategyInstructionsClient`, `OpenAIMultiMarketDecisionProvider`, un vrai `CycleDecisionPlanInput` et le vrai schéma `build_strategic_plan_schema()` valide désormais les performances du transport local. Le problème traité ici est la qualité sémantique du plan, pas la vitesse GPU.

Sur un contexte contenant essentiellement trois prix SPOT et `10 000 EUR` de cash, le modèle a produit des affirmations non présentes dans l'input (`tendance haussière`, `volatilité extrême`, ratio BTC/ETH, classification/fondamentaux) et une contradiction de sizing : `0.1 BTC` à `98 250 EUR` représente `9 825 EUR`, soit `98,25 %` du cash disponible, alors que la rationale annonçait `1 % du capital`.

## Diagnostic

Le contrat existant interdisait déjà d'inventer des faits, mais cette règle restait générale. Le schéma structurel vérifiait seulement qu'un BUY/SELL possède une quantité strictement positive ; il ne pouvait pas garantir la cohérence sémantique entre `proposed_quantity`, prix, notionnel et pourcentage annoncé dans la rationale.

Le Risk Engine déterministe doit continuer à contrôler les limites et à autoriser, modifier ou refuser les propositions. Ajouter un deuxième moteur de sizing stratégique déterministe en amont créerait une autorité parallèle et dégraderait l'architecture canonique.

## Décision

### 1. Grounding factuel explicite

Le contrat multi-marchés indique désormais que chaque affirmation factuelle de rationale ou de thèse doit être justifiable par un champ de l'input causal ou un résultat de tool read-only du même appel.

Les connaissances générales ou mémorisées du modèle ne constituent pas une source autorisée. En particulier, un prix isolé ne permet pas d'affirmer une tendance, un momentum, une volatilité, une consolidation, un breakout, un ratio inter-actifs, une classification technologique ou un fait fondamental.

Quand une information n'est pas fournie, elle doit être traitée comme inconnue et ne peut pas justifier la décision.

### 2. Références arithmétiques de sizing

`agent/grounding.py` dérive uniquement depuis le payload causal des références descriptives compactes par marché :

- `symbol`, `market_type` et `last_price` réellement fournis ;
- solde disponible de l'actif de cotation pour un marché SPOT ;
- notionnel correspondant à 1 % de ce solde de cotation ;
- quantité d'actif de base correspondant arithmétiquement à ce 1 % ;
- quantité SPOT de base disponible pour une vente ;
- `cash_available` et `equity` uniquement lorsqu'ils sont réellement fournis, avec leur référence à 1 %.

Ces valeurs sont purement arithmétiques. Elles ne sont ni une recommandation d'allocation, ni une limite Risk, ni un montant supposé intégralement dépensable. Aucun indicateur, tendance, signal ou fait de marché n'est dérivé. La section est rendue dans un format ligne compact pour éviter de dupliquer le payload complet : le benchmark observé à `2712` tokens de prompt avec un contexte Ollama `4096` laisse peu de marge à une injection verbeuse.

### 3. Contrat quantitatif de `proposed_quantity`

Le contrat rappelle que `proposed_quantity` est une quantité d'actif de base, pas un pourcentage et pas un notionnel en devise de cotation.

Pour un BUY SPOT, l'Agent doit vérifier :

```text
gross_notional = proposed_quantity × last_price
```

Toute mention d'un pourcentage doit nommer sa référence réellement fournie et rester arithmétiquement cohérente :

```text
X = 100 × gross_notional / reference_amount
```

Ainsi, pour le cas observé :

```text
0.1 BTC × 98 250 EUR/BTC = 9 825 EUR
9 825 / 10 000 × 100 = 98.25 %
```

La même proposition ne peut donc plus être rationnellement décrite comme `1 % du capital` par le contrat.

Pour un SELL SPOT, le contrat interdit de proposer plus que la quantité de base disponible. Si action, quantité et rationale ne peuvent pas être rendues cohérentes à partir des faits présents, HOLD reste une décision valide.

## Architecture préservée

Le changement est injecté au niveau canonique de `StrategyInstructionsClient` et s'applique au plan stratégique multi-marchés quel que soit le transport LLM. Il n'ajoute aucun appel LLM et ne crée aucun chemin spécifique Ollama parallèle.

Invariants inchangés :

- un seul Agent stratégique ;
- PAPER ;
- BUY / SELL / HOLD ;
- aucune sortie LLM directement vers Broker/Kraken ;
- Risk Engine déterministe avec autorité finale ;
- aucun sizing automatique ajouté à Risk ou au Broker ;
- aucun fait externe implicite ajouté au contexte causal ;
- aucun secret, prompt brut, réponse brute ou chaîne de pensée exposé.

## Fichiers du batch

```text
backend/src/ai_spot_trader/agent/grounding.py
backend/src/ai_spot_trader/agent/strategy_client.py
backend/tests/test_batch51_5_grounding_sizing.py
docs/00_ETAT_ACTUEL.md
docs/51_5_GROUNDING_SIZING_OLLAMA.md
```

## Validation exécutée dans l'environnement de livraison

```text
python -m py_compile (grounding, strategy_client, test 51.5) : PASS
pytest standalone du calcul causal de sizing                 : PASS — 5/5
contrôle statique de l'injection multi-marchés               : PASS
reconstruction inverse de strategy_client.py                  : PASS
Git blob reconstruit = 6eb5cac2e6668dcfdc21504dcf7a5cf316a79148
contrôle lignes nouvelles <= 100 / espaces finaux            : PASS
```

Le rendu `SIZING_FACTS` du cas BTC/ETH/SOL de référence ajoute `529` caractères ; les deux garde-fous ajoutent `736` caractères, soit `1265` caractères supplémentaires au total sur cet exemple. Il ne s'agit pas d'une mesure de tokens, mais d'un contrôle de compacité destiné au contexte Ollama `4096`.

La suite repository complète n'a pas pu être exécutée dans cet environnement, qui ne dispose pas du checkout complet. `ruff` n'est pas installé ici. Le benchmark Ollama réel avec `qwen3.5:9b` doit donc être rejoué localement.

## Validation attendue après extraction locale

```powershell
Push-Location backend
pytest -q tests/test_batch51_5_grounding_sizing.py tests/test_strategy_instructions_client.py tests/test_multi_market_provider.py tests/test_batch51_1_1_ollama_contract.py
Pop-Location
git diff --check
```

Puis rejouer le benchmark canonique Ollama sur BTC/EUR, ETH/EUR et SOL/EUR. Le critère principal n'est pas qu'un BUY soit nécessairement produit : le plan doit éviter les faits non fournis et toute rationale quantitative doit être cohérente avec la quantité proposée.

## Hors périmètre

Ce batch n'ajoute pas de validateur NLP post-hoc des rationales, ne modifie pas les limites Risk, ne crée pas de sizing algorithmique stratégique, ne change pas la stratégie de trading et n'introduit ni fine-tuning ni apprentissage automatique à partir des backtests.
