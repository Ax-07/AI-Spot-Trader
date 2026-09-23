# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs
> et les décisions récentes nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Risk, SPOT sans short/levier, PERPETUAL avec protections déterministes, audit durable,
no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence intégrée après Batch 18.9B

```text
Commit code 18.9B : 1eb94e79c3b14fea04faca67d6b2c695b9a27f51
Message            : feat: add PAPER control plane cockpit
```

18.9A et 18.9B sont intégrés. Le cockpit 18.9B a été validé localement avec `pnpm lint`,
`pnpm typecheck`, `pnpm build` et `git diff --check`.

## Décisions Batch 18.9A toujours actives

ADR-173 à ADR-181 restent applicables : StrategyRevision immuable, contrat Agent protégé séparé,
digest prompt déterministe, Campaign snapshot non sensible, `paper-experiment-v4`, distinction
Campaign/paper_run, ownership runtime backend, preview canonique et lineage recovery exposé.

## Décisions Batch 18.9B — intégrées

### ADR-182 — Le frontend reste un client du Control Plane

**INTÉGRÉ.** Le cockpit ne possède ni TradingEngine, ni RiskEngine, ni Broker, ni logique de
sélection d'opportunité. Il envoie des commandes aux routes canoniques et affiche leurs réponses.
Fermer ou redémarrer le frontend n'arrête pas le moteur backend.

### ADR-183 — Étendre le client API existant

**INTÉGRÉ.** Les routes Strategy/Campaign/prompt-preview/paper-runs et `run-cycle` sont ajoutées
à `frontend/src/lib/api/client.ts`, derrière le rewrite `/backend` déjà utilisé. Aucun second client,
SDK ou proxy métier n'est créé.

### ADR-184 — Ne pas dupliquer CampaignConfiguration dans une logique métier frontend

**INTÉGRÉ.** Le TypeScript décrit le payload pour la sûreté de compilation, mais les validators
métier restent Pydantic/backend : univers, quote/règlement, whitelist, FUTURE, ISOLATED, levier et
limites PERPETUAL, spread/slippage. L'UI affiche les refus 409/422/503 au lieu de les contourner.

### ADR-185 — Charger les révisions via le contrat unitaire existant

**INTÉGRÉ.** 18.9A n'expose pas de route de listing des révisions. Comme les révisions sont créées
séquentiellement de 1 à `latest_revision`, le cockpit lit chaque révision avec le GET canonique
existant. Aucun endpoint backend parallèle n'est ajouté pour 18.9B.

### ADR-186 — Le preview visuel ne recompose pas le prompt

**INTÉGRÉ.** Le frontend consomme `instructions` renvoyé par `/prompt-preview` et ne génère aucune
instruction stratégique. Le découpage visuel s'appuie sur les marqueurs de la composition canonique ;
en cas d'écart, le contenu retourné est affiché sans inventer de données. L'input futur reste
explicitement `dynamic_input=null`.

### ADR-187 — Ne pas persister les drafts Control Plane dans le navigateur

**INTÉGRÉ.** StrategyPrompt, CampaignConfiguration et paramètres Risk restent uniquement dans l'état
React avant envoi. Le nouveau cockpit n'utilise ni `localStorage` ni `sessionStorage` pour ces
données. Les secrets serveur ne sont ni demandés ni exposés.

### ADR-188 — Rendre l'activation et la reprise visiblement distinctes

**INTÉGRÉ.** Chaque Campaign propose deux actions distinctes : activation fraîche et reprise
explicite. Le cockpit ne déduit pas silencieusement laquelle utiliser ; le backend conserve les
règles de conflit/recovery et l'autorité fail-closed.

## Changelog — 2026-09-23 — Batch 18.9B intégré

Audit et intégration confirmés :

- commit code intégré `1eb94e79c3b14fea04faca67d6b2c695b9a27f51` ;
- Control Plane 18.9A fournit les contrats backend consommés par le cockpit ;
- aucun patch backend requis par 18.9B ;
- types API frontend alignés sur les contrats backend actuels ;
- client API existant étendu ;
- hook `use-control-plane` ajouté ;
- panneau Control Plane complet monté dans la page principale ;
- Strategy/StrategyRevision, prompt preview et Campaign builder exposés ;
- PAPER SPOT/PERPETUAL, Luna/Sol, Risk, levier déterministe et `ISOLATED` exposés ;
- activation fraîche, reprise explicite, `run-cycle`, Start et Stop exposés ;
- lineage Campaign/paper_run/recovery et digests affichés ;
- erreurs 409/422/503 rendues explicitement ;
- aucun stockage navigateur des prompts/Campaigns/secrets du Control Plane.

Validation ChatGPT réellement exécutée avant livraison :

```text
harness source : 50 assertions passées
node --experimental-strip-types --check types.ts : OK
node --experimental-strip-types --check client.ts : OK
node --experimental-strip-types --check use-control-plane.ts : OK
tsc ciblé avec stubs de dépendances : OK
```

Validation locale opérateur réellement exécutée après correctif ESLint :

```text
pnpm lint : OK
pnpm typecheck : OK
pnpm build : OK (Next.js 16.3.3)
git diff --check : OK hors avertissements LF -> CRLF
```

Aucun fichier backend n'est modifié par 18.9B ; `pytest backend`, Ruff et mypy ne sont donc pas
rejoués pour ce batch.
