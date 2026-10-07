# Batch 51.5 — Grounding factuel et sizing stratégique Ollama

## Statut

Batch intégré sur `main` :

```text
6cbae5535fbc480b73ffa06cd876ab48be22094d
fix: ground strategic reasoning and sizing
```

Le HEAD pré-intégration audité était :

```text
e0ddeba3d5170a53d0796f0345af1c5912ee8259
docs: sync documentation after batch 51.4 integration
```

Le présent document conserve la distinction entre les contrôles exécutés lors de la préparation du patch et les validations locales/réelles effectuées ensuite par l'opérateur.

## Contexte

Le benchmark canonique Ollama avec `qwen3.5:9b`, `OllamaStructuredDecisionClient`, `StrategyInstructionsClient`, `OpenAIMultiMarketDecisionProvider`, un vrai `CycleDecisionPlanInput` et le vrai schéma `build_strategic_plan_schema()` avait montré que le problème prioritaire n'était plus le transport local mais la qualité sémantique du plan.

Sur un contexte contenant essentiellement trois prix SPOT et `10 000 EUR` de cash, le modèle avait produit des affirmations non présentes dans l'input (`tendance haussière`, `volatilité extrême`, ratio BTC/ETH, classification/fondamentaux) et une contradiction de sizing : `0.1 BTC` à `98 250 EUR` représente `9 825 EUR`, soit `98,25 %` du cash disponible, alors que la rationale annonçait `1 % du capital`.

## Diagnostic

Le contrat existant interdisait déjà d'inventer des faits, mais cette règle restait générale. Le schéma structurel vérifiait seulement qu'un BUY/SELL possède une quantité strictement positive ; il ne pouvait pas garantir la cohérence sémantique entre `proposed_quantity`, prix, notionnel et pourcentage annoncé dans la rationale.

Le Risk Engine déterministe doit continuer à contrôler les limites et à autoriser, modifier ou refuser les propositions. Ajouter un deuxième moteur de sizing stratégique déterministe en amont créerait une autorité parallèle et dégraderait l'architecture canonique.

## Décision intégrée

### 1. Grounding factuel explicite

Le contrat multi-marchés indique que chaque affirmation factuelle de rationale ou de thèse doit être justifiable par un champ de l'input causal ou un résultat de tool read-only du même appel.

Les connaissances générales ou mémorisées du modèle ne constituent pas une source autorisée. En particulier, un prix isolé ne permet pas d'affirmer une tendance, un momentum, une volatilité, une consolidation, un breakout, un ratio inter-actifs, une classification technologique ou un fait fondamental.

Quand une information n'est pas fournie, elle doit être traitée comme inconnue et ne peut pas justifier la décision. Une condition future hypothétique peut être formulée comme condition d'invalidation ou de réévaluation, mais elle ne doit jamais être présentée comme une observation présente.

### 2. Références arithmétiques de sizing

`agent/grounding.py` dérive uniquement depuis le payload causal des références descriptives compactes par marché :

- `symbol`, `market_type` et `last_price` réellement fournis ;
- solde disponible de l'actif de cotation pour un marché SPOT ;
- notionnel correspondant à 1 % de ce solde de cotation ;
- quantité d'actif de base correspondant arithmétiquement à ce 1 % ;
- quantité SPOT de base disponible pour une vente ;
- `cash_available` et `equity` uniquement lorsqu'ils sont réellement fournis, avec leur référence à 1 %.

Ces valeurs sont purement arithmétiques. Elles ne sont ni une recommandation d'allocation, ni une limite Risk, ni un montant supposé intégralement dépensable. Aucun indicateur, tendance, signal ou fait de marché n'est dérivé.

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

Cas de régression :

```text
0.1 BTC × 98 250 EUR/BTC = 9 825 EUR
9 825 / 10 000 × 100 = 98.25 %
```

La même proposition ne peut donc pas être rationnellement décrite comme `1 % du capital`.

Pour un SELL SPOT, le contrat interdit de proposer plus que la quantité de base disponible. Si action, quantité et rationale ne peuvent pas être rendues cohérentes à partir des faits présents, HOLD reste une décision valide.

## Architecture préservée

Le changement est injecté au niveau canonique de `StrategyInstructionsClient` et s'applique au plan stratégique multi-marchés quel que soit le transport LLM. Il n'ajoute aucun appel LLM et ne crée aucun chemin spécifique Ollama parallèle.

Invariants inchangés :

- un seul Agent stratégique ;
- PAPER pour les premiers usages ;
- BUY / SELL / HOLD ;
- aucune sortie LLM directement vers Broker/Kraken ;
- Risk Engine déterministe avec autorité finale ;
- aucun sizing automatique ajouté à Risk ou au Broker ;
- aucun fait externe implicite ajouté au contexte causal ;
- aucun secret, prompt brut, réponse brute ou chaîne de pensée exposé.

## Fichiers du Batch 51.5 intégré

```text
backend/src/ai_spot_trader/agent/grounding.py
backend/src/ai_spot_trader/agent/strategy_client.py
backend/tests/test_batch51_5_grounding_sizing.py
docs/00_ETAT_ACTUEL.md
docs/51_5_GROUNDING_SIZING_OLLAMA.md
```

## Validation historique de préparation du patch

Avant intégration, l'environnement de livraison avait exécuté :

```text
python -m py_compile (grounding, strategy_client, test 51.5) : PASS
pytest standalone du calcul causal de sizing                 : PASS — 5/5
contrôle statique de l'injection multi-marchés               : PASS
reconstruction inverse de strategy_client.py                  : PASS
Git blob reconstruit = 6eb5cac2e6668dcfdc21504dcf7a5cf316a79148
contrôle lignes nouvelles <= 100 / espaces finaux            : PASS
```

Ces contrôles restent l'historique de la préparation pré-intégration ; ils ne remplacent pas les validations locales post-intégration ci-dessous.

## Validation locale post-intégration communiquée par l'opérateur

Tests ciblés :

```text
tests/test_batch51_5_grounding_sizing.py
tests/test_strategy_instructions_client.py
tests/test_multi_market_provider.py
tests/test_batch51_1_1_ollama_contract.py
```

Résultat :

```text
39 tests PASS
```

Suite backend complète :

```powershell
Push-Location backend
pytest -q
Pop-Location
```

Résultat communiqué :

```text
100 % PASS
```

Deux warnings de dépréciation externes seulement ont été observés : Starlette `httpx` / `testclient` et alias `anyio.abc.BlockingPortal`. Ils ne sont pas attribués au Batch 51.5.

`git diff --check` a été communiqué PASS ; les seuls messages associés étaient les avertissements Windows LF → CRLF.

## Smoke réel Ollama — grounding factuel

Modèle :

```text
qwen3.5:9b
```

Input volontairement pauvre :

```text
BTC/EUR = 98 250
ETH/EUR = 3 245
SOL/EUR = 184.20
cash EUR = 10 000
```

Résultat réel communiqué :

```text
elapsed = 15.11 s
BTC/EUR : HOLD
ETH/EUR : HOLD
SOL/EUR : HOLD
```

Le modèle n'a pas présenté comme faits observés de tendance, momentum, volatilité, ratio inter-actifs ou fondamentaux absents de l'input. Il a explicitement indiqué l'absence de thèse défendable, conservé le cash et laissé les `supporting_facts` vides lorsque les faits nécessaires n'étaient pas présents.

Conclusion :

```text
Grounding factuel réel Ollama : PASS
```

## Smoke réel Ollama — sizing, Structured Output et fail-closed

Avec un contexte Ollama `4096`, plusieurs sorties longues ont été tronquées ou incomplètes. Les erreurs observées incluaient notamment :

```text
Expecting ',' delimiter
Unterminated string
```

Ces sorties ont été rejetées avant Risk/Broker, conformément au comportement fail-closed.

Après passage du contexte à `8192`, `ollama ps` a confirmé pour la machine de test :

```text
qwen3.5:9b
PROCESSOR : 12%/88% CPU/GPU
CONTEXT   : 8192
```

Le léger offload CPU est accepté sur cette machine équipée d'une RTX 3060 Ti.

Un premier essai à `8192` a produit un JSON valide mais davantage de décisions que `max_decisions_per_cycle`. Le provider l'a rejeté via :

```text
AgentContractViolationError:
LLM decision plan exceeds max_decisions_per_cycle
```

Un second smoke de contrat plus explicite a produit exactement :

```text
BUY  BTC/EUR
HOLD ETH/EUR
HOLD SOL/EUR
```

Temps observé :

```text
28.57 s
```

Cas de sizing demandé :

```text
cash               = 10 000 EUR
cible arithmétique = 1 %
notionnel attendu  = 100 EUR
prix BTC/EUR       = 98 250 EUR
```

Quantité Ollama :

```text
0.0010178117048346 BTC
```

Cette quantité représente pratiquement exactement `100 EUR`, soit `1 %` du cash fourni. La rationale précisait que le BUY était imposé uniquement pour le test de contrat, qu'aucun signal/tendance/fondamental n'était supposé et que la quantité correspondait à 1 % des `10 000 EUR`.

Conclusion communiquée :

```text
Sizing quantitatif réel Ollama : PASS
Structured output/Pydantic     : PASS
Cardinalité finale             : PASS
Fail-closed                    : PASS
```

Réserve mineure non bloquante : une formulation de thèse a parlé de « sizing limits provided in input ». Il s'agissait d'une cible arithmétique de test, pas d'une limite Risk. Cette formulation ne constitue pas une décision architecturale.

## Recommandation opérationnelle locale Ollama

Pour `qwen3.5:9b` dans la configuration locale testée :

```text
contexte Ollama recommandé : 8192
```

Le contexte `4096` s'est révélé insuffisant dans les essais concernés pour garantir des réponses JSON complètes après le renforcement 51.5. Le contexte `8192` a permis les smokes réels validés ci-dessus.

Cette recommandation :

- décrit la configuration locale testée ;
- ne modifie aucun comportement du code ;
- n'est pas une limite du Risk Engine ;
- ne constitue ni une règle universelle ni une garantie pour tous les modèles ou matériels.

## Hors périmètre

Le Batch 51.5 n'ajoute pas de validateur NLP post-hoc des rationales, ne modifie pas les limites Risk, ne crée pas de sizing algorithmique stratégique, ne change pas la stratégie de trading et n'introduit ni fine-tuning ni apprentissage automatique à partir des backtests.
