# 50.1 — Mémoire de thèse stratégique des positions

## 1. Statut du batch

Base auditée :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 8a0054091c39079dfc5d2c5a9504470b2fbf9493
Commit     : docs: close batch 49.4 integration
```

Le présent document décrit le patch Batch 50.1. Son intégration GitHub et la validation complète locale doivent être effectuées après extraction du ZIP.

## 2. Problème

Le pipeline intégré savait déjà construire un univers SPOT/PERPETUAL, injecter le contexte multi-timeframes et Radar/Analytics, demander un plan `BUY / SELL / HOLD`, appliquer Risk puis exécuter/persister en PAPER.

La faiblesse restante était la continuité entre cycles : la rationale d'une décision était auditée, mais la thèse qui avait conduit à une exposition ouverte n'était pas remise au cycle suivant sous forme d'état structuré. Une position pouvait donc être réanalysée comme un cas presque neuf à chaque cycle.

Le Batch 50.1 transforme cette continuité en **fait applicatif explicite**.

## 3. Décision architecturale

Trois options ont été auditées :

### Option A — table dédiée

Avantages : état actif direct et lifecycle explicite. Inconvénient : nouvelle responsabilité persistante parallèle à la persistence de cycle existante.

### Option B — reconstruction depuis les audits/rationales

Avantage : pas de colonne/table supplémentaire. Rejetée car une rationale historique n'est pas un contrat de thèse et ne permet pas de distinguer proprement état actif, revue courante et motivation historique réellement connue.

### Option C — faits de cycle + projection canonique

**Retenue.**

La persistence de cycle possède déjà l'atomicité nécessaire avec le portefeuille et la lineage des `paper_run`. Le Batch 50.1 ajoute donc :

```text
decision_plan_payload
  -> contient les thesis_updates proposées/revues par l'Agent

audit_cycles.strategic_thesis_state_payload
  -> snapshot des seules thèses encore actives après un cycle COMPLETED
```

Le snapshot n'est pas un nouvel historique parallèle : l'historique détaillé reste dans les plans/cycles immuables, tandis que le snapshot sert de projection canonique rapide pour le prochain cycle et le recovery.

## 4. Contrats de domaine

Nouveau module :

```text
backend/src/ai_spot_trader/domain/strategic_thesis.py
```

### 4.1 Statuts

```text
NEW
CONFIRMED
WEAKENING
INVALIDATED
COMPLETED
```

Ces statuts sont stratégiques et descriptifs.

Règle absolue :

```text
INVALIDATED != SELL automatique
COMPLETED   != SELL automatique
```

### 4.2 Mise à jour structurée de thèse

`StrategicThesisUpdate` contient :

- `status` ;
- `horizon` ;
- `thesis_summary` ;
- `supporting_facts` bornés ;
- `invalidation_conditions` bornées ;
- `review_summary`.

Aucun champ ne stocke une chaîne de pensée cachée, un transcript complet du LLM ou une justification non bornée.

### 4.3 Thèse active

`ActiveStrategicThesis` porte notamment :

- `thesis_id` ;
- `symbol` ;
- `market_type` ;
- `side` ;
- `origin` ;
- `created_at` ;
- `activated_at` ;
- `horizon` ;
- `thesis_summary` ;
- faits de support ;
- conditions d'invalidation ;
- `status` ;
- `last_review` ;
- `updated_at`.

Origines :

```text
AGENT_OPENING
LEGACY_ADOPTION
```

`LEGACY_ADOPTION` ne prétend pas connaître la raison historique de l'entrée. Elle signifie uniquement qu'une nouvelle thèse de gestion a été créée à partir d'un cycle post-50.1 pour une exposition déjà existante.

## 5. Contexte remis à l'Agent

`CycleDecisionPlanInput` possède un nouveau champ optionnel :

```text
strategic_position_context
```

Il contient uniquement les positions ouvertes correspondant aux `market_states` du cycle. Pour chaque exposition :

```text
symbol
market_type
side
quantity
memory_state
thesis éventuelle
```

États :

```text
ACTIVE
UNAVAILABLE_LEGACY
```

`UNAVAILABLE_LEGACY` est explicite et ne contient aucune thèse fabriquée.

Le contexte est :

- typé ;
- borné ;
- trié déterministement ;
- sérialisable ;
- causal ;
- limité aux positions réellement ouvertes/gérables.

## 6. Un seul appel Agent

Nouveau décorateur :

```text
StrategicThesisContextDecisionProvider
```

Il suit le pattern déjà utilisé par le contexte multi-timeframes et le contexte Radar :

```text
lire la mémoire durable
-> attacher strategic_position_context
-> revalider CycleDecisionPlanInput
-> delegate.generate_decision_plan(...) UNE SEULE FOIS
```

Il n'existe aucun second Agent de mémoire.

Le plan possède désormais :

```text
thesis_updates: tuple[StrategicThesisUpdate | None, ...]
```

aligné sur l'ordre des décisions. Le tuple vide reste accepté pour compatibilité avec les plans/audits historiques et les providers de tests existants.

## 7. Structured Outputs / doctrine Agent

Le schéma `STRATEGIC_PLAN_SCHEMA` est enrichi avec `thesis_update` sur chaque entrée.

Règles du provider OpenAI courant :

- `BUY` ou `SELL` => `thesis_update` obligatoire ;
- `HOLD` sur une position ouverte => revue de thèse obligatoire ;
- `HOLD` sans position ouverte => `thesis_update` peut être `null`.

Le contrat rappelle au même Agent :

1. repartir de la thèse active lorsqu'elle existe ;
2. comparer les faits actuels aux faits de support et d'invalidation ;
3. qualifier la thèse ;
4. comparer maintien/réduction/fermeture/augmentation et alternatives ;
5. choisir `BUY / SELL / HOLD` ;
6. produire la révision structurée.

Le contrat interdit d'interpréter `INVALIDATED` ou `COMPLETED` comme une action automatique.

## 8. Activation économique d'une thèse

La sortie Agent est une **proposition stratégique**. La projection active est calculée après les faits économiques du cycle.

### Nouvelle ouverture SPOT

```text
BUY proposé
-> Risk ALLOW/MODIFY
-> fill
-> position SPOT réellement ouverte
-> thèse active LONG
```

Sans fill ou si Risk rejette et qu'aucune position n'existe après la trajectoire : aucune thèse active n'est créée.

### Nouvelle ouverture PERPETUAL

```text
BUY  sans position -> LONG après fill -> thèse LONG active
SELL sans position -> SHORT après fill -> thèse SHORT active
```

Le côté est déterminé par l'exposition économique réellement présente après exécution, pas uniquement par le texte Agent.

### Augmentation

Si l'exposition reste du même côté, l'identité de thèse est conservée et la revue courante met à jour son contenu.

### Réduction partielle

Si une exposition subsiste du même côté, la thèse reste active et peut être marquée `WEAKENING`, `INVALIDATED`, `COMPLETED` ou autre selon le jugement Agent. Le statut ne force aucune action ultérieure.

### Fermeture complète

Si l'exposition devient nulle :

- la thèse est retirée du snapshot actif ;
- la dernière `thesis_update` reste durablement disponible dans `decision_plan_payload` du cycle de fermeture.

### Retournement de côté

La mémoire est identifiée par `(symbol, market_type, side)`. Si une exposition change réellement de côté, l'ancienne identité est retirée. Une nouvelle thèse n'est créée pour le nouveau côté que si l'exposition correspondante est réellement ouverte avec fill.

Le Risk Engine continue d'empêcher les retournements non autorisés dans un seul intent selon ses règles existantes.

## 9. HOLD et REJECT

`HOLD` peut mettre à jour la revue stratégique sans exécution. La persistence peut donc conserver la continuité de pensée structurée même lorsque le bon choix stratégique est de ne rien trader.

Un `REJECT` Risk sur une décision concernant une position déjà ouverte ne supprime pas la revue stratégique produite par l'Agent si l'exposition reste ouverte : l'état stratégique et l'autorisation d'exécution sont deux responsabilités différentes.

Un `REJECT` sur une nouvelle ouverture ne crée aucune exposition et donc aucune thèse active.

## 10. Causalité

Toute thèse injectée dans un cycle doit respecter :

```text
thesis.created_at        <= context.as_of
thesis.updated_at        <= context.as_of
thesis.activated_at      <= context.as_of, si présent
last_review.reviewed_at  <= context.as_of
context.as_of            <= plan.created_at
```

Le contexte est également limité aux `market_states` du plan.

Aucune révision créée par un cycle ultérieur ne peut être fournie rétroactivement à un ancien cycle.

## 11. Identités de marché et d'exposition

La mémoire ne fusionne jamais :

```text
BTC/USD SPOT
BTC/USD PERPETUAL LONG
BTC/USD PERPETUAL SHORT
```

SPOT est toujours LONG dans ce contrat. Aucun short SPOT n'est ajouté.

## 12. Persistence

Migration :

```text
0007_multi_decision_cycles
-> 0008_strategic_thesis_state
```

Nouvelle colonne nullable :

```text
audit_cycles.strategic_thesis_state_payload JSONB
```

Comportement :

- cycle `COMPLETED` => calcule et écrit un snapshot déterministe, y compris `[]` si aucune thèse active ;
- cycle `FAILED` => colonne `NULL`, donc aucun nouvel état actif n'est promu ;
- ancien cycle pré-50.1 => colonne `NULL` après migration.

Le snapshot et `paper_runs.current_portfolio_payload` sont écrits dans la même transaction de repository.

## 13. Recovery / reprise de Session

Lecture :

```text
run courant
-> dernier cycle COMPLETED ?
   oui -> lire son snapshot 50.1 (NULL => legacy)
   non -> suivre resumed_from_paper_run_id
          -> répéter
```

Cette règle signifie qu'un redémarrage process ne détruit pas la mémoire. La mémoire n'est pas process-local.

Dès qu'un run courant a son propre cycle `COMPLETED`, son snapshot devient la source canonique de ce run.

## 14. Compatibilité legacy

La migration ne tente aucune backfill de thèse.

Pour une position ouverte reconstruite par le recovery mais dépourvue de snapshot 50.1 correspondant :

```text
memory_state = UNAVAILABLE_LEGACY
thesis       = null
```

L'Agent reçoit clairement l'absence d'historique et peut créer une nouvelle thèse de gestion à partir de ce cycle. `created_at` de cette adoption est alors le cycle courant, jamais la date historique supposée de l'entrée.

## 15. Taille du prompt

Le prochain cycle reçoit seulement la projection active compacte : thèse courante, faits synthétiques, conditions d'invalidation, statut, dernière revue et timestamps nécessaires.

L'historique complet des cycles n'est pas réinjecté.

Le Batch 50.1 ne modifie ni le Prompt Cache OpenAI ni l'observabilité détaillée des coûts LLM.

## 16. Risk / Broker

Aucune modification de `risk/` ou `broker/` n'est requise.

Le pipeline reste :

```text
Agent propose action + revue de thèse
-> Risk autorise/modifie/refuse l'action
-> Broker exécute seulement l'ExecutionIntent autorisé
-> persistence dérive la mémoire depuis les faits réellement commités
```

La mémoire stratégique n'est jamais directement exécutable.

## 17. Tests dédiés

Le fichier :

```text
backend/tests/test_batch50_1_strategic_thesis_memory.py
```

couvre notamment :

1. activation après ouverture SPOT réellement fillée ;
2. absence d'activation après ouverture rejetée/non économique ;
3. absence d'activation sans fill ;
4. réinjection et un seul appel delegate ;
5. causalité des timestamps ;
6. distinction SPOT/PERP ;
7. distinction LONG/SHORT PERP ;
8. HOLD ;
9. augmentation ;
10. réduction partielle ;
11. fermeture complète ;
12. recovery lineage ;
13. legacy explicite ;
14. cycle FAILED ;
15. multi-décisions ;
16. absence de second appel Agent ;
17. absence de dépendance Risk/Broker dans les nouveaux modules de mémoire ;
18. sérialisation stable ;
19. contexte limité à l'univers du plan ;
20. compatibilité des anciens plans sans `thesis_updates` ;
21. doctrine `INVALIDATED != SELL` et absence de hidden CoT ;
22. présence obligatoire du champ structuré dans le JSON Schema.

## 18. Hors périmètre

Le Batch 50.1 ne contient pas :

- UI détaillée des thèses ;
- graphiques de thèse ;
- changement Radar/Analytics ;
- nouveaux indicateurs ;
- Prompt Cache OpenAI ;
- tuning automatique par P&L ;
- stop-loss/take-profit algorithmique ;
- LIVE ;
- API Kraken Futures privée ;
- second Agent.

L'UI détaillée éventuelle est réservée à un Batch 50.2 séparé, non démarré ici.
