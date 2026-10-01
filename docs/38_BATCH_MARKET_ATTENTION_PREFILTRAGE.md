# Batch 38 — Market Attention Radar : préfiltrage Kraken et maîtrise du coût IA

> **Document historique.** Le Batch 38 est intégré dans `2776fc68fb0ff8c094148a246d22de844ee868c7`. Sa couche de recherche publique est **supplantée par le Batch 39**, qui retire entièrement OpenAI/Web du Radar. Les caractéristiques et le scoring déterministes introduits ici restent actifs.

## Référence intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD Batch 38 intégré : 2776fc68fb0ff8c094148a246d22de844ee868c7
Commit                  : feat: prefilter market attention web research
```

## Apports déterministes conservés

Le Batch 38 a consolidé l'entonnoir Kraken avant la couche Web alors existante :

```text
catalogue Kraken
-> scan OHLCV 5m canonique
-> activité + liquidité
-> structure déterministe descriptive
-> niveau d'intérêt déterministe
-> shortlist diversifiée
```

Caractéristiques introduites et conservées en Batch 39 :

```text
TRENDING
VOLUME_ANOMALY
VOLATILITY_EXPANSION
BREAKOUT_WATCH
REVERSAL_WATCH
CONSOLIDATING
PRICE_VOLUME_DIVERGENCE
```

Niveaux d'intérêt conservés : `LOW`, `MEDIUM`, `HIGH`, `VERY_HIGH`.

Les horizons ont été enrichis avec retour précédent/courant, range de référence, expansion du range, volatilité de référence, expansion de volatilité et distance descriptive au breakout. Le ranking reste déterministe et la shortlist conserve une diversification par régime de liquidité, y compris pour `MICRO`.

## Mécanisme historique supprimé par Batch 39

Le Batch 38 contenait encore une couche Public Attention avec recherches Web événementielles, cache, TTL, cooldown et budget par refresh. Cette couche n'appartient plus à l'architecture courante proposée :

```text
Batch 38 historique : shortlist -> OpenAI/web_search
Batch 39 courant    : shortlist -> observabilité -> Agent stratégique séparé
```

Les anciennes classes et métriques de recherche publique ne doivent donc plus être utilisées comme contrat runtime ou UI.

## Invariants toujours valides

- un seul Agent stratégique ;
- Risk Engine final ;
- aucun second pipeline OHLC ;
- aucun look-ahead ;
- aucune recommandation LONG/SHORT ;
- Market Attention reste `informative_only=True` ;
- les caractéristiques signifient uniquement « mérite davantage d'attention ».

Voir `docs/39_BATCH_RADAR_KRAKEN_SANS_IA.md` pour l'architecture active proposée.
