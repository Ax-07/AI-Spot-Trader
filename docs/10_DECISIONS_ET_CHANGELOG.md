# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs, les décisions récentes et les choix nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers Broker/Kraken, SPOT sans short/levier/marge, PERPETUAL PAPER derrière les contrôles dérivés déterministes, FUTURE daté interdit, audit durable des cycles, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Les Sessions PAPER canoniques autorisent `SPOT` et `PERPETUAL` linéaire. `FUTURE` daté reste interdit.

## Référence courante

```text
HEAD GitHub audité     : b46f463c474e25a38da7ddcaebf588753922031b
HEAD                   : feat: add session economic history
Recalibrage net/cost   : ADR-277 intégré dans 463850d
Historique économique  : ADR-278 intégré dans b46f463c
Doctrine reasoning     : ADR-279 proposée dans le présent patch local
```

## Décisions historiques toujours actives

- ADR-173 à ADR-239 : immutabilité Strategy/Campaign, Control Plane, accounting, monitoring, discovery, explicabilité, candles/charts et overlays ;
- ADR-240 à ADR-247 : façade Session, lifecycle, immutabilité et modes de marchés ;
- ADR-248 à ADR-255 : Trading Style, coûts Agent et contexte stratégique multi-timeframes ;
- ADR-256 à ADR-258 : UX Session du style et compatibilité legacy ;
- ADR-259 à ADR-262 : gestion stratégique des positions, `position-management-v1`, plafond Risk par ordre et rotation du capital ;
- ADR-263 : classification robuste des limites fournisseur OpenAI et fail-closed ;
- ADR-264 : précision PAPER PERPETUAL et normalisation descendante du quantum ;
- ADR-265 à ADR-268 : multi-décisions / multi-marchés, Risk séquentiel, atomicité PAPER et audit 1:N ;
- ADR-269, ADR-270 et ADR-272 : Structured Outputs strict, contrat multi-marchés protégé et diagnostic sécurisé ;
- ADR-271 : garde-fou SPOT-only intégré par erreur dans `aa404e4`, supersédé ;
- ADR-273 : Sessions PAPER SPOT + PERPETUAL, FUTURE daté interdit ;
- ADR-274 : inspection en lecture seule du payload OpenAI réel à la frontière `OpenAIResponsesClient` ;
- ADR-275 : refresh initial des marks PAPER avant ouverture des cycles ;
- ADR-276 : recalibrage du prompt stratégique sans cible de rendement injectée ni biais de quantité maximale ;
- ADR-277 : recalibrage cost-aware vers l'equity nette, allocation du capital et agressivité sans turnover obligatoire ;
- ADR-278 : historique économique Session/run comme projection en lecture seule, sans second ledger ni seconde comptabilité ;
- ADR-279 : doctrine qualitative de raisonnement trading pour les prompts stratégiques courants, sans règles mécaniques.

## ADR-240 — Session est une façade UX, pas un nouvel agrégat persistant

**ADOPTÉ AU BATCH 19.8.** `Session` reste une projection sur Strategy, StrategyRevision, Campaign, paper_run et runtime actif. Aucune table `sessions` n'est créée.

## ADR-241 — La création Session est atomique côté backend

**ADOPTÉ AU BATCH 19.8.** Strategy + StrategyRevision 1 + Campaign sont créées dans une seule transaction.

## ADR-242 à ADR-247 — Versioning, archivage, lifecycle et marchés

**ADOPTÉS AU BATCH 19.8.** Les modifications créent de nouveaux faits immuables ; `Supprimer` archive ; les statuts sont dérivés ; `stop` ferme runtime/run ; `AUTOMATIC_AI` et `MANUAL` restent explicites.

## ADR-248 à ADR-255 — Style, coûts et multi-timeframes

**ADOPTÉS AUX BATCHES 19.9A/19.9B.** `SCALP`/`SWING`, `trading-style-map-v1`, `ExecutionCostContext` et `strategic-mtf-v1` enrichissent l'Agent sans modifier Risk. `history_as_of(...)` garantit la causalité des candles.

## ADR-256 à ADR-258 — UX du style

**ADOPTÉS AU BATCH 19.9C.** Le style est exposé sans couplage silencieux à l'agressivité, aux marchés ou à Risk.

## ADR-259 à ADR-262 — Gestion des positions et rotation du capital

**ADOPTÉS AU BATCH 19.10.** Les positions ouvertes restent des opportunités stratégiques ; `position-management-v1` reste factuel ; `risk_max_order_notional` reste un plafond par ordre ; aucune règle déterministe `après SELL -> BUY` n'est introduite.

## ADR-263 — Les limites fournisseur OpenAI sont classifiées avant retry

**ADOPTÉ AU BATCH 19.12.** Quota/crédit/usage/spend sont non retryables ; les limitations temporaires restent retryables avec `Retry-After` valide ou backoff borné. Toute erreur LLM reste fail-closed.

## ADR-264 — Précision PAPER PERPETUAL et quantum provider-derived

**ADOPTÉ ET INTÉGRÉ HISTORIQUEMENT AU COMMIT `18596ac9d4f6554aa4817a9bdb374ab597c2399f`.** Les validations de précision dérivées restent canoniques.

## ADR-265 — Un cycle peut porter un plan stratégique ordonné multi-marchés

**ADOPTÉ ET INTÉGRÉ AU COMMIT `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.** Un seul appel du même Agent stratégique produit un plan ordonné contenant plusieurs décisions sur des marchés distincts. `max_decisions_per_cycle` vaut `6` par défaut, hard limit `20`.

## ADR-266 — Risk et Broker suivent l'ordre du plan sur un portefeuille causal

**ADOPTÉ ET INTÉGRÉ AU COMMIT `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.** Chaque décision est évaluée après application des éventuelles exécutions précédentes. `HOLD` et `REJECT` n'interrompent pas le plan.

## ADR-267 — Une défaillance technique rend le cycle PAPER atomique

**ADOPTÉ ET INTÉGRÉ AU COMMIT `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.** Une erreur technique Risk ou Broker fait passer le cycle à `FAILED` et restaure le portefeuille au checkpoint initial.

## ADR-268 — L'audit devient 1:N et les analytics restent économiques

**ADOPTÉ ET INTÉGRÉ AU COMMIT `29316d7521accfe46316cb2bc6dfcf7652ba04bf`.** La migration `0007_multi_decision_cycles` conserve plusieurs décisions, évaluations Risk et intentions d'exécution dans leur ordre.

## ADR-269 — Le schéma Structured Outputs encode le contrat action/quantité

**ADOPTÉ ET INTÉGRÉ AU COMMIT `aa404e46c1f05269ac2279507aa746b3af7a965d`.** `BUY`/`SELL` imposent une quantité strictement positive et `HOLD` impose `null`.

## ADR-270 — Le nouveau chemin reçoit un contrat protégé multi-marchés explicite

**ADOPTÉ ET INTÉGRÉ AU COMMIT `aa404e46c1f05269ac2279507aa746b3af7a965d`.** `StrategyInstructionsClient` injecte `strategic-multi-market-plan-v1`. Le singleton historique reste disponible pour legacy/replay.

## ADR-271 — Garde-fou SPOT-only du runtime

**INTÉGRÉ PAR ERREUR DANS `aa404e4` — SUPERSEDÉ PAR ADR-273.** La restriction contredisait le support dérivés canonique.

## ADR-272 — Les erreurs de plan sont diagnostiquées sans sortie brute

**ADOPTÉ ET INTÉGRÉ AU COMMIT `aa404e46c1f05269ac2279507aa746b3af7a965d`.** Les erreurs de contrat sont catégorisées sans persister la sortie LLM brute ; aucun retry sémantique n'est ajouté.

## ADR-273 — Les Sessions PAPER supportent SPOT et PERPETUAL ; FUTURE reste interdit

**ADOPTÉ ET INTÉGRÉ AU COMMIT `b4f1e50f22164c7d019d11d930485733c01c6711`.** Le garde-fou SPOT-only est retiré. Les marchés `SPOT` et `PERPETUAL` linéaires restent soumis au pipeline Agent -> Risk -> Broker PAPER. `FUTURE` daté reste refusé.

## ADR-274 — L'inspection LLM se fait à la frontière canonique OpenAI

**ADOPTÉ ET INTÉGRÉ AU COMMIT `7846d892d2c4b3aea3fb7ca628d5976639eac0c0`.**

`OpenAIResponsesClient` capture en best-effort le dictionnaire exact utilisé comme body JSON de chaque appel Responses API réussi. La trace expose `instructions`, `input`, Structured Output, tools, `parallel_tool_calls`, `store`, output fournisseur et texte final lorsqu'il existe. Les headers HTTP, la clé OpenAI, les chaînes de connexion et secrets ne sont jamais ajoutés au record.

Les tool loops sont représentées par plusieurs records ordonnés. La corrélation cycle/discovery est inférée des inputs canoniques ; le chat ajoute `session_id` via un `ContextVar` asynchrone sans modifier le prompt transmis. La rétention est bornée en mémoire et une exception de l'audit ne peut pas faire échouer le moteur.

## ADR-275 — Les marks PAPER sont rafraîchis avant le premier cycle

**ADOPTÉ ET INTÉGRÉ AU COMMIT `5fdd9a32bce45deda30c652b6b6f8c59e4996559`.**

Les moniteurs SPOT et PERPETUAL terminent un premier `refresh_once()` avant de rendre le runtime initialisé. Une erreur de refresh ne fabrique aucune valorisation : le portefeuille reste incomplet et Capacity/Risk conservent leur comportement fail-closed.

## ADR-276 — L'agressivité ne détermine pas une quantité maximale

**ADOPTÉ ET INTÉGRÉ AU COMMIT `282267b1f491bb07b2644f6b9c5dca01c539697f`.**

Les instructions stratégiques canoniques des Sessions/Campaigns ne contiennent plus la cible expérimentale `+4 %/jour`. Cette cible demeure documentée au niveau projet et reste explicitement non garantie.

À ce commit, le mapping LLM courant `aggressiveness-map-v2` supprimait les formulations de quantité maximale et conservait une progression de posture. Il est ensuite supersédé pour les Campaigns courantes par `aggressiveness-map-v3` via ADR-277. Le mapping durable `aggressiveness-map-v1` reste conservé à l'identique pour les manifests/replays.

Le `AGENT_SYSTEM_PROMPT` historique `agent-strategy-v4` reste figé pour les protocoles v1/v2/v3 et leurs replays ; le recalibrage porte sur les instructions courantes composées par `StrategyInstructionsClient`.

## ADR-277 — L'Agent optimise la qualité économique nette, pas le turnover

**ADOPTÉ ET INTÉGRÉ AU COMMIT `463850d8281faebe86a6ee733d58781c349015d0`.**

Motivation expérimentale : une session PAPER réelle d'environ 9 h, partie de `100`, a produit environ `+0,727` de P&L brut mais `-2,287` net, avec une equity finale d'environ `97,713`, `1 246` fills et des coûts importants. Cette observation montre qu'un turnover élevé peut annuler un avantage brut faible ; elle ne prouve pas la performance générale de la stratégie.

Décision :

- rendre explicite l'objectif de progression de l'equity **nette après coûts** ;
- considérer frais, spread, slippage et funding lorsqu'il est disponible dans les faits fournis ;
- raisonner en allocation et coût d'opportunité entre cash, positions existantes et nouvelles opportunités ;
- considérer `HOLD`, cash et conservation d'une position comme des allocations valides ;
- rappeler qu'une rotation cumule plusieurs coûts d'exécution ;
- interdire l'interprétation « faible conviction -> petite position pour essayer » ;
- faire évoluer le mapping LLM courant vers `aggressiveness-map-v3`, où l'agressivité augmente l'initiative sur les opportunités convaincantes mais n'impose ni turnover, ni micro-trades, ni fréquence minimale ;
- ne créer aucun seuil de profit, cooldown, durée minimale, quota de trades, score algorithmique ou garantie de rendement ;
- ne modifier ni Risk, ni Broker, ni planner, ni `AGENT_SYSTEM_PROMPT`, ni `aggressiveness-map-v1` historique.

Validation locale du commit : tests ciblés `47/47` passés ; suite backend complète `pytest -q` passée à `100 %` sans échec. Deux avertissements de dépréciation Starlette/AnyIO restent hors périmètre.

### Audit SELL / SHORT PERPETUAL associé

Classification :

- **confirmé** : le mapping BUY/SELL PERPETUAL, le planner, la sélection multi-marchés et Risk sont directionnellement symétriques ; aucune cause centrale ne favorise explicitement SHORT ;
- **confirmé** : `aggressiveness-map-v2` augmentait explicitement rotation/fréquence potentielle aux niveaux élevés, facteur plausible de turnover global mais pas de biais SHORT démontré ;
- **confirmé** : le texte générique de gestion utilisait « signal automatique de vente », asymétrique pour la réduction d'un SHORT ; le recalibrage neutralise la formulation et rappelle `SELL` réduit LONG / `BUY` réduit SHORT ;
- **corrigé** : objectif net-equity, coûts de rotation et coût d'opportunité explicites ;
- **à décider** : existence d'un biais SHORT persistant du modèle sur plusieurs sessions comparables.

Aucun quota LONG/SHORT ni contre-biais déterministe n'est introduit.

## ADR-278 — L'historique économique est une projection, pas une seconde comptabilité

**ADOPTÉ ET INTÉGRÉ AU COMMIT `b46f463c474e25a38da7ddcaebf588753922031b`.**

Le cockpit doit pouvoir expliquer un run de plusieurs heures sans reconstruire manuellement des centaines de cycles. La solution retenue réutilise exclusivement les faits persistés et les analytics canoniques :

- `PaperAnalyticsReport` reste source de vérité pour equity, P&L brut/net, drawdown, exposition, frais, spread, slippage et funding ;
- les opérations économiques sont projetées depuis les fills économiquement engagés et les snapshots de portefeuille avant/après ;
- les fills d'un cycle `FAILED` restent auditables mais sont exclus de la projection économique, conformément à l'atomicité PAPER ;
- `Fill.realized_pnl` est réutilisé directement ; aucun P&L réalisé n'est recalculé parallèlement ;
- le turnover est défini comme `total_notional / initial_equity` ;
- les coûts totaux sont définis comme `fees + spread + slippage - funding_pnl`, en conservant la convention de signe canonique du funding ;
- l'effet d'un BUY/SELL PERPETUAL est déduit de la position signée avant/après, afin de distinguer ouverture, augmentation, réduction, clôture et flip LONG/SHORT ;
- le frontend filtre et affiche les valeurs fournies par le backend, sans recalcul financier.

La Session reste une façade : le cockpit associe Session -> Campaign -> têtes de lineage PAPER existantes, puis sélectionne explicitement le run économique à afficher. Aucune table Session, aucun ledger et aucune migration SQL ne sont ajoutés.

## ADR-279 — Les prompts courants reçoivent une Trading Reasoning Doctrine qualitative

**PROPOSÉ DANS LE PRÉSENT PATCH LOCAL SUR LA BASE `b46f463c`.**

La doctrine `trading-reasoning-doctrine-v1` est une section canonique concise qui guide la façon dont le LLM construit une thèse à partir des faits disponibles. Elle couvre régime/structure, cohérence multi-timeframe, momentum/volatilité, qualité breakout/pullback lorsque les données le permettent, comparaison cash/positions/opportunités, coûts et invalidation de la thèse.

Décision :

- centraliser le texte dans `TRADING_REASONING_DOCTRINE` ;
- l'injecter une seule fois dans le chemin singleton Campaign courant et une seule fois dans `strategic-multi-market-plan-v1` ;
- ne pas l'injecter dans `market-discovery-v1`, qui construit une watchlist et ne produit pas la décision finale `BUY`/`SELL`/`HOLD` ;
- laisser `AGENT_SYSTEM_PROMPT` `agent-strategy-v4` strictement inchangé ;
- conserver `aggressiveness-map-v1` historique et `aggressiveness-map-v3` courant ;
- conserver le recalibrage net/cost-aware ;
- ne créer aucun seuil RSI/MACD, règle BUY/SELL mécanique, score, stop, take-profit, timer, quota de trades ou quota LONG/SHORT ;
- ne modifier ni Risk, ni Broker, ni planner.

L'invalidation d'une thèse est explicitement un concept de raisonnement stratégique et non un ordre automatique de sortie. `HOLD` ou conserver du cash restent des décisions valides lorsque les faits ne soutiennent pas une thèse suffisamment convaincante après coûts.

## SCALP — audit de fraîcheur associé

Aucun changement de politique dans ce batch. `RiskEngine` / `SequentialCycleRiskEngine` possèdent déjà les rejets `MARKET_FRESHNESS_UNAVAILABLE` et `MARKET_DATA_STALE`. `kraken_stale_after_seconds` est toujours optionnel et vaut `None` par défaut. Au HEAD audité, `campaign_composition.py` ne renseigne pas `RiskPolicy.stale_after`, donc le rejet stale Risk n'est pas activé par défaut dans les Campaigns courantes.

Un durcissement SCALP éventuel doit être traité séparément après mesure de la latence `MarketState -> LLM -> Risk`, afin de choisir un seuil fondé sur la distribution réelle des latences.

## Changelog — 2026-09-28 — Trading Reasoning Doctrine v1 (patch local)

- HEAD GitHub resynchronisé : `b46f463c474e25a38da7ddcaebf588753922031b` ;
- doctrine qualitative centralisée dans `prompt.py` ;
- injection singleton courant + plan multi-marchés ;
- discovery laissée volontairement sans doctrine finale ;
- `AGENT_SYSTEM_PROMPT` historique et mappings d'agressivité inchangés ;
- SPOT/PERPETUAL, HOLD, net-cost-aware et autorité Risk préservés ;
- aucun signal mécanique, scoring, quota ou changement Risk/Broker/planner ;
- compilation Python des quatre fichiers runtime/tests modifiés : succès ;
- harness local de composition des prompts : PASS ;
- `test_trading_reasoning_doctrine.py` dans le harness isolé : `3/3` passés ;
- validation locale utilisateur : suite ciblée `44/44` passée ;
- premier `pytest -q` complet : un seul échec dans `test_trading_style.py`, dû à une attente exacte de composition non mise à jour pour la nouvelle section canonique ;
- correctif : ajout de `TRADING_REASONING_DOCTRINE` à cette attente et contrôle d'unicité, sans modification runtime ;
- rerun complet restant à effectuer localement après extraction du ZIP correctif.

## Changelog — 2026-09-28 — Batch 25 historique économique Session/run

- base GitHub vérifiée avant intégration : `59f92938bf5159004783ae004fe99c808cb2c8c2` ;
- intégration GitHub constatée au HEAD `b46f463c474e25a38da7ddcaebf588753922031b` ;
- projection économique en lecture seule ajoutée au-dessus d'analytics + audit existants ;
- nouveaux endpoints `GET /api/v1/economic-history` et `/api/v1/economic-history/export` ;
- distinction explicite `trade_count` / `fill_count` / décisions ;
- turnover, coûts/notional, coûts/equity, fills/heure et rotation entre marchés ajoutés ;
- classification PERPETUAL fondée sur la position avant/après, sans hypothèse `SELL = clôture` ;
- écran Historique orienté Session/run avec filtres action/marché/type et export JSON ;
- aucun changement Agent, prompt, `aggressiveness-map-v3`, Risk, Broker, cadence ou coûts ;
- aucune migration SQL ;
- validation locale finale documentée : backend ciblé `11/11`, suite backend complète à `100 %`, frontend `39/39`, `pnpm lint` passé et `pnpm typecheck` passé.

## Changelog — 2026-09-28 — Recalibrage net/cost-aware intégré

- commit `463850d8281faebe86a6ee733d58781c349015d0` (`refactor: make strategic agent cost aware`) ;
- base précédente : `282267b1f491bb07b2644f6b9c5dca01c539697f` ;
- objectif courant : equity nette après coûts, pas activité brute ;
- allocation cash / positions / nouvelles opportunités explicitée ;
- coûts de rotation explicités sans seuil algorithmique ;
- `aggressiveness-map-v3` courant, mapping v1 historique intact ;
- formulation de management PERPETUAL rendue directionnellement neutre ;
- aucune modification Risk/Broker/planner ;
- constat du run 9 h documenté comme observation expérimentale, non comme vérité générale ;
- validation locale : tests ciblés `47/47`, suite backend complète `pytest -q` à `100 %` sans échec.

## Changelog — 2026-09-27 — Recalibrage prompts intégré

- commit `282267b1f491bb07b2644f6b9c5dca01c539697f` (`refactor: recalibrate strategic LLM prompts`) ;
- suppression de `+4 %/jour` des contrats stratégiques courants ;
- mapping agressivité courant `v2` sans biais de quantité maximale à cette étape ;
- garde-fou explicite « 10/10 != max quantity » ;
- qualité de thèse > fréquence ; `HOLD` conservé ;
- `niveat=` corrigé via renderer partagé ;
- règles SPOT/PERPETUAL/Risk/multi-décisions inchangées.

## Changelog — 2026-09-27 — Correctif valorisation PAPER intégré

- commit `5fdd9a32bce45deda30c652b6b6f8c59e4996559` (`fix: refresh paper marks before trading starts`) ;
- premier refresh des marks avant démarrage effectif des cycles ;
- fail-closed conservé si le refresh échoue.

## Changelog — 2026-09-27 — Inspecteur LLM intégré

- commit `7846d892d2c4b3aea3fb7ca628d5976639eac0c0` (`feat: add read-only LLM request inspector`) ;
- instrumentation canonique : `OpenAIResponsesClient` ;
- endpoint lecture seule : `GET /api/v1/llm-audit` ;
- cockpit : Réglages -> Inspecteur LLM ;
- rétention bornée et fail-open de l'observabilité.

## Changelog — 2026-09-27 — Correctif PERPETUAL intégré

- commit `b4f1e50f22164c7d019d11d930485733c01c6711` (`fix: restore paper perpetual session support`) ;
- retrait du garde-fou SPOT-only erroné ;
- SPOT + PERPETUAL linéaire PAPER restaurés ;
- FUTURE daté reste interdit.

## Changelog — 2026-09-27 — Durcissement multi-market LLM intégré

- commit `aa404e46c1f05269ac2279507aa746b3af7a965d` (`fix: harden multi-market LLM plan contract`) ;
- Structured Outputs strict ;
- contrat protégé `strategic-multi-market-plan-v1` ;
- diagnostic Agent sécurisé ;
- aucun retry LLM sémantique.

## Changelog — 2026-09-27 — Batch 19.13 intégré

- commit `29316d7521accfe46316cb2bc6dfcf7652ba04bf` ;
- plan ordonné multi-marchés, multi-`BUY` / `SELL` / `HOLD` ;
- Risk séquentiel et causal ;
- rollback PAPER atomique ;
- persistence 1:N et migration `0007_multi_decision_cycles` ;
- analytics basés sur fills/trades réels.
