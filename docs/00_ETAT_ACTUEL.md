# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 2aaff09b01300008e63eaadbca242817bcb4ce28
Commit     : docs: mark batch 39 as integrated
```

État revérifié le 01/10/2026 au démarrage du Batch 40. Le commit applicatif principal du Batch 39 reste `5bff583b47acf2b3a2a112611c40e0046c78cc3e` (`feat: make market attention radar kraken-only`) ; `2aaff09` est le HEAD GitHub documentaire qui marque cette intégration.

## Batch 40 — Microstructure Kraken

**État : patch proposé/local, non intégré tant que l'utilisateur ne l'a pas validé puis commit/push.**

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

Le contrat API proposé devient `market-attention-radar-v3`. Les données microstructure sont fail-soft : l'OHLCV valide reste disponible lorsqu'un carnet ou des trades sont indisponibles.

Voir `docs/40_BATCH_MICROSTRUCTURE_KRAKEN.md`.
