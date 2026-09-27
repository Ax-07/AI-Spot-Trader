# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs, les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers Broker/Kraken, SPOT sans short/levier/marge, PERPETUAL PAPER derrière les contrôles dérivés déterministes, FUTURE daté interdit, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Les Sessions PAPER canoniques autorisent `SPOT` et `PERPETUAL` linéaire. `FUTURE` daté reste interdit.

## Référence courante

```text
HEAD GitHub intégré : aa404e46c1f05269ac2279507aa746b3af7a965d
Commit              : fix: harden multi-market LLM plan contract
Batch 19.13         : intégré depuis 29316d7 ; durcissement LLM intégré dans aa404e4
Correctif PERPETUAL : patch proposé au-dessus de aa404e4, non intégré à GitHub
```

## Décisions historiques toujours actives

- ADR-173 à ADR-239 : immutabilité Strategy/Campaign, Control Plane, accounting, monitoring, discovery, explicabilité, candles/charts et overlays ;
- ADR-240 à ADR-247 : façade Session, lifecycle, immutabilité et modes de marchés ;
- ADR-248 à ADR-255 : Trading Style, coûts Agent et contexte stratégique multi-timeframes ;
- ADR-256 à ADR-258 : UX Session du style et compatibilité legacy ;
- ADR-259 à ADR-262 : gestion stratégique des positions, `position-management-v1`, plafond Risk par ordre et rotation du capital ;
- ADR-263 : classification robuste des limites fournisseur OpenAI et fail-closed ;
- ADR-264 : précision PAPER PERPETUAL et normalisation descendante du quantum, toujours actives ;
- ADR-265 à ADR-268 : Batch 19.13 multi-décisions / multi-marchés, intégré depuis `29316d…` ;
- ADR-269, ADR-270 et ADR-272 : durcissement du contrat Structured Outputs, instructions multi-marchés et diagnostic sécurisé, intégrés dans `aa404e4` ;
- ADR-271 : garde-fou SPOT-only intégré par erreur dans `aa404e4`, supersédé par ADR-273.

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

La phrase historique « une seule décision finale par cycle » est supersédée uniquement sur la cardinalité par ADR-265. Le principe d'arbitrage stratégique par le même Agent reste actif.

## ADR-260 — `position-management-v1` reste factuel

**ADOPTÉ AU BATCH 19.10.**

Le contexte expose inventaire, coût, mark, P&L et estimation de sortie nette sans score, `should_sell` ou take-profit automatique.

## ADR-261 — `risk_max_order_notional` reste un plafond par ordre

**ADOPTÉ AU BATCH 19.10.**

Le plafond reste applicable aux BUY comme aux SELL réducteurs. Le Batch 19.13 ne change pas cette sémantique : chaque décision du plan est évaluée séparément par Risk.

## ADR-262 — La rotation du capital reste pilotée par l'Agent

**ADOPTÉ AU BATCH 19.10, ÉTENDU PAR LE BATCH 19.13.**

Il n'existe aucune règle `après SELL -> BUY`. ADR-265/266 permettent une rotation intra-cycle uniquement lorsque le plan Agent l'ordonne et que Risk l'autorise séquentiellement.

## ADR-263 — Les limites fournisseur OpenAI sont classifiées avant retry

**ADOPTÉ AU BATCH 19.12.**

Quota/crédit/usage/spend sont non retryables ; les limitations temporaires restent retryables avec `Retry-After` valide ou backoff borné. Toute erreur LLM reste fail-closed : aucun HOLD artificiel et aucun fallback algorithmique.

## ADR-264 — Précision PAPER PERPETUAL et quantum provider-derived

**ADOPTÉ ET INTÉGRÉ HISTORIQUEMENT AU HEAD `18596ac9d4f6554aa4817a9bdb374ab597c2399f`.**

Les validations de précision dérivées restent canoniques et s'appliquent au support PAPER PERPETUAL. Elles ne rendent pas `FUTURE` daté exécutable.

## ADR-265 — Un cycle peut porter un plan stratégique ordonné multi-marchés

**ADOPTÉ ET INTÉGRÉ AU HEAD `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.**

Au stade décisionnel du cycle, un seul appel du même Agent stratégique produit un plan ordonné contenant plusieurs décisions sur des marchés distincts.

Le plan accepte `BUY`, `SELL` et `HOLD`. `max_decisions_per_cycle` est configurable, vaut `6` par défaut et possède une limite dure de `20`.

## ADR-266 — Risk et Broker suivent l'ordre du plan sur un portefeuille causal

**ADOPTÉ ET INTÉGRÉ AU HEAD `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.**

Chaque décision est évaluée par Risk après application des éventuelles exécutions précédentes du même cycle. `HOLD` et `REJECT` n'interrompent pas le plan.

## ADR-267 — Une défaillance technique rend le cycle PAPER atomique

**ADOPTÉ ET INTÉGRÉ AU HEAD `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.**

Une erreur technique Risk ou Broker fait passer le cycle à `FAILED` et restaure le portefeuille au checkpoint initial.

## ADR-268 — L'audit devient 1:N et les analytics restent économiques

**ADOPTÉ ET INTÉGRÉ AU HEAD `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.**

La migration `0007_multi_decision_cycles` conserve plusieurs décisions, évaluations Risk et intentions d'exécution dans leur ordre. Les analytics comptent les fills/trades effectivement exécutés et non le nombre de décisions du plan.

## ADR-269 — Le schéma Structured Outputs encode le contrat action/quantité

**ADOPTÉ ET INTÉGRÉ AU HEAD `aa404e46c1f05269ac2279507aa746b3af7a965d`.**

Le schéma du `CycleDecisionPlan` utilise des variantes strictes par action : `BUY`/`SELL` imposent une quantité numérique strictement positive et `HOLD` impose `null`.

Pydantic conserve la même validation comme seconde barrière. Une sortie invalide reste un échec ; aucune coercition et aucun ordre synthétique ne sont créés.

## ADR-270 — Le nouveau chemin reçoit un contrat protégé multi-marchés explicite

**ADOPTÉ ET INTÉGRÉ AU HEAD `aa404e46c1f05269ac2279507aa746b3af7a965d`.**

`StrategyInstructionsClient` détecte `strategic_plan_contract` et injecte `strategic-multi-market-plan-v1`. Le contrat historique singleton est conservé pour les chemins legacy/replay mais n'est plus utilisé comme description finale du nouveau plan.

Les sections stratégie opérateur, agressivité, style et coûts restent présentes. Il n'existe ni second Agent ni second appel stratégique de planification.

## ADR-271 — Garde-fou SPOT-only du runtime

**INTÉGRÉ PAR ERREUR DANS `aa404e4` — SUPERSEDÉ PAR ADR-273.**

Le garde-fou ajouté dans `campaign_composition.py` refusait toute configuration contenant un bootstrap ou une discovery non-SPOT. Cette restriction contredisait l'architecture dérivés déjà canonique et rendait PERPETUAL inutilisable dans les Sessions PAPER.

## ADR-272 — Les erreurs de plan sont diagnostiquées sans sortie brute

**ADOPTÉ ET INTÉGRÉ AU HEAD `aa404e46c1f05269ac2279507aa746b3af7a965d`.**

Les catégories distinguent au minimum sortie vide, JSON invalide, violation action/quantité, liste invalide, limite, doublon et marché hors univers. Les messages n'embarquent ni sortie LLM brute ni secret.

Aucun retry sémantique n'est ajouté : un plan invalide échoue avant Risk.

## ADR-273 — Les Sessions PAPER supportent SPOT et PERPETUAL ; FUTURE reste interdit

**PROPOSÉ DANS LE CORRECTIF PERPETUAL POST-`aa404e4` — NON INTÉGRÉ.**

Le garde-fou SPOT-only de composition est retiré sans revenir sur ADR-269/270/272. Les marchés `SPOT` et `PERPETUAL` linéaires restent soumis au même pipeline Agent -> Risk -> Broker PAPER. Les règles dérivés canoniques demeurent actives : marge isolée, plafonds de levier et d'exposition, buffer de liquidation et `reduce_only` sont déterministes. `FUTURE` daté reste refusé par les validations de configuration, discovery et exécution.

## Changelog — 2026-09-27 — Correctif PERPETUAL proposé

- base GitHub vérifiée : `aa404e46c1f05269ac2279507aa746b3af7a965d` ;
- cause : `_ensure_spot_only_session()` ajouté dans `campaign_composition.py` bloque à tort PERPETUAL avant composition du runtime ;
- correction : retrait du garde-fou SPOT-only et réalignement des instructions protégées sur SPOT + PERPETUAL ;
- `FUTURE` daté reste interdit ;
- aucun assouplissement du Risk Engine, de la discovery causale ou du contrat multi-market ;
- statut : patch proposé, non intégré à GitHub.

## Changelog — 2026-09-27 — Durcissement multi-market LLM intégré

- commit `aa404e46c1f05269ac2279507aa746b3af7a965d` (`fix: harden multi-market LLM plan contract`) ;
- cause racine corrigée : désalignement JSON Schema / validation Pydantic pour `proposed_quantity` ;
- contrat protégé `strategic-multi-market-plan-v1` injecté sur le nouveau chemin ;
- diagnostic Agent sécurisé et plus précis ;
- aucun retry LLM sémantique ;
- Risk reste non appelé lorsqu'un plan est invalide ;
- note : ce commit a aussi introduit le garde-fou SPOT-only supersédé par ADR-273.

## Changelog — 2026-09-27 — Batch 19.13 intégré

- commit `29316d7521accfe46316cb2bc6dfcf7652ba04bf` (`feat: add multi-market multi-decision trading cycles`) ;
- un seul Agent et un seul appel stratégique de planification au stade décisionnel ;
- plan ordonné multi-marchés, multi-`BUY` / `SELL` / `HOLD` ;
- Risk séquentiel et causal sur le portefeuille mis à jour ;
- `HOLD` et `REJECT` non bloquants ;
- rollback PAPER atomique en cas d'échec technique Risk/Broker ;
- persistence 1:N et migration `0007_multi_decision_cycles` ;
- trajectoire ordonnée exposée par API/cockpit ;
- analytics basés sur fills/trades réels ;
- `max_decisions_per_cycle` : défaut `6`, hard limit `20`.

## Changelog — 2026-09-26 — Correctif PAPER PERPETUAL historique

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
