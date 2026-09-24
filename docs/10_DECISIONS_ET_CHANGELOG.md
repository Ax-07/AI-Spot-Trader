# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs
> et les décisions récentes nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Risk, SPOT sans short/levier, PERPETUAL avec protections déterministes, audit durable,
no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence avant Batch 18.12

```text
HEAD main audité             : c6cf03e62ce49ad6b294ea1d4c44d933b4688b0a
Commit fonctionnel 18.11     : c02b9e8edd52b416969922f12a17e32f047d3989
Batch 18.12                  : PATCH PRÉPARÉ / NON INTÉGRÉ
```

## Décisions historiques toujours actives

- ADR-173 à ADR-181 : StrategyRevision immuable, contrat Agent protégé, digests, Campaign snapshot,
  identité expérimentale v4, distinction Campaign/paper_run, runtime backend et recovery ;
- ADR-182 à ADR-188 : frontend client du Control Plane, API unique, validators backend, preview
  canonique, pas de draft sensible persistant, activation et reprise distinctes ;
- ADR-189/190 : adaptation JSON `market_type` à la frontière API et typing sans changement runtime ;
- ADR-191/192 : Vue d'ensemble comme surface principale et réutilisation des panneaux canoniques ;
- ADR-193 à ADR-195 : aide progressive, règles métier au backend et guide opérateur versionné.

## Décisions Batch 18.12 — patch proposé

### ADR-196 — Orienter la navigation vers les tâches opérateur

**PATCH PROPOSÉ.** La navigation principale devient :

- Accueil ;
- Configurer ;
- Positions ;
- Historique ;
- Réglages.

Strategy, StrategyRevision, Campaign, paper_run, digests et lineage cessent d'être des prérequis de
navigation. Ils restent disponibles sous **Réglages > Avancé**.

### ADR-197 — Orchestrer les objets canoniques au lieu de créer un modèle métier simplifié parallèle

**PATCH PROPOSÉ.** L'assistant de configuration n'introduit aucun nouvel objet backend. Lorsqu'un
opérateur crée un test, le frontend enchaîne les appels canoniques existants :

```text
create Strategy (+ Revision r1)
-> create Campaign
-> optionnel : activate Campaign
-> optionnel : start Engine
```

Cette orchestration ne rend pas l'opération transactionnelle. Si une étape échoue après une
persistence réussie, l'objet déjà créé reste durable et consultable en mode avancé. Le frontend ne
le supprime ni ne le masque.

### ADR-198 — Les profils Risk sont des presets explicites de CampaignConfiguration

**PATCH PROPOSÉ.** Les profils UX ne contiennent aucune décision Risk dynamique. Ils convertissent le
capital et le profil choisi en valeurs persistées :

| Profil | ordre max | levier PERP | position dérivée max | exposition totale max | buffer |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prudent | 5 % | 1x | 10 % | 20 % | 1.25 |
| Équilibré | 10 % | 2x | 20 % | 40 % | 1.15 |
| Agressif | 20 % | 3x | 35 % | 70 % | 1.10 |

Le profil Personnalisé expose les champs détaillés. Le backend valide `CampaignConfiguration` et le
Risk Engine reste seul autorisé à ALLOW/MODIFY/REJECT une proposition Agent.

### ADR-199 — Ne pas reconstruire le coût moyen ni le P&L SPOT dans le frontend

**PATCH PROPOSÉ.** `AssetPositionResponse` ne fournit actuellement que `asset`, `quantity` et
`available`. Le cockpit n'infère donc pas un prix d'entrée ou un P&L par position à partir des fills.
Il affiche `—` pour ces valeurs et utilise les analytics backend pour le P&L/exposition globaux.

Cette décision évite une seconde comptabilité et respecte le backend comme source de vérité.

### ADR-200 — Faire d'Action suivante la porte d'entrée du pilotage courant

**PATCH PROPOSÉ.** L'Accueil dérive une action opérateur à partir des états déjà exposés par le
backend : absence de configuration, Campaign non activée, runtime STOPPED, moteur RUNNING ou session
historique à reprendre.

Une situation ambiguë renvoie vers les réglages avancés plutôt que d'effectuer automatiquement une
activation/reprise risquée. La reprise reste toujours explicite.

## Changelog — 2026-09-24 — Batch 18.12 préparé

Contenu du patch :

- navigation principale simplifiée à cinq tâches ;
- nouvel assistant de création PAPER avec SPOT/PERPETUAL, paires, capital, Luna/Sol, agressivité,
  instructions Agent et profils Risk ;
- boutons `Créer le test` et `Créer et démarrer` ;
- orchestration frontend des routes Strategy/Revision/Campaign/activation/Start existantes ;
- Accueil centré sur `Action suivante`, capital, P&L, positions, décision récente et alertes ;
- nouvelle vue Positions ;
- nouvelle vue Historique corrélée Agent -> Risk -> PAPER ;
- Guide, Assistant et ancien Control Plane déplacés sous Réglages ;
- aucun changement backend ;
- documentation opérateur simplifiée.

La validation `pnpm lint`, `pnpm typecheck` et `pnpm build` reste à exécuter localement avant de
qualifier le batch **INTÉGRÉ / VALIDÉ**.
