# 09 — Roadmap de développement

## Référence de reprise

```text
HEAD GitHub vérifié après intégration 19.10 : 8643b9412bd19791e3cfd60884126ca0c300dc33
Batch 19.9C intégré                    : feat: add session trading style UX
Batch 19.10 intégré                    : feat: add strategic position management and capital rotation
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Jalons intégrés

- 18.1 à 18.8 : tools Agent read-only, sélection multi-marchés, expérimentation, recovery et résilience réseau ;
- 18.9A à 18.9C : Control Plane backend/frontend et validation comportementale ;
- 18.10 à 18.13 : refonte UX, guide opérateur, simplification, dark mode et modernisation ;
- 19.1 : comptabilité SPOT canonique ;
- 19.2 : mark-to-market, equity/exposition backend et monitors sans LLM ;
- 19.3 : `CapacityEvaluator`, `NORMAL` / `MANAGEMENT` et barrière Risk ;
- 19.4 : discovery Kraken et watchlist multi-marchés par le même Agent ;
- 19.5 : explicabilité Agent/Risk/exécution depuis les faits persistés ;
- 19.6A : backend candles, cache borné, recovery et streaming partagé ;
- 19.6B : vue Marchés, Lightweight Charts et markers de fills persistés ;
- 19.7 : overlays de position canoniques `Prix moyen`, `Mark backend`, `Liquidation` ;
- 19.8 : façade utilisateur **Session**, CRUD/lifecycle versionné, configurateur simple/avancé et choix de marchés Automatique IA / Manuel ;
- 19.9A : Trading Style canonique `SCALP` / `SWING`, contextes style/coûts Agent et propagation Discovery -> Market Selection -> décision finale ;
- 19.9B : contexte stratégique candles multi-timeframes `strategic-mtf-v1`, causal, borné et partagé entre Market Selection et décision finale ;
- 19.9C : UX Session SCALP/SWING, persistance du style, timeframes en lecture seule, recommandations explicites et reconstruction persist-first ;
- 19.10 : gestion stratégique des positions ouvertes, contexte `position-management-v1` et rotation du capital multi-cycle par le même Agent.

## Batch 19.8 — Sessions v1

**État : intégré à GitHub `main` et validé localement.**

Objectif atteint : remplacer dans le parcours normal les concepts techniques Strategy/Revision/Campaign/paper_run par une façade utilisateur **Session** sans casser les faits canoniques existants.

### Backend

- façade `/api/v1/sessions` ;
- création transactionnelle Strategy + Revision 1 + Campaign ;
- projection de Session depuis Strategy/Campaign/runs/runtime ;
- mise à jour versionnée sans mutation d'historique ;
- duplication indépendante ;
- archivage logique via `Strategy.archived_at` ;
- lifecycle start/stop/resume/run-cycle ;
- arrêt = fermeture durable du runtime et du `paper_run` ;
- aucune migration SQL, aucune table `sessions`.

### Frontend

- navigation visible `Accueil | Sessions | Marchés | Positions | Historique | Réglages` ;
- page Sessions responsive ;
- création/édition simple et avancée ;
- mode `Automatique — IA` avec Market Discovery ;
- mode `Manuel` avec univers explicite ;
- technical Control Plane conservé dans `Réglages > Avancé` ;
- dette TypeScript `market_discovery`/`risk_allowed_pairs` corrigée.

### Statuts UX

```text
Brouillon
Prête
En cours
Arrêtée
À reprendre
Archivée
```

Ils sont dérivés des faits persistés et du runtime, jamais stockés comme une vérité concurrente.

### Validation obtenue

- backend complet : `606 passed`, 2 warnings de dépendances ;
- frontend : `21/21` tests passés ;
- `pnpm lint` : passé ;
- `pnpm typecheck` : passé ;
- `pnpm build` : passé ;
- `git diff --check` : aucune erreur de whitespace.

## Cadences à maintenir distinctes

1. monitoring / mark-to-market : déterministe, sans LLM ;
2. cycle stratégique IA : BUY / SELL / HOLD ;
3. discovery / watchlist IA : même Agent, cadence lente ;
4. streaming marché / candles : technique, déterministe, sans LLM.

## Batch 19.9A — Trading Style canonique / contexte Agent

**État : intégré à GitHub `main` au commit `4b6a851addea74d72af2c433827c935a87d4bc04`.**

Objectif atteint : poser les fondations versionnées `SCALP` / `SWING` dans la Campaign et propager le contexte stratégique et les coûts PAPER au même Agent, sans modifier Risk.

Livrables :

- enum `TradingStyle` ;
- mapping `trading-style-map-v1` et `TradingStyleContext` ;
- `ExecutionCostContext` dérivé exactement de la Campaign ;
- compatibilité digest des Campaigns historiques sans style ;
- propagation Discovery -> Market Selection -> décision finale ;
- forwarding du runner dynamique ;
- composition de prompt canonique ;
- tests de non-régression persistence/digest/runtime ;
- aucune migration SQL.

## Batch 19.9B — Données stratégiques multi-timeframes

**État : intégré à GitHub `main` au commit `88be7d50111c2e6210225071d3f1af3f7f07b4f0`.**

Objectif atteint : rendre la distinction SCALP/SWING opérationnelle côté données de marché sans déplacer la décision stratégique vers du code déterministe.

Livrables :

- contexte versionné `strategic-mtf-v1` ;
- réutilisation exclusive du mapping `trading-style-map-v1` ;
- `CandleStreamService` partagé avec les Campaign runtimes, sans second cache/pipeline OHLC ;
- lecture causale `history_as_of(...)` ;
- gaps conservés et statuts `AVAILABLE` / `PARTIAL` / `MISSING` avec stale ;
- bornes de 32 marchés, 128 KiB JSON, concurrence et profondeurs par timeframe ;
- snapshot construit pour Market Selection puis réutilisé inchangé pour la décision finale ;
- Discovery maintenue légère ;
- `ExecutionCostContext`, Risk Engine et `agent-contract-v1` inchangés ;
- compatibilité des Campaigns historiques sans `trading_style`.

Validation locale post-intégration :

- tests ciblés : `57 passed, 2 warnings` ;
- backend complet : `629 passed, 2 warnings` ;
- `git diff --check` : aucune erreur de whitespace.

## Batch 19.9C — UX Session pour le style de trading

**État : intégré à GitHub `main` au commit `b59020a4b354d9d56d593f3e39bcd608824bcd42` et validé localement par l'opérateur.**

Objectif atteint : exposer le Trading Style dans le parcours Session sans coupler le style à l'agressivité, au choix des marchés ou au Risk, et sans modifier le backend.

Livrables :

- choix `SCALP` / `SWING` dans le configurateur Session ;
- persistance de `trading_style` et `trading_style_mapping_version` avec `trading-style-map-v1` ;
- affichage en lecture seule des timeframes stratégiques : SCALP `1m/5m/15m/30m`, SWING `1h/4h/1d` ;
- recommandations UX : SCALP `60 s` / `300 s`, SWING `900 s` / `1800 s` pour cadence stratégique / watchlist refresh ;
- changement de style sans écrasement silencieux des personnalisations ;
- action explicite `Réappliquer les valeurs conseillées` ;
- Sessions historiques sans style affichées `Hérité / non défini`, sans inférence ;
- reconstruction persist-first de la configuration ;
- aucun fichier backend et aucune règle runtime dérivée du style.

Validation locale post-intégration :

- `pnpm test` : `29 tests`, `29 pass`, `0 fail` ;
- `pnpm lint` : PASS ;
- `pnpm typecheck` : PASS ;
- `pnpm build` : PASS sous Next.js 16.3.3 ;
- `git diff --check` : aucune erreur de whitespace ;
- warnings Node `MODULE_TYPELESS_PACKAGE_JSON` et Git LF -> CRLF : non bloquants.

## Batch 19.10 — Gestion stratégique des positions ouvertes et rotation du capital

**État : intégré à GitHub `main` au commit `8643b9412bd19791e3cfd60884126ca0c300dc33` et validé localement par l'opérateur.**

Objectif atteint : supprimer le biais structurel vers la recherche de nouvelles ouvertures en rendant les positions existantes explicitement gérables aussi en mode `NORMAL`, sans déplacer la décision de sortie dans du code déterministe.

Livrables :

- `CapacityAssessment.management_markets` renseigné aussi en mode `NORMAL` ;
- mapping positions ouvertes -> marchés centralisé et réutilisé ;
- contexte factuel versionné `position-management-v1` fourni au même Agent ;
- estimation économique de sortie SPOT via le modèle PAPER canonique, avec frais, spread et slippage ;
- réutilisation de `remaining_cost_basis` sans double comptage des coûts d'entrée ;
- `HOLD`, réduction partielle et clôture conservés comme décisions stratégiques ;
- aucune règle P&L, timer, style ou indicateur -> SELL ;
- `strategic-mtf-v1` et `trading-style-map-v1` préservés ;
- `risk_max_order_notional` conservé comme plafond par ordre, y compris pour un SELL SPOT réducteur ;
- protections anti-short/anti-oversell SPOT inchangées ;
- rotation du capital sur plusieurs cycles, sans BUY forcé après SELL ;
- frontière d'architecture Agent préservée : calcul économique côté trading, sans dépendance directe `agent -> broker` ;
- aucune migration SQL, aucun changement frontend et aucun second Agent.

Validation locale finale après correctif :

- tests ciblés : `11 passed` ;
- backend complet : `638 passed, 2 warnings` ;
- les deux warnings sont des dépréciations FastAPI/Starlette préexistantes ;
- `git diff --cached --check` : PASS ;
- `git diff --check` : aucune erreur, seulement des warnings LF -> CRLF.

## Périmètres ultérieurs

- LIVE reste séparé et ultérieur ;
- restauration d'une Session archivée si besoin produit démontré ;
- multi-quote/FX à traiter explicitement ;
- persistence durable des candles uniquement sur besoin démontré ;
- aucun ranking algorithmique stratégique ne doit être introduit silencieusement.
