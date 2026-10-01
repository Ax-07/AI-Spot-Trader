# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 5bff583b47acf2b3a2a112611c40e0046c78cc3e
Commit     : feat: make market attention radar kraken-only
```

État revérifié le 01/10/2026 après intégration du Batch 39. Les Batches 38 et 39 sont **intégrés** dans ce HEAD.

## Batch 39 — Radar Kraken sans IA/Web

**État : intégré sur `main`.**

Le Batch 39 supprime complètement le chemin auxiliaire OpenAI/Web du Market Attention Radar et conserve uniquement l'analyse déterministe des données Kraken.

Architecture intégrée :

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

Le contrat API est `market-attention-radar-v2`. Sont supprimés du contrat courant : Public Attention, recherche Web, cache/TTL/cooldown/budget Web et leurs compteurs. Le cockpit affiche directement les caractéristiques, raisons d'intérêt, régime de liquidité, fraîcheur/qualité des données et erreurs Kraken.

Invariants : `informative_only=True`, aucune décision `BUY/SELL/HOLD`, aucun appel LLM/Web depuis le Radar, aucune dépendance vers Agent/Risk/Broker/Discovery, réutilisation du `CandleStreamService`, calculs uniquement sur bougies finalisées et non futures.

Voir `docs/39_BATCH_RADAR_KRAKEN_SANS_IA.md`.
