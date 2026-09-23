# 09 — Roadmap de développement

## Référence auditée

```text
HEAD main : efe5a0f162a69e50bd6e5f5cd7aa61039792e911
Code      : 11a04be33bf209552e6337e28318d039b775b264
```

## Jalons intégrés

- Batch 18.1 : tools Agent read-only et traces causales ;
- Batch 18.2 : sélection causale multi-marchés SPOT/PERPETUAL ;
- Batch 18.3 : validation comportementale et parsing Kraken margin schedules ;
- Batch 18.5 : `paper-experiment-v3` et identité tools/sélection ;
- Batch 18.6 : recovery `paper-ledger-recovery-v1`, migration `0005` ;
- Batch 18.7 : retries réseau bornés ;
- Batch 18.8 : validation réelle recovery/réseau, 20/20 cycles `COMPLETED`, tous `HOLD` ;
- Batch 18.9A : Control Plane backend, stratégies versionnées, Campaigns persistantes,
  `paper-experiment-v4`, migration `0006`, runtime canonique par Campaign.

## Batch 18.9 — découpage

```text
18.9A — Control Plane + persistence + stratégie/prompt backend      INTÉGRÉ
18.9B — Cockpit de configuration + PERPETUAL UI                    PATCH PRÉPARÉ / À VALIDER
18.9C — validation comportementale via cockpit                     APRÈS INTÉGRATION 18.9B
```

## Batch 18.9B — patch livré

Périmètre frontend :

- extension du client API existant, sans seconde couche transport ;
- types TS alignés sur les réponses backend 18.9A et sur le lineage `paper_run` ;
- création/liste/renommage/archivage Strategy ;
- lecture des révisions séquentielles, création d'une nouvelle StrategyRevision, comparaison ;
- prompt preview canonique avec sections visuelles ;
- builder Campaign SPOT/PERPETUAL ;
- Luna/Sol, agressivité, cadence, capital, règlement ;
- frais, spread, slippage ;
- limites Risk SPOT/PERPETUAL ;
- levier déterministe, marge `ISOLATED` ;
- activation fraîche et reprise explicite ;
- `run-cycle`, Start, Stop via les routes moteur canoniques ;
- vue Campaign active, `campaign_id`, `paper_run_id`, `resumed_from_paper_run_id`,
  `recovery_version` et digests ;
- rendu explicite des 409/422/503 backend ;
- aucun stockage local de prompt/Campaign, aucun secret, aucune logique Risk/Trading frontend.

Validation exécutée par ChatGPT :

```text
harness source : 50 assertions passées
Node strip-types syntax checks : OK
TypeScript ciblé avec stubs de dépendances : OK
```

Non exécuté dans l'environnement ChatGPT :

```text
pnpm lint
pnpm typecheck
pnpm build
```

Cause : pnpm absent et Corepack ne peut pas joindre le registre. Le backend n'a pas été modifié ;
la suite backend n'est donc pas rejouée dans ce batch.

## Batch 18.9C — après validation/intégration 18.9B

Validation comportementale réelle via navigateur :

- création Strategy puis nouvelles révisions ;
- comparaison et preview ;
- Campaign SPOT ;
- Campaign PERPETUAL avec limites obligatoires ;
- activation fraîche ;
- run-cycle réel ;
- Start/Stop ;
- restart backend puis reprise explicite et vérification du lineage ;
- changement structurel => nouvelle Campaign, jamais resume ;
- observation de BUY/SELL naturels si le marché/Agent en produit, sans forcer artificiellement une
  décision stratégique ;
- comparaison Luna/Sol et audit des digests ;
- contrôle de l'absence de secrets et de replay.

## Plus tard

- enrichissement research uniquement sur besoin mesuré ;
- multi-quote/FX explicite avant tout univers multi-devise ;
- FUTURE daté seulement avec domaine/exécution dédiés ;
- LIVE dans un projet/batch séparé avec permissions et barrières explicites.
