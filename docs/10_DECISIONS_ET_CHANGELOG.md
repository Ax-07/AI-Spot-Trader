# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs
> et les décisions récentes nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Risk, SPOT sans short/levier, PERPETUAL avec protections déterministes, audit durable,
no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence GitHub avant intégration du Batch 18.9C

```text
HEAD GitHub audité      : 6e5dcdc1c33103bdd29e9c6fae5c1aca07856808
Dernier commit code     : 1eb94e79c3b14fea04faca67d6b2c695b9a27f51
Batch 18.9C             : validé localement, prêt à intégrer
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

**VALIDÉ LOCALEMENT.** Une Campaign créée depuis le navigateur transporte `market_type` comme chaîne
JSON. `ExecutableMarket` reste volontairement strict dans le domaine ; le Control Plane adapte donc
uniquement les valeurs canoniques `SPOT` et `PERPETUAL` vers `MarketType` avant la validation du
modèle imbriqué.

Une valeur inconnue n'est pas normalisée silencieusement et reste rejetée par la validation.
Le frontend, le Risk Engine, le TradingEngine et le Broker ne sont pas modifiés par ce correctif.

### ADR-190 — Corriger les frontières API mypy sans changer le runtime

**VALIDÉ LOCALEMENT.** La validation mypy globale a exposé quatre incompatibilités de typing
préexistantes entre valeurs `str` lues depuis les vues de persistence et schémas de réponse
`Literal[...]`.

La correction reste limitée aux frontières API :

- casts explicites pour `market_type` dans `paper_runs` ;
- cast explicite du `market_type` dans les résumés d'audit ;
- annotation explicite du type du modèle dynamique dans le prompt preview.

Aucune validation métier, décision Agent, règle Risk ou exécution Broker n'est modifiée.

## Changelog — 2026-09-24 — Batch 18.9C validé localement

Validation comportementale réelle effectuée depuis le cockpit :

- Strategy créée, renommée, archivée ; révisions immuables, comparaison et preview confirmées ;
- refus 409 confirmé lors d'une tentative de révision sur Strategy archivée ;
- bug de création Campaign identifié sur l'adaptation JSON de `market_type`, puis corrigé ;
- Campaign SPOT créée et activée avec Luna ;
- sélection multi-marchés réelle BTC/ETH/SOL par le même Agent ;
- BUY SPOT naturel sur SOL/USD : quantité proposée par l'Agent réduite par Risk pour respecter le
  max order notional, puis fill PAPER avec frais, spread et slippage ;
- HOLD naturels observés et journalisés sans exécution ;
- `run-cycle` isolé confirmé : un cycle et moteur restant `STOPPED` ;
- Start/Stop confirmés sur la boucle autonome backend ;
- après restart backend : aucune Campaign ni moteur repris automatiquement ;
- `run-cycle` sans runtime confirmé en 503 fail-closed ;
- reprise explicite confirmée avec nouveau `paper_run_id`, lineage correct et restauration exacte
  du ledger USD/ETH/SOL ;
- Campaign PERPETUAL BTC/ETH/SOL créée avec levier 2, marge `ISOLATED`, caps de position et
  d'exposition ;
- cycle PERPETUAL réel : sélection SOL/USD, BUY naturel, Risk `MODIFY`, fill PAPER, marge isolée,
  position LONG, maintenance margin et liquidation price persistés ;
- 422 confirmé pour un levier PAPER supérieur au plafond Risk ;
- Campaign `gpt-5.6-sol` persistée avec digests distincts ; aucune exécution Sol n'a été lancée
  dans ce batch ;
- aucun SELL naturel observé et aucun SELL forcé.

Validation locale opérateur finale :

```text
pytest backend : 506 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed
mypy backend/src : Success: no issues found in 89 source files
git diff --check : OK hors avertissements LF -> CRLF
git status --short : 8 fichiers attendus uniquement
```
