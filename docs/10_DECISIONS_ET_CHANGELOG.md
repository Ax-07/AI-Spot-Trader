# 10 — Décisions et changelog

> Ce document consolide les décisions courantes. L'historique détaillé antérieur au Batch 16 reste disponible dans l'historique Git.

## Principes historiques conservés

Les décisions intégrées des Batches 00 à 15.3 restent valides lorsqu'elles ne sont pas explicitement supersédées ici : agent unique, PAPER d'abord, Risk autorité finale, pas d'exécution directe LLM, audit durable, backend indépendant du frontend, no-look-ahead, contexte marché descriptif, chat opérateur latéral/non mutant.

Les anciennes mentions **SPOT uniquement / aucun future-perpetual** sont supersédées par les décisions Batch 16 uniquement pour le domaine Derivatives. Les règles SPOT correspondantes restent inchangées.

## Décisions Batch 16

### ADR-090 — Le projet devient SPOT + Kraken Derivatives
**ACCEPTÉE.** Le backend canonique peut représenter `SPOT`, `PERPETUAL` et `FUTURE`. SPOT conserve ses invariants historiques ; LONG/SHORT/levier/marge n'existent que dans le domaine dérivés.

### ADR-091 — Un seul pipeline et un seul agent
**ACCEPTÉE.** Aucun moteur dérivés parallèle. Le flux reste `Market -> Agent -> DecisionCandidate -> Risk -> ExecutionIntent -> Paper Broker`.

### ADR-092 — Perpetual linéaire uniquement pour la première exécution PAPER
**ACCEPTÉE.** Les contrats `PERPETUAL + LINEAR` sont exécutables. Les contrats `INVERSE` et futures datés sont découverts/représentés mais refusés à l'exécution.

### ADR-093 — Marge ISOLATED d'abord ; CROSS représenté mais fail-closed
**ACCEPTÉE.** `CROSS` existe dans le domaine mais la composition Batch 16 le refuse.

### ADR-094 — Levier déterministe, jamais choisi par le LLM
**ACCEPTÉE.** Le levier PAPER est un paramètre de configuration/Risk, par défaut `1x`.

### ADR-095 — Anti-retournement et reduce-only produits par Risk
**ACCEPTÉE.** Une action opposée réduit/ferme la position ; un dépassement ne peut pas la retourner silencieusement.

### ADR-096 — Funding et mark-to-market avant AgentInput
**ACCEPTÉE.** Le market source Derivatives marque la position et accumule le funding dans le ledger avant le snapshot portefeuille.

### ADR-097 — Modèle de liquidation conservateur
**ACCEPTÉE.** Le ledger calcule un prix de liquidation isolée estimé et Risk impose un buffer par rapport à la maintenance margin.

### ADR-098 — Kraken Derivatives public séparé de Kraken Spot
**ACCEPTÉE.** Intégration publique dédiée via `https://futures.kraken.com/derivatives/api/v3`. Aucun endpoint privé d'ordre, aucune clé Kraken et aucun LIVE.

### ADR-099 — Analytics combinés SPOT + Derivatives
**ACCEPTÉE.** Les positions dérivés sont persistées dans les payloads JSON ; les analytics ajoutent marge/unrealized/funding/exposition dérivés.

### ADR-100 — Prompt Agent `agent-strategy-v3`
**ACCEPTÉE.** Le prompt explique explicitement les sémantiques SPOT/PERPETUAL, LONG/SHORT, marge et levier tout en conservant `BUY/SELL/HOLD`.

## Décisions Batch 16.1

### ADR-101 — `contractValueTradePrecision` est un exposant décimal entier signé
**ACCEPTÉE ET INTÉGRÉE.** Le parser Kraken Derivatives ne rejette pas une valeur uniquement parce qu'elle est négative. La quantité minimale est dérivée par `10^-precision` : `-3 -> 1000`, `4 -> 0.0001`.

## Décisions Batch 16.2

### ADR-102 — `paper_run_id` durable au niveau du cycle
**ACCEPTÉE ET INTÉGRÉE.** Un run PAPER durable est représenté par `paper_runs.paper_run_id`. Le rattachement canonique est porté par `audit_cycles.paper_run_id`. Les décisions, Risk assessments, intents et fills héritent du run par leur relation au cycle.

### ADR-103 — Un run correspond à une initialisation cohérente du ledger PAPER
**ACCEPTÉE.** Le run est créé au démarrage du backend PAPER, avant les cycles. Un `engine stop/start` dans le même processus conserve le run. Un arrêt backend propre renseigne `ended_at`.

### ADR-104 — Un redémarrage backend crée un nouveau run
**ACCEPTÉE.** Le ledger PAPER étant process-local et réinitialisé au capital initial au démarrage, reprendre automatiquement l'ancien `paper_run_id` donnerait une continuité de portefeuille fausse.

### ADR-105 — Pas de reconstruction artificielle des données legacy
**ACCEPTÉE.** La migration `0002_paper_runs` ajoute `audit_cycles.paper_run_id` nullable. Les lignes antérieures restent `NULL`. Aucun pseudo-run historique unique n'est créé.

### ADR-106 — Analytics strictement run-scoped
**ACCEPTÉE.** Les analytics d'un run sélectionnent uniquement les cycles portant exactement son `paper_run_id`.

### ADR-107 — API de découverte des runs, sans rotation à chaud
**ACCEPTÉE.** Le backend expose les surfaces de découverte/sélection des runs. Aucun `POST new-run` n'est ajouté tant qu'un reset/recovery fiable du ledger n'existe pas.

### ADR-108 — Aucun changement frontend requis
**ACCEPTÉE.** Le cockpit existant continue d'utiliser le run courant par défaut.

## Décisions Batch 16.3

### ADR-109 — Harness déterministe réservé aux smokes techniques
**ACCEPTÉE ET INTÉGRÉE.** Le Batch 16.3 ajoute `ai_spot_trader.tools.derivatives_smoke`. Il réutilise les composants canoniques aval mais fournit des décisions déterministes explicitement marquées comme smoke. Il n'ajoute aucun mécanisme de force BUY/SELL dans FastAPI, la configuration runtime ou l'Agent normal.

### ADR-110 — Les smokes contrôlés ne sont pas des décisions Agent
**ACCEPTÉE.** Les décisions `CONTROLLED_SMOKE_BATCH_16_3` servent uniquement à valider l'exécution, Risk, ledger, audit et analytics. Elles ne sont pas attribuées à Luna/Sol et ne doivent pas être utilisées pour évaluer la qualité stratégique du modèle.

### ADR-111 — La fermeture opposée surdimensionnée doit rester reduce-only
**CONFIRMÉE PAR SMOKE.** Sur LONG comme sur SHORT, une demande de fermeture `0.0002` avec seulement `0.0001` restant a produit `MODIFY`, quantité autorisée `0.0001`, raison `DERIVATIVE_REDUCE_ONLY_LIMIT` et `reduce_only=true`, sans inversion accidentelle.

### ADR-112 — Les preuves brutes de smoke restent hors Git
**ACCEPTÉE.** Les JSON complets `smoke-long.json` et `smoke-short.json` sont des artefacts locaux de validation. Les résultats synthétiques et IDs de runs peuvent être documentés, mais les dumps bruts ne sont pas versionnés.

## Décisions Batch 16.5

### ADR-113 — Réutiliser le `MarketStateBuilder` canonique pour PERPETUAL
**ACCEPTÉE ET INTÉGRÉE au commit `595bd2c8b4311ac255db927515207f10875b1505`.** Le contexte multi-horizon n'est pas réimplémenté côté Derivatives. La source Kraken Derivatives normalise l'historique mark en `MarketObservation`, puis réutilise le builder provider-agnostic existant.

### ADR-114 — Les fenêtres PERPETUAL utilisent les bougies publiques mark 1 minute
**ACCEPTÉE ET INTÉGRÉE au commit `595bd2c8b4311ac255db927515207f10875b1505`.** Kraken Futures Charts fournit publiquement des bougies `mark`. Les fenêtres 5 min / 30 min utilisent uniquement des clôtures antérieures au ticker courant. Une bougie non clôturée ou future n'entre jamais dans les statistiques.

### ADR-115 — Le contexte descriptif n'est jamais un signal déterministe
**ACCEPTÉE ET INTÉGRÉE au commit `595bd2c8b4311ac255db927515207f10875b1505`.** Rendement, range, volatilité et fraîcheur sont transmis à Luna comme faits descriptifs. Ils ne produisent aucune action `BUY/SELL/HOLD`. L'Agent garde le choix stratégique et Risk garde l'autorité finale.

### ADR-116 — Pas d'enrichissement public supplémentaire sans besoin mesuré
**ACCEPTÉE ET INTÉGRÉE au commit `595bd2c8b4311ac255db927515207f10875b1505`.** Le Batch 16.5 n'ajoute pas encore volume, order book, funding historique ou analytics de liquidité. Le mark/index/funding courant déjà intégré est conservé ; le batch se limite au manque confirmé : un historique causal pour `MarketState.context`.

## Décisions Batch 16.6

### ADR-117 — Un HOLD naturel reste une observation valide
**ACCEPTÉE ET INTÉGRÉE au commit `251d530ad12951605068c1c8eb8cbeb313c36b49`.** Le Batch 16.6 ne modifie ni prompt, ni agressivité, ni stratégie pour provoquer BUY/SELL. Huit HOLD naturels consécutifs sur le run isolé final sont conservés comme résultat expérimental valide.

### ADR-118 — Un essai non isolé n'est pas utilisé comme preuve d'isolation
**ACCEPTÉE ET INTÉGRÉE au commit `251d530ad12951605068c1c8eb8cbeb313c36b49`.** Un premier essai 16.6 a continué le run Batch 16.5 faute de redémarrage complet du backend. Les cycles restent dans l'audit durable mais sont exclus de la preuve finale 16.6. La validation repose sur le run neuf `c9443243-57ca-43de-9356-adc1e6fe3226`.

## Décision post-Batch 16.6 — localisation du prompt Agent

### ADR-119 — Prompt Agent `agent-strategy-v4` en français
**ACCEPTÉE.** Le prompt stratégique est localisé en français et le champ `rationale` doit être rédigé en français. Les valeurs contractuelles `BUY`, `SELL`, `HOLD`, `SPOT`, `PERPETUAL`, `FUTURE`, `LONG` et `SHORT`, le schéma structuré, la séparation Agent/Risk et le chemin d'exécution restent inchangés. Le changement de version rend l'évolution traçable dans les manifestes expérimentaux.

## Décisions Batch 17 — validées localement

> Ces décisions décrivent le Batch 17 validé localement depuis le HEAD `b859b5f813e458ca26633406a557462953d39e5e`. Elles ne doivent pas être qualifiées d'intégrées tant que le commit et le push sur `main` ne sont pas confirmés.

### ADR-120 — La frontière Kraken Derivatives publique doit échouer fermée sur les métadonnées critiques
**VALIDÉE LOCALEMENT.** Un instrument `tradeable` exige des valeurs cohérentes pour `contractSize`, `tickSize`, `contractValueTradePrecision` et ses schedules de marge. Une structure malformed, un seuil négatif, un taux incohérent ou un `maxPositionSize` inférieur à la taille minimale provoque une erreur de payload au lieu d'une hypothèse implicite.

### ADR-121 — Supporter les trois formes publiques de schedules de marge sans prétendre connaître le tier privé
**VALIDÉE LOCALEMENT.** Le parser accepte `marginLevels`, `retailMarginLevels` et `marginSchedules`. Les seuils sont validés mais ne sont pas encore appliqués dynamiquement à la taille de position. Sans contexte privé prouvant le barème du compte, le runtime conserve le choix account-agnostic existant : prendre les taux publics les plus conservateurs observés.

### ADR-122 — `contractValueTradePrecision` absent n'a plus de valeur par défaut
**VALIDÉE LOCALEMENT.** La valeur est requise pour un instrument tradeable. Le défaut historique `None -> 1` est supprimé afin d'éviter une taille minimale inventée.

### ADR-123 — Le mark est obligatoire pour le chemin Derivatives PAPER
**VALIDÉE LOCALEMENT.** `markPrice` ou son alias historique `mark_price` est requis. `last` n'est plus utilisé comme substitut silencieux, car le mark alimente le P&L, la marge et la liquidation PAPER.

### ADR-124 — Un ticker suspendu ou post-only n'est pas exécutable par le PaperBroker full-fill
**VALIDÉE LOCALEMENT.** Si le ticker public indique `suspended=true` ou `postOnly=true`, le snapshot échoue fermé. Les flags non booléens ou des aliases contradictoires sont également rejetés. Cette décision évite de simuler un fill immédiat dans un état de marché où ce comportement ne représente pas l'exécution disponible.

### ADR-125 — Pas de faux modèle tier-aware ou de faux recovery dans Batch 17
**VALIDÉE LOCALEMENT.** Le Batch 17 n'étend pas le domaine pour des tiers de marge dynamiques et ne reconstruit pas un ledger à partir du journal. Ces sujets exigent des contrats explicites et un batch séparé. Un redémarrage backend continue donc de créer un nouveau run/ledger, sans fausse continuité.

### ADR-126 — Aucun enrichissement supplémentaire sans besoin mesuré
**VALIDÉE LOCALEMENT.** Funding historique, volume, liquidité, order book et cockpit Derivatives dédié restent hors périmètre. Le patch vise la robustesse d'une frontière existante, pas l'ajout de nouveaux signaux ou d'une seconde stratégie.

## Changelog — 2026-09-21 — Batch 16.1 Smoke PERPETUAL PAPER

Smoke réel : `BTC/USD / PF_XBTUSD`, cycle `COMPLETED`, Agent `HOLD`, Risk `ALLOW / HOLD_NO_EXECUTION`, analytics `1000 -> 1000`, `trade_count=0`, `hold_count=1`.

Ce smoke initial ne validait pas les branches LONG/SHORT.

## Changelog — 2026-09-21 — Batch 16.2 Isolation durable des runs PAPER

**État : intégré au commit fonctionnel `003bbadd7ae2f8288ccde049433832046f066957`.**

Changements : migration `0002_paper_runs`, lifecycle durable de run, FK `audit_cycles.paper_run_id`, readers/analytics run-scoped, endpoints de découverte/sélection des runs, compatibilité SPOT/PERPETUAL et absence de frontend/LIVE/private Kraken.

Validation locale : migration appliquée, `pytest` complet OK, Ruff OK, mypy OK et `git diff --check` OK.

## Changelog — 2026-09-21 — Batch 16.3 Smokes PERPETUAL PAPER contrôlés

**État fonctionnel : intégré sur GitHub `main` au commit `520b016eb501f1a208bcb6d0e90eb1df947e1d0b` (`test: add controlled perpetual paper smoke harness`).**

Validation locale avant push :

```text
pytest               : suite complète OK, 2 warnings externes FastAPI/Starlette
ruff check .          : All checks passed
mypy .                : Success: no issues found in 109 source files
git diff --check      : aucune erreur
```

### Smoke LONG

Run : `9523ec8c-7dd1-4706-bf07-47ef9669d56b`.

- ouverture BUY `0.0002` ;
- HOLD avec funding observé ;
- réduction SELL `0.0001`, `reduce_only=true` ;
- fermeture oversize SELL `0.0002` ramenée à `0.0001` par Risk ;
- 4 cycles `COMPLETED`, 3 exécutions ;
- position finale vide et exposition finale nulle.

### Smoke SHORT

Run : `b75f6e86-4724-41de-8d63-e8132d212530`.

- ouverture SELL `0.0002` ;
- HOLD avec funding observé ;
- réduction BUY `0.0001`, `reduce_only=true` ;
- fermeture oversize BUY `0.0002` ramenée à `0.0001` par Risk ;
- 4 cycles `COMPLETED`, 3 exécutions ;
- position finale vide et exposition finale nulle.

### Isolation

Les deux runs ont été fermés proprement avec `ended_at`. `verify-isolation` a retourné `isolation_verified=true`, avec 4 cycles propres à chaque run et des analytics/source digests distincts.

Le Batch 16.3 confirme donc le chemin technique complet PERPETUAL PAPER au-delà de HOLD : LONG, SHORT, fills, mark-to-market, funding, P&L, marge, `reduce_only`, fermeture et isolation durable.

Il ne mesure pas encore la qualité stratégique de l'Agent : les décisions des smokes sont déterministes et réservées à la validation.

## Changelog — 2026-09-22 — Batch 16.4 Premier run Luna réel PERPETUAL PAPER

Résultat réel confirmé hors harness sur `paper_run_id = 36fe73e0-f52f-4e27-995b-c5c848f46da2` :

- composition normale ;
- `OpenAIDecisionProvider` avec GPT-5.6 Luna ;
- 4 cycles `COMPLETED` ;
- 4 décisions naturelles `HOLD` ;
- 0 cycle `FAILED` ;
- Risk `ALLOW / HOLD_NO_EXECUTION` à chaque cycle ;
- aucun intent, fill ou trade ;
- portefeuille final `1000 USD`, exposition `0`, P&L `0` ;
- run fermé durablement avec `ended_at`.

L'audit du vrai `AgentInput` a confirmé `market_state.context = null`. Les rationales Luna indiquaient un contexte directionnel insuffisant ; ces HOLD sont donc cohérents avec l'agressivité `2` et les informations alors disponibles.

## Changelog — 2026-09-22 — Batch 16.5 Contexte marché PERPETUAL

Patch développé à partir du HEAD GitHub `0b7303c9e0737f39ac81a5af2517f2f7953c133c`, validé localement puis intégré sur `main` au commit fonctionnel `595bd2c8b4311ac255db927515207f10875b1505`. La clôture documentaire est intégrée au commit `84272713b66439a16e7769da83eccc1514aa64f7`.

- réutilisation de `MarketStateBuilder` pour Derivatives ;
- récupération publique des bougies mark Kraken Futures Charts en `1m` ;
- fenêtres statistiques causales 5 min / 30 min ;
- exclusion stricte des bougies dont la clôture n'est pas antérieure au ticker courant ;
- maintien intégral du mark/index/funding/instrument déjà présents ;
- tests ciblés no-look-ahead, déterminisme, sérialisation `AgentInput`, stale/fail-closed et absence d'auth privée.

Aucune décision BUY/SELL/HOLD n'est produite par les indicateurs. LIVE reste hors périmètre.

Validation locale finale :

```text
pytest backend                                  : 357 passed, 2 warnings externes
ruff check backend                             : All checks passed
mypy --config-file backend\pyproject.toml ... : Success, 107 source files
git diff --check                               : aucune erreur ; avertissements LF -> CRLF uniquement
```

Cycle réel de référence via la composition normale après redémarrage complet du backend :

- `paper_run_id = 8bbfe6a5-a5d5-4c32-96dc-eb9c5e4113d2` ;
- `cycle_id = c097f3fc-4954-4985-a364-f6ffe99b24e6`, `COMPLETED` ;
- `BTC/USD`, `PERPETUAL`, mark courant `86628.99777100343` ;
- `AgentInput.market_state.context` non nul ;
- fenêtre 5 min complète : 6 observations, rendement `-0.0008283458359064427`, volatilité réalisée `0.0003195517675049489` ;
- fenêtre 30 min complète : 31 observations, rendement `0.002818639241644028`, volatilité réalisée `0.0004142619704073510` ;
- fraîcheur `0.773542 s` ;
- index `86622.3` et funding `0.00001373689662899510173815517115` conservés.

Le premier essai effectué avant redémarrage du backend avait encore `context = null` parce que le processus FastAPI utilisait l'ancien module chargé en mémoire. Après redémarrage complet, le cycle de référence a confirmé le chemin runtime 16.5.

## Changelog — 2026-09-22 — Batch 16.6 Validation comportementale Luna PERPETUAL PAPER

**État : intégré sur GitHub `main` au commit `251d530ad12951605068c1c8eb8cbeb313c36b49` (`docs: validate Batch 16.6 Luna perpetual behavior`). Aucun changement de code dans le Batch 16.6.**

Audit effectué depuis GitHub `main` au HEAD `84272713b66439a16e7769da83eccc1514aa64f7`.

Run final propre : `paper_run_id = c9443243-57ca-43de-9356-adc1e6fe3226`.

Configuration conservée : `BTC/USD / PF_XBTUSD`, `PERPETUAL`, `ISOLATED`, levier déterministe `1x`, capital PAPER `1000 USD`, agressivité `2`, GPT-5.6 Luna, `agent-strategy-v3`, Risk inchangé.

Résultats complets :

- 8 cycles `COMPLETED`, 0 `FAILED` ;
- 8/8 `market_state.context != null` ;
- 8/8 fenêtres 5m complètes, 6 observations ;
- 8/8 fenêtres 30m complètes, 31 observations ;
- causalité vérifiée sur les 8 cycles ;
- fraîcheur entre `1.021449 s` et `1.110151 s` ;
- rendements 5m observés entre `0.001382112552274408121158548` et `0.004277054732762370494098960` ;
- rendements 30m observés entre `0.000595245832287674415770980` et `0.004189253453471024976633082` ;
- funding courant positif dans les 8 snapshots affichés ;
- 8 décisions naturelles `HOLD` ;
- rationales cohérentes avec les données réellement présentes : rendements 5m/30m, absence de position et funding lorsqu'il est cité ; aucun indicateur absent observé ;
- 8 Risk `ALLOW` ;
- 0 `ExecutionIntent`, 0 fill, 0 trade ;
- capital `1000 -> 1000 USD` ;
- P&L brut/net `0` ; frais, spread, slippage, funding P&L `0` ;
- exposition et drawdown `0` ;
- isolation : 8 cycles propres au run final et 0 `cycle_id` commun avec le run Batch 16.5 ;
- `started_at = 2026-09-22 08:35:12.561639 UTC` ;
- `ended_at = 2026-09-22 08:41:03.924351 UTC`.

Un premier essai 16.6 a continué le run Batch 16.5 parce que le backend n'avait pas été redémarré. Le préflight a ensuite conduit à créer un nouveau run. Les cycles de l'essai initial sont conservés dans le journal et ne sont ni supprimés ni sélectionnés comme preuve du Batch 16.6.

Conclusion : le contexte enrichi est systématiquement transmis dans le run final, la causalité est respectée, les rationales observées n'inventent pas d'indicateurs absents, Risk reste l'autorité finale, les analytics run-scoped restent cohérents et l'isolation est confirmée. Aucun BUY/SELL naturel n'est apparu ; ce résultat n'est pas un échec et ne déclenche aucune optimisation de stratégie.

## Changelog — 2026-09-22 — Prompt Agent `agent-strategy-v4` en français

- instructions stratégiques localisées en français ;
- valeurs contractuelles et schéma structuré inchangés ;
- `rationale` explicitement demandé en français ;
- mêmes invariants PAPER, Agent unique, Risk autorité finale et absence d'exécution directe LLM ;
- test du contrat de prompt mis à jour pour `agent-strategy-v4`.

## Changelog — 2026-09-22 — Batch 17 Robustesse Derivatives — validé localement

Audit démarré depuis le HEAD GitHub `b859b5f813e458ca26633406a557462953d39e5e`.

Le patch validé localement :

- étend le parsing de marge à `marginSchedules` en plus des listes historiques ;
- valide strictement les structures et cohérences de marge publiques ;
- supprime la taille minimale implicite lorsque `contractValueTradePrecision` manque ;
- exige le `markPrice` pour le ticker Derivatives PAPER ;
- refuse les états `suspended` et `postOnly` incompatibles avec un full-fill PAPER ;
- conserve le modèle conservateur account-agnostic actuel au lieu d'inventer un tier privé ;
- n'ajoute ni signal stratégique, ni changement Risk/Broker/ledger, ni API privée, ni LIVE.

Validation exécutée par ChatGPT dans l'environnement de livraison : compilation Python des deux fichiers code/test modifiés, `17 passed` sur le fichier de tests ciblé dans un shell de dépendances isolé exécutant le parser production modifié, et harness isolé complémentaire.

Validation locale finale confirmée : `pytest backend = 371 passed, 2 warnings externes`, Ruff `All checks passed`, mypy `Success: no issues found in 74 source files`, `git diff --check` sans erreur de contenu hors warnings LF -> CRLF. La première suite complète avait révélé un test de digest obsolète resté sur `agent-strategy-v3`; la fixture attendue a été mise à jour pour `agent-strategy-v4` vers `831b95456aa5612d2762e567c0e65579c8776dad753913e40750178c985c3d09`, sans modification de l'algorithme de digest.

## Prochaine étape

Le Batch 17 est validé localement. Il reste à commit puis push explicitement sur `main` avant de le déclarer intégré. Les sujets tiers de marge dynamiques, recovery durable du ledger, multi-instrument orchestré et liquidation Kraken plus fidèle restent des batches séparés à décider.

## LIVE

Aucune décision de passage LIVE n'est incluse. LIVE restera un batch séparé avec clés sans droit de retrait, permissions minimales, idempotence, réconciliation et activation explicite.
