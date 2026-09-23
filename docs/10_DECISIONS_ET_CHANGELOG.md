# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs
> et les décisions récentes nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Risk, SPOT sans short/levier, PERPETUAL avec protections déterministes, audit durable,
no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence de départ Batch 18.9B

```text
HEAD GitHub : efe5a0f162a69e50bd6e5f5cd7aa61039792e911
Code intégré: 11a04be33bf209552e6337e28318d039b775b264
```

18.9A est intégré. 18.9B est un patch frontend non intégré tant que l'opérateur ne l'a pas validé,
committé et poussé.

## Décisions Batch 18.9A toujours actives

ADR-173 à ADR-181 restent applicables : StrategyRevision immuable, contrat Agent protégé séparé,
digest prompt déterministe, Campaign snapshot non sensible, `paper-experiment-v4`, distinction
Campaign/paper_run, ownership runtime backend, preview canonique et lineage recovery exposé.

## Décisions Batch 18.9B — patch proposé

### ADR-182 — Le frontend reste un client du Control Plane

**PATCH PROPOSÉ.** Le cockpit ne possède ni TradingEngine, ni RiskEngine, ni Broker, ni logique de
sélection d'opportunité. Il envoie des commandes aux routes canoniques et affiche leurs réponses.
Fermer ou redémarrer le frontend n'arrête pas le moteur backend.

### ADR-183 — Étendre le client API existant

**PATCH PROPOSÉ.** Les routes Strategy/Campaign/prompt-preview/paper-runs et `run-cycle` sont ajoutées
à `frontend/src/lib/api/client.ts`, derrière le rewrite `/backend` déjà utilisé. Aucun second client,
SDK ou proxy métier n'est créé.

### ADR-184 — Ne pas dupliquer CampaignConfiguration dans une logique métier frontend

**PATCH PROPOSÉ.** Le TypeScript décrit le payload pour la sûreté de compilation, mais les
validators métier restent Pydantic/backend : univers, quote/règlement, whitelist, FUTURE,
ISOLATED, levier et limites PERPETUAL, spread/slippage. L'UI affiche les refus 409/422/503 au lieu
de les contourner.

### ADR-185 — Charger les révisions via le contrat unitaire existant

**PATCH PROPOSÉ.** 18.9A n'expose pas de route de listing des révisions. Comme les révisions sont
créées séquentiellement de 1 à `latest_revision`, le cockpit lit chaque révision avec le GET
canonique existant. Aucun endpoint backend parallèle n'est ajouté pour 18.9B.

### ADR-186 — Le preview visuel ne recompose pas le prompt

**PATCH PROPOSÉ.** Le frontend consomme `instructions` renvoyé par `/prompt-preview` et ne génère
aucune instruction stratégique. Le découpage visuel s'appuie sur les marqueurs de la composition
canonique ; en cas d'écart, le contenu retourné est affiché sans inventer de données. L'input futur
reste explicitement `dynamic_input=null`.

### ADR-187 — Ne pas persister les drafts Control Plane dans le navigateur

**PATCH PROPOSÉ.** StrategyPrompt, CampaignConfiguration et paramètres Risk restent uniquement dans
l'état React avant envoi. Le nouveau cockpit n'utilise ni `localStorage` ni `sessionStorage` pour
ces données. Les secrets serveur ne sont ni demandés ni exposés.

### ADR-188 — Rendre l'activation et la reprise visiblement distinctes

**PATCH PROPOSÉ.** Chaque Campaign propose deux actions distinctes : activation fraîche et reprise
explicite. Le cockpit ne déduit pas silencieusement laquelle utiliser ; le backend conserve les
règles de conflit/recovery et l'autorité fail-closed.

## Changelog — 2026-09-23 — Batch 18.9B patch frontend

Audit confirmé :

- GitHub `main = efe5a0f162a69e50bd6e5f5cd7aa61039792e911` ;
- dernier code `11a04be33bf209552e6337e28318d039b775b264` ;
- l'écart est documentaire et finalise l'intégration 18.9A ;
- Control Plane 18.9A fournit tous les contrats indispensables au cockpit ;
- aucun patch backend requis.

Implémentation proposée :

- types API frontend remis au niveau des contrats backend actuels ;
- client API étendu ;
- hook `use-control-plane` ;
- panneau Control Plane complet ;
- montage dans la page principale ;
- documentation 18.9B.

Validation ChatGPT réellement exécutée :

```text
harness source : 50 assertions passées
node --experimental-strip-types --check types.ts : OK
node --experimental-strip-types --check client.ts : OK
node --experimental-strip-types --check use-control-plane.ts : OK
tsc ciblé avec stubs de dépendances : OK
```

Les commandes `pnpm lint`, `pnpm typecheck` et `pnpm build` restent à exécuter localement : pnpm
n'est pas disponible dans l'environnement ChatGPT et Corepack ne peut pas accéder au registre.

Aucun fichier backend n'est modifié par 18.9B ; `pytest backend`, Ruff et mypy ne sont donc pas
rejoués pour ce patch.
