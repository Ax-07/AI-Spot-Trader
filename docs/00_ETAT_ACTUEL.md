# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main`.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité à l'ouverture du Batch 18.12 :
  `c6cf03e62ce49ad6b294ea1d4c44d933b4688b0a`
- Commit fonctionnel intégré du Batch 18.11 :
  `c02b9e8edd52b416969922f12a17e32f047d3989`
  (`feat: add operator guide and contextual help`).
- Les deux commits entre `c02b9e8...` et `c6cf03e...` sont documentaires uniquement.
- Batch 18.12 : **PATCH PRÉPARÉ / NON INTÉGRÉ AU MOMENT DE CETTE LIVRAISON**.

## État fonctionnel confirmé avant Batch 18.12

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Strategy, StrategyRevision immuable, Campaign PAPER et recovery explicite ;
- activation fraîche, `run-cycle`, Start/Stop et restart backend sans reprise silencieuse ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- coûts PAPER, positions, P&L, drawdown, exposition et audit durable disponibles via le backend ;
- frontend indépendant du moteur : fermer le cockpit n'arrête pas le trading ;
- LIVE reste indisponible.

## Batch 18.12 — simplification radicale de l'expérience opérateur

Le patch 18.12 remplace le modèle mental technique du cockpit par un parcours orienté tâches :

- navigation principale : **Accueil / Configurer / Positions / Historique / Réglages** ;
- bloc **Action suivante** sur l'accueil selon l'état réel du backend ;
- assistant de configuration PAPER en étapes simples : marché, capital, IA, sécurité, résumé ;
- création orchestrée côté frontend via les routes canoniques existantes :
  `Strategy -> StrategyRevision r1 -> Campaign`, sans exposer ces objets au parcours débutant ;
- profils Risk UX `Prudent`, `Équilibré`, `Agressif`, `Personnalisé` traduits uniquement en champs
  explicites de `CampaignConfiguration` ;
- activation fraîche, reprise et Start restent des commandes backend distinctes et explicites ;
- surface Positions dédiée utilisant exclusivement `/portfolio` et les analytics backend ;
- surface Historique corrélant visuellement `Décision IA -> Risk -> Exécution PAPER` ;
- ancien Control Plane, guide et assistant conservés sous **Réglages**, avec les concepts techniques
  accessibles en mode avancé ;
- aucun changement backend, Risk Engine, Broker, persistence ou contrat API requis.

## Limite de contrat volontairement respectée

Le contrat portefeuille SPOT canonique expose actuellement `asset`, `quantity` et `available`, mais
pas le prix d'entrée moyen ni un P&L par position SPOT. Le frontend 18.12 affiche donc `—` pour ces
champs au lieu de reconstruire un portefeuille parallèle. Le P&L global reste celui des analytics
backend.

## Validation de cette livraison

Validation réalisable dans l'environnement de génération :

- audit du HEAD GitHub et des contrats backend/frontend : effectué ;
- vérification de syntaxe/transpilation TypeScript/TSX : à enregistrer dans le compte-rendu de
  livraison ;
- contrôle du ZIP root-relative et absence de secrets : à enregistrer dans le compte-rendu.

Les commandes projet `pnpm lint`, `pnpm typecheck` et `pnpm build` doivent être exécutées localement
après extraction. L'environnement de génération ne dispose pas de `pnpm` ni d'un accès registre
permettant de l'installer.

## Suite

Après validation locale, intégrer le patch 18.12 sur `main`, puis mettre à jour ce document avec le
commit fonctionnel réel et le statut **INTÉGRÉ / VALIDÉ**. LIVE reste un périmètre séparé et ultérieur.
