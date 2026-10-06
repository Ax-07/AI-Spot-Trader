# 09 — Roadmap de développement

## Référence de reprise

```text
Repository                  : Ax-07/AI-Spot-Trader
Branche                     : main
HEAD GitHub vérifié 51.1    : e5887da5e8e6ebf0fa739a041c0226a6fed940dd
Batch 49.1                  : intégré via 3194fce
Batch 49.2                  : intégré via f0d4f94
Batch 49.3                  : intégré via d08cd31
Batch 49.4                  : intégré via 2e552cb
Batch 50.1                  : intégré via ebb859c4
Batch 50.2                  : intégré via e5887da
Batch 51.1                  : patch livré, validation/intégration à faire
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve :

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- Risk Engine déterministe comme autorité finale ;
- backend indépendant du frontend ;
- PAPER avant tout LIVE ;
- exécution PAPER SPOT + PERPETUAL Kraken linéaire ;
- SPOT sans short/levier/marge ;
- LONG/SHORT PERPETUAL autorisés sous contrôle Risk ;
- FUTURE daté non exécutable ;
- aucune sortie LLM directement exécutable ;
- aucune seconde décision LLM pour la mémoire ou l'observabilité ;
- aucun secret versionné ;
- aucun look-ahead ni adaptation post-hoc ;
- mémoire stratégique typée, causale et durable, jamais opaque ;
- observabilité strictement read-only, sans rétroaction sur Agent/Risk/Broker ;
- depuis 51.1, le moteur LLM peut être OpenAI ou Ollama sans dupliquer l'Agent.

Le Market Attention Radar reste un **outil de priorisation d'attention**. Il choisit l'univers candidat et fournit des faits descriptifs causaux au même Agent, sans devenir un moteur BUY/SELL/HOLD ni une autorité Risk.

## État intégré récent

### Batch 45 — Structure en amont

**Intégré via `45d41b7`.** Rotation/cache Structure séparés, BOS/CHOCH, filtres tendance/Structure et `UNKNOWN` fail-closed.

### Batch 46 / 46.1 — baseline adaptative

**Intégré via `b219365`.** Médiane + MAD normalisé, cible 12 périodes et fallback ratio uniquement lorsque cette sémantique est valide.

### Batch 47.1 — fondations Futures ticker

**Intégré via `842e6bd7`.** Snapshot bulk `/tickers` partagé pour volume/liquidité/contexte Futures.

### Batch 47.2 — historique Open Interest

**Intégré via `c09dd14`.** Infrastructure Analytics historique canonique avec rotation/cache/concurrence bornés et causalité explicite.

### Batch 47.3 — Funding historique + Liquidation Volume

**Intégré via `12051a7`.** Funding relatif signé et Liquidation Volume agrégé sur le scanner Analytics commun.

### Batch 47.4 — CVD + Aggressor Differential

**Intégré via `472f3ad`, clôturé via `e972fd9`.** CVD/Aggressor signés, MAD robuste, aucun fallback ratio pour séries signées.

### Batch 47.5 — influence multi-analytics bornée

**Intégré via `d988de4`, clôturé via `4278a5c`.** Score d'attention `0..4` avec quatre familles OI/Funding/Liquidations/Order Flow ; aucune création de candidat ni autorité directionnelle.

### Batch 48 — observabilité du ranking Analytics

**Intégré via `ebb664c`, clôturé via `8704eec`.** Agrégation read-only à la demande, aucun nouveau store et aucune rétroaction sur le ranking.

Route intégrée :

```text
GET /api/v1/market-attention/observability?limit=96
```

### Batch 49.1 — activation officielle du PERPETUAL PAPER

**Intégré via `3194fce`.** Univers PAPER SPOT + PERPETUAL linéaire, LONG/SHORT dérivés, levier/marge/exposition contrôlés par Risk, `DerivativePosition`, funding et P&L.

Règle critique : aucun retournement direct ne contourne `reduce_only`/Risk.

### Batch 49.2 — Radar shortlist -> univers Agent

**Intégré via `f0d4f94`.** Le Radar alimente la frontière canonique `MarketDiscoveryCoordinator`; le chemin de production n'effectue plus une deuxième sélection LLM de watchlist.

```text
Radar
-> shortlist bornée
-> validation catalogue/configuration
-> univers dynamique canonique
-> même Agent stratégique
```

Les nouvelles ouvertures sont fail-closed si le Radar est indisponible/stale/vide/inexploitable. Les positions existantes restent gérables en MANAGEMENT.

### Batch 49.3 — contexte Radar / Analytics causal fourni à l'Agent

**Intégré via `d08cd31`, clôturé via `e7d605a`.** `RadarAnalyticsStrategicContext` strict, borné et causal ; même snapshot que Discovery ; aucun second appel Agent ; aucun changement Risk/Broker.

Validation intégrée : `1189 passed, 2 warnings`, frontend typecheck/test PASS.

### Batch 49.4 — observabilité décisions et performances PAPER

**Intégré via `2e552cb`.** Projection read-only `PaperObservabilityReport` au-dessus de l'historique économique canonique : TOTAL/SPOT/PERP, funnel Agent/Risk/exécution, ventilation stricte `(symbol, market_type)` et métriques attribuables.

Aucun P&L brut/net par type n'est fabriqué lorsque la persistence ne permet pas l'attribution causale exacte.

Validation intégrée : `1195 passed, 2 warnings`, frontend typecheck/test PASS.

## Batch 50.1 — mémoire de thèse stratégique des positions

**Intégré via `ebb859c4ed83aada1c0bf3edf17ece85336849b9` (`feat: add persistent strategic thesis memory`).**

Validation intégrée communiquée :

```text
backend python -m pytest -q : PASS — 1217 passed, 2 warnings
migration PostgreSQL        : 0008 strategic_thesis_state appliquée
working tree après push     : propre
```

Architecture : extension additive des faits de cycle + projection canonique.

```text
positions ouvertes
+ dernier snapshot de thèses actives
+ contexte marché / MTF / Radar
        ↓
StrategicThesisContextDecisionProvider
        ↓
même generate_decision_plan(...)
        ↓
BUY / SELL / HOLD + thesis_update
        ↓
Risk -> PaperBroker
        ↓
commit cycle + portefeuille
        ↓
audit_cycles.strategic_thesis_state_payload
```

Règles intégrées :

- nouvelle entrée sans fill / Risk REJECT => aucune thèse active ;
- réduction partielle => thèse maintenue ;
- fermeture complète => thèse retirée du snapshot actif, révision auditée ;
- `INVALIDATED`/`COMPLETED` ne signifient jamais `SELL` automatique ;
- cycle `FAILED` => aucun snapshot promu ;
- legacy => `UNAVAILABLE_LEGACY`, sans reconstruction de rationale ;
- recovery par lineage `paper_run` ;
- aucun second Agent, aucun changement Risk/Broker.

Voir `docs/50_1_MEMOIRE_THESE_STRATEGIQUE.md`.

## Batch 50.2 — observabilité et cockpit des thèses stratégiques

**Intégré via `e5887da5e8e6ebf0fa739a041c0226a6fed940dd` (`feat: add strategic thesis observability`).**

Objectif : rendre visible la continuité stratégique de chaque position PAPER sans modifier le comportement de trading.

Architecture retenue : **endpoint dédié read-only dans le routeur Analytics existant**.

```text
audit_cycles.strategic_thesis_state_payload
+ decision_plan_payload.thesis_updates
+ lineage paper_run
+ portefeuille durable
        ↓
StrategicThesisObservabilityReport
        ↓
GET /api/v1/strategic-theses
        ↓
cockpit Historique
```

Livrables 50.2 intégrés : exposition active typée, `UNAVAILABLE_LEGACY`, historique causal borné des révisions, distinction proposition/Risk/fill/état actif, `PROPOSED_NOT_ACTIVATED`, `FAILED_CYCLE`, conservation de la révision finale après fermeture et cockpit Historique dédié.

Aucun second store, aucune migration, aucun second LLM et aucune dépendance Risk/Broker dans le projecteur.

Voir `docs/50_2_OBSERVABILITE_THESES_STRATEGIQUES.md`.

## Batch 51.1 — Provider LLM local / Ollama

**Patch livré sur HEAD intégré `e5887da5`; validation repository réelle puis intégration à faire.**

Objectif : permettre au même Agent stratégique de remplacer le transport OpenAI par un LLM Ollama local sans modifier la logique de décision, Risk, Broker, Radar ou la mémoire de thèse.

Architecture :

```text
Agent stratégique canonique
-> StrategyInstructionsClient / StructuredDecisionClient
   -> OpenAIResponsesClient
   -> OllamaStructuredDecisionClient
-> sortie JSON structurée
-> validation Pydantic existante
-> Risk Engine
```

Livrables 51.1 :

- `LLMProviderKind = OPENAI | OLLAMA` distinct du port domaine historique `LLMProvider` ;
- factory unique `build_structured_decision_client(...)` ;
- modèle Ollama séparé et configurable (`AI_SPOT_TRADER_OLLAMA_MODEL`) ;
- URL/timeout Ollama configurables ;
- `OPENAI_API_KEY` requise uniquement en mode OpenAI ;
- aucun fallback silencieux vers OpenAI ;
- `/api/chat` Ollama + JSON Schema `format` ;
- même validation Pydantic métier ;
- conversion des tools read-only vers le format Ollama et réutilisation du registre/budget existant ;
- audit LLM enrichi avec provider, modèle, statut, erreur, latence ;
- cockpit audit adapté minimalement ;
- chat opérateur explicitement indisponible en LOCAL pour 51.1 ;
- nom legacy `OpenAIMultiMarketDecisionProvider` conservé pour éviter un renommage transversal sans bénéfice fonctionnel.

Validation ChatGPT réellement exécutée :

```text
python -m compileall sur les fichiers Python du patch              : PASS
harnais isolé MockTransport Ollama structured/tools/network         : PASS
harnais isolé OpenAI audit SUCCESS/ERROR + latence                  : PASS
git diff --cached --check sur staging root-relative du patch        : PASS
```

À valider dans le repository réel :

```text
Push-Location backend
python -m pytest -q
Pop-Location

Push-Location frontend
pnpm typecheck
pnpm test
Pop-Location

git diff --check
git status --short
```

Smoke local Ollama :

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
ollama pull qwen3.5:9b
```

Une vraie décision structurée et un cycle avec tools doivent être testés sur le PC de l'opérateur ; aucune inférence Ollama réelle n'a été exécutée dans l'environnement ChatGPT.

Voir `docs/51_1_PROVIDER_LLM_LOCAL_OLLAMA.md`.

## Suite proposée après intégration 51.1

### Batch 51.2 — sélection UX/persistée du provider

Ajouter le choix `OpenAI / Local` au contrat Session/Campaign uniquement après validation du transport 51.1. Ce batch devra décider explicitement comment versionner le provider et le modèle local dans les snapshots/digests sans casser les Campaigns existantes.

Sujets séparés, non inclus dans 51.1 :

- comparaison de performance Luna/local ;
- fine-tuning/entraînement ;
- optimisation de stratégie ;
- Prompt Cache OpenAI ;
- auto-tuning ;
- recalibration Radar/Analytics ;
- stop-loss/take-profit algorithmique ;
- LIVE ;
- API Kraken Futures privée.
