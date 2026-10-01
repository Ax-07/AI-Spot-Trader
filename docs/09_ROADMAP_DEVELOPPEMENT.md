# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub réel          : c699e7ce9fc4f9f43f005d7e8c19199a30befdf1
Commit                    : feat: align AI decisions with candle closes
Batches 28 à 37           : intégrés
Batch 38 Market Attention : patch proposé/local non intégré
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve :

- un seul Agent IA stratégique ;
- backend Python/FastAPI comme application de trading ;
- frontend comme cockpit uniquement ;
- Risk Engine déterministe comme autorité finale ;
- PAPER comme mode actuel ;
- Kraken comme exchange initial ;
- SPOT + PERPETUAL selon les capacités canoniques intégrées, FUTURE daté interdit ;
- aucune sortie LLM directement exécutable sur Kraken ;
- aucun secret versionné ;
- LIVE séparé et ultérieur ;
- Market Attention strictement informatif.

## Cadences distinctes

1. monitoring / mark-to-market : déterministe, sans LLM stratégique ;
2. cycle stratégique IA : `INTERVAL` historique ou `CANDLE_CLOSE` ;
3. Market Discovery : cadence distincte ;
4. streaming marché / candles : technique et déterministe ;
5. Market Attention Radar : observation avec cadence/cache/TTL propres.

## État intégré jusqu'au Batch 37

Les Batches 28 à 35 ont construit et durci Market Attention Radar v1. Le Batch 36 a simplifié la terminologie financière sans modifier les contrats techniques. Le Batch 37 est intégré dans `c699e7c` : scheduler stratégique unique `INTERVAL` / `CANDLE_CLOSE`, déclenchement conseillé SCALP 5m et SWING 4h, réutilisation du `CandleStreamService`, sans replay/catch-up en rafale.

## Batch 38 — préfiltrage Kraken avant recherche publique

**État : patch proposé/local non intégré.**

Objectif : réduire fortement le coût du Radar sans réduire inutilement la fréquence du scan Kraken.

Architecture :

```text
catalogue Kraken
-> scan OHLCV déterministe
-> activité / liquidité
-> faits structurels déterministes
-> intérêt LOW / MEDIUM / HIGH / VERY_HIGH
-> shortlist bornée
-> web_search événementiel et mis en cache
```

Décisions du patch :

- pas de second pipeline OHLC ;
- `candidate_limit` par défaut réduit à 10 ;
- budget Web par défaut 2, plafond runtime 3 ;
- aucune nouvelle recherche pour LOW/MEDIUM ;
- TTL Public Attention porté à 2 h ;
- refresh anticipé uniquement sur événement significatif après cooldown 15 min ;
- recherches séquentielles et bornées ;
- observabilité de l'éligibilité, cache, déclencheur et raison d'absence de recherche ;
- Radar toujours `informative_only=True` et sans dépendance Agent/Risk/Broker/Discovery.

## Modèle auxiliaire Market Attention

Audit confirmé : le Radar utilise encore le même `resolved_settings.llm_model` que le process. La séparation vers un modèle auxiliaire distinct, Luna par défaut, est recommandée mais reste **à décider** dans un batch de configuration séparé.

## Périmètres ultérieurs possibles

À décider seulement sur besoin mesuré :

- modèle auxiliaire Market Attention configurable séparément ;
- journalisation agrégée des tokens fournisseur si elle reste fiable et peu intrusive ;
- cadence stratégique différente lorsqu'une position est ouverte ;
- réaction événementielle intra-bougie ;
- métriques de retard `scheduled_close -> cycle_start` ;
- éventuelle exposition de Market Attention à l'Agent : non décidée ;
- LIVE : séparé et ultérieur.

Aucun ranking déterministe stratégique, quota de trades ou promesse de rendement ne doit être introduit silencieusement.
