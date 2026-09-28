# 30 — Batch Market Attention Activity Robustness

Date : 2026-09-28
Repository : `Ax-07/AI-Spot-Trader`
Branche : `main`

## 1. Resynchronisation

Base GitHub auditée avant modification :

```text
354e8cf083b2c45233c45e019bdaa7f4bf6b1d96
feat: improve market attention observability
```

Aucun commit intermédiaire n'était présent entre la référence annoncée et le HEAD GitHub vérifié.

`docs/00_ETAT_ACTUEL.md` était en retard : il mentionnait encore `3c609c7` et décrivait l'observabilité du Batch 29 comme patch proposé alors que `354e8cf` l'intègre déjà.

## 2. Symptôme de départ

Observation locale fournie avant le batch :

```text
Catalogue          1633
Marchés frais       360
Scannés refresh     120
Candidats             0
Recherches web         0

AVAILABLE              0
PARTIAL              158
STALE                  0
ERROR                202

NORMAL                 0
ELEVATED               0
ACCELERATING           0
VERY_HIGH              0
UNKNOWN              360
```

Le problème n'était donc pas un manque de candidats au-dessus des seuils : aucun ratio exploitable n'était produit.

Les seuils `1.40 / 1.75 / 2.50` ne sont pas modifiés par ce batch.

## 3. Causes confirmées par audit

### 3.1 SPOT — `PARTIAL` provoqué par une continuité trop stricte

Le `MarketActivityAnalyzer` intégré exigeait une suite 5m parfaitement contiguë via `_is_contiguous(...)` avant de calculer un horizon.

Le contrat Kraken SPOT documente que les données OHLCVT ne contiennent des entrées que pour les intervalles où des trades ont eu lieu. Un intervalle absent peut donc signifier « aucun trade » et non « donnée fournisseur cassée ».

Conséquence confirmée : sur un marché peu liquide, un seul intervalle 5m sans trade faisait basculer l'horizon en incomplet, puis le snapshot en `PARTIAL`, même lorsque la fenêtre temporelle était autrement couverte.

### 3.2 PERPETUAL — mauvaise sémantique de candles pour un Radar de volume

L'historique PERPETUAL intégré demandait :

```text
/api/charts/v1/mark/<venue_symbol>/5m
```

alors que le Radar mesure l'activité par **volume échangé**.

L'API Kraken Futures distingue explicitement les tick types `mark` et `trade`. Les candles `mark` décrivent le mark price et ne sont pas la source correcte pour mesurer le volume réellement échangé.

Le provider canonique est donc corrigé vers :

```text
/api/charts/v1/trade/<venue_symbol>/5m
```

avec une fenêtre temporelle explicite `from/to`.

### 3.3 Les `202 ERROR` historiques ne pouvaient pas être attribués précisément avant ce batch

Le Batch 29 exposait seulement le compteur global `ERROR`; le `error_type` existait par snapshot mais n'était pas agrégé dans l'overview/cockpit.

Il serait donc incorrect d'affirmer rétrospectivement que les `202 ERROR` provenaient tous d'un seul type d'exception.

Le batch ajoute précisément la ventilation bornée suivante :

```text
KrakenConnectionError
KrakenPayloadError
UnknownKrakenSymbolError
CandleValidationError
Other
```

La première exécution locale après extraction permettra d'identifier factuellement la répartition réelle des erreurs historiques/récurrentes.

## 4. Correction SPOT : fenêtre volume-only, sans candle synthétique

La correction est volontairement conservatrice.

Pour SPOT seulement, le Radar active explicitement une sémantique :

```text
intervalle 5m absent à l'intérieur d'une fenêtre réellement couverte
=> volume de l'intervalle = 0
```

Cette logique :

- ne crée aucun objet `Candle` synthétique ;
- n'invente aucun `open`, `high`, `low`, `close` ;
- ne remplit pas silencieusement un début d'historique tronqué ;
- ne remplit pas une discontinuité mal alignée ou dupliquée ;
- conserve les métriques prix uniquement à partir des vraies observations reçues ;
- reste causale et ne lit aucune candle postérieure à `observed_at`.

Un bord de fenêtre non prouvé reste `INSUFFICIENT_HISTORY` / `PARTIAL`.

Une discontinuité non justifiée reste `DISCONTINUOUS_HISTORY` / `PARTIAL`.

## 5. Correction PERPETUAL

`KrakenCandleProvider._perpetual_history()` conserve le même pipeline canonique `CandleStreamService`, mais :

- utilise `trade/<venue_symbol>/<resolution>` ;
- utilise le `venue_symbol` issu du mapping dérivés canonique ;
- demande une fenêtre `from/to` bornée à la profondeur nécessaire ;
- conserve `KrakenConnectionError` pour les erreurs transport/HTTP ;
- conserve `KrakenPayloadError` pour les payloads invalides ;
- conserve `UnknownKrakenSymbolError` pour un mapping introuvable après refresh ;
- ne transforme aucune erreur technique en `PARTIAL`.

Une vraie discontinuité des trade candles PERPETUAL reste stricte : elle n'est pas assimilée automatiquement à un intervalle sans trade.

## 6. Qualité de données explicite

Les snapshots Market Activity exposent désormais une qualité bornée :

```text
COMPLETE
NO_TRADE_GAPS
INSUFFICIENT_HISTORY
DISCONTINUOUS_HISTORY
TECHNICAL_ERROR
```

Les horizons exposent également :

```text
no_trade_interval_count
unexplained_gap_count
```

Cela permet de distinguer :

- snapshot exploitable continu ;
- snapshot exploitable malgré des intervalles SPOT sans trade ;
- historique trop court/tronqué ;
- vraie discontinuité non expliquée ;
- erreur technique.

## 7. Observabilité overview / cockpit

L'overview ajoute :

```text
activity_data_quality_counts
activity_error_counts
activity_market_type_status_counts
```

Le cockpit garde le panneau compact et affiche en plus :

```text
Par marché
SPOT        ... disponibles · ... partiels · ... périmés · ... erreurs
PERPETUAL   ... disponibles · ... partiels · ... périmés · ... erreurs

Erreurs activité
KrakenConnectionError       ...
KrakenPayloadError          ...
UnknownKrakenSymbolError    ...
CandleValidationError       ...
Other                       ...
```

Seules les catégories d'erreur non nulles sont affichées.

Le badge suivant reste visible :

```text
INFORMATIF — N’INFLUENCE PAS LE TRADING
```

## 8. Candidat / web inchangés

Le chemin reste :

```text
Market Activity
    ↓
AVAILABLE + état inhabituel
    ↓
Candidate
    ↓
OpenAI web_search
```

Les nouveaux diagnostics :

- ne deviennent jamais candidats ;
- ne déclenchent jamais de recherche web ;
- ne sont jamais fournis à l'Agent ;
- ne modifient pas Market Discovery ;
- ne modifient pas Risk ;
- ne modifient pas Broker ;
- ne modifient aucun ordre.

## 9. Seuils et périmètre

Inchangés :

```text
ELEVATED     1.40
ACCELERATING 1.75 + accélération 0.25
VERY_HIGH    2.50 + accélération 0.50
```

Aucun changement : Agent, prompts stratégiques, Risk Engine, Broker, persistence SQL, Market Discovery, budget web, logique d'ordre, API X/Reddit/LunarCrush.

## 10. Fichiers modifiés / créés

Backend :

```text
backend/src/ai_spot_trader/market/attention.py
backend/src/ai_spot_trader/integrations/kraken/candles.py
backend/tests/test_market_attention_activity_robustness.py
backend/tests/test_kraken_candle_activity_history.py
```

Frontend :

```text
frontend/src/lib/market-attention.ts
frontend/src/lib/market-attention.test.mjs
frontend/src/components/cockpit/market-attention-dock.tsx
```

Documentation :

```text
docs/00_ETAT_ACTUEL.md
docs/10_DECISIONS_ET_CHANGELOG.md
docs/30_BATCH_MARKET_ATTENTION_ACTIVITY_ROBUSTNESS.md
```

`docs/01_PROJECT_MASTER.md`, `docs/02_ARCHITECTURE_TECHNIQUE.md` et `docs/09_ROADMAP_DEVELOPPEMENT.md` ont été audités sans changement nécessaire : le batch ne change pas les invariants d'architecture ni la roadmap stratégique. `docs/10_DECISIONS_ET_CHANGELOG.md` est corrigé pour remettre sa référence courante et les ADR Radar en cohérence avec le HEAD déjà intégré, puis documenter le Batch 30.

## 11. Tests réellement exécutés par ChatGPT

### Backend

Compilation Python :

```text
backend/src/ai_spot_trader/market/attention.py                         PASS
backend/src/ai_spot_trader/integrations/kraken/candles.py            PASS
backend/tests/test_market_attention_activity_robustness.py            PASS py_compile
backend/tests/test_kraken_candle_activity_history.py                  PASS py_compile
```

Harness pytest isolé avec les contrats minimaux nécessaires :

```text
test_market_attention_activity_robustness.py   8 passed
test_kraken_candle_activity_history.py         3 passed
```

Ces harness exécutent le code livré mais ne remplacent pas la suite complète du repository.

### Frontend

Test isolé du mapping :

```text
node --experimental-strip-types --test market-attention.test.mjs
7 passed
```

TypeScript ciblé sur la librairie :

```text
tsc market-attention.ts --noEmit --target ES2022 --module ESNext --moduleResolution Bundler --strict
PASS
```

## 12. Validation locale utilisateur

Validation exécutée le 2026-09-28 sur la copie locale réelle du repository :

```text
backend / pytest -q     PASS à 100 %
frontend / pnpm test    46/46 PASS
frontend / pnpm lint    PASS
frontend / pnpm typecheck PASS
frontend / pnpm build   PASS
git diff --check        PASS
```

Avertissements non bloquants observés :

- deux dépréciations FastAPI/Starlette/AnyIO dans la suite backend ;
- avertissement Node `MODULE_TYPELESS_PACKAGE_JSON` pendant les tests frontend ;
- avertissements Git LF -> CRLF sous Windows lors de `git diff --check`.

`git status --short` confirme les dix fichiers du batch et conserve `trades_9h_analysis.json` comme fichier local non suivi et hors périmètre.

## 13. Validation fonctionnelle runtime restante

Vérification recommandée : laisser le Radar effectuer plusieurs rotations de `scan_limit`, puis contrôler :

```text
AVAILABLE > 0
PARTIAL explicable par la qualité de données
ERROR ventilé par type
SPOT/PERPETUAL séparés
NORMAL ou états inhabituels réels > 0 lorsque des ratios existent
```

Le succès du batch n'exige aucun candidat.
