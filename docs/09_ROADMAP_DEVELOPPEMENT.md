# 09 — Roadmap de développement

## Référence

Base intégrée auditée au démarrage du Batch 18.9A :

```text
2b0d227454f2bf894b075b8deef3378e2fe823b4
docs: finalize batch 18.8 integration reference
```

Dernier code intégré :

```text
0886216324106d941c3df0e30f074e24dbe1d33a
feat: add bounded network retry resilience
```

## Jalons intégrés

- Batch 18.1 : tools Agent read-only et traces causales ;
- Batch 18.2 : sélection causale multi-marchés SPOT/PERPETUAL ;
- Batch 18.3 : validation comportementale et parsing Kraken margin schedules ;
- Batch 18.5 : `paper-experiment-v3` et identité tools/sélection ;
- Batch 18.6 : recovery `paper-ledger-recovery-v1`, migration `0005` ;
- Batch 18.7 : retries réseau bornés ;
- Batch 18.8 : validation réelle recovery/réseau, 20/20 cycles `COMPLETED`, tous `HOLD`.

## Batch 18.9 — découpage décidé

```text
18.9A — Control Plane + persistence + stratégie/prompt backend
18.9B — Cockpit de configuration + PERPETUAL UI
18.9C — validation comportementale via cockpit
```

Ne pas fusionner ces trois périmètres.

## Batch 18.9A — validé localement, en attente d'intégration

### Objectif

Créer la frontière backend permettant au cockpit futur de créer/versionner des stratégies, créer
des campagnes PAPER reproductibles, prévisualiser le prompt puis activer/reprendre un runtime
canonique.

### Implémentation du patch

- Strategy + StrategyRevision immuable ;
- normalisation/digest prompt ;
- rejet des motifs de secret dans les prompts opérateur ;
- contrat Agent protégé séparé du texte stratégique ;
- CampaignConfiguration whitelistée et sans secret ;
- `paper-experiment-v4` au niveau Campaign ;
- couverture complète des paramètres Risk PERPETUAL par `configuration_digest` ;
- migration `0006_paper_control_plane` ;
- FK `paper_runs.campaign_id` ;
- lifecycle recovery par campagne ;
- CampaignRuntimeManager avec un runtime actif maximum ;
- activation/reprise refusée pendant `RUNNING` ;
- prompt preview canonique ;
- API Strategy/Campaign ;
- recovery lineage exposée dans `/api/v1/paper-runs` ;
- aucun frontend 18.9B.

### Statut de validation

Validation opérateur confirmée :

```text
pytest backend/tests/test_control_plane_persistence.py::test_strategy_revisions_are_immutable_and_campaign_snapshots_revision : 1 passed
ruff check backend : All checks passed!
pytest backend : 504 passed, 2 warnings
mypy --config-file backend/pyproject.toml backend/src : Success, 89 source files
Alembic 0005_paper_run_recovery -> 0006_paper_control_plane sur PostgreSQL : OK
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Les deux warnings pytest sont des dépréciations de dépendances Starlette/httpx et AnyIO.

18.9A est donc **validé localement**. Il ne doit être marqué **intégré** qu'après commit et push
explicites par l'opérateur.

## Batch 18.9B — prochain batch après intégration 18.9A

Cockpit frontend uniquement à partir des contrats backend stabilisés :

- liste/création/édition par nouvelle révision des stratégies ;
- comparaison de révisions ;
- builder Campaign SPOT/PERPETUAL ;
- Luna/Sol, agressivité, cadence, capital, coûts ;
- levier et Risk PERPETUAL ;
- preview prompt ;
- activation/reprise ;
- contrôle `run-cycle`, Start, Stop ;
- visualisation `campaign_id`, `paper_run_id`, recovery.

Le frontend ne devient jamais l'application de trading et sa fermeture ne doit pas arrêter le
backend.

## Batch 18.9C — après 18.9B

Validation comportementale réelle via cockpit :

- création stratégie/révision ;
- campagnes SPOT et PERPETUAL ;
- reprise après restart ;
- campagne modifiée => nouvelle identité ;
- observation de BUY/SELL naturels si le marché/Agent en produit, sans forcer artificiellement une
  décision stratégique ;
- comparaison Luna/Sol et audit des digests ;
- contrôle de l'absence de secrets et de replay.

## Plus tard

- enrichissement research uniquement sur besoin mesuré ;
- multi-quote/FX explicite avant tout univers multi-devise ;
- FUTURE daté seulement avec domaine/exécution dédiés ;
- LIVE dans un projet/batch séparé avec permissions et barrières explicites.
