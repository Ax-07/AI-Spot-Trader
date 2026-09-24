# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub intégré :
  `5fc7704e7ca43ded4c2565b21871b81fe2161b0a`
  (`fix: finalize batch 18.9C behavioral validation`).
- Batch 18.9A, 18.9B et 18.9C : **intégrés**.
- Batch 18.9C : **validation comportementale terminée et intégrée**.

## État confirmé après 18.9C

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Strategy : création, renommage, archivage, révisions immuables, comparaison et preview canonique ;
- Campaign PAPER SPOT et PERPETUAL ; Luna et Sol sélectionnables par configuration ;
- activation fraîche, `run-cycle`, Start/Stop et restart backend sans reprise silencieuse validés ;
- reprise explicite avec nouveau `paper_run_id`, lineage et ledger restauré ;
- SPOT : BUY naturel observé, Risk `MODIFY`, fill PAPER avec coûts, puis HOLD naturels ;
- PERPETUAL : BUY naturel sur SOL/USD, Risk `MODIFY`, levier 2, marge `ISOLATED` et position LONG persistée ;
- refus backend 409 / 422 / 503 validés en fail-closed ;
- aucun SELL naturel observé et aucun SELL forcé ;
- correctif JSON `market_type` intégré à la frontière Control Plane sans relâcher le domaine strict ;
- nettoyage mypy type-only intégré sur trois routes API, sans changement fonctionnel.

## Validation historique du commit 18.9C

Validation locale opérateur exécutée avant le push de `5fc7704` :

```text
pytest backend : 506 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed
mypy backend/src : Success: no issues found in 89 source files
git diff --check : OK hors avertissements LF -> CRLF
working tree propre avant push
validation comportementale réelle via cockpit : SPOT + PERPETUAL + recovery + erreurs
```

## Suite

Aucune étape d'intégration 18.9C ne reste à effectuer. Tout nouveau batch doit repartir du `main`
GitHub courant, conserver le mode PAPER et traiter LIVE dans un périmètre séparé et ultérieur.
