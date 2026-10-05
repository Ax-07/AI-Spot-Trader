# 00 — État actuel

## Référence de reprise — Batch 50.1 livré, intégration à valider

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub de base vérifié        : 8a0054091c39079dfc5d2c5a9504470b2fbf9493
Commit HEAD de base                : docs: close batch 49.4 integration
Dernier commit fonctionnel 49.4    : 2e552cbaf1b8ffcae9244c1fb472f1ee8fb0f193
Batch 50.1                         : PATCH LIVRÉ — validation locale / intégration GitHub à faire
```

Le Batch 50.1 part exclusivement de l'état intégré GitHub `main` ci-dessus. Il introduit une mémoire de thèse stratégique structurée pour les positions PAPER ouvertes, sans second Agent et sans modifier l'autorité du Risk Engine.

## État fonctionnel cible après intégration 50.1

```text
Radar / Analytics causal
+ contexte multi-timeframes
+ positions courantes
+ mémoire de thèse active / état legacy explicite
        ↓
Agent stratégique unique — un seul generate_decision_plan(...)
        ↓
BUY / SELL / HOLD + création/révision structurée de thèse
        ↓
Risk Engine déterministe
        ↓
PaperBroker
        ↓
cycle audité + portefeuille commités atomiquement
        ↓
projection durable des thèses encore actives
```

La source durable retenue est additive : `audit_cycles.strategic_thesis_state_payload` contient le snapshot canonique des thèses actives après chaque cycle `COMPLETED`. Les révisions proposées restent auditées dans `decision_plan_payload`. Un cycle `FAILED` ne promeut aucun nouvel état stratégique.

## Sémantique 50.1

- statuts : `NEW`, `CONFIRMED`, `WEAKENING`, `INVALIDATED`, `COMPLETED` ;
- `INVALIDATED` et `COMPLETED` ne déclenchent jamais automatiquement un `SELL` ;
- une nouvelle thèse n'est activée qu'après exposition économique réellement ouverte par fill ;
- `REJECT` Risk ou absence de fill sur une entrée => aucune thèse active ;
- réduction partielle => thèse active conservée/révisée ;
- fermeture complète => thèse retirée du snapshot actif mais historique d'audit conservé ;
- position historique sans mémoire 50.1 => `UNAVAILABLE_LEGACY`, sans reconstruction depuis une ancienne rationale ;
- recovery : lecture du dernier snapshot `COMPLETED`, puis suivi de `resumed_from_paper_run_id` si nécessaire.

## Invariants inchangés

- un seul Agent IA stratégique ;
- PAPER uniquement ;
- Kraken ;
- SPOT + PERPETUAL linéaire ;
- SPOT sans short, levier ni marge ;
- PERPETUAL LONG/SHORT sous contrôle Risk ;
- FUTURE daté non exécutable ;
- aucun LIVE ni API Kraken Futures privée ;
- Risk Engine déterministe = autorité finale ;
- aucune sortie LLM directement exécutable ;
- Radar = sélection/priorisation d'attention, jamais action ;
- aucune règle déterministe d'entrée/sortie ajoutée ;
- aucun hidden chain-of-thought ni transcript LLM persisté ;
- aucun look-ahead ;
- aucun secret versionné ;
- frontend non requis par le moteur.

## Validation du patch 50.1

Dans l'environnement de livraison ChatGPT, les fichiers Python du patch sont compilés avec succès via `python -m py_compile`. La suite complète `python -m pytest -q`, Alembic sur la base locale et `git diff --check` doivent être exécutés après extraction dans le repository réel avant intégration.
