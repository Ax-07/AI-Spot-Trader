# 00 — État actuel

## Référence de reprise — Batch 50.2 patch livré, intégration locale à valider

```text
Repository                         : Ax-07/AI-Spot-Trader
Branche                            : main
HEAD GitHub vérifié                : ebb859c4ed83aada1c0bf3edf17ece85336849b9
Commit HEAD                        : feat: add persistent strategic thesis memory
Batch 50.1                         : INTÉGRÉ ET VALIDÉ
Validation intégrée 50.1           : 1217 passed, 2 warnings
Migration PostgreSQL 50.1          : 0008 strategic_thesis_state appliquée
Batch 50.2                         : PATCH LIVRÉ — intégration/validation repository à faire
```

Le Batch 50.1 est désormais la base intégrée. La mention précédente « patch livré / intégration à faire » était obsolète et est supprimée.

## Batch 50.2 — observabilité des thèses stratégiques

Le patch 50.2 ajoute une projection **read-only** de la mémoire stratégique existante, sans nouvelle persistence et sans modifier le pipeline de trading.

```text
audit_cycles.strategic_thesis_state_payload
+ decision_plan_payload / thesis_updates
+ lineage paper_run
+ faits de cycle persistés
        ↓
projection stratégique read-only
        ↓
GET /api/v1/strategic-theses
        ↓
cockpit Historique
```

Choix architectural : endpoint dédié dans le routeur Analytics existant. Le snapshot actif provient uniquement du dernier cycle `COMPLETED`; les révisions proviennent uniquement des `thesis_updates` persistées et sont évaluées contre l'état précédent et l'état du même cycle, jamais contre un futur snapshot.

Sémantique opérateur :

- `SPOT` / `PERPETUAL` et `LONG` / `SHORT` restent des identités distinctes ;
- une position sans mémoire durable reste `UNAVAILABLE_LEGACY` ;
- aucune ancienne `rationale` n'est reconstruite en thèse ;
- une proposition rejetée peut apparaître en audit comme `PROPOSED_NOT_ACTIVATED`, jamais comme thèse active ;
- `HOLD` peut être une revue sans exécution ;
- une réduction partielle conserve la thèse si elle reste active ;
- une fermeture complète retire la thèse active mais conserve la révision durable ;
- un cycle `FAILED` n'est jamais promu comme état actif ;
- `INVALIDATED`, `COMPLETED` et `WEAKENING` restent des qualifications de l'Agent et ne déclenchent aucune action automatique ;
- Risk Engine déterministe reste l'autorité finale.

## Validation du patch 50.2 dans l'environnement ChatGPT

Exécuté réellement :

```text
python -m py_compile (fichiers Python du patch)                          : PASS
pytest ciblé projection 50.2, environnement de contrats minimal         : PASS — 9 passed
node --test --experimental-strip-types strategic-theses.test.mjs        : PASS — 3 passed
tsc ciblé src/lib/strategic-theses.ts                                   : PASS
```

À exécuter dans le repository réel après extraction :

```text
python -m pytest -q
cd frontend
pnpm typecheck
pnpm test
cd ..
git diff --check
git status --short
```

## Invariants inchangés

Un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ; SPOT sans short/levier/marge ; PERPETUAL LONG/SHORT sous contrôle Risk ; FUTURE daté non exécutable ; aucun LIVE ; aucune sortie LLM directement exécutable ; Radar informatif/priorisation uniquement ; aucun second Agent mémoire ; aucun second appel LLM d'observabilité ; aucun hidden chain-of-thought ; aucun secret versionné ; frontend non requis par le moteur.
