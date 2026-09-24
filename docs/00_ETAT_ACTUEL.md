# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité au démarrage du Batch 18.10 :
  `34145a904c07af90e1c9ed370479cd5e5a0c0139`
  (`docs: sync batch 18.9C integrated state`).
- Le HEAD de référence encore mentionné dans la documentation intégrée était
  `5fc7704e7ca43ded4c2565b21871b81fe2161b0a` ; le commit `34145a9` est un commit de
  synchronisation documentaire post-18.9C, sans modification du code frontend/backend.
- Batches 18.9A, 18.9B et 18.9C : **intégrés et validés**.
- Batch 18.10 — refonte UX/UI cockpit : **patch local livré, non intégré à GitHub**.

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

Direction retenue : **Option A — Vue d'ensemble**.

Le patch frontend :

- ajoute une shell opérateur avec navigation latérale simple ;
- fait de la Vue d'ensemble la landing screen ;
- rend PAPER, Campaign active et état moteur visibles dans le header ;
- expose les commandes canoniques `run-cycle`, Start et Stop sans reproduire de logique métier ;
- regroupe les KPI PAPER, Marché & activité, Actions rapides, dernières décisions IA et alertes ;
- conserve les panneaux canoniques existants comme vues secondaires : Pilotage, Activité,
  Performance et Assistant ;
- ne modifie ni backend, ni Risk Engine, ni Broker, ni persistence ;
- ne persiste aucun nouveau secret ou draft sensible dans le navigateur.

Fichiers frontend du patch :

```text
frontend/src/app/page.tsx
frontend/src/app/globals.css
frontend/src/components/cockpit/cockpit-shell.tsx
```

## Validation du patch 18.10

Exécuté par ChatGPT dans l'environnement de livraison :

```text
TypeScript transpile/syntax check : OK sur page.tsx et cockpit-shell.tsx
typecheck ciblé avec contrats GitHub actuels : OK
harness structure UX/invariants : OK
git diff --check sur le contenu livré : OK
```

Les dépendances frontend du repository ne sont pas installables dans l'environnement de livraison ;
les commandes officielles restent à exécuter localement après extraction :

```powershell
cd frontend
pnpm lint
pnpm typecheck
pnpm build
cd ..
git diff --check
```

## Suite

Extraire le ZIP 18.10 à la racine du repository, exécuter les validations frontend ci-dessus, puis
intégrer le batch uniquement après validation opérateur. Le projet reste exclusivement PAPER ; LIVE
reste un périmètre séparé et ultérieur.
