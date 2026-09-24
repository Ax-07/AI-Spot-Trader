# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub audité pour 18.12 : c6cf03e62ce49ad6b294ea1d4c44d933b4688b0a
Commit fonctionnel 18.11      : c02b9e8edd52b416969922f12a17e32f047d3989
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
- 18.9A : Control Plane backend, Strategy/Revision, Campaigns, `paper-experiment-v4`, migration
  `0006`, runtime canonique par Campaign ;
- 18.9B : cockpit Control Plane frontend SPOT/PERPETUAL ;
- 18.9C : validation comportementale réelle via cockpit ;
- 18.10 : refonte UX/UI Option A, `CockpitShell` et Vue d'ensemble ;
- 18.11 : guide opérateur et aide contextuelle.

## État

```text
18.9A  — Control Plane backend                                INTÉGRÉ
18.9B  — Cockpit configuration SPOT/PERPETUAL                 INTÉGRÉ / VALIDÉ
18.9C  — Validation comportementale                           INTÉGRÉ / VALIDÉ
18.10  — Refonte UX/UI Option A                               INTÉGRÉ / VALIDÉ
18.11  — Guide opérateur                                      INTÉGRÉ / VALIDÉ
18.12  — Simplification radicale expérience opérateur         PATCH PRÉPARÉ / À VALIDER
```

## Batch 18.12 — simplification radicale expérience opérateur

### Objectif

Passer d'une interface qui rend l'architecture backend compréhensible à une interface où cette
architecture n'est plus nécessaire pour réussir un premier test PAPER.

### Architecture proposée

```text
CockpitShell
├─ Accueil
│  ├─ Action suivante
│  ├─ état du bot
│  ├─ configuration humaine
│  ├─ capital / P&L / positions
│  ├─ dernière décision + Risk
│  └─ alertes
├─ Configurer
│  └─ assistant Marché -> Capital -> IA -> Sécurité -> Résumé
├─ Positions
├─ Historique
│  └─ Agent -> Risk -> PAPER par cycle
└─ Réglages
   ├─ Aide
   ├─ Assistant
   └─ Avancé : Control Plane historique
```

### Orchestration

Aucun endpoint backend supplémentaire n'est nécessaire. Le frontend appelle séquentiellement les
routes canoniques existantes pour créer le test puis, sur demande, l'activer et le démarrer.
Activation fraîche et reprise restent deux opérations différentes.

### Profils Risk UX

- **Prudent** : ordre 5 % capital, PERP 1x, position 10 %, exposition 20 %, buffer 1.25 ;
- **Équilibré** : ordre 10 %, PERP 2x, position 20 %, exposition 40 %, buffer 1.15 ;
- **Agressif** : ordre 20 %, PERP 3x, position 35 %, exposition 70 %, buffer 1.10 ;
- **Personnalisé** : champs canoniques avancés.

Ces valeurs sont des presets frontend explicites. Elles ne changent aucune règle du Risk Engine.

### Contrats préservés

- backend canonique inchangé ;
- `CampaignConfiguration` inchangée ;
- TradingEngine/RiskEngine/PaperBroker inchangés ;
- persistence/migrations inchangées ;
- chat informatif inchangé ;
- aucune reprise silencieuse ;
- frontend toujours non requis pour que la boucle backend continue.

### Limite connue conservée

Les positions SPOT ne possèdent pas dans `PortfolioResponse` de prix d'entrée moyen ni de P&L par
position. Le cockpit 18.12 refuse de les inventer et affiche les métriques globales backend à la
place.

### Validation attendue avant intégration

```powershell
cd frontend
pnpm lint
pnpm typecheck
pnpm build
cd ..
git diff --check
git status --short
```

Si ces validations passent, le batch peut être commité puis la référence fonctionnelle mise à jour
dans `docs/00_ETAT_ACTUEL.md`.

## Plus tard

- enrichissement research uniquement sur besoin mesuré ;
- multi-quote/FX explicite avant univers multi-devise ;
- FUTURE daté seulement avec domaine/exécution dédiés ;
- éventuel enrichissement du contrat SPOT si un vrai besoin de coût moyen/P&L par position est
  confirmé ;
- LIVE dans un projet/batch séparé avec permissions et barrières explicites.
