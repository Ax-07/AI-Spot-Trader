# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub audité        : d011faa98e7e347875186f12cb24b5e7041aa25c
Trading Reasoning Doctrine: intégrée
Batch 25 historique éco   : intégré
Market Attention Radar v1 : patch proposé dans ce batch
Migration courante        : 0006_paper_control_plane -> 0007_multi_decision_cycles
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Jalons intégrés avant Market Attention Radar v1

- 18.x : tools Agent read-only, sélection multi-marchés, expérimentation, recovery, résilience et Control Plane ;
- 19.1 : comptabilité SPOT canonique ;
- 19.2 : mark-to-market, equity/exposition backend et monitors sans LLM ;
- 19.3 : `CapacityEvaluator`, `NORMAL` / `MANAGEMENT` et barrière Risk ;
- 19.4 : discovery Kraken et watchlist multi-marchés par le même Agent ;
- 19.5 : explicabilité Agent/Risk/exécution depuis les faits persistés ;
- 19.6A/19.6B : candles backend, streaming partagé, vue Marchés et markers de fills ;
- 19.7 : overlays de position canoniques ;
- 19.8 : façade utilisateur Session ;
- 19.9A : Trading Style `SCALP` / `SWING` et coûts Agent ;
- 19.9B : contexte stratégique `strategic-mtf-v1` causal ;
- 19.9C : UX Session du style ;
- 19.10 : gestion stratégique des positions et rotation du capital ;
- 19.12 : classification robuste des limites fournisseur OpenAI, retry borné et fail-closed ;
- 19.13 : cycle stratégique multi-marchés / multi-décisions ;
- 19.13 correctif : refresh candles PERPETUAL ;
- 19.15 / Batch 26 : valorisation PAPER PERPETUAL ;
- Batch 25 : historique économique Session/run ;
- Batch 27 : Trading Reasoning Doctrine v1, intégrée au HEAD `d011faa`.

## Cadences à maintenir distinctes

1. monitoring / mark-to-market : déterministe, sans LLM ;
2. cycle stratégique IA : plan ordonné `BUY` / `SELL` / `HOLD` ;
3. discovery / watchlist IA : même Agent, cadence distincte ;
4. streaming marché / candles : technique, déterministe, sans LLM ;
5. **Market Attention Radar** : observation déterministe + recherche publique auxiliaire, cadence/cache/TTL propres, sans influence sur le cycle stratégique.

## Market Attention Radar v1

**État : patch proposé, à valider localement avant intégration.**

### Objectif

Détecter où une activité inhabituelle semble commencer, puis croiser :

```text
activité marché Kraken
+
attention publique récente sourcée
=
shortlist d'attention informative
```

### Market Activity Radar

- réutilisation des candles Kraken canoniques ;
- base `5m`, agrégation descriptive `5m / 15m / 1h / 4h` ;
- volume relatif contre fenêtres comparables ;
- volume change / acceleration ;
- rendement, range, volatilité réalisée ;
- freshness / données insuffisantes / stale explicites ;
- SPOT et PERPETUAL linéaire observés séparément ;
- scanner borné et rotation sur le catalogue pour ne pas provoquer un burst massif de requêtes Kraken ;
- cache d'activité avec TTL ;
- présélection maximale de 30 marchés et 20 par défaut.

### Public Web Attention

- aucune API X/Reddit/LunarCrush ;
- OpenAI Responses API + hosted `web_search` ;
- Structured Output strict `public_attention_v1` ;
- sources/citations fournisseur conservées ;
- métriques quantitatives optionnelles sans invention ;
- qualitatif conservé comme qualitatif ;
- pas de BUY/SELL/HOLD, pas de recommandation, pas de probabilité de hausse/baisse ;
- recherche dédupliquée par actif ;
- 8 recherches web maximum par refresh par défaut, borne dure 30 ;
- cache public avec TTL ;
- retry borné et fail-soft.

### Croisement

États v1 :

```text
NORMAL
MARKET_ONLY
PUBLIC_ONLY
CONVERGING
```

Les niveaux d'attention `NORMAL / MEDIUM / HIGH` décrivent uniquement l'inhabituel/convergence. Ils ne représentent ni un rendement attendu, ni une probabilité, ni une préférence LONG/SHORT.

### Persistence

La v1 n'ajoute aucune migration. Les snapshots agrégés récents sont gardés dans un historique process-local borné. Cette décision évite de dupliquer les candles, les pages web ou les posts publics avant d'avoir observé l'utilité réelle du radar. Une persistence PostgreSQL durable pourra être décidée plus tard si les observations justifient le coût et le schéma.

### Cockpit

Panneau global `Market Attention` :

- badge `INFORMATIF — N’INFLUENCE PAS LE TRADING` ;
- état activité marché / attention publique / croisement ;
- ratios volume 5m / 15m / 1h ;
- mouvement de prix ;
- nombre de sources ;
- contexte/catalyseur ;
- freshness et heure de recherche ;
- détail des sources publiques avec liens cliquables.

### Barrières d'architecture

- aucun changement `CycleDecisionPlan` ;
- aucun changement prompt stratégique ;
- aucun changement Market Discovery ;
- aucun changement Risk/Broker ;
- aucune shortlist Radar injectée à l'Agent ;
- une panne Radar ne peut pas faire échouer un cycle de trading.

### Validation attendue avant intégration

Backend :

```powershell
cd backend
pytest -q
```

Frontend :

```powershell
cd ..\frontend
pnpm test
pnpm lint
pnpm typecheck
pnpm build
```

Voir `docs/28_BATCH_MARKET_ATTENTION_RADAR_V1.md`.

## Batch 19.13 — Cycle stratégique multi-marchés / multi-décisions

**État : intégré et validé.**

### Objectif atteint

Permettre à un seul cycle stratégique de contenir plusieurs décisions ordonnées sur des marchés distincts, sans introduire de second Agent, sans déplacer la stratégie dans du code déterministe et sans affaiblir Risk.

### Contrat stratégique

- un seul Agent IA ;
- un seul appel stratégique de planification au stade décisionnel ;
- plusieurs `BUY` / `SELL` / `HOLD` possibles dans un même cycle ;
- ordre explicite ;
- `max_decisions_per_cycle` configurable ;
- défaut `6` ;
- hard limit `20`.

### Exécution causale

- Risk exécuté séquentiellement pour chaque décision ;
- chaque décision suivante voit le portefeuille après les exécutions précédentes ;
- `HOLD` ne stoppe pas le plan ;
- `REJECT` ne stoppe pas le plan ;
- un SELL peut libérer du capital pour une décision ultérieure, uniquement si le plan Agent le prévoit et si Risk l'autorise ;
- aucune règle automatique `SELL -> BUY`.

### Atomicité

- checkpoint PAPER au début du cycle ;
- erreur technique Risk/Broker => `FAILED` ;
- rollback PAPER atomique de toutes les mutations économiques du cycle ;
- audit de l'échec conservé.

### Persistence / API / cockpit

- migration `0007_multi_decision_cycles` ;
- relations d'audit 1:N pour decisions / Risk assessments / execution intents ;
- trajectoire ordonnée exposée par l'API et le cockpit ;
- compatibilité de lecture avec les anciens cycles/configurations ;
- analytics basés sur les fills/trades réels, pas sur le nombre de décisions.

### Validation locale fournie

Backend :

- ciblé : `51 passed` ;
- complet : `698 passed, 2 warnings` ;
- `alembic upgrade head` : succès sur PostgreSQL réel.

Frontend :

- `pnpm test` : `39 passed` ;
- `pnpm lint` : succès ;
- `pnpm typecheck` : succès ;
- `pnpm build` : succès.

### Documentation de batch

Voir `docs/24_BATCH_19_13_CYCLE_STRATEGIQUE_MULTI_MARCHES.md`.

## Étape d'intégration du présent batch

Après extraction du ZIP Market Attention et validation locale :

```text
1. git status --short
2. exécuter les tests backend/frontend du batch
3. git diff --check
4. vérifier que seuls les fichiers du batch sont modifiés
5. commit explicite Market Attention Radar v1
6. push main uniquement sur décision de l'opérateur
```

Le HEAD GitHub réel doit rester la source de vérité pour déterminer l’identifiant de commit effectivement intégré ; ne pas déduire ce statut d’une ancienne mention documentaire.

## Périmètres ultérieurs

- persistence PostgreSQL durable des snapshots Radar si besoin démontré ;
- étude après données réelles d'une éventuelle exposition du contexte Radar à l'Agent stratégique — **non décidée** ;
- LIVE reste séparé et ultérieur ;
- restauration d'une Session archivée si besoin démontré ;
- multi-quote/FX à traiter explicitement ;
- persistence durable des candles uniquement sur besoin démontré ;
- aucun ranking algorithmique stratégique introduit silencieusement ;
- aucune promesse de rendement.
