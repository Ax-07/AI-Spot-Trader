# 11 — Améliorations planifiées

> Référence de reprise des chantiers 19.x. Ce document distingue ce qui est **intégré**, ce qui reste **ouvert** et ce qui doit encore être **décidé**.

## 1. Référence

```text
Repository                      : Ax-07/AI-Spot-Trader
Branche                         : main
Référence d'audit avant fusion  : a254df4d56208c4472bb97b9b80077ad0856f9cd
Référence fonctionnelle 19.6A   : 3c53af3bdb1ef53c574e26afe9b6178a374d9f06
Référence fonctionnelle 19.6B   : a446628918a614d2ae0ac3b55243881aad5ef410
Référence fonctionnelle 19.7    : 8b969b434916d89f6b6aa127c3bac9c27e990966
Référence fonctionnelle 19.8    : f3a8eae8528648c07723aa97350852428254acc7
Date                            : 2026-09-25
```

Les Batches 19.1 à 19.8 sont intégrés. Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## 2. Invariants transverses

- un seul Agent IA stratégique ;
- Kraken ;
- PAPER uniquement ;
- SPOT + PERPETUAL linéaire dans l'état intégré ;
- aucune sortie LLM ne déclenche directement Broker/Kraken ;
- Risk Engine déterministe = autorité finale ;
- IA = choix stratégique ;
- calculs, comptabilité, monitoring, capacité, filtrage technique, statistiques et streaming candles = déterministes ;
- frontend jamais source de vérité trading ;
- aucun secret dans prompts, logs, docs ou Git ;
- frais, spread, slippage et funding pris en compte sans double comptage ;
- HOLD auditable ;
- aucun look-ahead ni sélection rétrospective ;
- aucune candle manquante inventée ;
- Session = façade UX, pas nouveau ledger ni nouvelle source de vérité.

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## 3. Cadences cibles

| Cadence | But | LLM |
| --- | --- | --- |
| Monitoring / mark-to-market | prix, marks, P&L, exposition, marge, liquidation, funding | non |
| Cycle stratégique | BUY / SELL / HOLD, avec restriction MANAGEMENT si nécessaire | oui, Agent unique |
| Discovery / watchlist | réévaluer les marchés intéressants | oui, même Agent |
| Streaming marché / candles | historique, candle courante, recovery, diffusion cockpit | non |

Ces cadences restent indépendantes. Le streaming candles ne déclenche aucune décision Agent et n'intervient pas dans l'autorisation Risk.

# 4. Comptabilité SPOT par position — INTÉGRÉE 19.1

Confirmé : coût économique moyen pondéré, coût restant frais BUY inclus, ventes partielles au prorata, P&L réalisé net, pas de double comptage spread/slippage/frais, recovery JSON et compatibilité `accounting_complete=false`.

# 5. Monitoring / mark-to-market — INTÉGRÉ 19.2

Confirmé : marks SPOT causaux, P&L latent backend, agrégats portfolio, monitors backend indépendants de l'Agent et cockpit branché sur les champs canoniques.

# 6. Mode gestion lorsque l'exposition est saturée — INTÉGRÉ 19.3

Confirmé : `CapacityEvaluator`, `NORMAL` / `MANAGEMENT`, même `RiskPolicy`, recherche d'ouverture désactivée en MANAGEMENT, Risk bloque les hausses d'exposition et aucun nouvel état durable parallèle n'est créé.

# 7. Discovery automatique et watchlist — INTÉGRÉ 19.4

Confirmé : catalogue `MarketResearchService`, filtrage factuel sans ranking, watchlist sélectionnée par le même Agent, fallback, interaction avec MANAGEMENT, univers effectif incluant les positions, audit durable et recovery canonique.

Validation opérateur communiquée : 12 tests discovery, 578 tests backend avec 2 warnings de dépréciation, `pnpm lint`, `pnpm typecheck`, `pnpm build` passés.

# 8. Explicabilité des décisions IA — INTÉGRÉE 19.5

Le Batch 19.5 transforme les faits du journal de cycle en une vue de présentation typée et défensive sans créer une nouvelle source de vérité.

Architecture :

```text
CycleAuditDetail existant
  + contexte capacité/discovery
  + MarketSelection
  + DecisionCandidate
  + RiskAssessment
  + ExecutionIntent / Fill
-> CycleExplainabilityResponse
-> /api/v1/cycles/latest
-> /api/v1/cycles/{cycle_id}
```

La projection distingue contexte NORMAL/MANAGEMENT, discovery, sélection de marché, BUY/SELL/HOLD, ALLOW/MODIFY/REJECT, fills et FAILED.

Référence intégrée : `07050faea54bbed89cf250b34f8e97bd10d94bd3`.

# 9. Historique candles + WebSocket — INTÉGRÉ 19.6A

## 9.1 Pipeline

```text
SPOT      : Kraken REST OHLC + Kraken WS v2 OHLC
PERPETUAL : Kraken Futures charts + Futures WS trade
                         |
                         v
                 Candle OHLCV canonique
                         |
              cache backend process-local
                         |
          API historique + WebSocket cockpit
```

Le backend gère normalisation, déduplication, candle courante mutable, finalisation, recovery et limites de profondeur.

## 9.2 Modèle canonique

Chaque candle porte au minimum : symbole canonique, type de marché, timeframe, `open_time` / `close_time` UTC, OHLC, volume, `is_final` et `updated_at` causal.

Les clés sont séparées par `symbol + market_type + timeframe`. Une candle future ou une candle finale prétendument disponible avant sa clôture est refusée.

## 9.3 Timeframes explicites

SPOT : `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`, `15d`.

PERPETUAL : `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `12h`, `1d`, `1w`.

FUTURE daté n'est pas supporté par le pipeline intégré.

## 9.4 Historique initial

SPOT : l'endpoint OHLC est borné à 720 rows.

PERPETUAL : Kraken Futures charts est interrogé avec une cible bornée à 1000 rows. Le backend accepte une profondeur plus faible si c'est ce que le fournisseur retourne réellement.

Aucune donnée n'est interpolée ou reconstruite artificiellement.

## 9.5 Cache et WebSocket

Le cache est process-local, borné et dédupliqué. SPOT réutilise le canal public v2 `ohlc`. PERPETUAL agrège le feed public Futures `trade` et ne crée pas de candle vide pour une période sans trade.

Le hub effectue backfill initial, reconnexion, recovery de gap, fusion/déduplication et expose erreur/staleness. Un seul stream provider est créé par `CandleKey` et partagé entre consommateurs cockpit.

## 9.6 API cockpit

```text
GET /api/v1/markets/candles
GET /api/v1/markets/candles/status
WS  /api/v1/markets/candles/stream
```

Référence intégrée : `3c53af3bdb1ef53c574e26afe9b6178a374d9f06`.

# 10. Espace Marchés + charts + markers — INTÉGRÉ 19.6B

La vue Marchés :

- affiche la watchlist effective backend lorsqu'elle existe, sinon le bootstrap actif, puis réinjecte les positions ouvertes ;
- ne crée aucun ranking stratégique frontend ;
- charge le marché/timeframe actif à la demande ;
- consomme exclusivement les contrats candles backend ;
- utilise Lightweight Charts pour chandeliers et volume ;
- affiche loading/error/stale et reconnecte le WebSocket avec backoff borné ;
- utilise un cache mémoire client borné ;
- affiche le contexte de position depuis `/portfolio` ;
- crée les markers BUY/SELL uniquement depuis les fills persistés ;
- utilise `/cycles/{cycle_id}` pour afficher les faits Agent/Risk corrélés ;
- n'infère aucune clôture, aucune candle, aucun fill et aucune causalité.

Validation opérateur :

- `pnpm test` : 6/6 ;
- `pnpm lint` : passé sans erreur ni warning ;
- `pnpm typecheck` : passé ;
- `pnpm build` : passé ;
- `git diff --check` : aucune erreur de whitespace.

Référence fonctionnelle : `a446628918a614d2ae0ac3b55243881aad5ef410`.

# 11. Overlays de position sur charts — INTÉGRÉ 19.7

Le Batch 19.7 a fermé la lacune de présentation identifiée après 19.6B.

Sont projetés sur le chart, lorsqu'ils existent dans le portefeuille canonique :

- prix moyen d'entrée ;
- mark backend ;
- liquidation pour PERPETUAL.

Règles :

- aucune valeur n'est recalculée dans le frontend ;
- aucune ligne n'est inventée lorsque la donnée manque ;
- les lignes sont remplacées ou retirées lors d'un changement de marché, timeframe ou position ;
- markers de fills et overlays restent deux projections différentes de faits backend.

Référence fonctionnelle : `8b969b434916d89f6b6aa127c3bac9c27e990966`.

# 12. Sessions v1 — INTÉGRÉ 19.8

Le Batch 19.8 remplace dans le parcours normal les concepts techniques Strategy/Revision/Campaign/paper_run par une façade utilisateur `Session`.

Architecture :

```text
Session UX
-> Strategy = identité stable
-> StrategyRevision(s) immuables
-> Campaign(s) immuables/versionnées
-> paper_run(s) / recovery
```

Fonctions intégrées :

- création atomique ;
- listing et détail ;
- modification versionnée ;
- duplication indépendante ;
- archivage logique ;
- start / stop / resume / run-cycle ;
- configurateur simple + avancé ;
- mode marchés `AUTOMATIC_AI` ;
- mode marchés `MANUAL` ;
- navigation `Accueil | Sessions | Marchés | Positions | Historique | Réglages`.

Aucune table SQL `sessions` n'est ajoutée.

Validation opérateur :

- backend complet : 606 tests passés, 2 warnings de dépendances ;
- frontend : 21/21 tests passés ;
- `pnpm lint` : passé ;
- `pnpm typecheck` : passé ;
- `pnpm build` : passé ;
- `git diff --check` : aucune erreur de whitespace.

Référence fonctionnelle : `f3a8eae8528648c07723aa97350852428254acc7`.

# 13. Ordre 19.x intégré

| Ordre | Batch | Résultat principal | Statut |
| ---: | --- | --- | --- |
| 1 | 19.1 — Comptabilité SPOT | coût moyen, coût restant, P&L réalisé, recovery | intégré |
| 2 | 19.2 — Monitoring | P&L latent et état vivant sans LLM | intégré |
| 3 | 19.3 — Mode gestion | évite recherche IA inutile quand ouverture indisponible | intégré |
| 4 | 19.4 — Discovery/watchlist | univers dynamique audité, même Agent | intégré |
| 5 | 19.5 — Explicabilité | rationale Agent / raisons Risk visibles | intégré |
| 6 | 19.6A — Candles/streaming | données chart canoniques | intégré |
| 7 | 19.6B — Marchés/charts | rendu, onglets, markers | intégré |
| 8 | 19.7 — Overlays | prix moyen, mark, liquidation canoniques | intégré |
| 9 | 19.8 — Sessions v1 | façade UX Session et lifecycle simplifié | intégré |

# 14. Chantiers ouverts

## 14.1 Observabilité d'usage/coût LLM — OUVERT, À CADRER

Objectif : mesurer appels/tokens par phase et par cycle afin de quantifier l'économie IA.

Contraintes :

- observabilité uniquement ;
- aucune modification automatique de la stratégie ;
- aucun second Agent ;
- pas de métrique inventée lorsque le provider ne la fournit pas.

## 14.2 Multi-quote / FX — DÉCISION ARCHITECTURALE REQUISE

Objectif : valoriser de façon cohérente des marchés dont quote/settlement diffèrent.

Le chantier touche potentiellement portefeuille, Risk, analytics, recovery et sources de conversion causales. Aucun agrégat multi-devise ne doit être introduit sans contrat explicite.

## 14.3 Persistence durable des candles — À DÉCIDER SUR BESOIN

Le cache process-local satisfait le besoin actuel de présentation et de recovery technique. Aucun besoin démontré ne justifie encore une nouvelle table ou un historique maison.

## 14.4 Restauration d'une Session archivée — À DÉCIDER SUR BESOIN PRODUIT

Le Batch 19.8 archive sans effacer les faits historiques. Une action de restauration n'est pas intégrée et ne doit être ajoutée que si le besoin produit est confirmé.

## 14.5 FUTURE daté — HORS PÉRIMÈTRE ACTUEL

Le domaine peut connaître `MarketType.FUTURE`, mais l'exécution intégrée le refuse. Son ajout exige un chantier explicite distinct de PERPETUAL.

## 14.6 LIVE — SÉPARÉ ET ULTÉRIEUR

Aucun chantier PAPER ne doit basculer implicitement vers LIVE. Le passage au LIVE exige une décision et un parcours explicites, séparés et ultérieurs.
