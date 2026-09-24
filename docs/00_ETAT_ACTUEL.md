# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main`.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub courant :
  `4cb0567cae6ff100c5ad9ad1df9e3f68b8f7ffd7`
- Commit fonctionnel intégré du Batch 18.13 :
  `4cb0567cae6ff100c5ad9ad1df9e3f68b8f7ffd7`
  (`feat: add dark mode and modernize cockpit UI`).
- Batch 18.13 : **INTÉGRÉ / VALIDÉ**.

## État fonctionnel confirmé

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- navigation principale : **Accueil / Configurer / Positions / Historique / Réglages** ;
- assistant PAPER simple : marché, capital, IA, sécurité, résumé ;
- thèmes **clair / sombre / système** via `next-themes`, avec sélecteur dans la barre supérieure et Réglages ;
- activation fraîche, `run-cycle`, Start/Stop et recovery restent des commandes backend explicites ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- coûts PAPER, positions, P&L, drawdown, exposition et audit durable viennent du backend ;
- frontend indépendant du moteur : fermer le cockpit n'arrête pas le trading ;
- LIVE reste indisponible.

## Batch 18.13 — thème, contrastes et modernisation

Le Batch 18.13 intégré apporte :

- `next-themes` avec thèmes **clair / sombre / système** et persistance locale ;
- tokens sémantiques light/dark pour les états et composants partagés ;
- variantes Button/Badge/Card corrigées pour renforcer les contrastes ;
- modernisation visuelle du cockpit sans modifier l'architecture UX du Batch 18.12 ;
- P&L affiché avec signe `+`/`−` en plus de la couleur ;
- Historique explicitant `Exécuté` / `Non exécuté` ;
- compatibilité dark des anciens états rouge/ambre/vert/bleu des panneaux avancés.

Aucun changement backend n'a été introduit par ce batch.

## Limite de contrat volontairement respectée

Le contrat portefeuille SPOT canonique expose `asset`, `quantity` et `available`, mais pas le prix
d'entrée moyen ni un P&L par position SPOT. Le frontend continue donc d'afficher `—` pour ces champs
au lieu de reconstruire un portefeuille parallèle.

## Validation du Batch 18.13

Validation locale réellement exécutée avec succès avant commit/push :

```powershell
cd frontend
pnpm install
pnpm lint
pnpm typecheck
pnpm build

cd ..
git diff --check
git status --short
```

Le `git status --short` final après commit/push était vide.

## Suite

Le Batch 18.13 est intégré sur `main`. LIVE reste un périmètre séparé et ultérieur.
