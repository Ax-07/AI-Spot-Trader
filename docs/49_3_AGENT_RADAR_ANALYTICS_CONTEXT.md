# 49.3 — Contexte Radar / Analytics causal visible par l’Agent

## Statut

Batch intégré sur GitHub `main` via :

```text
d08cd31e6a795a8beb09530c2bc9a3f32f94fe35
feat: expose causal radar analytics context to agent
```

Base auditée au démarrage du Batch 49.3 :

```text
f0d4f94d2ed9b8f02eadb7ea021aa3fc817c973b
feat: feed radar shortlist into agent universe
```

Le Batch 49.2 était déjà intégré sur cette base ; le Batch 49.3 est désormais intégré et validé localement.

## Objectif

Enrichir le **même appel stratégique** de l’unique Agent avec des faits Radar/Analytics causaux pour les marchés déjà admis par la frontière 49.2, sans donner au Radar une autorité BUY/SELL/HOLD ni une autorité d’exécution.

```text
Radar
-> choisit où regarder
-> univers 49.2 typé SPOT/PERPETUAL

Radar / Analytics
-> projection descriptive bornée et figée du même snapshot

Agent stratégique unique
-> BUY / SELL / HOLD

Risk Engine
-> ALLOW / MODIFY / REJECT

PaperBroker
-> exécution PAPER d'un ExecutionIntent autorisé uniquement
```

## Audit des options d’architecture

### A — ajouter directement des champs Radar dans `CycleDecisionPlanInput`

Possible mais trop couplé : les faits deviennent des champs épars du contrat de plan et la frontière identité/contexte analytique devient moins claire.

### B — étendre `StrategicMultiTimeframeContext`

Rejeté. Ce contrat est actuellement une projection causale des candles stratégiques, liée au style et aux timeframes. Y injecter Radar, microstructure et Futures Analytics mélangerait deux responsabilités.

### C — contexte Radar/Analytics typé dédié référencé par `CycleDecisionPlanInput`

**Retenu.** `RadarAnalyticsStrategicContext` est immuable, strict, borné, déterministe et séparé de l’identité d’univers comme du contexte candles.

Le contexte est attaché au même `CycleDecisionPlanInput` juste avant l’appel `generate_decision_plan(...)`. Un décorateur `FrozenRadarContextDecisionProvider` enrichit l’entrée puis délègue **une seule fois** au provider Agent existant.

## Frontière causale

Discovery lit d’abord le Radar et persiste `radar_observed_at` dans son audit 49.2. Avant le plan stratégique, le runner relit le service Radar afin de construire la projection 49.3 uniquement si :

```text
latest.observed_at == discovery.audit.radar_observed_at
```

Si le snapshot a changé entre les deux lectures, les nouvelles ouvertures échouent fermées. Le service Radar n’est plus consulté pendant l’appel Agent : le provider reçoit un objet figé.

La validation de domaine impose aussi :

```text
chaque timestamp de fait <= radar_context.observed_at
radar_context.observed_at <= CycleDecisionPlanInput.created_at
```

Le contexte est enfin restreint aux `(symbol, market_type)` réellement présents dans `market_states`. Un candidat Radar hors univers ne peut donc pas apparaître dans le prompt.

## Faits retenus

### Activité / tendance / liquidité

Par marché :

- statut et fraîcheur activité ;
- qualité des données ;
- `activity_state` ;
- `trend_direction` récente ;
- `liquidity_regime` et référence USD lorsqu’elle existe ;
- `interest_level` comme niveau d’attention descriptif ;
- caractéristiques descriptives bornées ;
- jusqu’à quatre horizons avec ratio/anomalie de volume, rendement, anomalies range/volatilité et tendance ;
- `volume_24h_usd` lorsqu’il est disponible.

Pour la microstructure SPOT : statut/qualité/fraîcheur, spread bps, profondeur quote totale et book imbalance. La microstructure PERPETUAL reste `NOT_APPLICABLE` selon le Radar existant.

### Market Structure

La projection expose seulement :

- statut dérivé de disponibilité ;
- `global_state` ;
- jusqu’à quatre timeframes ;
- `state`, événement descriptif éventuel et `latest_final_close`.

Les swings complets, erreurs internes et diagnostics de calcul restent hors prompt.

### Analytics PERPETUAL

Le ranking 47.5 est copié sans recalcul :

```text
score total        : 0..4
OPEN_INTEREST      : 0/1
FUNDING            : 0/1
LIQUIDATION_VOLUME : 0/1
ORDER_FLOW         : 0/1
```

`CVD` et `Aggressor Differential` restent une seule famille `ORDER_FLOW`. Les flags `order_flow_deduplicated` et `order_flow_conflict` sont conservés afin que l’Agent puisse interpréter correctement l’indice sans inventer un double poids.

Valeurs compactes retenues :

- Open Interest : valeur courante, variation relative, anomaly score ;
- Funding : taux relatif courant, variation, anomaly score ;
- Liquidation Volume : volume courant, variation relative, anomaly score ;
- CVD : variation courante, anomaly score ;
- Aggressor Differential : valeur courante, variation, anomaly score.

Aucun rank avant/après Analytics, `rank_change`, diagnostic de couverture globale ou erreur brute n’est injecté.

## Données dégradées

Le contexte utilise explicitement :

```text
AVAILABLE
PARTIAL
STALE
INSUFFICIENT_HISTORY
TECHNICAL_ERROR
NOT_APPLICABLE
UNAVAILABLE
```

Une série dégradée conserve ses faits disponibles mais ne reçoit aucune valeur artificielle. Une panne technique ne devient jamais une information de marché.

Pour SPOT, les cinq séries Futures Analytics et le statut global sont toujours `NOT_APPLICABLE`, et aucun ranking Futures n’est exposé.

## Taille et déterminisme

Limites de domaine :

- au plus 20 marchés ;
- au plus 4 horizons d’activité par marché ;
- au plus 4 timeframes Structure ;
- au plus 4 composantes Analytics ranking ;
- au plus 2 éléments d’évidence par composante ;
- caractéristiques descriptives bornées.

Les marchés sont triés par `(market_type, symbol)`. La sérialisation du plan Agent continue d’utiliser JSON compact avec `sort_keys=True`.

## Contrat Agent

Le prompt sérialisé ajoute un contrat explicite uniquement lorsque le contexte 49.3 existe :

- le score `0..4` est un **indice d’attention descriptif** ;
- il n’est ni une probabilité, ni une conviction, ni une instruction BUY/SELL ;
- un statut dégradé signifie donnée absente/dégradée, pas direction de marché ;
- l’Agent reste seul responsable de BUY/SELL/HOLD ;
- Risk reste l’autorité finale.

Les outils read-only Agent existants sont conservés : ils répondent à des recherches stratégiques ponctuelles alors que le contexte 49.3 est un snapshot Radar causalisé et figé. Aucun second appel LLM d’interprétation Radar n’est ajouté.

## Risk / Broker

Aucune modification de Risk ou du Broker.

Le contexte 49.3 ne contient aucun champ `action`, `ExecutionIntent`, `leverage` ou `reduce_only`. Il ne peut ni créer un ordre, ni modifier directement le portefeuille.

## Fichiers du batch

```text
backend/src/ai_spot_trader/domain/radar_context.py
backend/src/ai_spot_trader/market/radar_agent_context.py
backend/src/ai_spot_trader/agent/radar_context.py
backend/src/ai_spot_trader/domain/planning.py
backend/src/ai_spot_trader/trading/discovery_runner.py
backend/src/ai_spot_trader/agent/planner.py
backend/src/ai_spot_trader/campaign_composition.py
backend/tests/test_batch49_3_agent_radar_analytics_context.py
README.md
docs/00_ETAT_ACTUEL.md
docs/01_PROJECT_MASTER.md
docs/09_ROADMAP_DEVELOPPEMENT.md
docs/10_DECISIONS_ET_CHANGELOG.md
docs/49_3_AGENT_RADAR_ANALYTICS_CONTEXT.md
```

## Validation réalisée

```text
backend python -m pytest -q : PASS — 1189 passed, 2 warnings
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 86/86
git diff --check            : PASS — avertissements LF/CRLF uniquement
git status --short          : PASS — working tree propre après push
push GitHub main            : PASS — d08cd31
```

Les deux warnings backend sont des avertissements de dépréciation de dépendances de test et n'ont provoqué aucun échec.

## Hors périmètre

- recalibration des poids/seuils Analytics 47.5 ;
- apprentissage selon le P&L futur ;
- LIVE ;
- ordres Kraken réels ;
- API Kraken Futures privée ;
- changement du modèle Risk ;
- nouveaux indicateurs non nécessaires au contexte ;
- observabilité détaillée de performance SPOT/PERP, réservée à 49.4.
