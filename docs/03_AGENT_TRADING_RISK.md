# 03 — Agent, Trading et Risk

## 1. Principe central

**L'Agent cherche. L'Agent analyse. L'Agent propose BUY / SELL / HOLD. Risk autorise, modifie ou refuse.**

Les tools du Batch 18.1 ajoutent des faits au contexte de raisonnement ; ils ne déplacent aucune autorité d'exécution.

## 2. Agent unique

L'Agent reçoit toujours un `AgentInput` complet :

- `MarketState` du symbole du cycle ;
- `PortfolioState` complet ;
- `cycle_id` et timestamps ;
- agressivité + contexte versionné ;
- éventuel manifeste expérimental.

Le provider reste `OpenAIDecisionProvider` pour Luna et Sol. Il n'existe ni Agent scanner ni Agent trader secondaire.

## 3. Recherche optionnelle

Avec le registry activé, l'Agent peut appeler :

- `list_markets` pour voir des marchés/métadonnées factuels ;
- `get_market_snapshot` pour examiner un snapshot SPOT ou PERPETUAL normalisé.

L'Agent choisit lui-même :

- s'il recherche ou non ;
- quel symbole examiner ;
- combien de recherches effectuer dans le budget technique ;
- quand arrêter et produire sa décision.

Le code ne calcule aucun score d'opportunité, classement, scanner momentum ou présélection stratégique.

## 4. Budget non stratégique

Les limites de nombre d'appels, timeout et taille de résultat sont des garde-fous d'ingénierie. Elles ne doivent jamais être interprétées comme une préférence de marché ou une instruction de trading.

Un dépassement de budget est une erreur technique du stade Agent, pas un HOLD automatique.

## 5. Sémantique des erreurs de tools

Une erreur de données/exécution d'un tool est transformée en résultat borné de forme factuelle, par exemple :

```text
{"ok": false, "error": {"type": "KrakenConnectionError"}}
```

Le message brut fournisseur n'est pas exposé au modèle ni au journal. L'Agent peut décider de poursuivre ses recherches ou de conclure avec les faits disponibles.

Un tool inconnu ou des arguments non conformes sont refusés avant handler et font échouer la boucle.

## 6. Symbole final en Batch 18.1

La validation historique reste en place :

```text
DecisionCandidate.symbol == AgentInput.market_state.symbol
```

Ainsi, rechercher un autre marché **n'autorise pas** à le trader dans ce batch. Le symbole de Risk/Broker reste celui du `MarketState` initial du runner.

Le Batch 18.2 devra traiter explicitement le choix du marché exécutable avant la construction du snapshot causal final.

## 7. SPOT

- `BUY` augmente une position de base ;
- `SELL` ne réduit qu'une quantité détenue/disponible ;
- aucun short, levier ou marge ;
- les tools n'assouplissent aucune de ces règles.

## 8. Derivatives

- `BUY` peut ouvrir/augmenter LONG ou réduire SHORT ;
- `SELL` peut ouvrir/augmenter SHORT ou réduire LONG ;
- levier et `reduce_only` restent déterministes ;
- Risk impose marge, caps, liquidation et anti-reversal ;
- un snapshot de recherche Derivatives ne marque jamais le ledger.

## 9. DecisionCandidate et traces

La sortie structurée LLM reste limitée à :

```text
action
symbol
proposed_quantity
rationale
```

Les `tool_traces` ne sont **pas** fournis par le LLM. L'application les ajoute au `DecisionCandidate` après exécution des tools. Le modèle ne peut donc ni fabriquer ni supprimer ses traces d'accès aux données.

## 10. Risk

Risk reste synchrone et déterministe. Il reçoit le `DecisionCandidate`, le `MarketState` causal du cycle et le `PortfolioState`.

Il peut produire :

- `ALLOW` ;
- `MODIFY` avec quantité strictement réduite ;
- `REJECT`.

Un HOLD valide reste `ALLOW` sans `ExecutionIntent`. Aucun tool ne peut appeler Risk directement.

## 11. Broker

Le Broker reçoit seulement un `ExecutionIntent` déjà autorisé par Risk. Aucun nom de function tool ne correspond à `buy`, `sell`, `execute`, `place_order` ou équivalent.

## 12. Causalité et audit

Chaque tool call possède des timestamps. Une décision ne peut être créée avant la fin d'une trace qu'elle utilise. Les recherches déjà terminées restent persistées même si le modèle échoue ensuite à produire une décision conforme.

Le digest du cycle intègre ces traces afin d'empêcher qu'une modification du contexte de recherche soit invisible dans l'identité durable.

## 13. Prompt

L'identifiant demandé reste `agent-strategy-v4`. Le texte précise désormais la possibilité d'utiliser des tools read-only factuels et la limitation cross-symbol de Batch 18.1. Les valeurs contractuelles `BUY`, `SELL`, `HOLD`, `SPOT`, `PERPETUAL`, `FUTURE`, `LONG`, `SHORT` restent inchangées et `rationale` reste en français.

### Dette à traiter avant expériences comparatives

Comme la capacité de recherche change le contexte accessible à l'Agent tout en conservant l'identifiant `agent-strategy-v4` imposé pour ce batch, une future campagne comparative doit versionner explicitement la **politique de tools / protocole Agent** dans son manifeste au lieu de supposer que le seul `prompt_version` distingue tous les environnements expérimentaux.

## 14. Interdits maintenus

- aucun LIVE ;
- aucune clé Kraken privée ;
- aucun LLM -> Broker ;
- aucun tool -> Broker/Risk ;
- aucun second Agent ;
- aucune obligation de trader ;
- aucun look-ahead ;
- aucun signal déterministe transformé en BUY/SELL/HOLD.
