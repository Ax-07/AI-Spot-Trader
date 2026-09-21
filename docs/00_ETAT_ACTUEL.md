# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- Commit fonctionnel Batch 16.3 intégré sur GitHub `main` : `520b016eb501f1a208bcb6d0e90eb1df947e1d0b` (`test: add controlled perpetual paper smoke harness`).
- Parent documentaire Batch 16.2 : `8c03bd639736244ebc40fdeb82e770b17a6216cb` (`docs: finalize Batch 16.2 integration`).
- Le commit fonctionnel 16.3 a été poussé sur `origin/main` le 21 septembre 2026 après validation locale et smokes réels contrôlés.

## Batch 16.3 — Smokes PERPETUAL PAPER contrôlés

Un harness CLI de validation a été ajouté sans modifier le comportement de la composition normale. Il réutilise le pipeline canonique Market -> décision -> Risk -> Paper Broker -> ledger -> audit, mais fournit des décisions déterministes explicitement marquées comme **smoke technique, pas stratégie Agent**.

Smokes réels sur `BTC/USD / PF_XBTUSD`, levier `1x`, `ISOLATED` :

- LONG : ouverture, mark/HOLD, réduction, fermeture oversize ramenée par Risk sans reversal ;
- SHORT : même séquence symétrique ;
- `reduce_only=true` confirmé ;
- funding réellement observé dans les deux sens ;
- P&L réalisé/non réalisé et libération de marge observés ;
- 4 cycles `COMPLETED` et 3 exécutions par run ;
- exposition finale nulle ;
- deux runs distincts fermés proprement et isolation vérifiée.

Runs de preuve locaux :

```text
LONG  : 9523ec8c-7dd1-4706-bf07-47ef9669d56b
SHORT : b75f6e86-4724-41de-8d63-e8132d212530
```

Les JSON complets de preuve restent hors Git.

## Isolation durable

Le modèle Batch 16.2 reste inchangé :

- table PostgreSQL `paper_runs` ;
- `audit_cycles.paper_run_id` comme FK canonique ;
- décisions, Risk, intents et fills héritent du run via leur cycle ;
- SPOT et PERPETUAL utilisent le même mécanisme ;
- migration `0002_paper_runs` ;
- legacy pré-migration conservé avec `paper_run_id = NULL`.

Le contrôle `verify-isolation` du Batch 16.3 a confirmé que les deux runs LONG/SHORT restent séparés dans l'audit et les analytics.

## Validation confirmée

Validation locale avant commit/push fonctionnel 16.3 :

```text
pytest               : suite complète OK, 2 warnings externes FastAPI/Starlette
ruff check .          : OK
mypy .                : OK sur 109 fichiers
git diff --check      : OK
git status --short    : propre après push
```

Smokes : LONG OK, SHORT OK, funding observé, réduction/fermeture `reduce_only`, `MODIFY / DERIVATIVE_REDUCE_ONLY_LIMIT` sur fermeture oversize, aucune inversion accidentelle et isolation multi-runs validée.

## Prochaine étape

Lancer le premier **run expérimental Agent réel GPT-5.6 Luna en PERPETUAL PAPER**, sans forcer BUY/SELL. Un `HOLD` naturel restera un résultat valide. LIVE reste hors périmètre.
