# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub intégré :
  `b445b70b02d2c4af4b24a86ccfbdeff6f18a75e9`
  (`feat: redesign PAPER cockpit UX`).
- Batches 18.9A, 18.9B, 18.9C et 18.10 : **intégrés et validés**.
- Batch 18.10 — refonte UX/UI cockpit : **INTÉGRÉ / VALIDÉ**.

## État fonctionnel confirmé

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Strategy : création, renommage, archivage, révisions immuables, comparaison et preview canonique ;
- Campaign PAPER SPOT et PERPETUAL ; Luna et Sol sélectionnables par configuration ;
- activation fraîche, `run-cycle`, Start/Stop et restart backend sans reprise silencieuse validés ;
- reprise explicite avec nouveau `paper_run_id`, lineage et ledger restauré ;
- SPOT : BUY naturel observé, Risk `MODIFY`, fill PAPER avec coûts, puis HOLD naturels ;
- PERPETUAL : BUY naturel sur SOL/USD, Risk `MODIFY`, levier 2, marge `ISOLATED` et position LONG persistée ;
- refus backend 409 / 422 / 503 validés en fail-closed ;
- aucun SELL naturel observé et aucun SELL forcé ;
- aucune sortie LLM ne déclenche directement un ordre ; le Risk Engine reste l'autorité finale.

## Batch 18.10 — refonte UX/UI cockpit

Direction intégrée : **Option A — Vue d'ensemble**.

- `CockpitShell` avec navigation latérale simple ;
- Vue d'ensemble comme landing screen ;
- PAPER, Campaign active et état moteur visibles dans le header ;
- commandes canoniques `run-cycle`, Start et Stop exposées sans logique métier parallèle ;
- KPI PAPER, Marché & activité, Actions rapides, dernières décisions IA et alertes regroupés ;
- `ControlPlanePanel`, `CockpitDashboard`, `AnalyticsPanel` et `ChatPanel` conservés comme vues secondaires ;
- aucun changement backend, Risk Engine, Broker ou persistence ;
- aucun nouveau secret ou draft sensible persisté dans le navigateur.

## Validation opérateur du Batch 18.10

Validation visuelle et locale effectuée avant intégration :

```text
validation visuelle opérateur : OK
pnpm lint : OK, 0 erreur, 0 warning
pnpm typecheck : OK
pnpm build : OK
git diff --check : OK hors avertissements LF -> CRLF
working tree propre après push
```

## Suite

Aucune étape d'intégration 18.10 ne reste à effectuer. Tout nouveau batch doit repartir du `main`
GitHub courant. Le projet reste exclusivement PAPER ; LIVE reste un périmètre séparé et ultérieur.
