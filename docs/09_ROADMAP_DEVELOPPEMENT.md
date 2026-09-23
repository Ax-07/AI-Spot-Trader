# 09 — Roadmap de développement

## Référence code intégrée

```text
11a04be33bf209552e6337e28318d039b775b264
feat: add PAPER control plane
```

## Jalons intégrés

- Batch 18.1 : tools Agent read-only et traces causales ;
- Batch 18.2 : sélection causale multi-marchés SPOT/PERPETUAL ;
- Batch 18.3 : validation comportementale et parsing Kraken margin schedules ;
- Batch 18.5 : `paper-experiment-v3` et identité tools/sélection ;
- Batch 18.6 : recovery `paper-ledger-recovery-v1`, migration `0005` ;
- Batch 18.7 : retries réseau bornés ;
- Batch 18.8 : validation réelle recovery/réseau, 20/20 cycles `COMPLETED`, tous `HOLD` ;
- Batch 18.9A : Control Plane backend, stratégies versionnées, campagnes persistantes,
  `paper-experiment-v4`, migration `0006`, runtime canonique par campagne.

## Batch 18.9 — découpage décidé

```text
18.9A — Control Plane + persistence + stratégie/prompt backend      INTÉGRÉ
18.9B — Cockpit de configuration + PERPETUAL UI                    PROCHAIN
18.9C — validation comportementale via cockpit                     APRÈS 18.9B
```

Ne pas fusionner ces trois périmètres.

## Batch 18.9A — intégré

### Périmètre livré

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

### Validation finale

```text
pytest backend/tests/test_control_plane_persistence.py::test_strategy_revisions_are_immutable_and_campaign_snapshots_revision : 1 passed
ruff check backend : All checks passed!
pytest backend : 504 passed, 2 warnings
mypy --config-file backend/pyproject.toml backend/src : Success, 89 source files
Alembic 0005_paper_run_recovery -> 0006_paper_control_plane sur PostgreSQL : OK
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Commit d'intégration :

```text
11a04be33bf209552e6337e28318d039b775b264
feat: add PAPER control plane
```

## Batch 18.9B — prochain batch

Cockpit frontend uniquement, à partir des contrats backend 18.9A stabilisés :

- liste/création/renommage/archivage des stratégies ;
- édition via création d'une nouvelle révision ;
- comparaison de révisions ;
- builder Campaign SPOT/PERPETUAL ;
- sélection Luna/Sol ;
- agressivité, cadence, capital initial ;
- frais, spread, slippage ;
- paramètres Risk ;
- levier PERPETUAL déterministe et marge isolée ;
- preview du prompt ;
- activation fraîche / reprise explicite ;
- contrôle `run-cycle`, Start, Stop ;
- visualisation `campaign_id`, `paper_run_id`, lineage recovery ;
- état moteur et campagne active ;
- aucune responsabilité de trading déplacée dans le frontend.

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
