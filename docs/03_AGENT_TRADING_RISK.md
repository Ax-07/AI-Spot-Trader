# 03 — Agent, trading et Risk

## 1. Principe d'autorité

**L'Agent propose. Le Risk Engine autorise, modifie ou refuse.**

Le Batch 19.13 change la cardinalité d'un cycle, pas la hiérarchie d'autorité. Le déterministe prépare les faits et applique les contraintes ; l'Agent conserve le jugement stratégique ; Risk conserve l'autorité finale sur chaque décision.

## 2. Un seul Agent, phases distinctes

```text
DISCOVERY
MarketDiscoveryInput -> même Agent -> WatchlistSelection

CYCLE STRATÉGIQUE
CycleDecisionPlanInput -> même Agent -> CycleDecisionPlan ordonné

EXÉCUTION DU PLAN
D1 -> Risk -> Broker éventuel
D2 -> Risk -> Broker éventuel
...
Dn -> Risk -> Broker éventuel
```

La discovery utilise toujours le même Agent stratégique et ne constitue pas un second Agent. Au stade décisionnel du cycle, un seul appel stratégique produit la trajectoire ordonnée plutôt qu'une succession d'appels opportunistes.

Le protocole protégé courant de ce stade est `strategic-multi-market-plan-v1`. Le contrat singleton historique (`MarketSelectionInput -> AgentInput`) reste conservé pour compatibilité et replay, mais il n'est plus injecté comme contrat final du nouveau chemin de planification.

## 3. Contrat de plan multi-décisions

Le plan peut contenir plusieurs `BUY`, `SELL` et `HOLD` sur des marchés distincts de l'univers causal du cycle.

Contraintes :

- ordre explicite ;
- symboles/types limités aux `market_states` fournis ;
- pas de marché inventé ;
- pas de doublon `symbol + market_type` ;
- `max_decisions_per_cycle` configurable ;
- défaut `6` ;
- limite dure `20` ;
- sortie structurée validée fail-closed.

Le schéma Structured Outputs et la validation Pydantic portent le même contrat quantité/action :

```text
BUY  -> proposed_quantity > 0
SELL -> proposed_quantity > 0
HOLD -> proposed_quantity = null
```

Une sortie qui ne respecte pas ce contrat est un échec Agent. Elle n'est jamais réparée silencieusement, convertie en `HOLD`, ni envoyée à Risk.

L'ordre du plan a un sens causal : il détermine l'ordre d'évaluation Risk et d'exécution éventuelle.

## 4. Ce que fait le déterministe

Le déterministe peut :

- filtrer type de marché, quote, statut tradable, fraîcheur des données et whitelist ;
- calculer contexte candles, coûts, portefeuille, exposition et contraintes ;
- appliquer Risk ;
- exécuter/persister en PAPER lorsqu'un `ExecutionIntent` autorisé existe.

Il ne calcule pas un ranking stratégique destiné à remplacer le plan Agent, ne force pas BUY/SELL et ne choisit pas une rotation automatique.

## 5. NORMAL et MANAGEMENT

### NORMAL

Lorsque la capacité de nouvelle exposition existe, l'univers peut contenir watchlist et positions ouvertes. Le plan Agent peut arbitrer entre plusieurs marchés et plusieurs actions dans le même cycle.

### MANAGEMENT

Lorsque la capacité d'ouverture est indisponible ou incertaine :

- pas de refresh discovery destiné à de nouvelles ouvertures ;
- les positions ouvertes restent l'univers de gestion ;
- réduction, clôture ou `HOLD` restent stratégiques ;
- Risk refuse toute augmentation d'exposition incompatible.

Le passage au multi-décisions n'autorise pas une décision à sortir de l'univers de marché ou des contraintes de capacité.

## 6. Watchlist + positions ouvertes

Invariant :

```text
univers effectif = watchlist IA actuelle + toutes les positions ouvertes gérables
```

Un retrait de watchlist n'est jamais une clôture forcée. Une position ouverte reste gérable jusqu'à sa clôture.

## 7. SPOT — règles spécifiques

Le runtime PAPER canonique autorise les marchés `SPOT` et `PERPETUAL` linéaires. Les règles SPOT restent strictes : `BUY` acquiert la base et `SELL` réduit uniquement un actif effectivement détenu. Aucun short, levier ni margin n'est autorisé sur SPOT.

Dans un plan multi-décisions, Risk réévalue la quantité disponible après chaque exécution. Un SELL SPOT ne peut donc pas être autorisé à partir d'un inventaire obsolète.

## 8. PERPETUAL — support PAPER canonique

Les marchés `PERPETUAL` linéaires sont supportés dans les Sessions PAPER et dans la discovery dynamique lorsque le type est présent dans l'univers bootstrap autorisé.

Sémantique stratégique :

- `BUY` exprime ou augmente une exposition LONG, ou réduit une position SHORT existante ;
- `SELL` exprime ou augmente une exposition SHORT, ou réduit une position LONG existante ;
- l'Agent ne choisit jamais le levier, la marge, `reduce_only` ni les limites d'exposition.

Le Risk Engine déterministe conserve l'autorité finale : marge isolée, levier configuré, plafond de levier, notionnel par position, exposition dérivés totale, buffer de liquidation et logique `reduce_only` restent contrôlés hors LLM. Une décision opposée ne peut pas inverser librement une position.

`FUTURE` daté reste interdit à l'exécution et à la discovery.

## 9. Évaluation Risk séquentielle

Pour chaque décision `Di`, Risk reçoit le portefeuille courant après `D1 ... D(i-1)`.

```text
P0 -> Risk(D1) -> exécution éventuelle -> P1
P1 -> Risk(D2) -> exécution éventuelle -> P2
...
```

Cette règle empêche le plan de réserver implicitement plusieurs fois le même cash ou le même inventaire.

Un `REJECT` n'arrête pas le reste du plan. Un `HOLD` n'arrête pas non plus le reste du plan. Les décisions suivantes continuent avec le portefeuille réellement courant.

## 10. Rotation du capital

Le Batch 19.10 autorisait déjà la gestion stratégique des positions et la rotation sur plusieurs cycles. Le Batch 19.13 permet aussi une trajectoire causale intra-cycle, par exemple :

```text
SELL marché A
-> Risk + fill PAPER
-> cash libéré
-> BUY marché B plus tard dans le même plan
-> Risk réévalué sur le nouveau portefeuille
```

Cet exemple n'est pas une règle. Il n'existe aucun automatisme `SELL -> BUY`, aucun take-profit fixe et aucun seuil P&L déterministe imposant la rotation.

## 11. HOLD, REJECT et audit

Toutes les décisions du plan sont auditables, y compris :

- `HOLD` ;
- `BUY`/`SELL` rejeté par Risk ;
- `BUY`/`SELL` modifié par Risk ;
- décisions ayant produit une intention/fill ;
- trajectoires interrompues par une erreur technique.

La rationale Agent et les raisons Risk restent deux catégories distinctes. L'UI ne fabrique aucune causalité absente.

## 12. Échec Agent et diagnostic sécurisé

Un plan vide, un JSON invalide, une violation du contrat action/quantité, un dépassement de limite, un doublon ou un marché hors univers échoue avant Risk.

Les erreurs sont catégorisées pour l'opérateur sans persister la réponse LLM brute, un secret, une clé API ou un prompt secret. Il n'existe aucun retry LLM sémantique destiné à « réparer » une décision invalide ; l'invariant d'un seul appel stratégique de planification par cycle est mainten.

## 13. Échec technique et rollback PAPER

Une erreur technique Risk ou Broker transforme le cycle en `FAILED`.

Le runner audité restaure le checkpoint du ledger PAPER pris au début du cycle afin qu'aucune mutation économique partielle de la trajectoire ne subsiste.

Le rollback économique ne supprime pas l'information d'audit nécessaire pour comprendre l'échec.

## 14. Causalité / no-look-ahead

Aucun candidat, snapshot, candle ou contexte ne peut introduire une donnée postérieure au temps de décision concerné. `history_as_of(...)` reste la primitive de lecture causale pour les candles stratégéques.

L'ordre intra-cycle est causal mais n'autorise aucun accès au futur : la décision suivante observe uniquement les effets déjà produits par les étapes précédentes et les faits disponibles dans le contexte du cycle.

## 15. Persistence 1:N et compatibilité

Migration Batch 19.13 :

```text
0006_paper_control_plane
-> 0007_multi_decision_cycles
```

Un cycle peut désormais posséder plusieurs décisions, plusieurs évaluations Risk et plusieurs intentions d'exécution ordonnées.

Les anciens cycles mono-décision restent lisibles sans réécriture de leur historique.

## 16. Analytics

Le nombre de décisions n'est pas le nombre de trades. Les analytics utilisent les fills/trades économiques réellement exécutés.

Un `HOLD` ou un `REJECT` reste important pour l'audit mais n'incrémente pas artificiellement les métriques d'exécution.

## 17. Frontend

Le frontend peut afficher :

- watchlist effective ;
- contexte de marché ;
- trajectoire ordonnée des décisions ;
- rationale de chaque décision ;
- résultat Risk ;
- intentions/fills réellement persistés ;
- portefeuille/P&L backend.

Il ne peut pas produire un ranking, recalculer Risk, inventer un fill ou réordonner la causalité.

## 18. Interdits maintenus

- aucun LIVE implicite ;
- aucun second Agent ;
- aucun second appel stratégique de « réparation » du plan ;
- aucun ranking déterministe remplaçant le jugement stratégique ;
- aucun ordre direct LLM/tool ;
- aucun contournement Risk ;
- aucun `FUTURE` daté ; aucun short/levier/margin sur SPOT ; aucun contournement des contrôles de levier, marge ou exposition PERPETUAL ;
- aucun look-ahead ;
- aucune obligation de trader ;
- aucun calcul financier canonique déporté dans le frontend ;
- aucun effacement d'historique ;
- aucune promesse de rendement.
