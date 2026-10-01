# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 2776fc68fb0ff8c094148a246d22de844ee868c7
Commit     : feat: prefilter market attention web research
```

État revérifié le 01/10/2026 au démarrage du Batch 39. Le Batch 38 est **intégré** dans ce HEAD. L'ancienne référence `c699e7c` et la mention « Batch 38 local/non intégré » étaient obsolètes.

## Batch 39 — Radar Kraken sans IA/Web

**État : patch proposé/local non intégré.**

Objectif du patch : supprimer complètement le chemin auxiliaire OpenAI/Web du Market Attention Radar et conserver uniquement l'analyse déterministe des données Kraken.

Architecture proposée :

```text
Kraken
-> OHLCV 5m canonique finalisé
-> analyse 5m / 15m / 1h / 4h
-> volume / prix / range / volatilité / liquidité
-> caractéristiques déterministes
-> intérêt LOW / MEDIUM / HIGH / VERY_HIGH
-> shortlist diversifiée
-> observabilité read-only
```

Le contrat API passe à `market-attention-radar-v2`. Sont supprimés du contrat courant : Public Attention, recherche Web, cache/TTL/cooldown/budget Web et leurs compteurs. Le cockpit affiche directement les caractéristiques, raisons d'intérêt, régime de liquidité, fraîcheur/qualité des données et erreurs Kraken.

Invariants : `informative_only=True`, aucune décision `BUY/SELL/HOLD`, aucun appel LLM/Web depuis le Radar, aucune dépendance vers Agent/Risk/Broker/Discovery, réutilisation du `CandleStreamService`, calculs uniquement sur bougies finalisées et non futures.

Voir `docs/39_BATCH_RADAR_KRAKEN_SANS_IA.md`.
