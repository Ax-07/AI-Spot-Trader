# 09 — Roadmap de développement

## Référence de reprise

```text
Repository                  : Ax-07/AI-Spot-Trader
Branche                     : main
HEAD GitHub clôture 49.4     : 2e552cbaf1b8ffcae9244c1fb472f1ee8fb0f193
Batch 49.3 fonctionnel      : intégré via d08cd31
Clôture documentaire 49.3   : e7d605a
Batch 49.4                  : intégré via 2e552cb
Batch 49.1                  : intégré via 3194fce
Batch 49.2                  : intégré via f0d4f94
Batch 48 fonctionnel        : intégré via ebb664c
Batch 47.5                  : intégré via d988de4
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve :

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- Risk Engine comme autorité finale ;
- backend indépendant du frontend ;
- PAPER avant tout LIVE ;
- exécution PAPER SPOT + PERPETUAL Kraken linéaire ;
- SPOT sans short/levier/marge ;
- LONG/SHORT PERPETUAL autorisés sous contrôle Risk ;
- FUTURE daté non exécutable ;
- aucune sortie LLM directement exécutable ;
- aucun secret versionné ;
- aucune optimisation post-hoc.

Le Market Attention Radar est un **outil de priorisation d'attention** : depuis 49.2 il choisit l'univers candidat ; depuis 49.3 il peut fournir des faits descriptifs causaux au même Agent. Il n'est jamais un moteur BUY/SELL/HOLD ni une autorité Risk.

## État intégré récent

### Batch 45 — Structure en amont

**Intégré via `45d41b7`.** Rotation/cache Structure séparés, événements BOS/CHOCH, filtres tendance/Structure et `UNKNOWN` fail-closed. Contrat `market-attention-radar-v6` conservé.

### Batch 46 / 46.1 — baseline adaptative

**Intégré via `b219365`.** Médiane + MAD normalisé, cible 12 périodes et fallback ratio uniquement pour les métriques où cette sémantique est justifiée.

### Batch 47.1 — fondations Futures ticker

**Intégré via `842e6bd7`.** Snapshot bulk `/tickers` partagé pour volume/liquidité/contexte Futures, sans impact stratégique à ce stade historique.

### Batch 47.2 — historique Open Interest

**Intégré via `c09dd14`.** Infrastructure Analytics historique canonique avec rotation/cache/concurrence bornés et causalité explicite.

### Batch 47.3 — Funding historique + Liquidation Volume

**Intégré via `12051a7`.** Funding relatif signé et Liquidation Volume agrégé réutilisent le même scanner Analytics.

### Batch 47.4 — CVD + Aggressor Differential

**Intégré via `472f3ad`, clôturé documentairement via `e972fd9`.** CVD sur variation, Aggressor signé, MAD robuste, aucun fallback ratio pour les séries signées. Cinq séries partagent le même scanner/cache/cursor/sémaphore.

### Batch 47.5 — influence multi-analytics bornée sur le ranking

**Intégré via `d988de4`, clôturé documentairement via `4278a5c`.**

Décision architecturale :

```text
score séparé 0..4
= OI 0/1
+ Funding 0/1
+ Liquidations 0/1
+ Order Flow 0/1
```

CVD et Aggressor Differential forment une seule composante `ORDER_FLOW`. Ils ne peuvent jamais fournir +2.

Règles intégrées :

- score calculé uniquement sur les PERP déjà retenus ;
- `interest_level` inchangé ;
- `candidate_limit` inchangé ;
- aucune création/suppression de candidat ;
- données absentes/dégradées neutres ;
- signes positifs/négatifs symétriques pour l'attention ;
- priorité : intérêt -> Structure -> Analytics -> reste de la clé ;
- `SPOT` inchangé ;
- en `ALL`, positions SPOT figées ;
- contrat API v6 étendu additivement ;
- diagnostics cockpit explicites ;
- aucun impact direct Agent/Risk/Broker dans ce batch historique.

Voir `docs/47_5_MULTI_ANALYTICS_RANKING.md`.

### Batch 48 — observabilité du ranking Analytics

**Intégré fonctionnellement via `ebb664c`, clôturé documentairement via `8704eec`.**

Objectif : mesurer le comportement réel du ranking 47.5 avant toute nouvelle pondération ou toute exposition à l'Agent.

Décision architecturale intégrée :

```text
historique Radar borné existant
-> agrégation read-only à la demande
-> endpoint observability dédié
-> cockpit compact
```

Pas de nouvelle persistence et pas de second buffer. La persistence SQL actuelle reste réservée à ses responsabilités PAPER/audit économique.

Mesures intégrées :

- distribution score `0..4` ;
- contribution des quatre familles ;
- statuts des cinq séries ;
- fréquence de reranking applicable/effectif ;
- snapshots applicables sans mouvement ;
- distribution exacte de `rank_change`, moyenne et maximum de `abs(rank_change)` ;
- candidats montés/descendus/inchangés ;
- déduplications et conflits CVD/Aggressor ;
- PERP sans Analytics exploitable ;
- ventilation par scope ;
- couverture descriptive par marché ;
- fenêtre et taille d'échantillon explicites.

Route additive :

```text
GET /api/v1/market-attention/observability?limit=96
```

Le score, l'admission, `interest_level`, `candidate_limit`, Agent, Risk et Broker n'ont pas été modifiés par le Batch 48.

Voir `docs/48_OBSERVABILITE_RANKING_ANALYTICS.md`.

## Batch 49.1 — activation officielle du PERPETUAL PAPER

**Intégré via `3194fce`.**

La majorité de la capacité était déjà présente et testée avant le batch :

- univers `ExecutableMarket` typé SPOT/PERPETUAL ;
- routage marché exécutable SPOT/derivatives ;
- JSON Schema Agent conservant `market_type` ;
- `RiskEngine` dérivés linéaires ;
- levier/marge/caps/buffer liquidation déterministes ;
- `PaperBroker` PERPETUAL ;
- ledger LONG/SHORT, funding, P&L et liquidation théorique ;
- Market Discovery capable de conserver `PERPETUAL` ;
- configuration/cockpit capables de représenter les paramètres dérivés.

Le batch a officialisé l'invariant PAPER SPOT + PERPETUAL linéaire, aligné le contrat opérateur et ajouté la preuve d'intégration Agent -> Risk -> Broker -> `DerivativePosition`.

### Règle de retournement 49.1

```text
LONG + SELL surdimensionné  -> clamp/reject à la fermeture, jamais SHORT direct
SHORT + BUY surdimensionné  -> clamp/reject à la fermeture, jamais LONG direct
```

Avec `risk_allow_quantity_reduction=true`, Risk borne la quantité à la position courante et émet `reduce_only=true`. Sinon l'ordre opposé surdimensionné est rejeté.

## Batch 49.2 — Radar shortlist -> univers Agent SPOT + PERPETUAL

**Intégré via `f0d4f94`.**

Décision architecturale : **le Radar alimente la frontière canonique de Market Discovery**. Aucun second système de discovery et aucune deuxième shortlist ne sont créés.

```text
Market Attention Radar
-> shortlist finale bornée
-> extraction {symbol, market_type}
-> validation catalogue public Kraken + Campaign/Risk
-> DynamicMarketTradingCycleRunner
-> MultiMarketTradingCycleRunner canonique
-> même Agent stratégique
-> Risk
-> PaperBroker
```

Le chemin dynamique de production n'appelle plus `OpenAIWatchlistSelector`. Le seul appel stratégique reste `generate_decision_plan(...)`.

Règles 49.2 :

- `BTC/USD SPOT` et `BTC/USD PERPETUAL` restent deux identités distinctes ;
- seuls les marchés présents dans la shortlist Radar peuvent devenir de nouveaux candidats ;
- quote incompatible, statut non tradable, marché absent du catalogue, type non activé, PERP non linéaire ou whitelist Risk incompatible => candidat rejeté ;
- `FUTURE` reste rejeté par les contrats de domaine/policy ;
- la frontière Discovery/audit persiste uniquement les identités Radar, pas les Analytics ;
- aucune modification des poids Analytics ou recalibration ;
- Radar ne touche ni Risk ni Broker.

### Mode dégradé 49.2

Les nouvelles ouvertures sont **fail-closed** si le Radar est `ERROR`, `NOT_CONFIGURED`, `STALE`, trop ancien, si sa shortlist est vide ou si aucun candidat n'est exécutable. Le bootstrap n'est pas utilisé comme faux signal de remplacement.

S'il existe des positions ouvertes, elles restent gérables en mode MANAGEMENT par la chaîne canonique, sans nouvelle exposition.

Voir `docs/49_2_RADAR_AGENT_UNIVERSE.md`.

## Batch 49.3 — contexte Radar / Analytics causal fourni à l'Agent

**Intégré fonctionnellement via `d08cd31`, clôturé documentairement via `e7d605a`.**

Décision architecturale : **contexte typé dédié C**.

```text
univers 49.2
-> vérification du même snapshot Radar
-> projection RadarAnalyticsStrategicContext bornée
-> filtrage final sur les market_states du plan
-> même appel generate_decision_plan(...)
-> Agent BUY / SELL / HOLD
-> Risk
-> PaperBroker
```

Faits retenus : activité/tendance/liquidité, microstructure SPOT compacte, Market Structure compacte, score Analytics 47.5 et faits OI/Funding/Liquidations/CVD/Aggressor pour PERPETUAL. Les statuts dégradés restent explicites ; SPOT reçoit `NOT_APPLICABLE` pour les Analytics Futures.

Règles causales :

- le snapshot utilisé pour la projection doit porter exactement le `radar_observed_at` de Discovery ;
- tout timestamp imbriqué postérieur au snapshot est rejeté ;
- le contexte ne peut pas postdater `CycleDecisionPlanInput.created_at` ;
- un marché hors `market_states` est rejeté/filtré ;
- aucun résultat futur, P&L futur ou recalibration post-hoc.

Le score 47.5 reste `0..4` avec quatre familles. CVD et Aggressor restent une seule famille `ORDER_FLOW`.

Aucune modification Risk/Broker, aucune seconde décision LLM et aucune migration.

Voir `docs/49_3_AGENT_RADAR_ANALYTICS_CONTEXT.md`.

## Validation intégrée du Batch 49.3

```text
backend python -m pytest -q : PASS — 1189 passed, 2 warnings
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 86/86
git diff --check            : PASS — avertissements LF/CRLF uniquement
git status --short          : PASS — working tree propre après push
push GitHub main            : PASS — d08cd31
```

## Batch 49.4 — observabilité décisions et performances PAPER SPOT/PERP

**Intégré via `2e552cb`.**

Décision architecturale intégrée : **projection read-only dédiée au-dessus de `EconomicHistoryReport` et des audits persistés**, attachée à l'endpoint économique existant.

```text
faits PAPER persistés
-> PaperAnalyticsReport canonique
-> EconomicHistoryReport canonique
-> PaperObservabilityReport
-> /api/v1/economic-history
-> cockpit Historique
```

État intégré :

- vue TOTAL / SPOT / PERPETUAL ;
- funnel Agent -> Risk -> exécution ;
- distinction décisions / intents / fills / trades ;
- ventilation stricte `(symbol, market_type)` ;
- coûts, funding, notionnel, P&L réalisé et exposition attribués uniquement lorsqu'ils sont déterminables ;
- métriques indisponibles laissées à `null` au lieu d'être fabriquées.

Le P&L brut/net par type de marché n'est volontairement pas attribué : les faits durables actuels ne permettent pas une décomposition exacte de l'equity globale entre SPOT et PERPETUAL. Le P&L global reste canonique et inchangé.

Aucune nouvelle persistence, aucun nouvel endpoint, aucun changement Agent/Risk/Broker, aucun LIVE et aucune recalibration Analytics/Radar.

Voir `docs/49_4_OBSERVABILITE_DECISIONS_PERFORMANCES_PAPER.md`.

## Validation intégrée du Batch 49.4

```text
backend python -m pytest -q : PASS — 1195 passed, 2 warnings
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 89/89
git diff --check            : PASS — avertissements LF/CRLF uniquement
git status --short          : PASS — working tree propre après push
push GitHub main            : PASS — 2e552cb
```

Les warnings Node `MODULE_TYPELESS_PACKAGE_JSON` sont non bloquants et ne changent pas le statut de validation.

## Suite après intégration de 49.4

La suite devra être décidée à partir des métriques observées sans adaptation rétroactive. Le LIVE, l'authentification Kraken Futures privée et l'exécution réelle restent des décisions séparées et ultérieures.
