# 11 — Guide opérateur

> Guide pratique du cockpit AI Spot Trader. Le parcours principal utilise **Session**. Les objets Strategy, StrategyRevision, Campaign, paper_run, digests et UUID restent dans **Réglages > Avancé**.

## 1. Avant de commencer

AI Spot Trader fonctionne actuellement en **PAPER uniquement** avec Kraken. Le frontend est un cockpit ; le moteur de trading, le mark-to-market, Risk, Broker et la discovery restent dans le backend.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Une sortie LLM ne déclenche jamais directement un ordre. LIVE n'est pas disponible.

## 2. Navigation

Le parcours normal comporte six pages :

- **Accueil** : état et prochaine action ;
- **Sessions** : créer et piloter les configurations PAPER ;
- **Marchés** : watchlist, charts, positions et fills ;
- **Positions** : portefeuille et P&L backend ;
- **Historique** : Agent → Risk → exécution PAPER ;
- **Réglages** : apparence, aide et mode avancé.

## 3. Qu'est-ce qu'une Session ?

Une Session est l'objet que vous créez et pilotez. Techniquement, le backend conserve :

```text
Session
-> Strategy
-> StrategyRevision(s)
-> Campaign(s)
-> paper_run(s)
```

Vous n'avez pas besoin de connaître ces objets pour le parcours normal. Ils sont conservés pour l'immuabilité, l'audit et le recovery.

## 4. Créer une Session

Ouvrez **Sessions** puis **Nouvelle session**. Si aucune Session n'existe, l'Accueil propose également la création directe.

La configuration simple demande :

1. un nom ;
2. `SPOT` ou `PERPETUAL` ;
3. un mode de sélection des marchés ;
4. un capital PAPER ;
5. Luna ou Sol ;
6. agressivité 1–10 ;
7. profil Risk ;
8. instructions IA/opérateur.

Deux boutons sont disponibles :

- **Créer** : persiste la Session sans démarrer ;
- **Créer et démarrer** : crée puis active et démarre explicitement le moteur backend.

La création technique Strategy + revision 1 + Campaign est atomique côté backend.

## 5. Mode marchés Automatique — IA

Choisissez **Automatique — laisser l'IA chercher les opportunités**.

La ou les paires saisies sont un **bootstrap/fallback**. Elles ne signifient pas que l'Agent est obligé de trader ces actifs.

Le pipeline reste :

```text
Kraken
-> filtrage déterministe d'admissibilité
-> candidats
-> même Agent IA choisit la watchlist
-> même Agent décide BUY / SELL / HOLD
-> Risk Engine autorise / modifie / refuse
-> PaperBroker éventuel
```

La discovery n'est pas un second Agent et le filtre déterministe ne produit aucun score stratégique d'opportunité.

## 6. Mode marchés Manuel

Choisissez **Manuel — choisir les marchés** puis fournissez une liste comme :

```text
BTC/USD
ETH/USD
SOL/USD
```

Dans ce mode :

- aucune Market Discovery n'est utilisée ;
- l'Agent ne travaille que dans l'univers fourni ;
- la whitelist Risk est alignée sur ce même univers ;
- l'Agent conserve BUY / SELL / HOLD ;
- Risk reste final.

Toutes les paires doivent utiliser le même actif de règlement dans une Session simple.

## 7. Profils Risk

Les profils sont des raccourcis UX vers des valeurs de CampaignConfiguration ; ils ne remplacent jamais le Risk Engine.

| Profil | Ordre max | Levier PERP | Position dérivée max | Exposition dérivée totale max | Buffer liquidation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prudent | 5 % du capital | 1x | 10 % | 20 % | 1.25 |
| Équilibré | 10 % | 2x | 20 % | 40 % | 1.15 |
| Agressif | 20 % | 3x | 35 % | 70 % | 1.10 |
| Personnalisé | saisi | saisi | saisi | saisi | saisi |

Le backend valide toujours les limites finales.

## 8. Configuration avancée

Le même formulaire permet d'ouvrir **Configuration avancée**. Il affiche les valeurs effectivement utilisées :

- cadence stratégique ;
- frais PAPER ;
- spread ;
- slippage ;
- timeouts marché / Agent / Broker ;
- caps Risk ;
- levier et limites PERPETUAL ;
- whitelist Risk optionnelle en mode automatique.

En mode automatique, les paramètres Market Discovery sont aussi visibles :

```text
catalog_refresh_seconds      900
watchlist_refresh_seconds    900
refresh_timeout_seconds      45
candidate_probe_limit        24
candidate_limit              12
watchlist_limit              6
max_snapshot_age_seconds     120
min_window_observations      2
require_complete_window      false
```

## 9. Lire la page Sessions

Chaque carte affiche le nom, le statut et un résumé : capital, modèle, mode de marchés et agressivité.

Statuts possibles :

- **Brouillon** : jamais exécutée ;
- **Prête** : runtime chargé, moteur arrêté ;
- **En cours** : moteur autonome RUNNING ;
- **Arrêtée** : historique existant mais non active ;
- **À reprendre** : recovery explicite requis/possible ;
- **Archivée** : retirée de la liste normale.

Ces statuts sont dérivés des faits backend, pas d'un champ manipulé dans le navigateur.

## 10. Démarrer, arrêter, reprendre, tester un cycle

### Démarrer

Une Session jamais exécutée utilise une activation fraîche puis démarre le moteur.

### Arrêter

`Arrêter` termine explicitement la Session active : la boucle est stoppée si nécessaire, le runtime est fermé et le `paper_run` reçoit sa fin durable. Fermer seulement le navigateur ne fait **pas** cela et ne stoppe jamais le moteur backend.

### Reprendre

Une Campaign déjà exécutée n'est jamais fresh-activée. `Reprendre` restaure explicitement le ledger compatible et crée la continuité de recovery prévue par le backend.

### Tester 1 cycle

`Tester 1 cycle` exécute exactement un cycle canonique et laisse le moteur autonome arrêté. Si la Session n'avait jamais tourné, un run est créé ; si sa Campaign possède un historique, le recovery explicite est utilisé.

## 11. Modifier une Session

`Modifier` ouvre le formulaire prérempli avec la configuration courante.

Le backend ne réécrit jamais l'historique :

- modifier seulement le nom renomme la Session ;
- modifier les instructions crée une nouvelle StrategyRevision ;
- modifier la configuration crée une nouvelle Campaign ;
- les anciens runs et leurs faits restent intacts.

Une Session **En cours** ne peut pas être modifiée silencieusement. Arrêtez-la avant d'appliquer une nouvelle version.

## 12. Dupliquer une Session

`Dupliquer` crée une nouvelle Session indépendante avec les instructions et la configuration courantes. Par défaut le nom reçoit `- copie`.

La copie possède un nouvel ID technique et **aucun historique/run** de l'original.

## 13. Supprimer une Session

`Supprimer` signifie **archiver** dans le parcours utilisateur. Le backend ne supprime pas physiquement :

- revisions ;
- Campaigns ;
- paper_runs ;
- cycles ;
- décisions ;
- évaluations Risk ;
- executions/fills ;
- données nécessaires au P&L et à l'audit.

La restauration d'une Session archivée n'est pas proposée en v1.

## 14. SPOT et PERPETUAL

### SPOT

Pas de short, levier ni marge. SELL ne peut réduire qu'un actif réellement détenu. Accounting, mark, valeur de marché et P&L sont fournis par le backend.

### PERPETUAL

Périmètre actuel : contrats linéaires PAPER selon les capacités intégrées, marge `ISOLATED`, levier configuré/déterministe et caps Risk. Le LLM ne choisit jamais librement le levier.

## 15. Positions, Marchés et Historique

Le frontend affiche les faits backend et ne les reconstruit pas :

- P&L/exposition depuis le backend ;
- candles via le pipeline backend ;
- markers uniquement depuis les fills persistés ;
- prix moyen/mark/liquidation depuis `/portfolio` ;
- rationales et statuts Agent/Risk/exécution depuis les faits d'audit.

Une valeur absente reste absente ; aucune causalité ni donnée financière n'est inventée.

## 16. Réglages > Avancé

Cette surface reste destinée au diagnostic et aux besoins techniques : Strategies, StrategyRevision, Campaigns, comparaison de versions, prompt preview, activation/recovery technique, digests et UUID.

Le parcours normal doit privilégier **Sessions**.

## 17. Sécurité

- PAPER uniquement ;
- un seul Agent IA ;
- Kraken ;
- Risk final ;
- aucune sortie LLM directe vers Broker ;
- aucun secret dans les instructions ou fichiers versionnés ;
- toutes les décisions, HOLD inclus, restent auditables ;
- frontend = cockpit seulement ;
- LIVE reste séparé.
