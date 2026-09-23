# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié au démarrage du Batch 18.9A :
  `2b0d227454f2bf894b075b8deef3378e2fe823b4`
  (`docs: finalize batch 18.8 integration reference`).
- Dernier commit code intégré : `0886216324106d941c3df0e30f074e24dbe1d33a`
  (`feat: add bounded network retry resilience`).
- Batches 18.6, 18.7 et 18.8 : **intégrés**.
- Batch 18.9A : **patch backend validé localement, non intégré tant que commit/push ne sont pas
  effectués**.

## État intégré avant 18.9A

- un seul Agent IA ; Kraken ; PAPER ; SPOT + PERPETUAL linéaire ;
- sélection causale multi-marchés puis décision BUY/SELL/HOLD ;
- Risk autorité finale ; aucun LLM/tool -> Broker/Risk ;
- `agent-strategy-v4` historique ; `paper-experiment-v1/v2/v3` ;
- recovery `paper-ledger-recovery-v1` ;
- retry réseau borné ;
- 20/20 cycles PAPER réels Batch 18.8 `COMPLETED`, tous `HOLD`.

## Patch Batch 18.9A

Le patch ajoute :

- Control Plane backend ;
- `Strategy` + `StrategyRevision` immuable ;
- contrat Agent protégé `agent-contract-v1` séparé du prompt opérateur ;
- digest prompt déterministe `strategy-prompt-sha256-v1` ;
- `Campaign` persistante avec whitelist de configuration non sensible ;
- `paper-experiment-v4` au niveau campagne, sans modifier v1/v2/v3 ;
- couverture v4 des paramètres Risk/PERPETUAL effectifs via `configuration_digest` ;
- migration `0006_paper_control_plane` ;
- lien `campaign_id -> paper_run` ;
- activation fraîche distincte de la reprise ;
- reprise limitée à la même campagne, sans replay historique ;
- preview du prompt via la même composition que le runtime de campagne ;
- exposition API de `campaign_id`, `resumed_from_paper_run_id`, `recovery_version`.

Le backend peut démarrer avec son infrastructure DB sans campagne active. Le frontend 18.9B reste
hors périmètre.

## Validation locale 18.9A

Validation opérateur confirmée le 23 septembre 2026 :

```text
pytest ciblé persistence : 1 passed
pytest backend : 504 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 89 source files
Alembic 0005_paper_run_recovery -> 0006_paper_control_plane sur PostgreSQL : OK
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Les 2 warnings pytest concernent Starlette/httpx et AnyIO ; ils sont non bloquants pour 18.9A.

## Suite

Committer et pousser 18.9A. Après intégration confirmée sur `main`, ouvrir un **nouveau
batch/discussion 18.9B** pour le cockpit de configuration PERPETUAL.
