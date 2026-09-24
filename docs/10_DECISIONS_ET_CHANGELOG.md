# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs
> et les décisions récentes nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Risk, SPOT sans short/levier, PERPETUAL avec protections déterministes, audit durable,
no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence intégrée après Batch 18.9C

```text
HEAD GitHub : 5fc7704e7ca43ded4c2565b21871b81fe2161b0a
Message     : fix: finalize batch 18.9C behavioral validation
Batch 18.9C: intégré et validé
```

## Décisions Batch 18.9A toujours actives

ADR-173 à ADR-181 restent applicables : StrategyRevision immuable, contrat Agent protégé séparé,
digest prompt déterministe, Campaign snapshot non sensible, `paper-experiment-v4`, distinction
Campaign/paper_run, ownership runtime backend, preview canonique et lineage recovery exposé.

## Décisions Batch 18.9B toujours actives

ADR-182 à ADR-188 restent applicables : frontend client du Control Plane, client API unique,
validators métier backend, révisions lues via les contrats existants, preview non recomposé côté
frontend, aucun draft Control Plane persistant dans le navigateur, activation fraîche et reprise
explicitement distinctes.

## Décisions Batch 18.9C

### ADR-189 — Adapter les enums JSON à la frontière Control Plane sans relâcher le domaine strict

**INTÉGRÉ.** Une Campaign créée depuis le navigateur transporte `market_type` comme chaîne JSON.
`ExecutableMarket` reste strict dans le domaine ; le Control Plane adapte uniquement les valeurs
canoniques `SPOT` et `PERPETUAL` vers `MarketType` avant la validation du modèle imbriqué.

Une valeur inconnue n'est pas normalisée silencieusement et reste rejetée par la validation.
Le frontend, le Risk Engine, le TradingEngine et le Broker ne sont pas modifiés par ce correctif.

### ADR-190 — Corriger les frontières API mypy sans changer le runtime

**INTÉGRÉ.** La validation mypy globale avait exposé quatre incompatibilités de typing entre valeurs
`str` lues depuis les vues de persistence et schémas de réponse `Literal[...]`.

La correction reste limitée aux frontières API :

- casts explicites pour `market_type` dans `paper_runs` ;
- cast explicite du `market_type` dans les résumés d'audit ;
- annotation explicite du type du modèle dynamique dans le prompt preview.

Aucune validation métier, décision Agent, règle Risk ou exécution Broker n'est modifiée.

## Changelog — 2026-09-24 — Batch 18.9C intégré et validé

Le commit `5fc7704e7ca43ded4c2565b21871b81fe2161b0a` est intégré sur `main`.

Validation comportementale réelle effectuée depuis le cockpit avant intégration :

- Strategy créée, renommée, archivée ; révisions immuables, comparaison et preview confirmées ;
- refus 409 confirmé lors d'une tentative de révision sur Strategy archivée ;
- correctif de création Campaign intégré pour l'adaptation JSON de `market_type` ;
- Campaign SPOT créée et activée avec Luna ;
- sélection multi-marchés réelle BTC/ETH/SOL par le même Agent ;
- BUY SPOT naturel sur SOL/USD : quantité proposée par l'Agent réduite par Risk pour respecter le
  max order notional, puis fill PAPER avec frais, spread et slippage ;
- HOLD naturels observés et journalisés sans exécution ;
- `run-cycle` isolé confirmé : un cycle et moteur restant `STOPPED` ;
- Start/Stop confirmés sur la boucle autonome backend ;
- après restart backend : aucune Campaign ni moteur repris automatiquement ;
- `run-cycle` sans runtime confirmé en 503 fail-closed ;
- reprise explicite confirmée avec nouveau `paper_run_id`, lineage correct et restauration du ledger ;
- Campaign PERPETUAL BTC/ETH/SOL créée avec levier 2, marge `ISOLATED`, caps de position et
  d'exposition ;
- cycle PERPETUAL réel : sélection SOL/USD, BUY naturel, Risk `MODIFY`, fill PAPER, marge isolée et
  position LONG persistée ;
- 422 confirmé pour un levier PAPER supérieur au plafond Risk ;
- `gpt-5.6-sol` sélectionnable et persisté par configuration avec digests distincts ;
- aucun SELL naturel observé et aucun SELL forcé.

Validation locale opérateur exécutée avant le push du commit intégré :

```text
pytest backend : 506 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed
mypy backend/src : Success: no issues found in 89 source files
git diff --check : OK hors avertissements LF -> CRLF
working tree propre avant push
```
