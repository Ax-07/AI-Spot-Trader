# Batch 19.13 — Refresh-on-miss du catalogue Kraken PERPETUAL pour les candles

## Référence

Audit réalisé sur GitHub `main` au HEAD `1408a74f5256ff3674b154d3a64794f4ffd012c2` (`docs: sync post-19.12 state`).

Ce HEAD ne modifie que la documentation par rapport à `f8397d207be67309db083e49e113253fe88b3624` ; le code runtime audité est donc bien celui intégré avant ce correctif.

## Symptôme

Des cycles PAPER échouent pendant `MARKET_SELECTION` avec `UnknownKrakenSymbolError` lorsque Dynamic Market Discovery découvre un PERPETUAL Kraken apparu après l'initialisation du `KrakenCandleProvider` partagé.

La chaîne causale auditée est :

`Dynamic Market Discovery -> TradingCycleRunner -> MultiTimeframeDecisionProvider -> StrategicMultiTimeframeContextService -> CandleStreamService -> KrakenCandleProvider`.

Le fail-closed aval est correct : aucun `RiskAssessment` ni `ExecutionIntent` n'est créé après cet échec.

## Cause confirmée

`KrakenCandleProvider` conservait un `_instrument_cache` construit lors du premier besoin PERPETUAL et ne le rafraîchissait plus. Discovery peut, elle, voir un catalogue Kraken plus récent. Un marché valide nouvellement découvert pouvait donc être absent du cache candles jusqu'au redémarrage backend.

Le contexte `strategic-mtf-v1` construit toutes les séries demandées avec `asyncio.gather()`. Une exception provider est volontairement propagée ; seules des séries réellement vides sont résumées en `MISSING`.

## Correctif

### Catalogue canonique

La construction du mapping d'instruments Kraken Derivatives est centralisée dans `integrations/kraken/derivatives.py` :

- préférence aux PERPETUAL `LINEAR`, seule famille dérivée exécutable par l'architecture PAPER actuelle ;
- tie-break déterministe par `venue_symbol` ;
- extraction du sous-ensemble PERPETUAL `LINEAR` réutilisée par le provider candles.

Cela évite d'entretenir une troisième logique de sélection de contrats.

### Refresh-on-miss

`KrakenCandleProvider` applique désormais :

1. cold start : charge une fois le catalogue ;
2. hit cache : retourne l'instrument sans appel Kraken supplémentaire ;
3. miss sur un cache déjà chargé : rafraîchit une fois le catalogue ;
4. retente la résolution ;
5. si le symbole reste absent, lève `UnknownKrakenSymbolError`.

Le refresh est protégé par un `asyncio.Lock`. Les lectures multi-timeframes concurrentes qui observent le même cache périmé partagent ainsi le même refresh au lieu de lancer plusieurs appels `/instruments`.

## Sémantique `strategic-mtf-v1`

Aucun changement de sémantique n'est introduit dans `agent/multi_timeframe.py` ni `market/strategic_context.py` :

- `history_as_of(...) == ()` -> `MISSING` ;
- historique incomplet -> `PARTIAL` ;
- historique complet -> `AVAILABLE` ;
- `UnknownKrakenSymbolError` après refresh -> exception technique propagée, donc cycle fail-closed avant Risk/Broker.

Le correctif ne masque donc pas un marché réellement incohérent ou non résolu par le catalogue Kraken courant.

## Observabilité

Le journal canonique de cycle persiste actuellement `failure_stage`, `failure_error_type` et `failure_timed_out`. Ajouter `symbol` / `market_type` au niveau exact de l'exception multi-timeframes nécessiterait une évolution structurée de `TradingCycleFailure`, du schéma/persistence et des vues API.

Ce batch ne réalise pas cette migration afin de rester limité au défaut de catalogue et de ne pas contourner la sanitation générale. Aucun message brut provider n'est ajouté au journal. Une évolution dédiée pourra transporter des champs bornés et typés plutôt qu'un texte d'exception arbitraire.

## Fichiers modifiés / créés

- `backend/src/ai_spot_trader/integrations/kraken/candles.py`
- `backend/src/ai_spot_trader/integrations/kraken/derivatives.py`
- `backend/tests/test_kraken_candle_instrument_refresh.py`
- `backend/tests/test_strategic_mtf_kraken_fail_closed.py`
- `docs/00_ETAT_ACTUEL.md`
- `docs/10_DECISIONS_ET_CHANGELOG.md`
- `docs/24_BATCH_19_13_KRAKEN_PERPETUAL_CANDLE_REFRESH.md`

## Tests ajoutés

- cache initial ne contenant que BTC puis catalogue suivant contenant `CFG/USD` PERPETUAL LINEAR ; quatre demandes de timeframes concurrentes résolvent CFG après un unique refresh sans redémarrage ;
- symbole toujours absent après refresh -> `UnknownKrakenSymbolError` ;
- symbole déjà en cache -> aucun refresh supplémentaire ;
- historique candles vide -> `MISSING`, mais `UnknownKrakenSymbolError` reste propagée par `StrategicMultiTimeframeContextService`.

## Invariants préservés

- PAPER uniquement ;
- aucun ordre direct LLM -> Kraken ;
- même Agent IA stratégique ;
- Risk Engine autorité finale ;
- aucun fallback HOLD ;
- aucune règle indicateur -> action ;
- aucune donnée future ni look-ahead ;
- frontend inchangé ;
- aucune clé Kraken privée requise.

## Validation effectuée lors de la préparation

Exécuté dans l'environnement de préparation du patch :

- compilation syntaxique des fichiers Python modifiés/créés : PASS ;
- harness `pytest` isolé qui exécute les fonctions/méthodes exactes extraites du patch pour le mapping, le cache hit, le miss concurrent et le miss réel : `4 passed` ;
- reconstruction des baselines `candles.py`, `derivatives.py`, `docs/00_ETAT_ACTUEL.md` et `docs/10_DECISIONS_ET_CHANGELOG.md` vérifiée par SHA Git blob contre GitHub `1408a74...` avant calcul du diff ;
- `git diff --check` sur ces baselines exactes : PASS ;
- `git diff --cached --check` incluant les nouveaux fichiers : PASS.

Non exécuté dans cet environnement : le `pytest` ciblé du repository et le `pytest` backend complet, car le checkout complet du repository n'est pas disponible dans le conteneur de préparation. Ils restent obligatoires sur le clone opérateur avant commit/push.
