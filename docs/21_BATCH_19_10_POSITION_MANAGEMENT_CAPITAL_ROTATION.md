# Batch 19.10 — Gestion stratégique des positions ouvertes et rotation du capital

## Statut

Batch intégré à GitHub `main` au commit fonctionnel :

```text
8643b9412bd19791e3cfd60884126ca0c300dc33
feat: add strategic position management and capital rotation
```

Commit précédent :

```text
105aaae47efbeed4a2208fcf036c09aa096f9351
docs: sync post-19.9C state
```

Le commit fonctionnel contient le correctif appliqué après la première validation locale et a été poussé après validation finale par l'opérateur.

## Objectif

Permettre au même Agent stratégique de considérer explicitement les positions déjà ouvertes comme des opportunités de gestion à chaque cycle, y compris lorsqu'une nouvelle exposition reste possible.

Le comportement reste multi-cycle :

```text
portefeuille
→ réévaluation d'une position ouverte ou recherche d'une nouvelle opportunité
→ BUY / SELL / HOLD sur un seul marché
→ Risk
→ Broker PAPER éventuel
→ portefeuille mis à jour
→ cycle suivant
```

Aucun BUY n'est imposé après un SELL. Aucun SELL n'est imposé parce qu'une position est gagnante, perdante ou détenue depuis une durée donnée.

Principe préservé : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Audit de départ

### Confirmé avant intégration

- `CapacityEvaluator` calculait déjà les marchés correspondant aux positions ouvertes via `management_markets`.
- En mode `MANAGEMENT`, le même Agent sélectionnait uniquement parmi ces marchés et pouvait produire HOLD ou une réduction/clôture.
- En mode `NORMAL`, l'Agent recevait le portefeuille complet mais `CapacityAssessment.management_markets` n'était pas renseigné lorsque de la capacité d'ouverture existait.
- `DynamicMarketTradingCycleRunner` réinjectait déjà les positions ouvertes dans l'univers effectif afin qu'une disparition de watchlist ne les rende pas ingérables.
- `AssetPosition` exposait quantité, quantité disponible, PRU, coût de revient restant, mark, valeur de marché et P&L non réalisé.
- Le ledger PAPER incluait le débit BUY réel dans `remaining_cost_basis`; les frais d'entrée étaient donc déjà incorporés au coût restant.
- `estimate_paper_execution()` et `PaperExecutionCostModel` constituaient la source canonique de calcul des frais/spread/slippage de sortie PAPER.
- `strategic-mtf-v1` construisait un snapshot pour tout l'univers de Market Selection puis le réutilisait pour la décision finale.
- `_evaluate_spot()` appliquait `max_order_notional` avant la distinction BUY/SELL : un SELL supérieur au plafond était déjà réduit lorsque `allow_quantity_reduction=True`.

### Problème traité

Le mode `MANAGEMENT` rendait les positions ouvertes explicitement prioritaires seulement lorsque la capacité d'ouverture devenait indisponible ou incertaine. En `NORMAL`, l'Agent pouvait sélectionner une position ouverte, mais le contrat ne lui signalait pas avec la même clarté quels marchés représentaient déjà du capital engagé ni l'économie nette d'une sortie immédiate.

Le Batch 19.10 supprime ce biais structurel sans créer de seconde autorité stratégique.

## Architecture retenue

### Option C — généralisation des primitives existantes

Aucun second Agent, aucun nouveau pipeline de décision et aucun modèle persistant parallèle n'ont été ajoutés.

1. `CapacityAssessment.management_markets` est renseigné en `NORMAL` comme en `MANAGEMENT`.
2. Le mapping portefeuille -> marchés ouverts est centralisé par `open_position_markets()` puis réutilisé par Capacity et Dynamic Discovery.
3. Le client d'instructions Campaign construit un contexte descriptif `position-management-v1` à partir des mêmes faits canoniques déjà présents dans l'input.
4. Les estimations de sortie SPOT utilisent exclusivement `PaperExecutionCostModel` / `estimate_paper_execution`.
5. Le contrat Agent protégé rappelle que la gestion du capital engagé fait partie de la responsabilité stratégique de l'unique Agent.
6. Le schéma de sortie Agent reste inchangé : une seule décision finale `BUY` / `SELL` / `HOLD` avec quantité proposée.

Cette solution préserve `agent-contract-v1`, les digests expérimentaux historiques et les modèles Pydantic persistés existants.

### Frontière architecturale finale

Le premier patch plaçait le calcul économique directement sous `agent/`, ce qui introduisait un import interdit vers `broker.pricing`. Le correctif intégré retient la frontière suivante :

```text
agent/position_management.py
→ façade de compatibilité
→ trading/position_management.py
→ broker/pricing.py + risk/capacity.py
```

Le calcul économique canonique de gestion de position vit donc côté trading. Le package Agent ne dépend pas directement du broker ni du Risk Engine pour cette primitive.

## `position-management-v1`

Le contexte n'est produit que lorsqu'au moins une position ouverte correspond à l'univers exécutable de la phase courante.

Pour une position SPOT, il expose notamment :

```text
symbol
quantity
available_quantity
can_reduce_now
can_fully_close_now
average_entry_price
remaining_cost_basis
mark_price
market_value
gross_unrealized_pnl
realized_pnl_to_date
```

Lorsque les coûts PAPER et un mark sont disponibles, il ajoute pour la quantité actuellement disponible :

```text
estimated_execution_price
estimated_exit_fee
estimated_exit_spread_cost
estimated_exit_slippage_cost
estimated_net_exit_proceeds
estimated_released_cost_basis
estimated_net_pnl_if_available_sold_now
estimated_net_pnl_if_closed_now  # renseigné seulement si toute la position disponible peut être clôturée
```

Ces champs sont descriptifs. Le contexte ne contient aucun `should_sell`, score de prise de profit, seuil P&L ou décision automatique.

### Comptabilité de sortie

Le ledger PAPER stocke dans `remaining_cost_basis` le coût réellement débité à l'entrée. Pour une vente partielle, le coût libéré est donc :

```text
remaining_cost_basis * available_quantity / quantity
```

Le P&L net hypothétique de la quantité disponible est :

```text
estimated_net_exit_proceeds - estimated_released_cost_basis
```

Les frais d'entrée ne sont jamais ajoutés une deuxième fois.

## Mode NORMAL

Quand du cash reste disponible :

- `CapacityAssessment.mode` reste `NORMAL` ;
- la Discovery peut continuer à rechercher de nouvelles opportunités ;
- `management_markets` liste néanmoins les positions ouvertes sélectionnables ;
- le même Agent peut choisir une position ouverte ou un nouveau marché ;
- la décision finale reste BUY / SELL / HOLD sur un seul marché.

Aucune priorité déterministe n'est imposée entre gestion et nouvelle ouverture.

## Mode MANAGEMENT

Le comportement existant reste le garde-fou :

- nouvelle recherche d'ouverture désactivée ;
- sélection limitée aux positions ouvertes ;
- Risk refuse les actions qui augmenteraient l'exposition ;
- HOLD ou réduction/clôture restent possibles.

## SCALP / SWING

Le batch ne modifie ni `trading-style-map-v1` ni `strategic-mtf-v1`.

La guidance Agent est seulement clarifiée :

- SCALP peut conduire l'Agent à réévaluer plus fréquemment l'utilité du capital engagé ;
- SWING peut conduire l'Agent à conserver plus longtemps une position si la thèse multi-timeframe reste valide ;
- aucun timer, seuil de profit ou indicateur ne déclenche automatiquement une vente.

Le style influence donc le contexte et l'interprétation stratégique, jamais une règle déterministe de sortie.

## Décision Risk — `risk_max_order_notional`

La sémantique existante est conservée explicitement : `max_order_notional` reste un plafond de taille notionnelle **par ordre**, indépendamment du fait que l'ordre augmente ou réduise l'exposition.

Exemple :

```text
position SPOT = 250 USD
max_order_notional = 100 USD
Agent -> SELL toute la position
Risk -> MODIFY vers environ 100 USD
```

La clôture complète peut donc nécessiter plusieurs décisions stratégiques sur plusieurs cycles.

Raisons du maintien :

- le nom et l'implémentation existants représentent une limite d'ordre, pas seulement une limite d'augmentation d'exposition ;
- l'exemption des SELL changerait silencieusement la sémantique d'un paramètre Risk déjà exposé et persisté ;
- le batch vise la rotation stratégique, pas une redéfinition générale des limites d'exécution.

Les protections existantes restent impératives : actif détenu, quantité disponible, aucun short SPOT, Risk autorité finale.

## Rotation du capital

La rotation est volontairement multi-cycle :

```text
cycle N   : l'Agent choisit éventuellement SELL sur une position détenue
Risk      : autorise, modifie ou refuse la quantité
Broker    : exécution PAPER éventuelle
ledger    : cash/position mis à jour
cycle N+1 : capacité et opportunités recalculées depuis le nouvel état
```

Un SELL peut donc libérer du capital qui sera réévalué lors d'un cycle ultérieur. Aucun second Agent, aucun portfolio manager autonome et aucune règle `SELL -> BUY` ne sont introduits.

## Explicabilité

Le pipeline durable existant reste la source d'audit :

- `CapacityAssessment.to_payload()` persiste `management_markets` aussi en `NORMAL` ;
- `MarketSelectionInput` conserve le `PortfolioState` complet ;
- `MarketSelection` identifie le marché réellement choisi ;
- `AgentInput`, décision, Risk assessment, intent, fills et portefeuille post-trade restent inchangés ;
- le contexte `position-management-v1` est déterministement reconstructible depuis ces faits et la configuration de coûts Campaign.

Aucune seconde base d'audit n'est créée.

## Compatibilité

Préservés :

- un seul Agent ;
- PAPER ;
- SPOT sans short ;
- composants PERPETUAL historiques ;
- `agent-contract-v1` et schémas de sortie ;
- Campaigns historiques sans `trading_style` ;
- manifests/digests historiques ;
- Control Plane et lifecycle Session ;
- aucun changement SQL ;
- backend indépendant du frontend.

Le `AGENT_SYSTEM_PROMPT` historique reste inchangé pour les protocoles expérimentaux historiques. La clarification de gestion est portée par le contrat protégé Campaign composé par `StrategyInstructionsClient`.

Le correctif final préserve aussi exactement les instructions historiques des inputs legacy sans `ExecutionCostContext` : aucune section `position-management-v1` n'y est ajoutée.

## Fichiers fonctionnels du batch

```text
backend/src/ai_spot_trader/risk/capacity.py
backend/src/ai_spot_trader/trading/discovery_runner.py
backend/src/ai_spot_trader/trading/position_management.py
backend/src/ai_spot_trader/agent/position_management.py  # façade de compatibilité
backend/src/ai_spot_trader/agent/strategy_client.py
backend/src/ai_spot_trader/agent/prompt.py
backend/tests/test_position_management_rotation.py
```

## Tests ciblés

Le module `backend/tests/test_position_management_rotation.py` couvre notamment :

- position ouverte visible en `NORMAL` avec cash disponible ;
- mapping canonique des positions ouvertes ;
- estimation nette de sortie avec fee/spread/slippage ;
- absence de double comptage du coût d'entrée ;
- sortie partielle ;
- sélection d'une position ouverte par le même Agent en mode normal ;
- présence du contexte SCALP dans les instructions ;
- absence de règle automatique de prise de profit ;
- sémantique explicite de `max_order_notional` sur un SELL SPOT réducteur ;
- parsing transport compatible avec les modèles Pydantic stricts ;
- respect de la frontière d'import Agent ;
- compatibilité exacte des instructions Campaign legacy.

Les tests existants couvrent en complément la Discovery dynamique, le cycle MANAGEMENT, le Risk anti-short/anti-oversell, le broker/ledger PAPER, l'explicabilité et le contexte multi-timeframe.

## Hors périmètre confirmé

- LIVE ;
- take-profit fixe ;
- stop-loss/trailing stop/timer déterministe ;
- second Agent ;
- ranking technique automatique ;
- short ou levier SPOT ;
- BUY obligatoire après SELL ;
- refonte UX.

## Validation et correctif après première livraison

### Première validation locale opérateur

- `python -m pytest backend/tests/test_position_management_rotation.py` : `6 passed, 1 failed` ;
- `python -m pytest backend/tests` : `633 passed, 3 failed, 2 warnings`.

Les trois échecs étaient bornés à deux causes :

1. `ExecutableMarket.model_validate(...)` refusait la chaîne JSON `SPOT` avec le modèle Pydantic strict ;
2. le nouveau module sous `agent/` importait directement `ai_spot_trader.broker.pricing`, interdit par la frontière d'architecture existante.

Le troisième échec correspondait à la même cause de parsing sur le test Trading Style legacy avant son assertion de compatibilité.

### Correctif intégré

- parsing transport via `ExecutableMarket.model_validate_json(...)` ;
- implémentation du calcul déplacée dans `trading/position_management.py` ;
- façade `agent/position_management.py` conservée sans dépendance directe Risk/Broker ;
- absence de section `position-management-v1` pour les inputs legacy sans `ExecutionCostContext`, ce qui conserve exactement leur prompt historique ;
- tests ciblés ajoutés pour la frontière d'import, le parsing strict et la compatibilité legacy.

### Validation finale opérateur

Après application du correctif :

- tests ciblés Batch 19.10 : `11 passed` ;
- suite backend complète : `638 passed, 2 warnings` ;
- les deux warnings sont des dépréciations FastAPI/Starlette préexistantes et ne constituent pas des échecs du Batch 19.10 ;
- `git diff --cached --check` : PASS ;
- `git diff --check` : aucune erreur, seulement les warnings Windows LF -> CRLF.

Aucun test backend supplémentaire n'est requis pour la présente synchronisation documentaire tant qu'aucun fichier de code n'est modifié.
