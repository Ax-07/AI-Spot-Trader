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
**ACCEPTÉE ET INTÉGRÉE.** Un run PAPER durable est représenté par `paper_runs.paper_run_id`. Le rattachement canonique est porté par `audit_cycles.paper_run_id`. Les décisions, Risk assessments, intents et fills héritent du run par leur relation au cycle ; l'identifiant n'est pas dupliqué inutilement dans toutes les tables.

### ADR-103 — Un run correspond à une initialisation cohérente du ledger PAPER
**ACCEPTÉE.** Le run est créé au démarrage du backend PAPER, avant les cycles. Un `engine stop/start` dans le même processus conserve le run. Un arrêt backend propre renseigne `ended_at`.

### ADR-104 — Un redémarrage backend crée un nouveau run
**ACCEPTÉE.** Le ledger PAPER étant encore process-local et réinitialisé au capital initial au démarrage, reprendre automatiquement l'ancien `paper_run_id` donnerait une continuité de portefeuille fausse. Le redémarrage crée donc un nouveau run. La reprise d'un run existant restera interdite tant qu'un recovery durable du ledger n'est pas implémenté.

Un crash peut laisser `ended_at = NULL`. Ce `NULL` signifie seulement qu'aucune clôture propre n'a été persistée ; il ne prouve pas que le run soit encore actif.

### ADR-105 — Pas de reconstruction artificielle des données legacy
**ACCEPTÉE.** La migration `0002_paper_runs` ajoute `audit_cycles.paper_run_id` nullable. Les lignes antérieures restent `NULL`. Aucun pseudo-run historique unique n'est créé, car les frontières d'expériences passées ne peuvent pas être démontrées déterministement.

Les données legacy restent consultables dans l'historique audit global mais sont exclues des analytics d'un run identifié.

### ADR-106 — Analytics strictement run-scoped
**ACCEPTÉE.** Les analytics d'un run sélectionnent uniquement les cycles portant exactement son `paper_run_id`. Equity, drawdown, trade/hold counts, coûts et exposition ne traversent jamais deux runs.

La composition PAPER normale utilise le run courant par défaut. L'API accepte aussi une sélection explicite avec `GET /api/v1/analytics?paper_run_id=<uuid>`.

### ADR-107 — API de découverte des runs, sans rotation à chaud dans ce batch
**ACCEPTÉE.** Le backend expose `GET /api/v1/paper-runs`, `/paper-runs/current` et `/paper-runs/{id}`. Les endpoints audit acceptent une sélection run-scoped lorsque le reader le supporte.

Aucun `POST new-run` n'est ajouté au Batch 16.2 : une rotation à chaud sans reset/reconstruction fiable du ledger séparerait l'identité du run de l'état portefeuille réellement utilisé. Pour démarrer une nouvelle expérience, l'opérateur arrête proprement le backend puis le redémarre.

### ADR-108 — Aucun changement frontend requis
**ACCEPTÉE.** Le cockpit existant continue d'appeler les endpoints sans sélecteur ; dans la composition canonique, les readers sont déjà scopés sur le run courant. Fermer/redémarrer le frontend n'a aucun effet sur le run backend.

## Changelog — 2026-09-21 — Batch 16.1 Smoke PERPETUAL PAPER

Batch 16.1 est intégré ; le HEAD GitHub vérifié au démarrage du Batch 16.2 est `08926e98dda3fe9ad7b68b4ddb5c582cbe49529c` (`docs: finalize Batch 16.1 integration`).

Smoke réel : `BTC/USD / PF_XBTUSD`, cycle `COMPLETED`, Agent `HOLD`, Risk `ALLOW / HOLD_NO_EXECUTION`, analytics `1000 -> 1000`, `trade_count=0`, `hold_count=1`.

**Non validé par ce smoke :** LONG/SHORT réel PAPER, fills dérivés, funding accumulé sur position, P&L de position et `reduce_only`.

## Changelog — 2026-09-21 — Batch 16.2 Isolation durable des runs PAPER

**État : intégré sur GitHub `main` au commit fonctionnel `003bbadd7ae2f8288ccde049433832046f066957` (`feat: add durable paper run isolation`).**

Changements intégrés :

- migration `0002_paper_runs` ;
- lifecycle durable de run ;
- FK `audit_cycles.paper_run_id` ;
- repository audit run-scoped et refus des écritures sur run fermé ;
- readers audit filtrables par run ;
- analytics strictement isolés par run ;
- endpoints de découverte/sélection des runs ;
- tests multi-runs incluant HOLD, trade/fill, equity, drawdown et legacy ;
- même mécanisme SPOT/PERPETUAL ;
- aucun frontend, LIVE ou API privée Kraken ajouté.

Validation locale confirmée avant intégration : migration PostgreSQL `0001_audit_journal -> 0002_paper_runs`, `alembic current = 0002_paper_runs (head)`, `pytest = 344 passed` avec 2 warnings externes, Ruff OK, mypy OK sur 106 fichiers et `git diff --check` sans erreur hors warnings LF -> CRLF. ChatGPT avait en complément validé la compilation Python et des contrôles statiques/SQLAlchemy dans l'environnement de livraison.

## LIVE

Aucune décision de passage LIVE n'est incluse. LIVE restera un batch séparé avec clés sans droit de retrait, permissions minimales, idempotence, réconciliation et activation explicite.
