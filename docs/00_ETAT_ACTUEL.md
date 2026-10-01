# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : c699e7ce9fc4f9f43f005d7e8c19199a30befdf1
Commit     : feat: align AI decisions with candle closes
```

État revérifié le 01/10/2026 au démarrage du Batch 38. Le Batch 37 est **intégré** dans ce HEAD. L'ancienne référence `9fc6a4a...` et la mention « Batch 37 local/non intégré » étaient obsolètes.

## Batch 38 — Market Attention : préfiltrage Kraken et maîtrise du coût IA

**État : patch proposé/local non intégré.**

Le Radar conserve son rôle strictement informatif et indépendant du trading. Le changement principal est un entonnoir déterministe avant toute recherche publique :

```text
catalogue Kraken
-> OHLCV canonique 5m
-> activité / liquidité
-> caractéristiques structurelles descriptives
-> niveau d'intérêt déterministe
-> shortlist réduite
-> web_search seulement si HIGH / VERY_HIGH et événement justifié
```

Le pipeline OHLC existant est réutilisé ; aucun second cache ou pipeline candles n'est créé.

Nouvelles caractéristiques descriptives possibles : tendance multi-horizons, anomalie de volume, expansion de volatilité/range, breakout à surveiller, retournement à surveiller, consolidation et divergence prix/volume. Elles ne constituent ni un signal directionnel ni un ordre.

Politique proposée :

- `candidate_limit` par défaut : `10` au lieu de `20` ;
- `max_web_searches_per_refresh` : `2` par défaut, plafond runtime `3` ;
- `public_attention_ttl_seconds` : `7200` s (2 h) ;
- cooldown événementiel : `900` s avant un refresh anticipé ;
- aucun appel web pour `LOW` ou `MEDIUM` ;
- cache réutilisé tant qu'il reste valable, sauf changement déterministe significatif après cooldown ;
- recherches exécutées séquentiellement et bornées pour éviter les bursts.

L'observabilité API expose le nombre de candidats éligibles, recherches réalisées, cache utilisé, rafraîchissements événementiels et recherches évitées, ainsi que la décision de recherche par candidat.

Le couplage actuel du modèle auxiliaire Radar à `resolved_settings.llm_model` est confirmé par audit. La séparation de configuration `Agent stratégique / Market Attention` reste **à décider** dans un batch dédié afin de ne pas élargir ce patch de coût/radar à la configuration globale sans validation opérateur.

Voir `docs/38_BATCH_MARKET_ATTENTION_PREFILTRAGE.md`.
