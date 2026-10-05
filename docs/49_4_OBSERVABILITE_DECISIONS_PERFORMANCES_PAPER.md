# Batch 49.4 — Observabilité des décisions et performances PAPER SPOT/PERP

## Statut

Patch proposé sur le HEAD GitHub `main` audité au démarrage :

```text
e7d605aa2b6393516c0ccd391cd4d11193c18671
docs: close batch 49.3 integration
```

Le parent fonctionnel de cette clôture documentaire est :

```text
d08cd31e6a795a8beb09530c2bc9a3f32f94fe35
feat: expose causal radar analytics context to agent
```

Le Batch 49.4 n'est pas intégré à GitHub dans cette livraison.

## Objectif

Rendre observable, de manière causale et read-only, ce qui se produit réellement entre :

```text
Agent
-> Risk
-> ExecutionIntent
-> fills PAPER
-> conséquences économiques persistées
```

La vue opérateur distingue `TOTAL`, `SPOT` et `PERPETUAL`, ainsi que chaque identité stricte `(symbol, market_type)`.

## Audit de l'existant

### Confirmé

`analytics/paper.py` est la source canonique pour :

- equity initiale/finale ;
- P&L brut et net ;
- frais, spread et slippage ;
- funding selon la convention signée existante ;
- drawdown ;
- exposition ;
- trades ;
- performance quotidienne.

`economic_history.py` est déjà une projection read-only au-dessus de ce rapport canonique et des audits persistés. Il apporte :

- P&L réalisé et latent lorsque disponible ;
- opérations économiques ;
- notionnel, turnover et ratios de coûts ;
- cadence de fills et changements de marché ;
- effets `OPEN / INCREASE / REDUCE / CLOSE` SPOT et LONG/SHORT PERPETUAL ;
- conservation des trajectoires multi-décisions grâce à `decision_results`.

`persistence/query.py` expose déjà les compteurs de décisions, les états Risk, les intents, fills et détails de chaque décision.

Le cockpit Historique consomme déjà `/api/v1/economic-history` et affiche les métriques économiques et l'audit Agent -> Risk -> PAPER.

### Obsolète

Aucun moteur économique existant n'est obsolète. Le Batch 49.4 ne remplace ni `PaperAnalyticsReport` ni `EconomicHistoryReport`.

### Manquant avant 49.4

- ventilation explicite TOTAL/SPOT/PERP ;
- funnel global décision -> Risk -> fill/trade ;
- agrégation par identité `(symbol, market_type)` ;
- indication structurée des métriques impossibles à attribuer honnêtement ;
- présentation compacte de ces données dans le cockpit.

## Options architecturales examinées

### Option A — étendre directement `PaperAnalyticsReport`

Écartée pour 49.4. Le moteur Analytics canonique doit rester centré sur le replay économique global ; lui ajouter les vues opérateur détaillées décision/Risk/marché mélangerait calcul canonique et projection descriptive.

### Option B — étendre uniquement `EconomicHistoryReport`

Possible, car il possède déjà une grande partie des faits nécessaires. Toutefois, ajouter toutes les ventilations directement dans son `summary` rendrait le contrat principal plus lourd et confondrait la synthèse historique avec une vue d'observabilité spécialisée.

### Option C — projection d'observabilité dédiée

**Retenue.** `PaperObservabilityReport` est calculé exclusivement à partir :

```text
EconomicHistoryReport canonique
+ CycleAuditDetail persistés
+ dernier PortfolioState durable disponible
```

La projection est attachée additivement à la réponse de `/api/v1/economic-history`. Elle ne crée donc ni nouvelle route ni nouvelle persistence.

### Option D — nouveau stockage / nouveau pipeline

Rejetée : les faits persistés actuels suffisent.

## Sources de vérité économiques

La hiérarchie reste :

```text
faits PAPER persistés
-> PaperAnalyticsReport
-> EconomicHistoryReport
-> PaperObservabilityReport (read-only)
```

`PaperObservabilityReport` ne recalcule jamais le P&L global, l'equity globale, le drawdown global ou l'exposition globale. Les valeurs `TOTAL` sont copiées depuis `EconomicHistoryReport.summary`. Le drawdown, le turnover, les cadences et la performance quotidienne déjà exposés par Analytics/Economic History restent canoniques et ne sont pas dupliqués dans un second moteur. Le cockpit Historique rend désormais le drawdown et l'exposition visibles dans son résumé principal.

Les métriques par marché/type sont uniquement dérivées de faits attribuables sans ambiguïté : opérations économiques, fills et portefeuille terminal durable.

## Contrat d'observabilité

### Ventilation TOTAL / SPOT / PERPETUAL

Chaque breakdown expose :

- P&L brut/net lorsqu'il est causalement disponible ;
- P&L réalisé ;
- P&L latent terminal lorsqu'il est attribuable ;
- frais, spread, slippage ;
- funding ;
- coûts d'exécution et coûts économiques ;
- montant total échangé ;
- nombre de trades et fills ;
- exposition terminale et ratio sur equity lorsque disponible.

### Métriques volontairement indisponibles

Les faits actuels ne permettent pas d'attribuer exactement la variation globale d'equity entre SPOT et PERPETUAL sur tout l'historique. Le contrat indique donc explicitement :

```text
SPOT.gross_pnl       = null
SPOT.net_pnl         = null
PERPETUAL.gross_pnl  = null
PERPETUAL.net_pnl    = null
```

La projection expose aussi ces limites dans `unavailable_metrics`.

Aucune différence résiduelle n'est répartie artificiellement.

## Funnel Agent -> Risk -> exécution

Le funnel expose séparément :

```text
Agent
  decision_count
  buy_count
  sell_count
  hold_count

Risk
  risk_allow_count
  risk_modify_count
  risk_reject_count

Execution
  execution_intent_count
  decisions_with_fill
  decisions_without_fill
  fill_count
  economic_trade_count
```

Une décision HOLD ou REJECT reste une décision mais ne devient pas un trade. Un cycle FAILED peut conserver des faits d'audit, mais ses fills ne sont pas considérés économiquement engagés.

## Ventilation par marché

Chaque ligne est identifiée par :

```text
(symbol, market_type)
```

Ainsi :

```text
BTC/USD SPOT
BTC/USD PERPETUAL
```

restent deux marchés différents même si le symbole canonique est identique.

Les métriques incluent décisions BUY/SELL/HOLD, Risk ALLOW/MODIFY/REJECT, décisions fillées/non fillées, trades, fills, montant, frais/spread/slippage/funding, coûts, P&L réalisé et exposition terminale lorsque attribuable.

## PERPETUAL

La projection réutilise les `EconomicOperation.economic_effect` existants :

```text
OPEN_LONG
INCREASE_LONG
REDUCE_LONG
CLOSE_LONG
OPEN_SHORT
INCREASE_SHORT
REDUCE_SHORT
CLOSE_SHORT
```

Les éventuels effets historiques `FLIP_*` restent seulement observables. Aucune règle d'exécution 49.1 n'est modifiée et aucun retournement direct n'est autorisé par 49.4.

## Funding et coûts

Convention conservée :

```text
funding_pnl < 0  -> coût
funding_pnl > 0  -> bénéfice

total_costs = fees + spread + slippage - funding_pnl
```

Au niveau `PERPETUAL`, le funding total vient de la valeur canonique `EconomicHistorySummary.funding_pnl`, qui inclut le funding réalisé dans les fills et le `cumulative_funding` encore porté par les positions ouvertes. Au niveau d'un marché PERPETUAL, la projection additionne le funding réalisé de ses opérations et le `cumulative_funding` de sa position terminale lorsqu'elle est disponible. Si cette attribution terminale n'est pas disponible, le funding et les coûts économiques par marché restent `null` plutôt que partiels.

Un funding SPOT non nul dans une opération durable est traité comme incohérence de données et provoque un échec explicite de la projection.

## Causalité

Le Batch 49.4 ne consulte aucun prix futur et ne rejoue aucune décision Agent.

Il n'effectue :

- aucune exclusion rétrospective de trades ;
- aucune sélection de période opportuniste ;
- aucune optimisation de paramètres ;
- aucune modification du ranking 47.5 ;
- aucune modification du contexte Agent 49.3 ;
- aucun retour de métriques dans le pipeline de décision.

L'ordre de sortie est déterministe : cycles triés par `(recorded_at, cycle_id)`, décisions par `decision_index`, marchés par `(symbol, market_type)`.

## API

Aucun nouvel endpoint.

La route existante reste :

```text
GET /api/v1/economic-history?paper_run_id=<uuid>
GET /api/v1/economic-history/export?paper_run_id=<uuid>
```

La réponse `EconomicHistoryResponse` reçoit additivement :

```text
observability: PaperObservabilityResponse | null
```

L'export JSON bénéficie automatiquement du même contrat.

## UI

Le cockpit Historique affiche, en plus de l'existant :

- trois cartes TOTAL / SPOT / PERPETUAL ;
- le funnel Agent -> Risk -> exécution ;
- une table par identité `(symbol, market_type)` ;
- les métriques volontairement indisponibles.

Le frontend ne recalcule aucun P&L ni coût : il formate uniquement les valeurs envoyées par le backend.

## Tests ajoutés

Backend :

- conservation du P&L global canonique ;
- ventilation SPOT/PERP sur scénario mixte ;
- distinction `BTC/USD SPOT` / `BTC/USD PERPETUAL` ;
- funding uniquement PERPETUAL ;
- HOLD décision sans trade ;
- REJECT sans fill ;
- multi-décisions ;
- distinction décisions/fills/trades ;
- ordre déterministe ;
- refus d'un funding SPOT incohérent ;
- contrat API additif.

Frontend :

- P&L SPOT/PERP indisponible conservé à `null` ;
- clé de marché distincte par `market_type` ;
- compatibilité avec une réponse historique sans projection 49.4.

## Validation réalisée dans l'environnement de livraison

```text
python -m py_compile des fichiers backend 49.4 : PASS
node --test --experimental-strip-types src/lib/economic-history.test.mjs : PASS — 3/3
```

Le test backend ciblé a été lancé mais sa collecte est impossible dans ce sandbox de patch isolé, qui ne contient pas le repository complet :

```text
ModuleNotFoundError: No module named 'ai_spot_trader.api.schemas'
```

Ce résultat n'est pas compté comme un échec fonctionnel ni comme un PASS. La validation doit être rejouée après extraction dans le repository complet.

## Validation locale attendue

```powershell
python -m pytest -q

Push-Location frontend
pnpm typecheck
pnpm test
Pop-Location

git diff --check
git status --short
```

## Hors périmètre

- LIVE ;
- authentification Kraken Futures privée ;
- ordres réels ;
- modification Agent/Risk/Broker ;
- nouvelle stratégie ;
- apprentissage automatique sur le P&L ;
- recalibration du ranking Radar/Analytics ;
- nouveau moteur P&L ;
- nouvelle persistence ;
- backtest opportuniste ou look-ahead.
