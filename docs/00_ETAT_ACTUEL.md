# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub de départ audité pour le Batch 18.9C :
  `6e5dcdc1c33103bdd29e9c6fae5c1aca07856808`
  (`docs: finalize batch 18.9B integration reference`).
- Dernier commit code intégré :
  `1eb94e79c3b14fea04faca67d6b2c695b9a27f51`
  (`feat: add PAPER control plane cockpit`).
- Batch 18.9C : **validé localement, prêt à intégrer**.
- Correctif local 18.9C : adaptation JSON `market_type` à la frontière Control Plane, sans relâcher
  les modèles domaine stricts.
- Dette mypy préexistante sur trois routes API corrigée localement par typage `Literal`/`cast`
  uniquement, sans changement fonctionnel.

## État confirmé par la validation 18.9C

- Strategy : création, renommage, archivage, révisions immuables, comparaison et preview canonique ;
- Campaign PAPER SPOT et PERPETUAL créées depuis le cockpit ;
- Luna et Sol sélectionnables et persistés dans des Campaigns immuables ;
- activation fraîche, `run-cycle`, Start et Stop validés ;
- restart backend : aucun runtime repris silencieusement ;
- reprise explicite : nouveau `paper_run_id`, `resumed_from_paper_run_id` correct et ledger restauré ;
- SPOT réel : BUY naturel observé puis Risk `MODIFY`, fill PAPER et HOLD naturels ;
- PERPETUAL réel : BUY naturel sur SOL/USD, Risk `MODIFY`, levier 2, marge `ISOLATED`, fill PAPER
  et position LONG persistée ;
- frais, spread, slippage, marge et limites Risk observés dans les artefacts de cycle ;
- refus fail-closed observés : 409, 422 et 503 ;
- aucun SELL naturel n'a été observé et aucun SELL n'a été forcé.

## Validation locale opérateur réellement exécutée

```text
pytest backend : 506 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed
mypy backend/src : Success: no issues found in 89 source files
git diff --check : OK hors avertissements LF -> CRLF
git status --short : exactement 8 fichiers attendus
validation comportementale réelle via cockpit : SPOT + PERPETUAL + recovery + erreurs
```

## Reste avant intégration

- relire le diff synthétique si souhaité ;
- créer le commit 18.9C ;
- pousser vers GitHub `main` uniquement après décision explicite de l'opérateur.
