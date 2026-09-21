# 10 — Décisions et changelog

> Ce document consolide les décisions courantes. L'historique détaillé antérieur au Batch 16 reste disponible dans l'historique Git.

## Principes historiques conservés

Les décisions intégrées des Batches 00 à 15.3 restent valides lorsqu'elles ne sont pas explicitement supersédées ici : agent unique, PAPER d'abord, Risk autorité finale, pas d'exécution directe LLM, audit durable, backend indépendant du frontend, no-look-ahead, contexte marché descriptif, chat opérateur latéral/non mutant.

Les anciennes mentions **SPOT uniquement / aucun future-perpetual** sont supersédées par les décisions Batch 16 uniquement pour le domaine Derivatives. Les règles SPOT correspondantes restent inchangées.

## Décisions Batch 16

### ADR-090 — Le projet devient SPOT + Kraken Derivatives
**ACCEPTÉE.** Le backend canonique peut représenter `SPOT`, `PERPETUAL` et `FUTURE`. SPOT conserve ses invariants historiques ; LONG/SHORT/levier/marge n'existent que dans le domaine dérivés.

### ADR-091 — Un seul pipeline et un seul agent
**ACCEPTÉE.** Aucun moteur dérivés parallèle. Le flux reste `Market -> Agent -> DecisionCandidate -> Risk -> ExecutionIntent -> Paper Broker`.

### ADR-092 — Perpetual linéaire uniquement pour la première exécution PAPER
**ACCEPTÉE.** Les contrats `PERPETUAL + LINEAR` sont exécutables. Les contrats `INVERSE` et futures datés sont découverts/représentés mais refusés à l'exécution.

### ADR-093 — Marge ISOLATED d'abord ; CROSS représenté mais fail-closed
**ACCEPTÉE.** `CROSS` existe dans le domaine mais la composition Batch 16 le refuse.

### ADR-094 — Levier déterministe, jamais choisi par le LLM
**ACCEPTÉE.** Le levier PAPER est un paramètre de configuration/Risk, par défaut `1x`.

### ADR-095 — Anti-retournement et reduce-only produits par Risk
**ACCEPTÉE.** Une action opposée réduit/ferme la position ; un dépassement ne peut pas la retourner silencieusement.

### ADR-096 — Funding et mark-to-market avant AgentInput
**ACCEPTÉE.** Le market source Derivatives marque la position et accumule le funding dans le ledger avant le snapshot portefeuille.

### ADR-097 — Modèle de liquidation conservateur
**ACCEPTÉE.** Le ledger calcule un prix de liquidation isolée estimé et Risk impose un buffer par rapport à la maintenance margin.

### ADR-098 — Kraken Derivatives public séparé de Kraken Spot
**ACCEPTÉE.** Intégration publique dédiée via `https://futures.kraken.com/derivatives/api/v3`. Aucun endpoint privé d'ordre, aucune clé Kraken et aucun LIVE.

### ADR-099 — Analytics combinés SPOT + Derivatives
**ACCEPTÉE.** Les positions dérivés sont persistées dans les payloads JSON ; les analytics ajoutent marge/unrealized/funding/exposition dérivés.

### ADR-100 — Prompt Agent `agent-strategy-v3`
**ACCEPTÉE.** Le prompt explique explicitement les sémantiques SPOT/PERPETUAL, LONG/SHORT, marge et levier tout en conservant `BUY/SELL/HOLD`.

## Décisions Batch 16.1

### ADR-101 — `contractValueTradePrecision` est un exposant décimal entier signé
**ACCEPTÉE ET INTÉGRÉE.** Le parser Kraken Derivatives ne rejette pas une valeur uniquement parce qu'elle est négative. La quantité minimale est dérivée par `10^-precision` : `-3 -> 1000`, `4 -> 0.0001`.

## Décisions Batch 16.2

### ADR-102 — `paper_run_id` durable au niveau du cycle
**ACCEPTÉE ET INTÉGRÉE.** Un run PAPER durable est représenté par `paper_runs.paper_run_id`. Le rattachement canonique est porté par `audit_cycles.paper_run_id`. Les décisions, Risk assessments, intents et fills héritent du run par leur relation au cycle.

### ADR-103 — Un run correspond à une initialisation cohérente du ledger PAPER
**ACCEPTÉE.** Le run est créé au démarrage du backend PAPER, avant les cycles. Un `engine stop/start` dans le même processus conserve le run. Un arrêt backend propre renseigne `ended_at`.

### ADR-104 — Un redémarrage backend crée un nouveau run
**ACCEPTÉE.** Le ledger PAPER étant process-local et réinitialisé au capital initial au démarrage, reprendre automatiquement l'ancien `paper_run_id` donnerait une continuité de portefeuille fausse.

### ADR-105 — Pas de reconstruction artificielle des données legacy
**ACCEPTÉE.** La migration `0002_paper_runs` ajoute `audit_cycles.paper_run_id` nullable. Les lignes antérieures restent `NULL`. Aucun pseudo-run historique unique n'est créé.

### ADR-106 — Analytics strictement run-scoped
**ACCEPTÉE.** Les analytics d'un run sélectionnent uniquement les cycles portant exactement son `paper_run_id`.

### ADR-107 — API de découverte des runs, sans rotation à chaud
**ACCEPTÉE.** Le backend expose les surfaces de découverte/sélection des runs. Aucun `POST new-run` n'est ajouté tant qu'un reset/recovery fiable du ledger n'existe pas.

### ADR-108 — Aucun changement frontend requis
**ACCEPTÉE.** Le cockpit existant continue d'utiliser le run courant par défaut.

## Décisions Batch 16.3

### ADR-109 — Harness déterministe réservé aux smokes techniques
**ACCEPTÉE ET INTÉGRÉE.** Le Batch 16.3 ajoute `ai_spot_trader.tools.derivatives_smoke`. Il réutilise les composants canoniques aval mais fournit des décisions déterministes explicitement marquées comme smoke. Il n'ajoute aucun mécanisme de force BUY/SELL dans FastAPI, la configuration runtime ou l'Agent normal.

### ADR-110 — Les smokes contrôlés ne sont pas des décisions Agent
**ACCEPTÉE.** Les décisions `CONTROLLED_SMOKE_BATCH_16_3` servent uniquement à valider l'exécution, Risk, ledger, audit et analytics. Elles ne sont pas attribuées à Luna/Sol et ne doivent pas être utilisées pour évaluer la qualité stratégique du modèle.

### ADR-111 — La fermeture opposée surdimensionnée doit rester reduce-only
**CONFIRMÉE PAR SMOKE.** Sur LONG comme sur SHORT, une demande de fermeture `0.0002` avec seulement `0.0001` restant a produit `MODIFY`, quantité autorisée `0.0001`, raison `DERIVATIVE_REDUCE_ONLY_LIMIT` et `reduce_only=true`, sans inversion accidentelle.

### ADR-112 — Les preuves brutes de smoke restent hors Git
**ACCEPTÉE.** Les JSON complets `smoke-long.json` et `smoke-short.json` sont des artefacts locaux de validation. Les résultats synthétiques et IDs de runs peuvent être documentés, mais les dumps bruts ne sont pas versionnés.

## Changelog — 2026-09-21 — Batch 16.1 Smoke PERPETUAL PAPER

Smoke réel : `BTC/USD / PF_XBTUSD`, cycle `COMPLETED`, Agent `HOLD`, Risk `ALLOW / HOLD_NO_EXECUTION`, analytics `1000 -> 1000`, `trade_count=0`, `hold_count=1`.

Ce smoke initial ne validait pas les branches LONG/SHORT.

## Changelog — 2026-09-21 — Batch 16.2 Isolation durable des runs PAPER

**État : intégré au commit fonctionnel `003bbadd7ae2f8288ccde049433832046f066957`.**

Changements : migration `0002_paper_runs`, lifecycle durable de run, FK `audit_cycles.paper_run_id`, readers/analytics run-scoped, endpoints de découverte/sélection des runs, compatibilité SPOT/PERPETUAL et absence de frontend/LIVE/private Kraken.

Validation locale : migration appliquée, `pytest` complet OK, Ruff OK, mypy OK et `git diff --check` OK.

## Changelog — 2026-09-21 — Batch 16.3 Smokes PERPETUAL PAPER contrôlés

**État fonctionnel : intégré sur GitHub `main` au commit `520b016eb501f1a208bcb6d0e90eb1df947e1d0b` (`test: add controlled perpetual paper smoke harness`).**

Validation locale avant push :

```text
pytest               : suite complète OK, 2 warnings externes FastAPI/Starlette
ruff check .          : All checks passed
mypy .                : Success: no issues found in 109 source files
git diff --check      : aucune erreur
```

### Smoke LONG

Run : `9523ec8c-7dd1-4706-bf07-47ef9669d56b`.

- ouverture BUY `0.0002` ;
- HOLD avec funding observé ;
- réduction SELL `0.0001`, `reduce_only=true` ;
- fermeture oversize SELL `0.0002` ramenée à `0.0001` par Risk ;
- 4 cycles `COMPLETED`, 3 exécutions ;
- position finale vide et exposition finale nulle.

### Smoke SHORT

Run : `b75f6e86-4724-41de-8d63-e8132d212530`.

- ouverture SELL `0.0002` ;
- HOLD avec funding observé ;
- réduction BUY `0.0001`, `reduce_only=true` ;
- fermeture oversize BUY `0.0002` ramenée à `0.0001` par Risk ;
- 4 cycles `COMPLETED`, 3 exécutions ;
- position finale vide et exposition finale nulle.

### Isolation

Les deux runs ont été fermés proprement avec `ended_at`. `verify-isolation` a retourné `isolation_verified=true`, avec 4 cycles propres à chaque run et des analytics/source digests distincts.

Le Batch 16.3 confirme donc le chemin technique complet PERPETUAL PAPER au-delà de HOLD : LONG, SHORT, fills, mark-to-market, funding, P&L, marge, `reduce_only`, fermeture et isolation durable.

Il ne mesure pas encore la qualité stratégique de l'Agent : les décisions des smokes sont déterministes et réservées à la validation.

## Prochaine étape

Premier run expérimental avec **GPT-5.6 Luna réel en PERPETUAL PAPER**, sans décision forcée. Risk conserve l'autorité finale. Un `HOLD` naturel reste valide.

## LIVE

Aucune décision de passage LIVE n'est incluse. LIVE restera un batch séparé avec clés sans droit de retrait, permissions minimales, idempotence, réconciliation et activation explicite.
