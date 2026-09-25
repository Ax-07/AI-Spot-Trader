# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **PAPER** sur Kraken, pilotée par **un seul Agent IA stratégique**. L'Agent recherche/sélectionne les opportunités puis propose `BUY`, `SELL` ou `HOLD`. Le **Risk Engine déterministe** conserve l'autorité finale : seul Risk peut autoriser, modifier ou refuser une intention d'exécution avant le `PaperBroker`.

> Objectif expérimental : rechercher une performance élevée, avec une cible de travail de +4 %/jour. Ce n'est ni une promesse ni une garantie de rendement.

## Parcours utilisateur

Le concept principal du cockpit est désormais la **Session** : l'utilisateur crée une Session, la configure, la démarre, l'arrête, la reprend, la duplique ou la supprime de son parcours courant.

La navigation cible est :

```text
Accueil | Sessions | Marchés | Positions | Historique | Réglages
```

Les objets techniques historiques restent canoniques derrière cette façade :

```text
Session UX
  ↓
Strategy                         identité technique stable
  ↓
StrategyRevision(s)              instructions versionnées et immuables
  ↓
Campaign(s)                      configuration versionnée et immuable
  ↓
paper_run(s) / recovery         lifetime d'exécution PAPER
```

`Strategy`, `StrategyRevision`, `Campaign`, digests et IDs restent consultables dans **Réglages > Avancé** mais ne sont plus nécessaires au parcours normal.

## Créer une Session

La configuration simple demande :

- nom ;
- capital PAPER ;
- `SPOT` ou `PERPETUAL` ;
- mode de marchés ;
- modèle IA Luna/Sol ;
- agressivité 1–10 ;
- profil Risk ;
- instructions IA/opérateur.

Deux modes de marchés sont disponibles :

- **Automatique — laisser l'IA chercher les opportunités** : `market_discovery` utilise le pipeline canonique Kraken → admissibilité déterministe → candidats → même Agent IA → watchlist ; la paire saisie reste un bootstrap/fallback, pas une obligation de trader cet actif ;
- **Manuel — choisir les marchés** : `market_discovery = null`, l'univers exécutable est exactement la liste fournie et `risk_allowed_pairs` est aligné sur cet univers.

La **Configuration avancée** expose les valeurs réellement persistées : cadence, frais, spread, slippage, timeouts, paramètres Risk, caps/levier PERPETUAL et paramètres `MarketDiscoveryPolicy` lorsque le mode automatique est utilisé.

## CRUD et versioning

La façade `/api/v1/sessions` orchestre les écritures côté backend. La création Strategy + révision 1 + Campaign est atomique afin d'éviter les états partiels créés auparavant par plusieurs appels React.

Une modification ne réécrit jamais l'historique :

- changement d'instructions → nouvelle `StrategyRevision` ;
- changement de configuration → nouvelle `Campaign` ;
- simple renommage → identité Strategy conservée sans nouvelle Campaign ;
- anciennes Campaigns/runs/cycles/decisions/Risk/executions/fills restent intacts.

`Supprimer` dans l'UX effectue un **archivage logique** de la Strategy. Aucune donnée d'audit trading n'est supprimée.

## Lifecycle Session

Les statuts UX sont dérivés des faits backend et non stockés dans une nouvelle vérité parallèle :

- `Brouillon` : jamais exécutée ;
- `Prête` : runtime chargé et moteur arrêté ;
- `En cours` : moteur RUNNING ;
- `Arrêtée` : historique existant mais runtime non actif ;
- `À reprendre` : recovery explicite possible/requis ;
- `Archivée` : masquée du parcours normal.

Actions : `Démarrer`, `Arrêter`, `Reprendre`, `Tester 1 cycle`. Une Campaign déjà exécutée n'est jamais fresh-activée silencieusement ; la reprise est explicite. Fermer le frontend ne stoppe jamais le backend.

## Invariants

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- PAPER uniquement ; LIVE séparé et ultérieur ;
- SPOT sans short/levier/marge ; PERPETUAL selon les capacités intégrées ;
- aucune sortie LLM → Broker ;
- Risk Engine déterministe = autorité finale ;
- frais, spread, slippage et comptabilité restent canoniques côté backend ;
- toutes les décisions, y compris `HOLD`, sont auditables ;
- aucun look-ahead ;
- aucun secret dans les prompts, logs, réponses UI ou fichiers versionnés ;
- frontend = cockpit ; aucune logique Risk/P&L/Broker/discovery stratégique parallèle.

Principe : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Pipeline canonique

```text
Kraken
-> admissibilité déterministe / données causales
-> même Agent IA : watchlist éventuelle
-> même Agent IA : BUY / SELL / HOLD
-> RiskEngine : ALLOW / MODIFY / REJECT
-> ExecutionIntent éventuel
-> PaperBroker
-> ledger + audit durable
```

Le frontend n'appartient pas à cette chaîne d'exécution.

## API principales

Sous `/api/v1` :

```text
GET    /sessions
POST   /sessions
GET    /sessions/{session_id}
PUT    /sessions/{session_id}
POST   /sessions/{session_id}/duplicate
DELETE /sessions/{session_id}
POST   /sessions/{session_id}/start
POST   /sessions/{session_id}/stop
POST   /sessions/{session_id}/resume
POST   /sessions/{session_id}/run-cycle
```

Les routes historiques Strategies/Campaigns/engine restent disponibles pour le mode avancé et la compatibilité technique.

## Persistence

Le Batch 19.8 n'introduit **aucune table `sessions`** et ne nécessite pas de migration SQL : la façade repose sur les faits canoniques déjà persistés.

## Référence de travail

Au démarrage du Batch 19.8, GitHub `main` a été revérifié au HEAD :

```text
130429eca6c7c8385c1caf4b2eb2870bef61ec3e
```

Le patch 19.8 livré séparément doit être validé localement avant intégration explicite par l'opérateur.
