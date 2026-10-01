# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 6d263be5edb589723101c32065ad68434b0b64f1
Commit     : feat: enrich market attention with kraken microstructure
```

État revérifié le 01/10/2026 lors de la clôture documentaire du Batch 40. Le Batch 40 est intégré sur GitHub `main` dans `6d263be5edb589723101c32065ad68434b0b64f1` (`feat: enrich market attention with kraken microstructure`).

## Batch 40 — Microstructure Kraken

**État : intégré sur GitHub `main` au HEAD `6d263be5edb589723101c32065ad68434b0b64f1`.**

Le Batch 40 enrichit le Radar déterministe sans remplacer le pipeline OHLCV canonique :

```text
Kraken SPOT public
├── CandleStreamService / OHLCV 5m finalisé
├── REST /public/Trades borné
└── REST /public/Depth L2 borné
        ↓
calculs déterministes
        ↓
spread / profondeur / déséquilibre
intensité des trades / côté fournisseur si connu
slippage théorique sans ordre
        ↓
Market Attention Radar v3
```

Le Radar reste `informative_only=True`, sans appel OpenAI, sans recherche Web, sans dépendance Agent/Risk/Broker et sans construction ou envoi d'ordre. La microstructure nouvelle s'applique aux marchés SPOT ; le support PERPETUAL historique du Radar OHLCV n'est pas étendu par ce batch.

Le contrat API intégré est `market-attention-radar-v3`. Les données microstructure sont fail-soft : l'OHLCV valide reste disponible lorsqu'un carnet ou des trades sont indisponibles.

Voir `docs/40_BATCH_MICROSTRUCTURE_KRAKEN.md`.
