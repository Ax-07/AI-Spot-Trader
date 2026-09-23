# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- Dernier commit code intégré 18.9A :
  `11a04be33bf209552e6337e28318d039b775b264`
  (`feat: add PAPER control plane`).
- Le HEAD GitHub peut être un commit documentaire ultérieur ; au démarrage d'une nouvelle discussion,
  comparer cette référence au HEAD réel puis inspecter l'écart.
- Batch 18.9A : **intégré et validé**.
- Batches 18.6, 18.7 et 18.8 : **intégrés**.

## État intégré

- un seul Agent IA ; Kraken ; PAPER ;
- SPOT + PERPETUAL linéaire ;
- sélection causale multi-marchés puis décision BUY/SELL/HOLD ;
- Risk autorité finale ; aucun LLM/tool -> Broker/Risk ;
- `agent-strategy-v4` historique ; `paper-experiment-v1/v2/v3` préservés ;
- `paper-experiment-v4` pour l'identité des Campaigns ;
- recovery `paper-ledger-recovery-v1` ;
- retry réseau borné ;
- Control Plane backend persistant avec Strategy/StrategyRevision/Campaign ;
- contrat Agent protégé `agent-contract-v1` séparé du prompt opérateur ;
- migration PostgreSQL `0006_paper_control_plane` ;
- lien durable `campaign_id -> paper_run` ;
- activation fraîche et reprise explicite séparées ;
- prompt preview canonique ;
- exposition API du lineage recovery.

## Validation Batch 18.9A

Validation opérateur du 23 septembre 2026 :

```text
pytest ciblé persistence : 1 passed
pytest backend : 504 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 89 source files
Alembic 0005_paper_run_recovery -> 0006_paper_control_plane sur PostgreSQL : OK
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Commit intégré :

```text
11a04be33bf209552e6337e28318d039b775b264
feat: add PAPER control plane
```

## Suite

Ouvrir un **nouveau batch/discussion 18.9B** pour le cockpit frontend de configuration
SPOT/PERPETUAL. Le frontend reste un cockpit : fermer ou redémarrer le frontend ne doit jamais
arrêter le moteur backend.
