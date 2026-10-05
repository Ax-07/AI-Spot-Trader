# Batch 50.2 — Observabilité et cockpit des thèses stratégiques

## Statut

```text
Repository de base : Ax-07/AI-Spot-Trader
Branche             : main
HEAD vérifié         : ebb859c4ed83aada1c0bf3edf17ece85336849b9
Batch 50.1           : intégré et validé
Batch 50.2           : patch livré — validation/intégration repository à faire
```

Le Batch 50.2 est **observabilité uniquement**. Il ne change aucune décision de trading, aucune règle Risk, aucun comportement Broker et aucun prompt Agent.

## Objectif

Rendre la mémoire de thèse 50.1 lisible par l'opérateur :

- position concernée ;
- identité SPOT/PERPETUAL et LONG/SHORT ;
- thèse active ;
- statut, horizon et timestamps ;
- faits de support ;
- conditions d'invalidation ;
- dernière revue ;
- état `UNAVAILABLE_LEGACY` explicite ;
- historique causal des révisions réellement persistées.

Le cockpit reste une fenêtre read-only : **l'Agent propose et maintient sa thèse, le Risk Engine garde l'autorité finale, le cockpit observe.**

## Audit du dépôt

### Source durable 50.1

Les faits canoniques sont déjà présents :

```text
decision_plan_payload.thesis_updates
    -> propositions / révisions structurées Agent

audit_cycles.strategic_thesis_state_payload
    -> snapshot canonique des thèses encore actives après cycle COMPLETED

paper_run.resumed_from_paper_run_id
    -> lineage de recovery

portfolio_state_after / decision_results
    -> exposition économique durable
```

`persistence/strategic_thesis.py` confirme les règles suivantes :

- snapshot promu uniquement pour `COMPLETED` ;
- nouvelle entrée sans exposition réelle => aucune thèse active ;
- réduction partielle => thèse conservée ;
- fermeture complète => thèse retirée du snapshot actif ;
- legacy => aucune inférence depuis les anciennes rationales ;
- recovery via lineage `paper_run`.

### Limite de lecture identifiée

`CycleAuditDetail` exposait déjà `decision_plan`, les trajectoires Risk/exécution et les portefeuilles, mais pas `strategic_thesis_state_payload`.

Le Batch 50.2 étend donc **additivement** ce contrat read-only avec :

```text
strategic_thesis_state: tuple[JsonObject, ...] | None
```

Le `None` est préservé afin de distinguer un ancien cycle sans mémoire 50.1 d'un snapshot valide mais vide `[]`.

## Choix API

### Option A — extension de `/api/v1/economic-history`

Rejetée : l'historique économique porte déjà P&L, coûts, exposition et observabilité 49.4. La continuité stratégique est une responsabilité distincte et alourdirait encore ce contrat.

### Option B — endpoint dédié read-only

**Retenue.**

```text
GET /api/v1/strategic-theses
```

L'endpoint reste dans le routeur Analytics existant et réutilise la résolution de `paper_run`, la lineage et les lecteurs d'audit existants. Il n'introduit donc pas une seconde pile d'accès aux données.

### Option C — réutiliser un endpoint audit générique

Non retenue : possible techniquement, mais moins explicite pour le cockpit et nécessiterait de reconstruire côté frontend une projection métier read-only qui appartient au backend.

## Architecture 50.2

```text
faits persistés 50.1
  ├─ strategic_thesis_state_payload
  ├─ decision_plan_payload.thesis_updates
  ├─ decision_results Risk / fills
  ├─ portfolio_state_after
  └─ paper_run lineage
            ↓
StrategicThesisObservabilityReport
            ↓
/api/v1/strategic-theses
            ↓
StrategicThesisSection
            ↓
cockpit Historique
```

Aucune nouvelle table, migration, cache métier, mémoire frontend ou second store n'est créé.

## Projection des positions/thèses actives

La vue active utilise :

1. les cycles de la lineage ordonnés causalement ;
2. le dernier cycle `COMPLETED` comme source du portefeuille durable ;
3. le `strategic_thesis_state_payload` du dernier cycle `COMPLETED` comme source de mémoire active.

Pour chaque exposition ouverte :

```text
thesis_id
symbol
market_type
side
quantity
memory_state
origin
status
created_at
activated_at
updated_at
horizon
thesis_summary
supporting_facts
invalidation_conditions
last_review
```

Identité stricte :

```text
(symbol, market_type, side)
```

Ainsi :

```text
BTC/USD SPOT LONG
BTC/USD PERPETUAL LONG
BTC/USD PERPETUAL SHORT
```

restent distincts.

SPOT reste LONG uniquement.

### Legacy

Si une exposition ouverte n'a pas de thèse correspondante dans le snapshot durable :

```text
memory_state = UNAVAILABLE_LEGACY
```

Les champs de thèse restent nuls/vides. Aucune `rationale` historique n'est consultée.

## Historique causal des révisions

Une révision n'est créée que depuis une `thesis_update` réellement persistée dans `decision_plan_payload`.

Pour chaque révision, la projection utilise uniquement :

- le snapshot durable précédent ;
- le snapshot du même cycle si celui-ci est `COMPLETED` ;
- le Risk associé à la décision alignée lorsqu'il existe ;
- le nombre de fills réellement persistés ;
- l'action Agent réellement persistée.

Aucun cycle futur n'est consulté pour requalifier la révision.

### États d'audit 50.2

```text
ACTIVE_COMMITTED
    la thèse correspondante est présente dans le snapshot du même cycle

RETIRED_COMMITTED
    une thèse précédente existe mais n'est plus présente après le cycle COMPLETED

PROPOSED_NOT_ACTIVATED
    thesis_update persistée mais aucune thèse correspondante n'est activée après le cycle

FAILED_CYCLE
    la proposition appartient à un cycle FAILED et n'est pas promue

UNAVAILABLE_LEGACY
    aucun snapshot 50.1 durable du cycle ne permet de conclure
```

Ces états sont des **qualifications d'audit**, pas des actions de trading.

### Cas critiques

#### HOLD

Un `HOLD` avec revue structurée apparaît dans l'historique avec :

```text
agent_action = HOLD
fill_count   = 0
```

sans fausse exécution.

#### Risk REJECT d'une nouvelle entrée

La proposition peut apparaître comme :

```text
PROPOSED_NOT_ACTIVATED
risk_status = REJECT
```

mais elle n'apparaît jamais dans les thèses actives.

#### Réduction partielle

Si l'exposition subsiste et que le snapshot conserve la thèse, celle-ci reste active.

#### Fermeture complète

Le portefeuille ne contient plus l'exposition et le snapshot ne contient plus la thèse. La vue active la retire, mais la révision finale reste dans l'historique durable.

#### Cycle FAILED

Le cycle peut exposer sa proposition dans l'audit, mais le dernier snapshot `COMPLETED` précédent reste la mémoire active.

## Endpoint

```text
GET /api/v1/strategic-theses
```

Paramètres :

```text
paper_run_id : UUID optionnel si un run courant est configuré
history_limit: 0..200, défaut 100
```

Réponse conceptuelle :

```json
{
  "paper_run_id": "...",
  "lineage_paper_run_ids": ["..."],
  "calculation_version": "strategic-thesis-observability-v1",
  "timezone": "UTC",
  "as_of": "...",
  "positions": [],
  "revisions": [],
  "total_revision_count": 0,
  "history_limit": 100
}
```

L'historique retourné conserve l'ordre chronologique et est borné aux dernières `history_limit` révisions.

## Cockpit

La vue est intégrée au panneau **Historique** existant via `StrategicThesisSection`.

États gérés :

- loading ;
- erreur API ;
- aucune exposition ouverte ;
- exposition legacy ;
- thèse active ;
- historique présent/absent.

Pour une thèse active, le cockpit affiche notamment :

```text
marché / type / side
quantité
statut
origine
horizon
créée / activée / dernière revue
thesis_summary
supporting_facts
invalidation_conditions
révisions durables liées au thesis_id
```

Pour une position legacy :

```text
Historique stratégique indisponible.
Position ouverte avant activation de la mémoire 50.1, ou sans thèse durable disponible.
Aucune ancienne rationale n'a été reconstruite.
```

Le frontend associe l'historique d'une position active par `thesis_id`. Il ne reconstruit pas de timeline par simple symbole.

## Sémantique UI obligatoire

Le cockpit rappelle explicitement :

```text
INVALIDATED != SELL
COMPLETED   != SELL
WEAKENING   != réduction obligatoire
```

Les statuts qualifient la stratégie de l'Agent. Le Risk Engine conserve l'autorité finale sur l'exécution.

## Fichiers du batch

Backend :

```text
backend/src/ai_spot_trader/strategic_thesis_observability.py
backend/src/ai_spot_trader/api/strategic_thesis_schemas.py
backend/src/ai_spot_trader/api/routes/analytics.py
backend/src/ai_spot_trader/persistence/query.py
backend/tests/test_batch50_2_strategic_thesis_observability.py
```

Frontend :

```text
frontend/src/lib/strategic-theses.ts
frontend/src/lib/strategic-theses.test.mjs
frontend/src/components/cockpit/strategic-thesis-section.tsx
frontend/src/components/cockpit/history-panel.tsx
frontend/package.json
```

Documentation :

```text
docs/00_ETAT_ACTUEL.md
docs/01_PROJECT_MASTER.md
docs/09_ROADMAP_DEVELOPPEMENT.md
docs/10_DECISIONS_ET_CHANGELOG.md
docs/50_2_OBSERVABILITE_THESES_STRATEGIQUES.md
```

## Tests couverts par le test backend dédié

Le test 50.2 couvre notamment :

- SPOT actif ;
- PERPETUAL LONG ;
- PERPETUAL SHORT ;
- même symbole SPOT/PERP distinct ;
- side explicite ;
- legacy sans reconstruction ;
- historique causal NEW -> CONFIRMED ;
- HOLD sans fill ;
- Risk REJECT d'ouverture sans thèse active ;
- réduction partielle ;
- fermeture complète et révision finale ;
- cycle FAILED non promu ;
- lineage/recovery ;
- historique borné ;
- sérialisation API ;
- absence de dépendance Risk/Broker/LLM dans le projecteur.

## Validation réellement exécutée par ChatGPT

L'environnement ne dispose pas du checkout complet du repository. Les validations suivantes ont néanmoins été réellement exécutées sur le patch :

```text
python -m py_compile sur tous les fichiers Python du patch
    PASS

pytest ciblé test_batch50_2_strategic_thesis_observability.py
avec un environnement minimal reproduisant les contrats 50.1 utilisés
    PASS — 9 passed

node --test --experimental-strip-types src/lib/strategic-theses.test.mjs
    PASS — 3 passed

tsc --noEmit ciblé src/lib/strategic-theses.ts
    PASS
```

Le `pytest` ciblé ci-dessus valide le projecteur et le contrat API dans un environnement de test minimal ; il ne remplace pas la suite intégrée du repository.

## Validations restant à exécuter localement

Après extraction du ZIP à la racine du repository :

```powershell
python -m pytest -q
cd frontend
pnpm typecheck
pnpm test
cd ..
git diff --check
git status --short
```

Vérifier également manuellement le rendu du cockpit avec :

- une thèse active SPOT ;
- une thèse PERPETUAL LONG ;
- une thèse PERPETUAL SHORT ;
- une position legacy ;
- un run sans exposition ;
- un historique contenant HOLD, REJECT et fermeture.

## Hors périmètre confirmé

Aucun ajout dans 50.2 de :

- Prompt Cache OpenAI ;
- optimisation coûts LLM ;
- nouvelle stratégie ;
- auto-tuning ;
- stop-loss/take-profit algorithmique ;
- recalibration Radar ;
- modification Risk/Broker ;
- LIVE ;
- API Kraken Futures privée ;
- alerte automatique basée sur `INVALIDATED` ;
- nouvelle persistence ;
- second modèle / second Agent.
