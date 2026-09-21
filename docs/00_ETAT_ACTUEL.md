# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- Commit fonctionnel Batch 16.2 intégré sur GitHub `main` : `003bbadd7ae2f8288ccde049433832046f066957` (`feat: add durable paper run isolation`).
- Parent documentaire Batch 16.1 : `08926e98dda3fe9ad7b68b4ddb5c582cbe49529c` (`docs: finalize Batch 16.1 integration`).
- Le commit Batch 16.2 a été poussé sur `origin/main` le 21 septembre 2026 après validation locale complète.

## Batch 16.2 — Isolation durable des runs PAPER

Le modèle retenu introduit un `paper_run_id` durable :

- table PostgreSQL `paper_runs` ;
- `audit_cycles.paper_run_id` comme FK canonique ;
- décisions, Risk, intents et fills héritent du run via leur cycle, sans dupliquer le même identifiant dans chaque table ;
- SPOT et PERPETUAL utilisent exactement le même mécanisme ;
- migration `0002_paper_runs` ;
- les anciennes lignes restent volontairement `paper_run_id = NULL` : aucun run legacy artificiel n'est reconstruit.

Les analytics et les lectures audit peuvent sélectionner explicitement un run. Dans la composition PAPER normale, le run courant est le défaut. `GET /api/v1/paper-runs` expose les runs durables ; `GET /api/v1/analytics?paper_run_id=<uuid>` permet une sélection explicite.

## Cycle de vie retenu

Un run correspond à une expérience PAPER utilisant une même initialisation du ledger mémoire.

- création : au démarrage du backend/composition PAPER, avant d'accepter les cycles ;
- `engine stop/start` dans le même processus : **même run** ;
- arrêt backend propre : `ended_at` est renseigné après arrêt du moteur ;
- crash : `ended_at` peut rester `NULL`, sans prétendre que le run est encore actif ;
- redémarrage backend : **nouveau run**, car le ledger PAPER actuel est recréé au capital initial et n'est pas encore récupéré durablement ;
- un run fermé refuse de nouveaux cycles.

Tant que la reprise durable du ledger n'existe pas, démarrer explicitement une nouvelle expérience signifie arrêter proprement le moteur/backend puis redémarrer le backend. Aucun endpoint de rotation à chaud n'est ajouté dans ce batch afin de ne pas séparer artificiellement l'identité du run de l'état portefeuille réellement utilisé.

## Compatibilité historique

La migration ajoute une FK nullable. Les cycles antérieurs au Batch 16.2 restent consultables dans l'historique global mais ne sont jamais intégrés dans les analytics d'un run moderne. Il n'existe pas de pseudo-run « legacy ».

## Validation confirmée

Validation locale avant intégration :

```text
alembic upgrade head : 0001_audit_journal -> 0002_paper_runs
alembic current      : 0002_paper_runs (head)
pytest               : 344 passed, 2 warnings externes
ruff check .          : OK
mypy .                : OK sur 106 fichiers
git diff --check      : aucune erreur, warnings LF -> CRLF uniquement
```

Le Batch 16.2 est donc intégré. Les données legacy pré-migration restent volontairement hors des analytics run-scoped.

## Prochaine étape

Le smoke Batch 16.1 était `HOLD` : LONG/SHORT réels PAPER, fills dérivés, funding accumulé, P&L de position et `reduce_only` ne sont toujours pas validés par un smoke réel. Le prochain batch proposé est donc le Batch 16.3, dédié à des smokes Derivatives contrôlés et séparés par `paper_run_id`.
