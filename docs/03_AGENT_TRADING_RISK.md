# 03 — Agent, Trading et Risk

## 1. Principe central

**L'Agent cherche, sélectionne et propose. Risk autorise, modifie ou refuse.**

Le Batch 18.2 donne à l'Agent la sélection du marché exécutable sans lui donner l'autorité
d'exécution. Le Batch 18.5 ne change pas ce comportement : il le rend explicitement versionné
pour les futures expériences contrôlées.

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

Le chemin causal ne relance pas les tools à cette phase. Les recherches antérieures sont déjà
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

## 15. Prompt et protocole expérimental

L'identifiant du prompt reste `agent-strategy-v4`. Le Batch 18.5 n'en modifie ni la stratégie ni
le texte.

Pour les futures expériences multi-marchés, `paper-experiment-v3` représente désormais le contexte
stratégique qui était auparavant implicite :

- univers exécutable exact `symbol + market_type` ;
- identité du protocole de sélection à deux phases ;
- tools autorisés pendant la sélection et absents pendant la décision finale ;
- digest des définitions OpenAI réellement exposées ;
- budget maximal de calls ;
- timeout par tool ;
- taille maximale du résultat ;
- limite maximale de `list_markets`.

Le provider valide cette identité contre sa configuration active **avant l'appel LLM**. Le runner
valide l'univers typé du manifeste contre son univers exécutable avant le premier cycle Agent.
Une divergence échoue fermé au lieu de produire une expérience faussement comparable.

`paper-experiment-v1` et `paper-experiment-v2` restent des identités historiques séparées. Elles ne
sont pas réinterprétées comme si elles contenaient ces nouvelles informations.

## 16. Identité des tools

Le Batch 18.5 ne repose pas sur un simple numéro manuel pour identifier la capacité tools.
`ReadOnlyToolRegistry` calcule un digest canonique à partir de `openai_tools`, c'est-à-dire les
définitions de fonctions effectivement présentées au modèle, dans un ordre déterministe.

Les limites runtime sont enregistrées en plus du digest, car elles peuvent modifier la quantité de
recherche réellement accessible à l'Agent sans nécessairement modifier la forme des fonctions.
La limite `list_markets` est lue depuis le schéma effectif du tool plutôt que recopiée depuis une
constante indépendante.

## 17. Comparaisons Luna/Sol

Le `experiment_group_digest` v3 inclut tous les facteurs contrôlés ci-dessus. Il exclut seulement :

- `llm_model`, variable comparée ;
- `replicate_index`, répétition de la même condition expérimentale.

Une différence d'univers typé, de politique de sélection, de définition de tools ou de borne
empêche donc deux runs d'appartenir au même groupe contrôlé.

## 18. Interdits maintenus

- aucun LIVE ;
- aucune clé Kraken privée ;
- aucun LLM -> Broker ;
- aucun tool -> Broker/Risk ;
- aucun second Agent ;
- aucun scanner/ranking/opportunity score déterministe ;
- aucune obligation de trader ;
- aucun look-ahead ;
- aucune modification post-hoc d'une décision.
