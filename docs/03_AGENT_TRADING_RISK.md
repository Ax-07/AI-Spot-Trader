# 03 — Agent, Trading et Risk

## 1. Principe central

**L'Agent cherche, sélectionne et propose. Risk autorise, modifie ou refuse.**

Le Batch 18.2 donne à l'Agent la sélection du marché exécutable sans lui donner l'autorité
d'exécution.

## 2. Agent unique

Il n'existe toujours qu'un `OpenAIDecisionProvider` par runtime. Le même Agent intervient en deux
phases :

1. sélection du marché ;
2. décision finale sur le snapshot exécutable acquis par le backend.

Aucun second Agent scanner/trader n'est créé.

## 3. Phase de sélection

Entrée : `MarketSelectionInput`.

L'Agent voit :

- portefeuille complet ;
- univers PAPER exécutable typé ;
- agressivité ;
- éventuel contexte expérimental.

Il peut :

- choisir directement un marché ;
- appeler `list_markets` ;
- appeler `get_market_snapshot` ;
- comparer plusieurs symboles ;
- arrêter lui-même ses recherches.

Les budgets de tools restent des limites de ressources, jamais une stratégie.

## 4. Sélection explicite

La sortie structurée de sélection contient seulement :

```text
symbol
market_type
rationale
```

L'application ajoute identité, timestamp, traces et digest pour produire `MarketSelection`.

Le couple choisi doit être présent exactement dans `executable_markets`. `FUTURE` est refusé.

La rationale reste explicative et en français. La sélection n'est donc pas cachée dans la
rationale : elle possède ses propres champs structurés et son propre digest.

## 5. Acquisition exécutable

Une sélection valide ne suffit pas à trader. Le backend doit encore acquérir un `MarketState`
canonique via la source **execution**, distincte de la source research.

Pour `PERPETUAL`, le routeur exige :

- contexte derivative présent ;
- instrument `PERPETUAL` ;
- contrat `LINEAR`.

Un instrument inverse, future daté, inconnu ou hors univers échoue fermé.

## 6. Phase de décision finale

Entrée : `AgentInput` contenant le `MarketState` exécutable exact et le `MarketSelection`.

Le même Agent choisit :

```text
BUY
SELL
HOLD
```

Le chemin 18.2 ne relance pas les tools à cette phase. Les recherches antérieures sont déjà
attachées à `MarketSelection` et le marché d'exécution vient d'être acquis.

La décision doit respecter :

```text
DecisionCandidate.symbol      == AgentInput.market_state.symbol
DecisionCandidate.market_type == AgentInput.market_state.market_type
```

Elle ne peut pas sélectionner ETH puis décider BTC après le snapshot.

## 7. HOLD

HOLD reste un résultat stratégique valide après n'importe quelle recherche/sélection :

```text
Risk = ALLOW
ExecutionIntent = None
Broker non appelé
```

La sélection et les recherches restent malgré tout auditables.

## 8. SPOT

- `BUY` acquiert l'actif de base ;
- `SELL` réduit uniquement une position détenue ;
- aucun short ;
- aucun levier/marge ;
- changement de marché ne relâche aucune de ces règles.

## 9. PERPETUAL

- `BUY` peut ouvrir/augmenter LONG ou réduire SHORT ;
- `SELL` peut ouvrir/augmenter SHORT ou réduire LONG ;
- le LLM ne choisit ni levier ni `reduce_only` ;
- Risk impose marge, caps, liquidation et anti-reversal ;
- contrat linéaire et marge ISOLATED seulement dans ce batch.

## 10. Portfolio global

Le portefeuille n'est jamais filtré selon le symbole choisi. L'Agent et Risk disposent des :

- balances ;
- positions SPOT ;
- positions Derivatives ;
- expositions globales.

Pour un PERPETUAL sélectionné, le portfolio final est recapturé après le mark/funding du snapshot
d'exécution.

## 11. Risk Engine

Risk reste la seule autorité pour :

- quantité autorisée ;
- max notional ;
- whitelist ;
- solvabilité SPOT ;
- disponibilité de position ;
- exposition Derivatives ;
- leverage ;
- marge ;
- liquidation ;
- `reduce_only` ;
- anti-reversal.

Le nouvel univers exécutable est une frontière supplémentaire en amont, pas un remplacement de
Risk.

## 12. Broker

Le Broker reçoit seulement un `ExecutionIntent` déjà autorisé et **exactement le même
`MarketState`** que Risk.

Chaque Fill doit rester corrélé au `market_state_id`, au `pricing_as_of`, au prix de référence, au
symbole et au type de marché.

## 13. Erreurs

Les échecs techniques ne deviennent jamais un HOLD :

- sélection hors univers ;
- résultat LLM non conforme ;
- marché exécutable indisponible ;
- mismatch symbole/type ;
- contrat derivative non supporté ;
- timeout ;
- incohérence de corrélation.

Ils produisent un cycle `FAILED` avec métadonnées sanitizées.

## 14. Audit causal

L'ordre reconstructible est :

```text
MarketSelectionInput
-> recherches
-> MarketSelection
-> MarketState
-> AgentInput final
-> DecisionCandidate
-> RiskAssessment
-> ExecutionIntent
-> Fill
```

Une panne à chaque frontière conserve les artefacts déjà terminés.

## 15. Prompt

L'identifiant reste `agent-strategy-v4` conformément à la décision de ne pas le renommer dans ce
batch. Son texte décrit désormais les deux phases.

Dette expérimentale conservée : une future campagne comparative doit versionner explicitement la
politique/capacité de tools et de sélection, car le seul `prompt_version` ne suffit pas à décrire
tout l'environnement expérimental.

## 16. Interdits maintenus

- aucun LIVE ;
- aucune clé Kraken privée ;
- aucun LLM -> Broker ;
- aucun tool -> Broker/Risk ;
- aucun second Agent ;
- aucun scanner/ranking/opportunity score déterministe ;
- aucune obligation de trader ;
- aucun look-ahead ;
- aucune modification post-hoc d'une décision.
