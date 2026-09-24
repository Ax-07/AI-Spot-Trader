# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs,
> les décisions intégrées récentes et les décisions de cadrage nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Kraken, SPOT sans short/levier, PERPETUAL linéaire avec protections déterministes, audit
durable, no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE
séparé.

## Référence auditée pour le cadrage des améliorations

```text
HEAD GitHub main audité       : 9a312040eb671976b44e5f50077ca11a9d9213b3
Commit fonctionnel 18.13      : 4cb0567cae6ff100c5ad9ad1df9e3f68b8f7ffd7
Commit documentaire post-18.13: 9a312040eb671976b44e5f50077ca11a9d9213b3
```

Le présent batch est documentaire : les décisions ci-dessous décrivent une direction de conception.
Elles ne doivent pas être lues comme des fonctionnalités déjà implémentées.

## Décisions historiques toujours actives

- ADR-173 à ADR-181 : StrategyRevision immuable, contrat Agent protégé, digests, Campaign snapshot,
  identité expérimentale v4, distinction Campaign/paper_run, runtime backend et recovery ;
- ADR-182 à ADR-188 : frontend client du Control Plane, API unique, validators backend, preview
  canonique, pas de draft sensible persistant, activation et reprise distinctes ;
- ADR-189/190 : adaptation JSON `market_type` à la frontière API et typing sans changement runtime ;
- ADR-191/192 : Vue d'ensemble comme surface principale et réutilisation des panneaux canoniques ;
- ADR-193 à ADR-195 : aide progressive, règles métier au backend et guide opérateur versionné ;
- ADR-196 à ADR-200 : navigation orientée tâches, orchestration des objets canoniques, profils Risk UX,
  absence de comptabilité SPOT parallèle et bloc `Action suivante` comme porte d'entrée ;
- ADR-201 à ADR-204 : `next-themes`, tokens sémantiques, états non encodés par la couleur seule et
  modernisation sans réintroduire de complexité opérateur.

## Décisions de cadrage — améliorations planifiées

### ADR-205 — La comptabilité SPOT enrichie doit devenir canonique côté backend

**PLANIFIÉE / NON IMPLÉMENTÉE.** Le coût moyen, le P&L réalisé et les données nécessaires au P&L
latent d'une position SPOT ne seront pas reconstruits uniquement dans le cockpit. Ils doivent être
portés par le domaine/ledger canonique et survivre à la persistence/recovery.

La méthode exacte de base de coût, l'allocation des frais lors d'une vente partielle et les règles
d'arrondi sont à figer au batch d'implémentation avec des tests de réconciliation. L'objectif est de
ne jamais compter deux fois spread/slippage/frais : le prix réel du fill et le cash réellement débité
ou crédité restent la référence comptable.

### ADR-206 — Séparer le monitoring déterministe du cycle stratégique IA

**PLANIFIÉE / NON IMPLÉMENTÉE.** L'état mark-to-market des positions doit pouvoir évoluer sans appel
LLM. Prix/mark, P&L latent, exposition, marge, liquidation et funding pertinent sont des calculs ou
données déterministes ; ils ne choisissent pas BUY/SELL/HOLD.

Le monitoring aura une cadence distincte et configurable. Le cycle IA consommera un snapshot
canonique cohérent issu du backend.

### ADR-207 — Saturation d'exposition = restriction déterministe du champ des actions, pas stratégie

**PLANIFIÉE / NON IMPLÉMENTÉE.** Le backend peut constater qu'aucune nouvelle exposition n'est
possible et éviter les phases d'ouverture inutiles. Il ne peut pas décider à la place de l'Agent quelle
position conserver, réduire ou clôturer.

Le même Agent reste responsable du choix stratégique parmi les positions ouvertes ; Risk conserve
l'autorité finale et refuse/modifie toute proposition contraire aux limites.

### ADR-208 — Distinguer univers admissible, watchlist stratégique et univers surveillé

**PLANIFIÉE / NON IMPLÉMENTÉE.** Les notions cibles sont :

```text
univers techniquement admissible = filtrage backend déterministe
watchlist                         = sélection du même Agent stratégique
univers surveillé                 = watchlist + toutes les positions ouvertes
```

Le backend peut filtrer des incompatibilités structurelles mais ne doit pas classer les opportunités
à la place de l'Agent. Le mode manuel reste nécessaire pour les tests reproductibles.

### ADR-209 — Versionner les révisions de watchlist

**PLANIFIÉE / NON IMPLÉMENTÉE.** Une révision automatique de watchlist doit être auditée avec son
horodatage, son origine, son univers admissible, sa sélection et les références causales nécessaires.
Une position ouverte reste surveillée même si elle sort de la sélection suivante.

Le schéma de persistence exact et son lien avec Campaign/paper_run sont **à décider** au batch dédié.

### ADR-210 — Exposer le `rationale` sans le confondre avec Risk

**PLANIFIÉE / NON IMPLÉMENTÉE.** Le `rationale` existant représente l'explication stratégique
journalisée de l'Agent. L'UI doit afficher séparément :

- **Pourquoi l'IA ?** : rationale stratégique ;
- **Risk Engine** : `ALLOW`, `MODIFY` ou `REJECT` et raisons déterministes.

Le rationale ne devient jamais une instruction d'exécution et ne doit pas être présenté comme une
chaîne de pensée cachée.

### ADR-211 — Kraken/backend restent la source canonique des charts

**PLANIFIÉE / NON IMPLÉMENTÉE.** TradingView Lightweight Charts est le renderer frontend privilégié.
Les données de marché viennent de Kraken via le backend. Aucun iframe ou service TradingView externe
ne devient une dépendance de la source de vérité du moteur.

### ADR-212 — Historique REST + temps réel WebSocket + accumulation durable si nécessaire

**PLANIFIÉE / NON IMPLÉMENTÉE.** Le pipeline cible est :

```text
Kraken REST -> historique initial
Kraken WebSocket -> mises à jour temps réel
backend -> normalisation + cache + persistence éventuelle
WebSocket cockpit -> frontend
Lightweight Charts -> rendu
```

Kraken Spot REST OHLC est limité à ses entrées récentes ; une accumulation backend est donc prévue si
le besoin produit dépasse la profondeur récupérable. La politique de rétention, les timeframes
persistés et le schéma de tables sont **à décider**.

### ADR-213 — Trois cadences indépendantes

**PLANIFIÉE / NON IMPLÉMENTÉE.** Le système doit distinguer :

1. monitoring/mark-to-market rapide sans LLM ;
2. cycle stratégique IA ;
3. découverte/révision de watchlist IA, beaucoup plus lente.

Les valeurs ne sont pas figées dans la documentation. Elles doivent être configurables lorsque cela
est pertinent et choisies sur mesures.

### ADR-214 — Les charts sont chargés à la demande

**PLANIFIÉE / NON IMPLÉMENTÉE.** La future vue Marchés privilégie la paire active. Les autres onglets
utilisent cache/lazy loading ; tous les charts ne sont pas montés et alimentés simultanément sans
raison mesurée.

## Points explicitement non décidés par ce cadrage

- formule exacte du prix de valorisation SPOT pour le P&L latent (`last`, autre référence canonique,
  ou valorisation conservatrice) ;
- représentation exacte de la base de coût SPOT dans les modèles persistés ;
- stratégie de migration des anciens snapshots/runs ne possédant pas ces nouveaux champs ;
- granularité et durée de persistence des marks/candles ;
- timeframes proposés par défaut dans le cockpit ;
- format final des identités de watchlist/revision ;
- mode précis de comptabilisation des tokens si le fournisseur ne retourne pas toutes les métriques ;
- seuils/cadences définitifs du monitoring et de la découverte.

Ces sujets doivent être décidés sur l'audit du batch qui les implémente, avec tests et impact de
compatibilité documentés.

## Changelog — 2026-09-24 — cadrage documentaire des améliorations

- resynchronisation documentaire sur le HEAD GitHub `9a312040...` ;
- remise à niveau de Project Master, Architecture et Agent/Risk par rapport à l'état intégré 18.13 ;
- création de `docs/11_AMELIORATIONS_PLANIFIEES.md` ;
- formalisation de la comptabilité SPOT canonique à construire ;
- formalisation des trois cadences monitoring / stratégie / découverte ;
- formalisation du mode gestion lorsque la capacité d'exposition est saturée ;
- formalisation de la découverte IA et de l'invariant watchlist + positions ouvertes ;
- formalisation de l'explicabilité rationale vs Risk ;
- cadrage de la vue Marchés, des candles, du WebSocket et des markers ;
- découpage proposé en batches 19.1 à 19.6B ;
- aucun code applicatif modifié par ce batch documentaire.
