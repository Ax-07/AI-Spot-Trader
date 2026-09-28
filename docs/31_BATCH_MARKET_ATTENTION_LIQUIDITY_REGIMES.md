# Batch 31 — Market Attention : notionnel USD et régimes de liquidité

## Statut

Patch proposé, non intégré à GitHub au moment de la préparation.

Référence GitHub auditée :

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 354e8cf083b2c45233c45e019bdaa7f4bf6b1d96
Commit     : feat: improve market attention observability
```

Le Batch 30 `Market Attention Activity Robustness` est présent localement mais non intégré à GitHub. Un premier ZIP Batch 31, construit depuis le seul état intégré GitHub, a écrasé deux contrats locaux du Batch 30 (`ActivityDataQuality` côté backend et les diagnostics `activityErrorEntries` côté frontend).

Le correctif de fusion documenté ici repart du bundle local fourni après cet incident et réunit explicitement Batch 30 + Batch 31 :

- gaps SPOT sans trade conservés comme zéro-volume uniquement dans une fenêtre réellement couverte ;
- PERPETUAL toujours strict sur les discontinuités ;
- qualité de données et compteurs d'erreurs du Batch 30 restaurés ;
- notionnels USD et régimes de liquidité du Batch 31 conservés ;
- provider Futures `trade/...` du Batch 30 laissé intact.

## Objectif

Conserver le caractère relatif du Radar tout en ajoutant un second axe descriptif : l'importance économique de l'activité lorsque cette importance peut être normalisée en USD sans ambiguïté.

Le Radar reste observation-only. Il ne produit aucun BUY/SELL/HOLD et n'alimente ni l'Agent, ni Market Discovery, ni le Risk Engine, ni le Broker.

## Audit des données Kraken

### SPOT

Les données publiques Kraken décrivent la quantité d'un trade SPOT comme une quantité de l'actif de base. Pour un marché canonique directement coté en USD, le pipeline de chandelles expose donc une quantité de base et un prix en USD.

Le modèle `Candle` canonique ne transporte actuellement pas le VWAP Kraken. Le Batch 31 ne crée pas un second pipeline OHLCV et ne modifie pas le contrat canonique de `Candle` dans ce patch. Le notionnel SPOT/USD est donc calculé comme une estimation bornée : somme, pour chaque chandelle 5m canonique de l'horizon, de `volume_base × close_usd`.

La méthode est explicitement exposée par :

```text
SPOT_BASE_VOLUME_X_5M_CLOSE_ESTIMATE
```

Cela évite de masquer la nature estimative du montant.

### SPOT non USD

Aucune conversion secondaire n'est inventée. Un marché comme `ASSET/EUR`, `ASSET/BTC` ou `ASSET/USDT` conserve ses métriques relatives, mais ses champs notionnels USD restent `null` tant qu'un mécanisme canonique de conversion n'est pas défini.

### PERPETUAL

Kraken expose des chandelles Futures `trade` distinctes des chandelles `mark`, ainsi que des métadonnées de contrats et des trades avec taille/notionnel. Le Batch 30 local corrige déjà, d'après l'état fourni, le choix des chandelles d'activité Futures.

Le Batch 31 n'infère pas que `Candle.volume × close` représente un notionnel USD PERPETUAL. Tant que l'unité exacte du volume canonique après le Batch 30 n'est pas reliée explicitement au `contract_size` de l'instrument dans le Radar, les champs notionnels PERPETUAL restent `null` et le régime de liquidité est `UNKNOWN`.

Cette limitation est volontaire : mieux vaut une absence explicite qu'un faux montant USD.

## Modèle de données

Chaque `ActivityHorizonSnapshot` ajoute :

```text
current_notional_usd
baseline_notional_usd
notional_delta_usd
notional_method
```

avec :

```text
notional_delta_usd = current_notional_usd - baseline_notional_usd
```

Les métriques existantes restent inchangées :

```text
current_volume
previous_comparable_volume
baseline_volume
volume_ratio
volume_change
volume_acceleration
```

Chaque `MarketActivitySnapshot` ajoute :

```text
liquidity_regime
liquidity_reference_usd
```

## Référence de liquidité

Le régime ne dépend pas du spike courant.

Pour chaque horizon disposant d'une baseline notionnelle USD, la baseline est ramenée à un équivalent horaire :

```text
baseline_hourly_equivalent = baseline_notional_usd × 3600 / horizon_seconds
```

La référence du marché est la médiane des équivalents horaires disponibles sur `5m / 15m / 1h / 4h`.

Cette construction :

- utilise la baseline historique et non le volume courant ;
- réduit la sensibilité à un horizon isolé ;
- rend les horizons comparables ;
- reste descriptive.

## Régimes de liquidité

Vocabulaire :

```text
MICRO
LOW
MEDIUM
HIGH
VERY_HIGH
UNKNOWN
```

La classification est relative à la population fraîche observée, séparée par `MarketType`.

La position percentile moyenne est utilisée en cas d'égalité, puis répartie en cinq bandes de distribution. Aucun seuil USD fixe n'est codé.

`UNKNOWN` signifie que le Radar ne dispose pas d'une référence USD fiable ; cela n'empêche jamais le marché de devenir candidat via ses métriques relatives.

## Shortlist

Les seuils d'activité restent strictement inchangés :

```text
ELEVATED      : 1.40
ACCELERATING : 1.75 + accélération 0.25
VERY_HIGH     : 2.50 + accélération 0.50
```

L'éligibilité reste fondée sur :

- `status == AVAILABLE` ;
- état `ELEVATED`, `ACCELERATING` ou `VERY_HIGH`.

Le tri relatif `_activity_sort_key` reste inchangé.

La sélection bornée est ensuite diversifiée :

1. classement global existant ;
2. meilleur candidat de chaque régime disponible ;
3. remplissage des places restantes selon le classement global.

Il n'existe pas de quota fixe par régime. Un petit marché avec une anomalie forte peut donc rester visible, sans laisser tous les premiers rangs être monopolisés par une série de micro-marchés au notionnel minuscule.

## Cockpit

Chaque candidat peut afficher de manière compacte :

- régime de liquidité ;
- ratio 5m ;
- notionnel USD 5m ;
- delta USD 5m vs baseline ;
- référence de liquidité dans le détail.

Formatage prévu :

```text
850 $
12.4 k$
3.8 M$
1.2 B$
```

Une valeur indisponible reste `—`.

Le badge suivant reste visible :

```text
INFORMATIF — N’INFLUENCE PAS LE TRADING
```

## Invariants préservés

- un seul Agent IA stratégique ;
- Radar observation-only ;
- aucune donnée Radar fournie à l'Agent ;
- aucune influence sur Market Discovery ;
- aucune influence sur Risk Engine ;
- aucune influence sur Broker/order flow ;
- aucun BUY/SELL/HOLD produit par le Radar ;
- aucun second pipeline OHLCV ;
- `CandleStreamService` reste canonique ;
- PAPER inchangé ;
- seuils relatifs inchangés ;
- aucune faible liquidité exclue par principe.

## Tests ajoutés

Backend :

- notionnel SPOT/USD courant, baseline et delta ;
- faible volume avec fort ratio ;
- marché non USD => notionnel indisponible ;
- PERPETUAL => notionnel indisponible tant que la sémantique canonique n'est pas reliée au contrat ;
- seuils relatifs inchangés ;
- quantiles de liquidité déterministes ;
- petit marché toujours candidat ;
- diversification de shortlist ;
- absence de dépendance Agent/Risk/Broker/Market Discovery.

Frontend :

- formatage compact USD ;
- delta USD signé ;
- `null`/valeur invalide => `—`.

## Validation dans l'environnement ChatGPT

Après réception du bundle local Batch 30 + Batch 31, le correctif de fusion a été testé sur les contrats ciblés.

Exécuté :

```text
python -m py_compile backend/src/ai_spot_trader/market/attention.py
pytest -q tests/test_market_attention_activity_robustness.py tests/test_market_attention_liquidity.py
node --experimental-strip-types --test frontend/src/lib/market-attention.test.mjs frontend/src/lib/market-attention-liquidity.test.mjs
TypeScript transpile/syntax check : market-attention.ts + market-attention-dock.tsx
```

Résultats dans l'environnement ChatGPT :

```text
Backend ciblé : 16 passed
Frontend ciblé : 9 passed
TypeScript syntax/transpile : OK
```

Les tests backend ciblés ont été exécutés dans un harnais minimal reproduisant les contrats de domaine nécessaires, car le repository complet et son environnement Python local ne sont pas montés dans l'environnement ChatGPT. Ils valident la compatibilité fonctionnelle des contrats Batch 30 + Batch 31, mais ne remplacent pas le `pytest -q` complet à exécuter localement.

## Validation locale requise

Après intégration du patch sur le working tree contenant le Batch 30 :

```powershell
cd backend
pytest -q

cd ..\frontend
pnpm test
pnpm lint
pnpm typecheck
pnpm build

cd ..
git diff --check
git status --short
```

## Suite recommandée

Une évolution séparée pourra rendre le notionnel PERPETUAL disponible lorsque le Radar recevra explicitement une métadonnée canonique reliant :

```text
volume de chandelle trade
× contract_size / unité de contrat
× prix
→ notionnel USD fiable
```

Cette évolution ne doit pas être improvisée dans le présent batch.
