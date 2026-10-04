# 00 — État actuel

## Référence intégrée GitHub

```text
Repository          : Ax-07/AI-Spot-Trader
Branche             : main
HEAD GitHub observé : 45d41b7
Commit              : feat: move market structure before radar shortlist
```

Le **Batch 45 est intégré** dans `main` via `45d41b7`. Les documents qui le présentaient encore comme un patch proposé étaient obsolètes et sont réconciliés par le Batch 46.

## État intégré — Batch 45

Le Market Attention Radar reste `market-attention-radar-v6`, strictement informatif, déterministe, causal et read-only.

Pipeline intégré :

```text
catalogue Kraken
-> scope SPOT / PERPETUAL / ALL
-> métadonnées / filtre capitalisation
-> rotation OHLCV et volume 24h
-> activité / tendance / liquidité / microstructure canonique
-> pool Structure borné et rotatif
-> cache Structure causal
-> filtres tendance / Structure
-> shortlist finale bornée
-> cockpit
```

La Market Structure utilise toujours les timeframes natives `5m / 15m / 1h / 4h`, des candles finalisées et des pivots confirmés. Les événements `BOS / CHOCH` peuvent compléter l'attention sans devenir une décision de trading. Les filtres Structure restent fail-closed pour les données `UNKNOWN` ou non couvertes.

## Batch 46 — patch proposé, non intégré

Le Batch 46 remplace la dépendance principale aux seuils universels de ratio d'activité par une baseline robuste propre à chaque marché et horizon :

```text
baseline = médiane des périodes historiques causales
MAD      = médiane(|x - baseline|)
dispersion robuste = 1,4826 * MAD
score adaptatif = (courant - baseline) / dispersion robuste
```

La baseline cible par défaut passe de `6` à `12` périodes. Sur H4, le défaut utilise 12 périodes avec `48 * (12 + 2) = 672` candles M5. Le correctif 46.1 conserve toutefois un plancher de compatibilité à 6 périodes : les anciennes configurations/fixtures autour de 420 candles M5 restent exploitables avec 6 périodes H4 au lieu de basculer artificiellement en `PARTIAL`.

Si `MAD == 0`, aucun pseudo-score infini n'est produit : la méthode devient explicitement `LEGACY_RATIO_FALLBACK` lorsque le ratio historique est exploitable, sinon `UNAVAILABLE`.

Le patch reste additif au contrat v6 et ne modifie ni Agent, ni Risk Engine, ni Broker, ni exécution PERP, ni Market Structure Batch 45.

## Validation connue

Batch 45 — validations connues du patch avant intégration :

```text
Python py_compile des fichiers Python modifiés : PASS
frontend market-attention.test.mjs ciblé       : PASS — 16/16
typecheck TypeScript ciblé market-attention.ts : PASS
typecheck cockpit ciblé avec stubs              : PASS
```

L'intégration GitHub `45d41b7` confirme la présence du code, mais ne permet pas d'inventer une validation complète non observée.

Batch 46 — validations exécutées par ChatGPT sur le patch préparé :

```text
Python py_compile backend ciblé                 : PASS
exécution helpers robustes extraits du code       : PASS
frontend market-attention.test.mjs ciblé       : PASS — 19/19
typecheck TypeScript ciblé market-attention.ts : PASS
parse TypeScript/TSX ciblé cockpit              : PASS
```

Validation locale de la première livraison Batch 46 : frontend `pnpm typecheck` PASS, `pnpm test` PASS 65/65, `git diff --check` sans erreur ; backend `pytest -q` a révélé 7 régressions de shortlist liées à l'exigence rigide de 12 périodes H4 sur des fixtures historiques de 404–420 candles. Le correctif 46.1 traite cette compatibilité ; la suite backend complète doit être relancée après extraction du ZIP correctif.
