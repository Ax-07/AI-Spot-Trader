# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub audité pour 18.13 : b491719edd7cbeeada0be2905e63af7dd20dd06d
Commit fonctionnel 18.12      : b491719edd7cbeeada0be2905e63af7dd20dd06d
```

Le HEAD doit être revérifié au démarrage de chaque nouveau batch.

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
- 18.12 : simplification radicale de l'expérience opérateur.

## État

```text
18.9A  — Control Plane backend                                INTÉGRÉ
18.9B  — Cockpit configuration SPOT/PERPETUAL                 INTÉGRÉ / VALIDÉ
18.9C  — Validation comportementale                           INTÉGRÉ / VALIDÉ
18.10  — Refonte UX/UI Option A                               INTÉGRÉ / VALIDÉ
18.11  — Guide opérateur                                      INTÉGRÉ / VALIDÉ
18.12  — Simplification radicale expérience opérateur         INTÉGRÉ
18.13  — Dark mode, contrastes et modernisation               PATCH PRÉPARÉ / À VALIDER
```

## Batch 18.13 — dark mode, accessibilité et modernisation

### Objectif

Conserver le parcours simplifié de 18.12 tout en donnant au cockpit une qualité visuelle plus
professionnelle, lisible et cohérente en clair comme en sombre.

### Architecture visuelle

- `next-themes` pilote `light`, `dark` et `system` ;
- les couleurs métier reposent sur des tokens sémantiques plutôt que sur des couleurs dispersées ;
- `Button`, `Badge` et `Card` portent les corrections communes ;
- les anciens panneaux avancés restent compatibles grâce à une couche de compatibilité dark ciblée ;
- la couleur n'est pas le seul canal : signes P&L, libellés BUY/SELL/HOLD, ALLOW/MODIFY/REJECT et Exécuté/Non exécuté restent explicites.

### Contrats préservés

- aucun changement backend ;
- aucune logique Risk/Broker/portfolio ajoutée au frontend ;
- `CampaignConfiguration`, TradingEngine, RiskEngine et persistence inchangés ;
- aucune reprise silencieuse ;
- frontend toujours non requis pour que la boucle backend continue.

### Validation attendue avant intégration

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

`pnpm install` est nécessaire une fois pour installer `next-themes` et mettre à jour le lockfile local.

## Plus tard

- enrichissement research uniquement sur besoin mesuré ;
- multi-quote/FX explicite avant univers multi-devise ;
- FUTURE daté seulement avec domaine/exécution dédiés ;
- éventuel enrichissement du contrat SPOT si un vrai besoin de coût moyen/P&L par position est confirmé ;
- LIVE dans un projet/batch séparé avec permissions et barrières explicites.
