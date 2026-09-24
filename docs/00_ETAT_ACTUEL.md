# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main`.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité à l'ouverture du Batch 18.13 :
  `b491719edd7cbeeada0be2905e63af7dd20dd06d`
- Commit fonctionnel intégré du Batch 18.12 :
  `b491719edd7cbeeada0be2905e63af7dd20dd06d`
  (`feat: simplify PAPER operator experience`).
- Batch 18.13 : **PATCH PRÉPARÉ / NON INTÉGRÉ AU MOMENT DE CETTE LIVRAISON**.

## État fonctionnel confirmé

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- navigation principale : **Accueil / Configurer / Positions / Historique / Réglages** ;
- assistant PAPER simple : marché, capital, IA, sécurité, résumé ;
- activation fraîche, `run-cycle`, Start/Stop et recovery restent des commandes backend explicites ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- coûts PAPER, positions, P&L, drawdown, exposition et audit durable viennent du backend ;
- frontend indépendant du moteur : fermer le cockpit n'arrête pas le trading ;
- LIVE reste indisponible.

## Batch 18.13 — thème, contrastes et modernisation

Le patch 18.13 ajoute :

- `next-themes` avec thèmes **clair / sombre / système**, persistance locale et absence de flash/hydratation via `suppressHydrationWarning` ;
- tokens sémantiques light/dark pour `primary`, `secondary`, `muted`, `destructive`, `success`, `warning`, `info`, `border`, `input`, `ring` et sidebar ;
- variantes partagées Button/Badge/Card corrigées pour éviter les couples texte/fond trop proches ;
- sélecteur de thème dans la barre supérieure et Réglages ;
- modernisation sobre du cockpit, sans modifier l'architecture UX du Batch 18.12 ;
- P&L affiché avec signe `+`/`−` en plus de la couleur ;
- pipeline Historique explicitant `Exécuté` / `Non exécuté` ;
- compatibilité dark des anciens états rouge/ambre/vert/bleu encore utilisés dans les panneaux avancés.

Aucun changement backend n'est nécessaire.

## Limite de contrat volontairement respectée

Le contrat portefeuille SPOT canonique expose `asset`, `quantity` et `available`, mais pas le prix
d'entrée moyen ni un P&L par position SPOT. Le frontend continue donc d'afficher `—` pour ces champs
au lieu de reconstruire un portefeuille parallèle.

## Validation de cette livraison

Dans l'environnement de génération :

- audit du HEAD GitHub et de la désynchronisation documentaire 18.12 : effectué ;
- audit statique des couleurs/contrastes et des états light/dark : effectué ;
- vérification du ZIP root-relative et absence de secrets : à enregistrer dans le compte-rendu ;
- `pnpm lint`, `pnpm typecheck`, `pnpm build` : non exécutables ici tant que `next-themes` ne peut pas être installé, car l'environnement n'a pas accès au registre npm.

Après extraction, exécuter `pnpm install` dans `frontend`, puis les validations frontend.

## Suite

Après validation locale, intégrer le patch 18.13 sur `main`, mettre à jour ce document avec le commit
fonctionnel réel et le statut **INTÉGRÉ / VALIDÉ**. LIVE reste un périmètre séparé et ultérieur.
