# 43.1 — Correctif du filtre Volume 24h du Market Attention Radar

## Statut

```text
Base auditée : 3b8bc6bcb83604cb20eb5ee27ef1b95fcc4210da
Branche      : main
État         : patch proposé, non intégré
Contrat      : market-attention-radar-v6
```

## Symptôme

Dans le cockpit, le Radar pouvait afficher plusieurs candidats avec `Volume 24h = Tous`, puis aucun après activation d'un seuil tel que `>= 100 k$`.

## Cause confirmée dans l'implémentation

Trois facteurs se cumulaient :

1. `SPOT` non coté directement en `USD` renvoyait `volume_24h_usd = None` ;
2. `PERPETUAL` renvoyait également `None` ;
3. tout `None` était exclu fail-closed dès qu'un seuil était actif, sans diagnostic détaillé dans le snapshot global.

Ce comportement explique qu'une shortlist composée majoritairement de marchés non-USD/PERP puisse disparaître en scope `ALL`.

Un second défaut SPOT/USD a été identifié : la fenêtre était construite à partir de `as_of - 24h`. Si `as_of` contenait des secondes ou microsecondes après une frontière 5m, la première candle finalisée de la fenêtre pouvait être exclue. La valeur restait causale mais était sous-comptée, ce qui pouvait faire échouer une borne proche du seuil.

## Correction

### Fenêtre SPOT/USD

La fin de fenêtre est maintenant la `close_time` de la dernière candle 5m finalisée connaissable à `as_of` :

```text
window_end   = dernière clôture 5m finalisée <= as_of
window_start = window_end - 24h
```

Avec une série continue, la fenêtre contient donc exactement 288 intervalles 5m.

Aucune candle postérieure à `as_of` n'est utilisée.

### Mesure typée et diagnostics

Le backend distingue :

```text
AVAILABLE
BELOW_THRESHOLD
UNKNOWN_UNSUPPORTED_QUOTE
UNKNOWN_UNSUPPORTED_MARKET_TYPE
UNKNOWN_INSUFFICIENT_HISTORY
UNKNOWN_TECHNICAL_ERROR
```

Les compteurs sont exposés dans :

```text
MarketAttentionOverviewV6.volume_24h_status_counts
```

`BELOW_THRESHOLD` signifie qu'une valeur USD fiable existe mais est trop faible. Les statuts `UNKNOWN_*` signifient qu'aucune valeur USD fiable n'est prétendue.

### Règle de filtrage

```text
seuil désactivé => UNKNOWN n'exclut pas à lui seul le marché
seuil actif     => seul AVAILABLE avec value_usd >= minimum est accepté
```

La borne reste inclusive.

## Cas volontairement UNKNOWN

### SPOT non-USD

Aucune équivalence implicite n'est ajoutée :

```text
USDT != USD par hypothèse
USDC != USD par hypothèse
EUR  != USD par hypothèse
GBP  != USD par hypothèse
```

Une future conversion multi-devise devra disposer d'une source FX explicite, causale et testée.

### PERPETUAL

Le pipeline Kraken Futures transporte actuellement le champ `volume` des candles de trade, tandis que la métadonnée de contrat (`contract_size`) vit dans le registre des instruments. Le correctif ne relie pas arbitrairement ces deux éléments pour fabriquer un notionnel USD.

Tant que l'unité exacte du volume de candle et la formule de notionnalisation ne sont pas démontrées de bout en bout dans ce pipeline, `PERPETUAL` reste `UNKNOWN_UNSUPPORTED_MARKET_TYPE` pour ce filtre.

## Frontend

Le cockpit intégré indique déjà sous le filtre Volume 24h que le notionnel est calculé lorsque prouvable et que `UNKNOWN` est exclu lorsqu'un seuil est actif. Le correctif ne masque donc pas le problème par une logique frontend et conserve le backend comme source de vérité.

L'observabilité détaillée est ajoutée au contrat backend. Son affichage graphique détaillé pourra être enrichi séparément sans modifier la sémantique du filtre.

## Tests ajoutés/adaptés

La suite Batch 43 couvre maintenant explicitement :

- fenêtre 24h ancrée sur la dernière clôture finalisée ;
- absence de look-ahead ;
- historique insuffisant ;
- borne minimum inclusive ;
- `SPOT` non-USD => raison explicite ;
- `PERPETUAL` => raison explicite ;
- comptage valeur disponible / sous seuil / raisons `UNKNOWN` ;
- régression `market_scope = ALL`, sans seuil puis `>= 100 k$`, avec conservation d'un `SPOT/USD` valide à 144 k$ ;
- ordre des filtres avant enrichissements coûteux ;
- API filtres existante.

## Tests exécutés par ChatGPT sur le patch livré

Dans l'environnement de génération, le repository complet et ses dépendances n'étaient pas matérialisés. Ont réellement été exécutés :

```text
python -m py_compile backend/src/ai_spot_trader/market/attention_filters.py
python -m py_compile backend/tests/test_market_attention_batch43_filters.py
```

Résultat : PASS.

Un test isolé exécutant directement la fonction corrigée `_causal_spot_volume_24h_usd` a également validé :

- 288 candles finalisées avec `as_of` décalé de 37 secondes => volume complet conservé ;
- historique de 12h => `None` ;
- candle future à très fort volume => ignorée.

Résultat : PASS.

`ruff` n'était pas installé dans l'environnement de génération.

## Validation restant à exécuter localement

Après extraction du ZIP à la racine du repository :

```powershell
cd E:\AI-Spot-Trader\backend
pytest -q

cd E:\AI-Spot-Trader\frontend
pnpm typecheck
pnpm test

cd E:\AI-Spot-Trader
git diff --check
git status --short
```

Ne pas considérer le patch intégré tant que ces validations locales n'ont pas été exécutées et que les modifications n'ont pas été commit/push explicitement par l'utilisateur.
