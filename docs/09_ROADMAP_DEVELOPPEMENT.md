# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub main audité       : 9a312040eb671976b44e5f50077ca11a9d9213b3
Commit fonctionnel 18.13      : 4cb0567cae6ff100c5ad9ad1df9e3f68b8f7ffd7
Commit documentaire post-18.13: 9a312040eb671976b44e5f50077ca11a9d9213b3
```

Le HEAD doit être revérifié au démarrage de chaque nouveau batch. Le document de cadrage détaillé des
améliorations futures est `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Jalons intégrés

- 18.1 : tools Agent read-only et traces causales ;
- 18.2 : sélection causale multi-marchés SPOT/PERPETUAL ;
- 18.3 : validation comportementale et parsing Kraken margin schedules ;
- 18.5 : `paper-experiment-v3` ;
- 18.6 : recovery `paper-ledger-recovery-v1`, migration `0005` ;
- 18.7 : retries réseau bornés ;
- 18.8 : validation recovery/réseau ;
- 18.9A : Control Plane backend, Strategy/Revision, Campaigns, `paper-experiment-v4`, migration `0006`, runtime canonique par Campaign ;
- 18.9B : cockpit Control Plane frontend SPOT/PERPETUAL ;
- 18.9C : validation comportementale réelle via cockpit ;
- 18.10 : refonte UX/UI Option A, `CockpitShell` et Vue d'ensemble ;
- 18.11 : guide opérateur et aide contextuelle ;
- 18.12 : simplification radicale de l'expérience opérateur ;
- 18.13 : dark mode, contrastes et modernisation du cockpit ;
- synchronisation documentaire post-18.13 : commit `9a312040...`.

## État intégré

```text
18.9A  — Control Plane backend                                INTÉGRÉ
18.9B  — Cockpit configuration SPOT/PERPETUAL                 INTÉGRÉ / VALIDÉ
18.9C  — Validation comportementale                           INTÉGRÉ / VALIDÉ
18.10  — Refonte UX/UI Option A                               INTÉGRÉ / VALIDÉ
18.11  — Guide opérateur                                      INTÉGRÉ / VALIDÉ
18.12  — Simplification radicale expérience opérateur         INTÉGRÉ
18.13  — Dark mode, contrastes et modernisation               INTÉGRÉ / VALIDÉ
```

## Prochaine séquence proposée

Les numéros ci-dessous sont une **proposition de découpage**, pas des batches intégrés. Chaque batch
doit être resynchronisé avec `main`, audité, testé et documenté avant le suivant.

### Batch 19.1 — Comptabilité SPOT canonique

Objectif : enrichir la source de vérité portefeuille SPOT avant de construire du monitoring ou des
écrans qui en dépendent.

Périmètre recommandé :

- coût/prix moyen d'entrée canonique ;
- P&L réalisé et bases nécessaires au P&L latent ;
- buys successifs ;
- ventes partielles et totales ;
- cohérence frais / spread / slippage sans double comptage ;
- persistence et recovery ;
- exposition API/Agent minimale nécessaire ;
- tests comptables de réconciliation.

Dépendance principale : aucune nouvelle vue frontend ne doit inventer cette comptabilité.

### Batch 19.2 — Monitoring et mark-to-market déterministes

Objectif : dissocier l'actualisation rapide des positions du cycle stratégique IA.

Périmètre recommandé :

- acquisition prix/marks Kraken adaptée au monitoring ;
- revalorisation SPOT et PERPETUAL ;
- P&L latent, exposition, marge, liquidation et funding lorsque pertinent ;
- snapshot cohérent consommable par API, Agent et analytics ;
- cadence dédiée et configurable ;
- absence complète de décision stratégique dans le monitor.

Le fonctionnement doit rester PAPER et le Risk Engine reste l'autorité finale au moment d'une action.

### Batch 19.3 — Mode gestion et optimisation de consommation IA

Objectif : lorsqu'aucune nouvelle exposition n'est possible, éviter les phases IA/tools inutiles de
recherche d'ouverture et concentrer le même Agent sur les positions existantes.

Périmètre recommandé :

- détermination backend de la capacité d'ouverture ;
- mode `NORMAL` / `MANAGEMENT` ou équivalent ;
- périmètre stratégique limité aux positions ouvertes en mode gestion ;
- HOLD, réduction et clôture autorisés ;
- retour automatique au mode normal ;
- métriques de nombre d'appels, tools et tokens réellement consommés, plus compteurs de phases
  évitées lorsque mesurables.

### Batch 19.4 — Découverte dynamique et watchlist versionnée

Objectif : remplacer le caractère exclusivement statique de l'univers observé par une révision
périodique pilotée par le même Agent, sans laisser le backend effectuer le ranking stratégique.

Périmètre recommandé :

- univers techniquement admissible construit déterministiquement ;
- mode manuel conservé ;
- cadence de découverte indépendante ;
- sélection/watchlist par le même Agent stratégique ;
- persistence/versionnement/audit de la watchlist ;
- invariant : `marchés surveillés = watchlist actuelle + positions ouvertes` ;
- recovery et reproductibilité explicités.

### Batch 19.5 — Explicabilité opérateur

Objectif : rendre le `rationale` déjà produit par l'Agent visible sans le confondre avec le résultat du
Risk Engine.

Périmètre recommandé :

- Accueil : dernière décision et « Pourquoi l'IA ? » ;
- Positions : décisions/trades associés ;
- Historique : lecture synthétique avant les JSON techniques ;
- contrats API typés si nécessaire ;
- séparation visuelle entre rationale stratégique et `ALLOW / MODIFY / REJECT` déterministe.

Ce batch peut être avancé plus tôt s'il reste strictement présentationnel, mais le rattachement riche
aux positions bénéficiera des identités/comptabilités des batches précédents.

### Batch 19.6A — Backend candles, cache et streaming cockpit

Objectif : construire la couche canonique de données de marché nécessaire aux charts avant le rendu
frontend.

Périmètre recommandé :

- historique initial Kraken REST ;
- mises à jour temps réel Kraken WebSocket ;
- normalisation des candles ;
- cache et, si requis, accumulation durable au-delà des limites historiques Kraken ;
- backfill/recovery sans look-ahead ;
- API historique et WebSocket cockpit ;
- chargement à la demande par marché/timeframe.

### Batch 19.6B — Vue Marchés, Lightweight Charts et markers

Objectif : ajouter la navigation cible et le rendu interactif en s'appuyant uniquement sur les
contrats backend de 19.6A.

Périmètre recommandé :

- navigation `Accueil | Marchés | Positions | Historique | Réglages` ;
- onglets par marché surveillé, incluant les positions ouvertes ;
- TradingView Lightweight Charts ;
- thème clair/sombre, timeframes, volume si disponible ;
- entrée moyenne, mark price et liquidation PERPETUAL ;
- markers BUY/SELL/réduction/clôture avec prix réel de fill ;
- hover/clic : timestamp, quantité, coûts, P&L réalisé, rationale Agent et résultat Risk ;
- lazy loading/cache, sans rendre tous les charts simultanément.

## Pourquoi cet ordre

La comptabilité SPOT précède le monitoring car le mark-to-market doit revaloriser un état canonique
complet et récupérable. Le monitoring précède le mode gestion car la décision « nouvelle exposition
impossible » doit reposer sur un état courant déterministe. La découverte/watchlist vient ensuite,
car elle introduit un second rythme IA et un nouvel état durable. L'explicabilité UI ne requiert pas
de changer l'autorité du moteur mais gagne à s'appuyer sur les identités de position/fill stabilisées.
Enfin, le chantier charts est volontairement séparé en backend de données puis rendu frontend afin de
préserver le backend comme source de vérité et de limiter chaque batch.

## Cadences à maintenir distinctes

La roadmap ne doit jamais fusionner implicitement :

1. **monitoring / mark-to-market** : rapide, déterministe, sans LLM ;
2. **cycle stratégique IA** : plus lent, décision BUY/SELL/HOLD ;
3. **découverte/révision de watchlist IA** : nettement plus lente.

Les valeurs définitives restent configurables et doivent être choisies sur mesures plutôt que figées
par ce document. Une cadence de découverte de l'ordre de 30 à 60 minutes est un exemple de départ,
pas une valeur contractuelle.

## Périmètres ultérieurs

- LIVE reste séparé et ultérieur avec permissions et barrières explicites ;
- FUTURE daté reste hors périmètre exécutable tant qu'un domaine/exécution dédiés n'est pas décidé ;
- multi-quote/FX reste à traiter explicitement avant un univers multi-devise ;
- enrichissement research additionnel uniquement sur besoin mesuré.
