# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs, les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers Broker/Kraken, SPOT sans short/levier, PERPETUAL selon les capacités intégrées, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

## Référence courante

```text
Base GitHub avant 19.13 : 18596ac9d4f6554aa4817a9bdb374ab597c2399f
Commit              : fix: harden paper perpetual execution precision
Batch 19.13         : présent dans cet état et validé
```

## Décisions historiques toujours actives

- ADR-173 à ADR-239 : immutabilité Strategy/Campaign, Control Plane, accounting, monitoring, discovery, explicabilité, candles/charts et overlays ;
- ADR-240 à ADR-247 : façade Session, lifecycle, immutabilité et modes de marchés ;
- ADR-248 à ADR-255 : Trading Style, coûts Agent et contexte stratégique multi-timeframes ;
- ADR-256 à ADR-258 : UX Session du style et compatibilité legacy ;
- ADR-259 à ADR-262 : gestion stratégique des positions, `position-management-v1`, plafond Risk par ordre et rotation du capital ;
- ADR-263 : classification robuste des limites fournisseur OpenAI et fail-closed ;
- ADR-264 : précision PAPER PERPETUAL et normalisation descendante du quantum, désormais intégrée ;
- ADR-265 à ADR-268 : décisions Batch 19.13 multi-décisions / multi-marchés.

## ADR-240 — Session est une façade UX, pas un nouvel agrégat persistant

**ADOPTÉ AU BATCH 19.8.**

`Session` reste une projection sur Strategy, StrategyRevision, Campaign, paper_run et runtime actif. Aucune table `sessions` n'est créée.

## ADR-241 — La création Session est atomique côté backend

**ADOPTÉ AU BATCH 19.8.**

Strategy + StrategyRevision 1 + Campaign sont créées dans une seule transaction. L'ordre de flush respecte les foreign keys sans réduire l'atomicité.

## ADR-242 à ADR-247 — Versioning, archivage, lifecycle et marchés

**ADOPTÉS AU BATCH 19.8.**

Les modifications créent de nouveaux faits immuables ; `Supprimer` archive ; les statuts sont dérivés ; `stop` ferme runtime/run ; `AUTOMATIC_AI` et `MANUAL` restent explicites ; les defaults de discovery restent backend-canoniques.

## ADR-248 à ADR-255 — Style, coûts et multi-timeframes

**ADOPTÉS AUX BATCHES 19.9A/19.9B.**

`SCALP`/`SWING`, `trading-style-map-v1`, `ExecutionCostContext` et `strategic-mtf-v1` enrichissent l'Agent sans modifier Risk. `history_as_of(...)` garantit la causalité des candles. Aucun indicateur ne devient une règle BUY/SELL/HOLD.

## ADR-256 à ADR-258 — UX du style

**ADOPTÉS AU BATCH 19.9C.**

Le style est exposé sans couplage silencieux à l'agressivité, aux marchés ou à Risk. Les recommandations de cadence sont explicites ; une Campaign legacy sans style reste `Hérité / non défini`.

## ADR-259 — Les positions ouvertes restent des opportunités stratégiques en NORMAL

**ADOPTÉ AU BATCH 19.10.**

`CapacityAssessment.management_markets` reste renseigné même lorsque de nouvelles ouvertures sont possibles. Le même Agent arbitre entre gestion d'inventaire et nouvelles opportunités.

La phrase historique « une seule décision finale par cycle » est **supersédée uniquement sur la cardinalité** par ADR-265. Le principe d'arbitrage stratégique par le même Agent reste actif.

## ADR-260 — `position-management-v1` reste factuel

**ADOPTÉ AU BATCH 19.10.**

Le contexte expose inventaire, coût, mark, P&L et estimation de sortie nette sans score, `should_sell` ou take-profit automatique.

## ADR-261 — `risk_max_order_notional` reste un plafond par ordre

**ADOPTÉ AU BATCH 19.10.**

Le plafond reste applicable aux BUY comme aux SELL réducteurs. Le Batch 19.13 ne change pas cette sémantique : chaque décision du plan est évaluée séparément par Risk.

## ADR-262 — La rotation du capital reste pilotée par l'Agent

**ADOPTÉ AU BATCH 19.10, ÉTENDU PAR LE BATCH 19.13.**

Il n'existe aucune règle `après SELL -> BUY`. Historiquement la rotation se produisait nécessairement sur plusieurs cycles ; ADR-265/266 permettent désormais aussi une rotation intra-cycle lorsque le plan Agent ordonne plusieurs décisions et que Risk les autorise séquentiellement.

## ADR-263 — Les limites fournisseur OpenAI sont classifiées avant retry

**ADOPTÉ AU BATCH 19.12.**

Quota/crédit/usage/spend sont non retryables ; les limitations temporaires restent retryables avec `Retry-After` valide ou backoff borné. Toute erreur LLM reste fail-closed : aucun HOLD artificiel et aucun fallback algorithmique.

## ADR-264 — Précision PAPER PERPETUAL et quantum provider-derived

**ADOPTÉ ET INTÉGRÉ AU HEAD `18596ac9d4f6554aa4817a9bdb374ab597c2399f`.**

Pour les dérivés Kraken exécutables, le quantum de quantité dérivé du provider est utilisé pour normaliser exclusivement vers le bas les quantités autorisées. Les minimums/plafonds sont revérifiés.

`estimate_paper_execution()` utilise l'ordre canonique `price × quantity × contract_size` et maintient l'égalité exacte attendue entre le delta de prix exécuté et les composantes spread/slippage. Les validations `Fill` restent strictes.

## ADR-265 — Un cycle peut porter un plan stratégique ordonné multi-marchés

**ADOPTÉ LOCALEMENT AU BATCH 19.13 — NON ENCORE INTÉGRÉ.**

Au stade décisionnel du cycle, un seul appel du même Agent stratégique produit un plan ordonné contenant plusieurs décisions sur des marchés distincts.

Le plan accepte `BUY`, `SELL` et `HOLD`. `max_decisions_per_cycle` est configurable, vaut `6` par défaut et possède une limite dure de `20`.

Cette décision supprime la contrainte de cardinalité mono-décision sans créer de second Agent, sans boucle d'appels stratégiques indépendants et sans déplacer la décision vers un ranking déterministe.

## ADR-266 — Risk et Broker suivent l'ordre du plan sur un portefeuille causal

**ADOPTÉ LOCALEMENT AU BATCH 19.13 — NON ENCORE INTÉGRÉ.**

Chaque décision est évaluée par Risk après application des éventuelles exécutions précédentes du même cycle. Une décision suivante ne voit jamais un snapshot de portefeuille antérieur à la trajectoire déjà exécutée.

`HOLD` et `REJECT` n'interrompent pas le plan. Risk conserve `ALLOW` / `MODIFY` / `REJECT` pour chaque décision et reste la seule autorité capable de produire une intention d'exécution autorisée.

## ADR-267 — Une défaillance technique rend le cycle PAPER atomique

**ADOPTÉ LOCALEMENT AU BATCH 19.13 — NON ENCORE INTÉGRÉ.**

Le runner audité checkpoint le ledger PAPER avant la trajectoire multi-décisions. Une erreur technique Risk ou Broker fait passer le cycle à `FAILED` et restaure le portefeuille au checkpoint initial.

Cette règle empêche un cycle partiellement exécuté de laisser des effets économiques orphelins. `HOLD` et `REJECT` restent des résultats métier normaux et ne déclenchent pas le rollback.

## ADR-268 — L'audit devient 1:N et les analytics restent économiques

**ADOPTÉ LOCALEMENT AU BATCH 19.13 — NON ENCORE INTÉGRÉ.**

La migration `0007_multi_decision_cycles` étend la persistence du cycle afin de conserver plusieurs décisions, évaluations Risk et intentions d'exécution dans leur ordre.

L'API et le cockpit exposent cette trajectoire ordonnée. Les anciens cycles/configurations restent compatibles.

Les analytics comptent les fills/trades effectivement exécutés et non le nombre de décisions du plan ; `HOLD`, `REJECT` ou une intention sans fill ne deviennent pas artificiellement des trades.

## Changelog — 2026-09-27 — Batch 19.13 validé, documentation synchronisée

- base GitHub vérifiée : `18596ac9d4f6554aa4817a9bdb374ab597c2399f` ;
- un seul Agent et un seul appel stratégique de planification au stade décisionnel ;
- plan ordonné multi-marchés, multi-`BUY` / `SELL` / `HOLD` ;
- Risk séquentiel et causal sur le portefeuille mis à jour ;
- `HOLD` et `REJECT` non bloquants ;
- rollback PAPER atomique en cas d'échec technique Risk/Broker ;
- persistence 1:N et migration `0007_multi_decision_cycles` ;
- trajectoire ordonnée exposée par API/cockpit ;
- analytics basés sur fills/trades réels ;
- `max_decisions_per_cycle` : défaut `6`, hard limit `20` ;
- compatibilité historique maintenue ;
- backend ciblé : `51 passed` ;
- backend complet : `698 passed, 2 warnings` ;
- `alembic upgrade head` : succès PostgreSQL réel ;
- frontend : `39 passed`, lint/typecheck/build réussis ;
- état : implémenté et validé ; le HEAD GitHub réel détermine l’identifiant de commit effectivement intégré.

## Changelog — 2026-09-26 — Correctif PAPER PERPETUAL intégré

- commit `18596ac9d4f6554aa4817a9bdb374ab597c2399f` (`fix: harden paper perpetual execution precision`) ;
- arithmétique PAPER `Decimal` canonique ;
- normalisation descendante du quantum PERPETUAL ;
- revalidation des caps/minimums ;
- exactitude du `Fill` préservée ;
- rollback audité préservé.

## Changelog — 2026-09-26 — Batch 19.12 intégré

- classification des HTTP 429 entre rate limit temporaire et quota/crédit/usage/spend ;
- retry borné sous timeout Agent ;
- aucune conversion d'erreur fournisseur en HOLD ou signal algorithmique ;
- note détaillée : `docs/23_BATCH_19_12_OPENAI_RATE_LIMIT_HANDLING.md`.
