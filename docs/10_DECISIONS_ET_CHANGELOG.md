# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les éléments nécessaires à la reprise.

## Principes actifs

Un seul Agent stratégique, Risk autorité finale, aucune sortie LLM directe vers Broker/Kraken, SPOT sans vente d'actif non détenu, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Market Attention Radar reste strictement observationnel et ne prend aucune décision de trading.

## Référence courante

```text
HEAD GitHub audité : 2aaff09b01300008e63eaadbca242817bcb4ce28
Commit              : docs: mark batch 39 as integrated
Batch 39            : intégré
Batch 40            : patch proposé/local non intégré
```

## Changelog — 2026-10-01 — Batch 40 Microstructure Kraken

- ajout d'un lecteur REST public Kraken SPOT pour `/Depth` et `/Trades` ;
- ajout d'un analyseur microstructure pur et déterministe ;
- calcul meilleur bid/ask, mid, spread absolu/bps ;
- calcul profondeur base/quote et bandes `±5/10/25/50 bps` ;
- calcul déséquilibre bid/ask ;
- calcul compte/volume/taille moyenne/médiane/cadence des trades ;
- comparaison d'une fenêtre récente de 60 s à une baseline précédente de 240 s dans une fenêtre totale de 300 s ;
- utilisation du côté fournisseur uniquement lorsqu'il est disponible ; aucune heuristique d'agresseur ;
- slippage théorique pour `100/500/1000/5000` unités de devise cotée ;
- sous-scan microstructure SPOT rotatif et borné à 24 marchés par refresh par défaut ;
- cache microstructure fail-soft ;
- nouveau contrat API `market-attention-radar-v3` ;
- cockpit enrichi sans transformer le Radar en terminal d'exécution ;
- aucune modification de l'Agent, du Risk Engine ou du Broker.

## ADR-298 — Microstructure comme enrichissement, pas comme second Radar

**PROPOSÉ Batch 40.**

`MicrostructureMarketAttentionRadar` réutilise `MarketAttentionRadar` Batch 39 et enrichit ses snapshots. Le pipeline OHLCV canonique n'est pas dupliqué.

## ADR-299 — REST snapshots bornés avant streaming microstructure

**PROPOSÉ Batch 40.**

Le Batch 40 utilise les endpoints publics REST L2/trades avec limites et cache court. Aucun nouveau WebSocket complexe n'est introduit sans besoin mesuré.

## ADR-300 — Unités de slippage explicites

**PROPOSÉ Batch 40.**

Les notionnels théoriques sont exprimés dans la devise cotée. Un marché `BTC/USD` utilise donc des USD ; un marché `BTC/EUR` utilise des EUR. Aucune conversion FX implicite n'est autorisée.

## ADR-301 — Côté Kraken sans inférence d'agresseur

**PROPOSÉ Batch 40.**

Le côté `b/s` fourni par Kraken peut alimenter une description acheteur/vendeur. Si la donnée est absente ou inconnue, les métriques directionnelles correspondantes restent `None`.

## ADR-302 — Microstructure additive et fail-soft

**PROPOSÉ Batch 40.**

Une indisponibilité du carnet ou des trades ne invalide pas l'OHLCV. Le statut/qualité microstructure est exposé séparément et ne déclenche Agent, Risk ou Broker.

## ADR-303 — Contrat API Radar v3

**PROPOSÉ Batch 40.**

`market-attention-radar-v3` ajoute spread, profondeur, déséquilibre, activité des trades, slippage, qualité/fraîcheur microstructure et diagnostics à la structure v2.

## Points explicitement non décidés

- utilisation du Radar comme contexte de l'Agent stratégique ;
- réaction stratégique intra-bougie ;
- streaming WebSocket L2/trades ;
- LIVE.
