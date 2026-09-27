# 09 — Roadmap de développement

## Référence de reprise

```text
Base GitHub avant Batch 19.13 : 18596ac9d4f6554aa4817a9bdb374ab597c2399f
Correctif PAPER PERPETUAL  : intégré
Batch 19.13                : présent dans cet état et validé
Migration 19.13            : 0006_paper_control_plane -> 0007_multi_decision_cycles
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Jalons intégrés avant 19.13

- 18.x : tools Agent read-only, sélection multi-marchés, expérimentation, recovery, résilience et Control Plane ;
- 19.1 : comptabilité SPOT canonique ;
- 19.2 : mark-to-market, equity/exposition backend et monitors sans LLM ;
- 19.3 : `CapacityEvaluator`, `NORMAL` / `MANAGEMENT` et barrière Risk ;
- 19.4 : discovery Kraken et watchlist multi-marchés par le même Agent ;
- 19.5 : explicabilité Agent/Risk/exécution depuis les faits persistés ;
- 19.6A/19.6B : candles backend, streaming partagé, vue Marchés et markers de fills ;
- 19.7 : overlays de position canoniques ;
- 19.8 : façade utilisateur Session ;
- 19.9A : Trading Style `SCALP` / `SWING` et coûts Agent ;
- 19.9B : contexte stratégique `strategic-mtf-v1` causal ;
- 19.9C : UX Session du style ;
- 19.10 : gestion stratégique des positions et rotation du capital ;
- 19.12 : classification robuste des limites fournisseur OpenAI, retry borné et fail-closed ;
- correctif post-19.12 : précision PAPER PERPETUAL et quantum de quantité dérivé, intégré au HEAD `18596ac…`.

## Cadences à maintenir distinctes

1. monitoring / mark-to-market : déterministe, sans LLM ;
2. cycle stratégique IA : plan ordonné `BUY` / `SELL` / `HOLD` ;
3. discovery / watchlist IA : même Agent, cadence distincte ;
4. streaming marché / candles : technique, déterministe, sans LLM.

## Batch 19.13 — Cycle stratégique multi-marchés / multi-décisions

**État : implémenté et validé dans le présent état du repository.**

### Objectif atteint

Permettre à un seul cycle stratégique de contenir plusieurs décisions ordonnées sur des marchés distincts, sans introduire de second Agent, sans déplacer la stratégie dans du code déterministe et sans affaiblir Risk.

### Contrat stratégique

- un seul Agent IA ;
- un seul appel stratégique de planification au stade décisionnel ;
- plusieurs `BUY` / `SELL` / `HOLD` possibles dans un même cycle ;
- ordre explicite ;
- `max_decisions_per_cycle` configurable ;
- défaut `6` ;
- hard limit `20`.

### Exécution causale

- Risk exécuté séquentiellement pour chaque décision ;
- chaque décision suivante voit le portefeuille après les exécutions précédentes ;
- `HOLD` ne stoppe pas le plan ;
- `REJECT` ne stoppe pas le plan ;
- un SELL peut libérer du capital pour une décision ultérieure, uniquement si le plan Agent le prévoit et si Risk l'autorise ;
- aucune règle automatique `SELL -> BUY`.

### Atomicité

- checkpoint PAPER au début du cycle ;
- erreur technique Risk/Broker => `FAILED` ;
- rollback PAPER atomique de toutes les mutations économiques du cycle ;
- audit de l'échec conservé.

### Persistence / API / cockpit

- migration `0007_multi_decision_cycles` ;
- relations d'audit 1:N pour decisions / Risk assessments / execution intents ;
- trajectoire ordonnée exposée par l'API et le cockpit ;
- compatibilité de lecture avec les anciens cycles/configurations ;
- analytics basés sur les fills/trades réels, pas sur le nombre de décisions.

### Validation locale fournie

Backend :

- ciblé : `51 passed` ;
- complet : `698 passed, 2 warnings` ;
- `alembic upgrade head` : succès sur PostgreSQL réel.

Frontend :

- `pnpm test` : `39 passed` ;
- `pnpm lint` : succès ;
- `pnpm typecheck` : succès ;
- `pnpm build` : succès.

### Documentation de batch

Voir `docs/24_BATCH_19_13_CYCLE_STRATEGIQUE_MULTI_MARCHES.md`.

## Étape d'intégration suivante

Après extraction de la synchronisation documentaire et validation locale :

```text
1. git status --short
2. git diff --check
3. vérifier que la migration locale est toujours en head
4. commit explicite Batch 19.13
5. push main uniquement sur décision de l'opérateur
```

Le HEAD GitHub réel doit rester la source de vérité pour déterminer l’identifiant de commit effectivement intégré ; ne pas déduire ce statut d’une ancienne mention documentaire.

## Périmètres ultérieurs

- LIVE reste séparé et ultérieur ;
- restauration d'une Session archivée si besoin démontré ;
- multi-quote/FX à traiter explicitement ;
- persistence durable des candles uniquement sur besoin démontré ;
- aucun ranking algorithmique stratégique introduit silencieusement ;
- aucune promesse de rendement.
