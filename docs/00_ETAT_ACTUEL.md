# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité au démarrage du Batch 18.11 :
  `e2807621352219e355810bcd212844ea646c83da`
  (`docs: sync batch 18.10 integrated state`).
- Le commit fonctionnel 18.10 reste
  `b445b70b02d2c4af4b24a86ccfbdeff6f18a75e9`
  (`feat: redesign PAPER cockpit UX`) ; `e280762` ne contient que la synchronisation documentaire.
- Batches 18.9A, 18.9B, 18.9C et 18.10 : **intégrés et validés**.
- Batch 18.11 — guide opérateur et aide intégrée : **patch local livré, non intégré à GitHub**.

## État fonctionnel confirmé

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Strategy, StrategyRevision immuable, Campaign PAPER et recovery explicite ;
- activation fraîche, `run-cycle`, Start/Stop et restart backend sans reprise silencieuse ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- coûts PAPER, positions, P&L, drawdown, exposition et audit durable visibles dans le cockpit ;
- LIVE reste séparé et ultérieur.

## Batch 18.11 — patch livré

Le patch frontend/documentation :

- ajoute une vue principale **Guide** dans `CockpitShell` ;
- ajoute un démarrage rapide depuis la Vue d'ensemble ;
- explique le pipeline Agent → Risk → Broker PAPER ;
- ajoute une aide progressive pour `run-cycle`/Start, HOLD/Risk et états moteur ;
- conserve les aides déjà présentes dans le Control Plane au lieu de les dupliquer ;
- ajoute `docs/11_GUIDE_OPERATEUR.md` comme guide versionné ;
- ne modifie ni backend, ni contrat API, ni Risk Engine, ni Broker, ni persistence.

## Validation de livraison 18.11

Exécuté dans l'environnement de livraison :

```text
TypeScript transpile/syntax check des fichiers frontend 18.11 : OK
TypeScript ciblé avec stubs locaux des dépendances : OK
harness structure/invariants + ancres Guide : OK
heuristique secrets sur les fichiers livrés : OK
git diff --cached --check sur les fichiers livrés : OK
```

Les dépendances frontend du repository ne sont pas disponibles dans l'environnement de livraison.
Les validations officielles restent donc à exécuter localement après extraction :

```powershell
cd frontend
pnpm lint
pnpm typecheck
pnpm build
cd ..
git diff --check
git status --short
```

## Suite

Extraire le ZIP 18.11 à la racine du repository, exécuter les validations frontend, puis valider
visuellement la nouvelle aide avant intégration. GitHub `main` n'est pas modifié par cette livraison.
