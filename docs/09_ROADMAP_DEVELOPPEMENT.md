# 09 — Roadmap de développement

## Règle de lecture

Un batch n'est **intégré** qu'après validation locale, commit et push confirmés sur `main`.

## Batches 00 à 15.3 — intégrés

Les étapes historiques suivantes sont intégrées : documentation/bootstrap, contrats domaine, Kraken Spot public, Market State, Portfolio/Paper Broker, Risk Engine, Agent Luna/Sol, boucle autonome, persistance PostgreSQL, API FastAPI, cockpit Next.js, analytics, expérimentation agressivité, comparaison Luna/Sol, chat opérateur, composition runtime PAPER, contexte marché multi-horizon et découplage contexte/cadence.

Référence fonctionnelle Batch 15.3 : `d0f6d46b9adb37117051a7a497a8d55075c41d32`.

## Batch 16 — Kraken Derivatives PAPER

**État : intégré sur `main` au commit fonctionnel `06e3185c8a8c638263427842ab6591a2397810e0` (`feat: add Kraken derivatives paper trading`).**

Le support intégré couvre le domaine `SPOT | PERPETUAL | FUTURE`, l'exécution PAPER des perpetuals linéaires en marge ISOLATED, LONG/SHORT, levier déterministe, P&L, funding, reduce-only, protections Risk, API/analytics étendus, sans API Kraken privée ni LIVE.

## Batch 16.1 — Smoke test PERPETUAL PAPER

**État : intégré.**

Le correctif accepte les valeurs négatives de `contractValueTradePrecision`. Le smoke réel `BTC/USD / PF_XBTUSD` a terminé `COMPLETED`, Agent `HOLD`, Risk `ALLOW / HOLD_NO_EXECUTION`, analytics `1000 -> 1000`, `trade_count=0`, `hold_count=1`.

Ce smoke initial ne validait pas encore les branches d'exécution LONG/SHORT.

## Batch 16.2 — Isolation durable des runs PAPER

**État : intégré sur GitHub `main` au commit fonctionnel `003bbadd7ae2f8288ccde049433832046f066957` (`feat: add durable paper run isolation`).**

Implémentation intégrée :

- table durable `paper_runs` ;
- FK nullable `audit_cycles.paper_run_id` ;
- décisions, Risk, intents et fills rattachés indirectement par leur cycle ;
- migration PostgreSQL `0002_paper_runs` sans backfill trompeur ;
- anciennes lignes conservées à `NULL` et exclues des analytics run-scoped ;
- même mécanisme pour SPOT et PERPETUAL ;
- analytics d'un run strictement filtrés par `paper_run_id` ;
- filtres run-scoped disponibles pour audit ;
- endpoints de découverte/sélection des runs ;
- aucun changement frontend requis.

## Batch 16.3 — Smokes d'exécution Derivatives contrôlés

**État : intégré sur GitHub `main` au commit fonctionnel `520b016eb501f1a208bcb6d0e90eb1df947e1d0b` (`test: add controlled perpetual paper smoke harness`).**

Le harness de validation est séparé du runtime normal et ne force jamais l'Agent de production.

Validation locale :

```text
pytest               : suite complète OK, 2 warnings externes FastAPI/Starlette
ruff check .          : All checks passed
mypy .                : Success: no issues found in 109 source files
git diff --check      : aucune erreur
```

Smokes réels contrôlés `BTC/USD / PF_XBTUSD`, levier `1x`, `ISOLATED` :

- LONG : ouverture, HOLD/mark, funding, réduction `reduce_only`, fermeture oversize bornée par Risk, position finale vide ;
- SHORT : scénario symétrique validé ;
- 4 cycles `COMPLETED` et 3 exécutions par run ;
- aucun cycle `FAILED` ;
- P&L, marge, frais/spread/slippage et funding valorisés ;
- aucune inversion accidentelle ;
- deux `paper_run_id` distincts fermés proprement ;
- contrôle `verify-isolation` : `isolation_verified=true`.

## Batch 16.4 — Premier run Agent réel GPT-5.6 Luna PERPETUAL PAPER

**État : résultat réel confirmé et documenté sur `main` via le commit `595bd2c8b4311ac255db927515207f10875b1505` du Batch 16.5.**

Run `36fe73e0-f52f-4e27-995b-c5c848f46da2` sur `BTC/USD / PF_XBTUSD`, `ISOLATED`, levier déterministe `1x`, capital `1000 USD`, agressivité `2` :

- 4 cycles `COMPLETED` ;
- 4 décisions Luna réelles `HOLD` ;
- 0 cycle `FAILED` ;
- 4 Risk `ALLOW / HOLD_NO_EXECUTION` ;
- 0 `ExecutionIntent`, fill ou trade ;
- portefeuille final `1000 USD`, exposition `0`, P&L `0` ;
- run clôturé durablement avec `ended_at` ;
- aucune décision forcée et aucun recours au harness 16.3.

L'audit a montré que `market_state.context` était `null` pour cette source Derivatives : les HOLD ne constituent donc pas un échec stratégique.

## Batch 16.5 — Contexte marché PERPETUAL pour l'Agent

**État : intégré sur GitHub `main` au commit fonctionnel `595bd2c8b4311ac255db927515207f10875b1505` (`feat: enrich perpetual paper market context`), clôture documentaire au commit `84272713b66439a16e7769da83eccc1514aa64f7`.**

Objectif : réutiliser le `MarketStateBuilder` canonique avec les bougies publiques Kraken Futures **mark 1 minute** afin de fournir à l'Agent les mêmes statistiques descriptives causales que sur SPOT : fraîcheur, fenêtres 5 min / 30 min, rendement, range et volatilité réalisée.

Principes du batch :

- aucune seconde implémentation d'indicateurs ;
- ticker Derivatives courant conservé pour mark/index/funding ;
- historique mark public uniquement, sans clé Kraken privée ;
- bougies non clôturées au moment du ticker exclues ;
- aucune métrique déterministe ne produit BUY/SELL/HOLD ;
- `AgentInput.market_state.context` devient non nul en PERPETUAL quand le snapshot est construit normalement ;
- Risk conserve l'autorité finale et LIVE reste hors périmètre.

Validation confirmée :

```text
pytest backend                                  : 357 passed, 2 warnings externes
ruff check backend                             : All checks passed
mypy --config-file backend\pyproject.toml ... : Success, 107 source files
git diff --check                               : aucune erreur
```

Cycle réel de référence : `paper_run_id = 8bbfe6a5-a5d5-4c32-96dc-eb9c5e4113d2`, cycle `c097f3fc-4954-4985-a364-f6ffe99b24e6` `COMPLETED`, `AgentInput.market_state.context` non nul, fenêtres 5m/30m complètes avec 6/31 observations, mark/index/funding conservés.

## Batch 16.6 — Validation comportementale GPT-5.6 Luna avec contexte enrichi

**État : intégré sur GitHub `main` au commit `251d530ad12951605068c1c8eb8cbeb313c36b49` (`docs: validate Batch 16.6 Luna perpetual behavior`). Aucun changement de code pour le batch.**

Run propre `paper_run_id = c9443243-57ca-43de-9356-adc1e6fe3226` sur `BTC/USD / PF_XBTUSD`, `PERPETUAL`, `ISOLATED`, levier `1x`, capital `1000 USD`, agressivité `2`, composition normale et GPT-5.6 Luna :

- 8 cycles `COMPLETED`, 0 `FAILED` ;
- 8/8 contextes PERPETUAL non nuls ;
- fenêtres 5m/30m complètes sur les 8 cycles avec 6/31 observations ;
- causalité vérifiée sur les 8 cycles ;
- fraîcheur comprise entre `1.021449 s` et `1.110151 s` ;
- 8 HOLD naturels, aucun BUY/SELL forcé ;
- rationales cohérentes avec les faits présents : rendements 5m/30m, absence de position et funding positif lorsqu'il est mentionné ;
- 8 Risk `ALLOW`, 0 intent, 0 fill, 0 trade ;
- analytics finaux : `1000 -> 1000 USD`, P&L brut/net `0`, coûts `0`, funding `0`, exposition `0`, drawdown `0` ;
- isolation : 8 cycles dans le run 16.6, 0 `cycle_id` commun avec le run Batch 16.5 ;
- run fermé proprement avec `ended_at = 2026-09-22 08:41:03.924351 UTC`.

Un premier essai a réutilisé le run Batch 16.5 parce que le backend n'avait pas encore été redémarré. Ces cycles ont été conservés dans l'audit, mais exclus comme preuve du Batch 16.6. La validation finale repose uniquement sur le nouveau run isolé `c9443243-57ca-43de-9356-adc1e6fe3226`.

L'absence de BUY/SELL naturel ne constitue pas un échec et ne justifie aucune modification destinée à provoquer un trade.

## Prompt Agent `agent-strategy-v4` — localisation française

**État : intégré sur GitHub `main` au commit `bacf29c83b4f29477ee9e35a1a65756a866ba250` (`feat: localize agent strategy prompt to French`).**

Évolution ciblée hors Batch 17 :

- instructions humaines du prompt stratégique en français ;
- valeurs contractuelles `BUY/SELL/HOLD`, `SPOT/PERPETUAL/FUTURE`, `LONG/SHORT` inchangées ;
- `rationale` demandé en français ;
- aucun changement du schéma structuré ni du chemin `Agent -> Risk -> Broker` ;
- test ciblé Agent : `30 passed` ;
- Ruff ciblé : `All checks passed!` ;
- `git diff --check` : aucune erreur de contenu.

## Batch 17 — Robustesse Derivatives

**Prochain batch proposé. À lancer dans une nouvelle discussion après resynchronisation avec `main`.**

Pistes à auditer avant implémentation : validation des schémas publics Kraken sur davantage d'instruments, tiers de marge par taille, liquidation PAPER plus fidèle, cockpit dédié dérivés, reprise/réconciliation du ledger mémoire, scénarios multi-position/multi-instrument, puis éventuel enrichissement public supplémentaire (funding historique, liquidité/volume) uniquement si son utilité est mesurée.

Le périmètre exact du Batch 17 doit être limité et décidé après audit de l'existant ; ces pistes ne constituent pas encore toutes des décisions architecturales.

## LIVE — toujours séparé

Le LIVE n'est pas une suite automatique. Il nécessitera une décision explicite et un batch séparé couvrant : adaptateur privé Kraken, permissions minimales sans retrait, idempotence, réconciliation, recovery, limites renforcées, activation opérateur et observabilité.
