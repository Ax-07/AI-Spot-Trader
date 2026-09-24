# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub intégré :
  `c02b9e8edd52b416969922f12a17e32f047d3989`
  (`feat: add operator guide and contextual help`).
- Batches 18.9A, 18.9B, 18.9C, 18.10 et 18.11 : **intégrés et validés**.
- Batch 18.11 — guide opérateur et aide intégrée : **INTÉGRÉ / VALIDÉ**.

## État fonctionnel confirmé

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Strategy, StrategyRevision immuable, Campaign PAPER et recovery explicite ;
- activation fraîche, `run-cycle`, Start/Stop et restart backend sans reprise silencieuse ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- coûts PAPER, positions, P&L, drawdown, exposition et audit durable visibles dans le cockpit ;
- guide opérateur accessible depuis la navigation principale et démarrage rapide depuis la Vue d'ensemble ;
- LIVE reste séparé et ultérieur.

## Batch 18.11 — guide opérateur et aide intégrée

Direction intégrée : aide en trois niveaux dans l'architecture **Option A — Vue d'ensemble**.

- démarrage rapide pour le premier test PAPER ;
- aide contextuelle progressive sur les notions ambiguës ;
- vue principale **Guide** dans `CockpitShell` ;
- pipeline pédagogique Agent → Risk → Broker PAPER ;
- guide versionné `docs/11_GUIDE_OPERATEUR.md` ;
- réutilisation des aides déjà présentes dans les panneaux canoniques ;
- aucun changement backend, contrat API, Risk Engine, Broker ou persistence.

## Validation opérateur du Batch 18.11

Validation locale finale effectuée avant intégration :

```text
pnpm lint : OK, 0 erreur
pnpm typecheck : OK
pnpm build : OK
git diff --check : OK hors avertissements LF -> CRLF
working tree propre avant et après push
```

Le premier passage ESLint avait relevé uniquement des apostrophes JSX non échappées dans les deux
fichiers frontend 18.11 ; le correctif typographique a été appliqué puis toutes les validations ont
été relancées avec succès avant le commit intégré.

## Suite

Aucune étape d'intégration 18.11 ne reste à effectuer. Tout nouveau batch doit repartir du `main`
GitHub courant. Le projet reste exclusivement PAPER ; LIVE reste un périmètre séparé et ultérieur.
