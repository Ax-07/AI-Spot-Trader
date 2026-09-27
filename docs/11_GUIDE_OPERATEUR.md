# 11 — Guide opérateur

> Guide pratique du cockpit AI Spot Trader. Le parcours principal utilise **Session**. Les objets Strategy, StrategyRevision, Campaign, paper_run, digests et UUID restent dans **Réglages > Avancé**.

## 1. Avant de commencer

AI Spot Trader fonctionne actuellement en **PAPER uniquement** avec Kraken. Le frontend est un cockpit ; moteur de trading, mark-to-market, Risk, Broker et discovery restent dans le backend.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

Une sortie LLM ne déclenche jamais directement un ordre. LIVE n'est pas disponible.

## 2. Navigation

Le parcours normal comporte :

- **Accueil** : état et prochaine action ;
- **Sessions** : créer et piloter les configurations PAPER ;
- **Marchés** : watchlist, charts, positions et fills ;
- **Positions** : portefeuille et P&L backend ;
- **Historique** : trajectoire Agent → Risk → exécution PAPER ;
- **Réglages** : apparence, aide et mode avancé.

## 3. Qu'est-ce qu'une Session ?

```text
Session
-> Strategy
-> StrategyRevision(s)
-> Campaign(s)
-> paper_run(s)
```

Ces objets techniques assurent l'immuabilité, l'audit et le recovery mais ne sont pas requis dans le parcours normal.

## 4. Créer une Session

La configuration simple demande notamment : nom, marché `SPOT`/`PERPETUAL`, style `SCALP`/`SWING`, mode de marchés, capital PAPER, Luna/Sol, agressivité, profil Risk et instructions.

`Créer` persiste sans démarrer. `Créer et démarrer` crée puis active explicitement le moteur backend.

### Style de trading

| Style | Cadence stratégique | Watchlist refresh | Timeframes |
| --- | ---: | ---: | --- |
| SCALP | 60 s | 300 s | `1m · 5m · 15m · 30m` |
| SWING | 900 s | 1800 s | `1h · 4h · 1d` |

Changer de style ne remplace pas automatiquement une cadence déjà personnalisée. Le style, l'agressivité, le mode de marchés et Risk restent indépendants.

## 5. Mode marchés Automatique — IA

Le bootstrap/fallback n'oblige pas l'Agent à trader les paires saisies.

Le pipeline Batch 19.13 devient :

```text
Kraken
-> filtrage déterministe d'admissibilité
-> candidats
-> même Agent choisit la watchlist si refresh nécessaire
-> contexte stratégique causal
-> même Agent produit un plan ordonné de décisions
-> pour chaque décision : Risk puis PaperBroker éventuel
```

La discovery n'est pas un second Agent et ne produit aucun score stratégique déterministe.

## 6. Mode marchés Manuel

Dans ce mode :

- aucune Market Discovery ;
- l'Agent travaille uniquement dans l'univers fourni ;
- la whitelist Risk est alignée sur cet univers ;
- le plan peut contenir plusieurs décisions sur des marchés distincts de cet univers ;
- Risk reste final pour chaque décision.

Toutes les paires d'une Session simple conservent le même actif de règlement attendu par les contrats existants.

## 7. Profils Risk

Les profils sont des raccourcis UX vers la configuration. Ils ne remplacent jamais le Risk Engine.

| Profil | Ordre max | Levier PERP | Position dérivée max | Exposition dérivée totale max | Buffer liquidation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prudent | 5 % du capital | 1x | 10 % | 20 % | 1.25 |
| Équilibré | 10 % | 2x | 20 % | 40 % | 1.15 |
| Agressif | 20 % | 3x | 35 % | 70 % | 1.10 |
| Personnalisé | saisi | saisi | saisi | saisi | saisi |

Le plafond d'ordre s'applique décision par décision. Le portefeuille et l'exposition sont recalculés causalement entre les décisions du même cycle.

## 8. Configuration avancée

La configuration avancée expose les valeurs réellement utilisées : style, timeframes, cadence, coûts PAPER, timeouts, caps Risk, paramètres PERPETUAL, whitelist éventuelle et paramètres de Market Discovery.

Le Batch 19.13 ajoute également `max_decisions_per_cycle` :

- défaut : `6` ;
- limite dure backend : `20`.

Augmenter cette valeur n'oblige pas l'Agent à produire autant de décisions et n'augmente aucune limite Risk par elle-même.

## 9. Statuts Session

- **Brouillon** : jamais exécutée ;
- **Prête** : runtime chargé, moteur arrêté ;
- **En cours** : moteur autonome RUNNING ;
- **Arrêtée** : historique existant mais non active ;
- **À reprendre** : recovery explicite requis/possible ;
- **Archivée** : retirée de la liste normale.

Ces statuts sont dérivés des faits backend.

## 10. Démarrer, arrêter, reprendre, tester un cycle

### Démarrer

Une Session jamais exécutée utilise une activation fraîche puis démarre le moteur.

### Arrêter

`Arrêter` stoppe la boucle, ferme le runtime et termine durablement le `paper_run`. Fermer seulement le navigateur ne stoppe pas le moteur.

### Reprendre

Une Campaign déjà exécutée utilise le recovery explicite prévu par le backend ; aucune reprise silencieuse après restart.

### Tester 1 cycle

`Tester 1 cycle` exécute exactement **un cycle canonique** puis laisse le moteur autonome arrêté. Depuis le Batch 19.13, ce cycle unique peut contenir plusieurs décisions et plusieurs exécutions PAPER sur des marchés distincts.

## 11. Comment lire un cycle multi-décisions

L'Historique doit être lu comme une trajectoire ordonnée :

```text
Décision 1
  -> rationale Agent
  -> Risk
  -> exécution/fill éventuel
Décision 2
  -> rationale Agent
  -> Risk sur le portefeuille déjà mis à jour
  -> exécution/fill éventuel
...
```

`HOLD` et `REJECT` sont des résultats normaux et auditables. Ils n'empêchent pas l'affichage ni le traitement des décisions suivantes.

Le nombre de lignes de décision ne correspond pas nécessairement au nombre de trades : seuls les fills réellement exécutés comptent comme activité économique.

## 12. Échec technique d'un cycle

Si une erreur technique Risk ou Broker intervient après une ou plusieurs exécutions PAPER, le cycle devient `FAILED` et le backend restaure le portefeuille au checkpoint du début du cycle.

Ainsi, un cycle échoué ne laisse pas un portefeuille partiellement muté. L'Historique conserve néanmoins les informations nécessaires pour diagnostiquer le stage technique en échec.

Un `REJECT` Risk n'est pas une erreur technique et ne déclenche pas ce rollback.

## 13. Modifier, dupliquer, archiver

Les règles d'immuabilité restent inchangées :

- nom seul : rename Strategy ;
- instructions : nouvelle StrategyRevision ;
- configuration : nouvelle Campaign ;
- duplication : nouvelle Session sans historique ;
- suppression UX : archivage logique, pas suppression des faits trading.

Une Session en cours doit être arrêtée avant modification.

## 14. SPOT et PERPETUAL

### SPOT

Pas de short, levier ni marge. `SELL` ne peut réduire qu'un actif réellement détenu. Dans un plan, chaque SELL est évalué sur la quantité encore disponible à cet instant.

### PERPETUAL

Périmètre actuel : contrats linéaires PAPER selon les capacités intégrées, marge `ISOLATED`, levier/caps déterministes. Le LLM ne choisit jamais librement le levier.

Le correctif intégré au HEAD `18596ac…` normalise les quantités autorisées sur le quantum provider-derived et préserve l'exactitude des fills PAPER.

## 15. Positions, Marchés et Historique

Le frontend affiche les faits backend et ne les reconstruit pas :

- P&L/exposition depuis le backend ;
- candles via le pipeline backend ;
- markers depuis les fills persistés ;
- prix moyen/mark/liquidation depuis `/portfolio` ;
- trajectoires de décisions et résultats Risk depuis l'audit.

Une valeur absente reste absente ; aucune causalité financière n'est inventée côté navigateur.

## 16. Réglages > Avancé

Surface de diagnostic pour Strategies, StrategyRevision, Campaigns, comparaison de versions, prompt preview, activation/recovery technique, digests, UUID et paramètres détaillés.

Le parcours normal doit privilégier **Sessions**.

## 17. Sécurité et invariants

- PAPER uniquement ;
- un seul Agent IA ;
- Kraken ;
- Risk final pour chaque décision ;
- aucune sortie LLM directe vers Broker ;
- décisions exécutées séquentiellement et causalement ;
- toutes les décisions, `HOLD`/`REJECT` inclus, auditables ;
- aucune donnée future / look-ahead ;
- frontend = cockpit seulement ;
- LIVE reste séparé ;
- aucune promesse de rendement.
