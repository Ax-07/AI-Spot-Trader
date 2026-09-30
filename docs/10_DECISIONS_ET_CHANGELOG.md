# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les éléments nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers Broker/Kraken, SPOT sans short, PERPETUAL derrière les contrôles dérivés déterministes, FUTURE daté interdit, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Market Attention Radar reste strictement observationnel et n'est pas un input de l'Agent stratégique.

## Référence courante

```text
HEAD GitHub audité     : 9fc6a4a15f1c44c8ff7b43a342ab8d74bbedb892
HEAD                   : ux: simplify financial terminology
Batch 36               : intégré
Batch 37               : patch cadence IA/bougies proposé localement
```

## Changelog — 2026-09-30 — Batch 37 cadence stratégique IA synchronisée aux bougies

- base GitHub auditée : `9fc6a4a15f1c44c8ff7b43a342ab8d74bbedb892` ;
- réalignement de la documentation qui décrivait encore le Batch 36 comme local ;
- extension optionnelle `CampaignConfiguration.strategic_schedule` sans changement de `configuration_version` et sans migration DB ;
- deux modes : `INTERVAL` et `CANDLE_CLOSE` ;
- absence de `strategic_schedule` = comportement historique `INTERVAL` et payload/digest ancien inchangé ;
- `CANDLE_CLOSE` exige un style explicite et un timeframe appartenant au mapping canonique de ce style ;
- ajout d'un scheduler unique `ScheduledTradingEngine`, sous-classe du moteur existant, sans second moteur stratégique ;
- alignement UTC sur les frontières canoniques 1m/5m/15m/30m/1h/4h/1d ;
- recalcul de la prochaine frontière depuis l'horloge après chaque cycle afin d'éviter la dérive et les rafales de rattrapage ;
- démarrage/restart sur une frontière strictement future, sans replay automatique des décisions manquées ;
- vérification de finalité via le `CandleStreamService` canonique avant le cycle autonome ;
- aucune bougie future/incomplète considérée comme clôturée ;
- `run-cycle` manuel conserve la primitive immédiate ;
- `stop()` interrompt l'attente ;
- monitoring/mark-to-market, Market Discovery et Market Attention conservent leurs responsabilités séparées ;
- UX : nouvelle Session SCALP -> clôture 5m ; SWING -> clôture 4h ;
- le changement de style seul ne réécrit pas silencieusement une personnalisation ; l'action explicite « Réappliquer les valeurs conseillées » peut appliquer les defaults ;
- intervalle fixe présenté en unités lisibles, tout en conservant `trading_cadence_seconds` côté contrat ;
- aucun changement de politique Risk, Broker, pricing PAPER, frais, spread, slippage ou décision stratégique.

## ADR-240 à ADR-247 — Session et lifecycle

`Session` reste une façade UX sur Strategy/Revision/Campaign/paper_run. La création est atomique, les modifications sont versionnées, l'archivage est logique et la reprise d'une Campaign déjà exécutée est explicite.

## ADR-248 à ADR-258 — Trading Style, coûts et multi-timeframes

`SCALP`/`SWING`, `trading-style-map-v1`, `ExecutionCostContext` et `strategic-mtf-v1` enrichissent l'Agent sans modifier Risk. `history_as_of(...)` garantit la causalité des candles. Les defaults UX liés au style ne doivent pas écraser silencieusement une configuration persistée.

## ADR-259 à ADR-268 — Gestion des positions et cycle multi-décisions

Les positions ouvertes restent des alternatives stratégiques. Le plan multi-marchés est ordonné, borné et produit par le même Agent. Risk et Broker suivent cet ordre sur le portefeuille courant. Les erreurs techniques du cycle PAPER conservent l'atomicité prévue et l'audit supporte les relations 1:N.

## ADR-269 à ADR-279 — Contrats Agent, coûts et reasoning

Les Structured Outputs imposent le contrat BUY/SELL/HOLD. Les Sessions PAPER supportent SPOT et PERPETUAL ; FUTURE reste interdit. L'inspection LLM se fait en lecture seule à la frontière OpenAI. Les marks sont rafraîchis avant le premier cycle. L'agressivité n'impose ni quantité maximale, ni turnover. Le raisonnement courant privilégie l'equity nette après coûts, l'allocation du capital et le coût d'opportunité sans seuil mécanique de profit.

## ADR-280 à ADR-286 — Market Attention Radar

Market Attention Radar v1, son observabilité, sa robustesse, ses régimes de liquidité et son runtime hardening restent intégrés. Il ne produit aucun ordre, aucun score stratégique et aucune préférence LONG/SHORT.

## ADR-287 — Le scheduling stratégique devient une propriété explicite de Campaign

**ADOPTÉ DANS LE PATCH BATCH 37 — À INTÉGRER.**

Décision : ajouter un objet optionnel `strategic_schedule` au snapshot `CampaignConfiguration` plutôt qu'un nouveau stockage ou une nouvelle table.

Raisons :

- la cadence fait partie de l'identité reproductible d'une Campaign ;
- le stockage Campaign JSON existe déjà ;
- l'extension optionnelle peut préserver exactement les anciens payloads/digests ;
- aucune migration DB n'est nécessaire ;
- `trading_cadence_seconds` reste conservé pour le legacy et les outils existants.

Contrat :

```text
absent                      -> INTERVAL historique
{mode: INTERVAL}            -> INTERVAL explicite
{mode: CANDLE_CLOSE,
 decision_timeframe: <tf>}   -> clôture canonique
```

Pour `CANDLE_CLOSE`, un style explicite est requis et le timeframe doit appartenir au mapping canonique : SCALP `1m/5m/15m/30m`, SWING `1h/4h/1d`.

## ADR-288 — Un seul moteur gère INTERVAL et CANDLE_CLOSE

**ADOPTÉ DANS LE PATCH BATCH 37 — À INTÉGRER.**

`ScheduledTradingEngine` étend la boucle autonome existante au lieu de créer un scheduler stratégique parallèle.

En `INTERVAL`, il délègue à la boucle historique inchangée.

En `CANDLE_CLOSE` :

1. calcul de la prochaine frontière UTC strictement future ;
2. attente interrompable par `stop()` ;
3. vérification que la candle cible est explicitement finale dans le service canonique ;
4. exécution d'un seul cycle stratégique ;
5. recalcul de la prochaine frontière depuis l'horloge réelle après le cycle.

Ainsi, la durée d'un cycle ne décale pas la grille et une suspension ne provoque pas de rafale de décisions rétrospectives.

La méthode manuelle `run_cycle()` n'est pas remplacée. Le moteur schedulé opte explicitement pour son utilisation pendant l'attente autonome ; le runner sérialise les cycles afin qu'un appel manuel ne chevauche jamais un cycle automatique.

## ADR-289 — Le timeframe de décision est un trigger, pas un nouveau contexte stratégique

**ADOPTÉ DANS LE PATCH BATCH 37 — À INTÉGRER.**

La bougie de décision ne remplace pas `StrategicMultiTimeframeContextService`. Le scheduler réutilise `CandleStreamService` uniquement pour l'alignement/finalité. L'Agent reçoit toujours le contexte multi-timeframes canonique du style avec les garanties de causalité existantes.

Aucun second cache OHLC, aucun indicateur de direction et aucun ranking technique ne sont introduits.

## ADR-290 — Discovery conserve sa cadence et son orchestration actuelles

**ADOPTÉ DANS LE PATCH BATCH 37 — À INTÉGRER.**

`watchlist_refresh_seconds` reste distinct de la cadence stratégique. `refresh_if_due()` continue d'être évalué lors du passage du cycle dynamique. Aucun scheduler Discovery séparé n'est créé dans ce batch.

Conséquence UX : une clôture 5m signifie « un cycle stratégique peut démarrer après cette clôture », pas « exactement un seul appel fournisseur toutes les cinq minutes ».

## Points explicitement non décidés

- cadence accélérée lorsqu'une position est ouverte ;
- réaction intra-bougie à un événement ;
- utilisation de Market Attention comme contexte Agent ;
- seuil de fraîcheur Risk spécifique au SCALP ;
- LIVE.
