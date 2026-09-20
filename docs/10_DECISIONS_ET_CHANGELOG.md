# 10 — Décisions et changelog

## 1. Règle d'utilisation

Ce document conserve les décisions architecturales durables et un changelog synthétique.

Statuts :

- **ACCEPTÉE** : décision confirmée.
- **PROPOSÉE** : candidat à valider.
- **SUPERSEDÉE** : remplacée par une décision ultérieure.
- **ABANDONNÉE** : option explicitement rejetée.

Les détails historiques volumineux ne doivent pas migrer dans `00_ETAT_ACTUEL.md`.

---

## 2. Décisions acceptées

### ADR-001 — Un agent IA unique

- **Statut : ACCEPTÉE**
- AI Spot Trader utilise un seul agent IA de trading.
- Une architecture multi-agents est hors périmètre sans décision explicite.

### ADR-002 — SPOT uniquement

- **Statut : ACCEPTÉE**
- Le projet opère uniquement en crypto SPOT.
- Short, levier, margin, futures et perpetuals sont interdits.
- Une vente ne peut porter que sur un actif réellement détenu.

### ADR-003 — Kraken comme exchange initial

- **Statut : ACCEPTÉE**
- Kraken est l'exchange initial.
- L'intégration Kraken reste derrière une interface afin de ne pas contaminer le domaine avec des détails fournisseurs.

### ADR-004 — Backend Python asynchrone

- **Statut : ACCEPTÉE**
- Backend en Python, `asyncio`, FastAPI et Pydantic.
- Rust n'est pas introduit sans besoin mesuré ou décision explicite.

### ADR-005 — Frontend cockpit Next.js

- **Statut : ACCEPTÉE**
- Next.js + TypeScript, shadcn/ui + Tailwind CSS.
- Le frontend est un cockpit, pas le moteur de trading.

### ADR-006 — Le backend est autonome vis-à-vis du frontend

- **Statut : ACCEPTÉE**
- Le backend constitue l'application de trading.
- Fermer ou redémarrer le frontend ne doit jamais arrêter le moteur.
- REST et WebSocket sont utilisés selon le besoin.

### ADR-007 — Agent stratégique, calculs déterministes de contexte

- **Statut : ACCEPTÉE**
- L'agent IA conserve la décision stratégique.
- Les calculs déterministes produisent contexte, statistiques, indicateurs et contraintes.
- Ils ne deviennent pas une stratégie algorithmique parallèle.

### ADR-008 — Risk Engine déterministe avec autorité finale

- **Statut : ACCEPTÉE**
- Toute intention à conséquence financière passe par le Risk Engine.
- Le Risk Engine peut autoriser, modifier/réduire ou refuser.
- Aucune sortie LLM ne déclenche directement un ordre Kraken.

### ADR-009 — Actions BUY / SELL / HOLD

- **Statut : ACCEPTÉE**
- Les actions stratégiques sont `BUY`, `SELL`, `HOLD`.
- `HOLD` doit être journalisé.
- `SELL` est borné par la quantité détenue et disponible.

### ADR-010 — PAPER en premier, LIVE séparé

- **Statut : ACCEPTÉE**
- Les premières versions sont exclusivement PAPER.
- Le LIVE est séparé, ultérieur et nécessite une activation/décision explicite.

### ADR-011 — Frais, spread et slippage inclus

- **Statut : ACCEPTÉE**
- L'évaluation PAPER intègre frais, spread et slippage.
- Le P&L net devra être mesuré séparément du P&L brut.

### ADR-012 — Luna initial, Sol configurable

- **Statut : ACCEPTÉE**
- GPT-5.6 Luna est utilisé pour les premiers tests.
- GPT-5.6 Sol est sélectionnable par configuration.
- Le fournisseur LLM reste isolé derrière une interface.

### ADR-013 — Agressivité configurable de 1 à 10

- **Statut : ACCEPTÉE**
- Un paramètre d'agressivité de 1 à 10 existe.
- Son mapping chiffré exact reste **À DÉCIDER**.
- Aucune valeur ne contourne les invariants ou limites absolues du Risk Engine.

### ADR-014 — Cible expérimentale de +4 % par jour

- **Statut : ACCEPTÉE**
- +4 %/jour est une cible expérimentale, pas une garantie.
- Le système ne force pas des trades pour atteindre cette cible.
- Les performances sont rapportées sans cherry-picking ni look-ahead.

### ADR-015 — Journaliser toutes les décisions

- **Statut : ACCEPTÉE**
- Toutes les décisions sont journalisées, y compris `HOLD`, refus et modifications du Risk Engine.
- Les journaux ne doivent contenir aucun secret.

### ADR-016 — PostgreSQL comme base cible

- **Statut : ACCEPTÉE**
- PostgreSQL est la base de données cible.
- ORM, migrations et schéma détaillé restent **À DÉCIDER**.

### ADR-017 — Sécurité des secrets

- **Statut : ACCEPTÉE**
- Aucun secret dans Git, prompts ou logs.
- Aucune clé Kraken avec droit de retrait.
- Les secrets restent côté backend.

### ADR-018 — Bootstrap en deux applications découplées

- **Statut : ACCEPTÉE**
- Le repository contient un backend sous `backend/` et un frontend sous `frontend/`.
- Le backend démarre comme une application/service Python unique avec modules internes clairs.
- Le frontend est un processus séparé.
- Aucun microservice n'est introduit dans le bootstrap.

### ADR-019 — pnpm comme gestionnaire de paquets frontend

- **Statut : ACCEPTÉE**
- Le frontend utilise `pnpm` comme gestionnaire de paquets canonique.
- Les commandes sont documentées depuis la racine avec `pnpm --dir frontend ...`.

### ADR-020 — Contrats Pydantic stricts aux frontières du domaine

- **Statut : ACCEPTÉE**
- Les contrats critiques sont centralisés dans `backend/src/ai_spot_trader/domain/`.
- Ils utilisent Pydantic strict avec champs supplémentaires interdits.
- Les modèles sont enrichis uniquement lorsqu'un besoin de batch le justifie.
- Le sizing stratégique de `DecisionCandidate` n'est pas figé par cette décision.

### ADR-021 — PAPER est le seul mode d'exécution actuellement représentable

- **Statut : ACCEPTÉE**
- `ExecutionMode` ne contient que `PAPER`.
- Un futur LIVE nécessitera une décision et un batch dédiés.

### ADR-022 — Timestamps techniques aware normalisés en UTC

- **Statut : ACCEPTÉE**
- Les timestamps des contrats de domaine sont timezone-aware et normalisés en UTC.
- Cette convention ne tranche pas la frontière statistique d'une journée.

### ADR-023 — Horloge injectable minimale

- **Statut : ACCEPTÉE**
- Le backend fournit `Clock.now()` et `SystemClock` UTC.
- L'objectif est de permettre tests déterministes, replays et prévention du look-ahead.

### ADR-024 — Ports externes minimaux via Protocol

- **Statut : ACCEPTÉE**
- Les frontières externes sont modélisées avec des `Protocol` dépendant des contrats du domaine, pas des SDK fournisseurs.
- `MarketDataSource`, `MarketObservationSource`, `LLMProvider` et `Broker` restent les ports canoniques actuels.

### ADR-025 — Adapter Kraken Spot public minimal

- **Statut : ACCEPTÉE**
- La première intégration Kraken utilise uniquement les APIs publiques Spot.
- REST `/0/public/AssetPairs` avec `assetVersion=1` découvre les paires et alias.
- WebSocket Spot v2 `ticker` fournit dernier prix et timestamp.
- Heartbeats/messages système ne produisent pas de snapshot.
- Reconnexion bornée/configurable, sans retry infini.
- Stale detection technique optionnelle via l'horloge injectable.
- `httpx` et `websockets` sont les dépendances runtime ajoutées pour cette intégration.
- Aucune clé, authentification privée, ordre ou LIVE.

### ADR-026 — Market State déterministe, multi-horizon et sans look-ahead

- **Statut : ACCEPTÉE**
- `MarketObservation` est le fait fournisseur-agnostique minimal : timestamp, symbole canonique et dernier prix positif.
- Il n'existe qu'un seul `MarketState` canonique ; `MarketContext` l'enrichit optionnellement.
- `MarketStateBuilder` est mono-symbole et conserve un historique mémoire borné à 10 000 observations par défaut.
- Les observations doivent être strictement ordonnées ; doublons, hors ordre et changement de symbole sont rejetés.
- Les horizons descriptifs par défaut sont 5 minutes et 30 minutes, surchargeables.
- Les statistiques sont count, min, max, amplitude, return simple et volatilité réalisée simple en `Decimal`.
- Les valeurs indisponibles restent absentes ; aucune interpolation n'est effectuée.
- La fraîcheur reste descriptive et le seuil métier final appartient au futur Risk Engine.
- Pour un snapshot à `T`, seules les observations `observed_at <= T` sont utilisées.
- Les statistiques ne produisent aucun signal stratégique.

### ADR-027 — Rôles canoniques du Portfolio State

- **Statut : ACCEPTÉE**
- `PortfolioState` conserve deux collections non chevauchantes.
- `balances` est la source canonique des actifs de règlement disponibles pour débiter/créditer une exécution.
- `positions` est la source canonique des actifs détenus, avec quantité totale et quantité disponible à la vente.
- Les actifs sont uniques dans chaque collection et un même symbole d'actif ne peut pas appartenir simultanément aux deux rôles dans un snapshot.
- Cette décision évite une double source de vérité sans imposer une devise de référence produit globale.

### ADR-028 — Ledger PAPER mémoire et état initial injecté

- **Statut : ACCEPTÉE**
- `PaperPortfolioLedger` est l'unique état mutable du portefeuille PAPER au Batch 05.
- Il est instancié depuis un `PortfolioState` explicitement fourni ; aucun capital initial ou actif de règlement par défaut n'est codé dans le produit.
- Les mutations BUY/SELL calculent un nouvel état avant de remplacer l'état interne, afin qu'un rejet ne laisse aucune mutation partielle.
- Aucune base PostgreSQL, persistance, tâche de fond ou dépendance FastAPI n'est ajoutée.
- Aucune base de coût n'est introduite au Batch 05 : elle n'est pas requise pour l'intégrité du portefeuille et les fills conservent les coûts nécessaires aux analytics ultérieures.

### ADR-029 — Pricing PAPER explicite via MarketState

- **Statut : ACCEPTÉE**
- Le port canonique évolue en `Broker.execute(execution_intent, market_state) -> tuple[Fill, ...]`.
- Le Paper Broker ne consulte jamais Kraken et ne récupère aucun prix réseau caché.
- Le symbole du `MarketState` doit correspondre à l'intention.
- Le `MarketState.as_of` ne peut pas être postérieur à `ExecutionIntent.created_at` ; cette règle préserve le no look-ahead lors des replays.
- Le modèle initial fait un fill complet immédiat ou lève une erreur explicite ; aucun order book, partial fill complexe, pending order ou hasard n'est simulé.

### ADR-030 — Modèle de coûts PAPER déterministe et auditable

- **Statut : ACCEPTÉE**
- Les coûts sont injectés dans `PaperExecutionCostModel` et ne deviennent pas des variables d'environnement globales au Batch 05.
- `fee_rate` est un taux décimal appliqué au notional exécuté.
- `spread_bps` représente un **impact adverse par côté**, et non le spread bid/ask total.
- `slippage_bps` représente un impact adverse additionnel par côté.
- BUY : le prix exécuté est augmenté des impacts spread + slippage ; SELL : il est diminué des mêmes impacts.
- Le modèle est symétrique, déterministe, sans aléatoire, sans quantification Kraken et entièrement en `Decimal`.
- `Fill` enregistre `market_state_id`, `pricing_as_of`, prix de référence, prix exécuté, notional, frais, coût spread et coût slippage afin que les coûts restent auditables même si la configuration future change.

---

## 3. Propositions non encore décidées

### ADR-P001 — Contrats Pydantic versionnés entre composants

- **Statut : SUPERSEDÉE par ADR-020**
- Le principe de contrats Pydantic explicites est confirmé.
- Un champ explicite de version de schéma reste à décider lorsqu'un besoin de compatibilité inter-version devient concret.

### ADR-P002 — Horloge injectable

- **Statut : SUPERSEDÉE par ADR-023**

### ADR-P003 — Architecture modulaire dans un backend unique

- **Statut : SUPERSEDÉE par ADR-018**

### ADR-P004 — Logs structurés corrélés

- **Statut : PROPOSÉE**
- Les contrats portent des UUID explicites, mais le format/bibliothèque de logs structurés n'est pas encore choisi.

---

## 4. Décisions encore ouvertes

À consigner comme ADR lorsqu'elles sont tranchées :

- capital PAPER initial produit ;
- devise de référence produit ;
- univers de paires Kraken ;
- cadence de décision ;
- éventuelle évolution des horizons 5 min / 30 min ;
- données supplémentaires du Market State : bid/ask, spread réel, volume, bougies, profondeur, etc. ;
- stratégie de streaming/caching persistant du futur moteur marché ;
- seuil métier global de fraîcheur/stale ;
- représentation du sizing stratégique dans `DecisionCandidate` ;
- taille et exposition maximales ;
- max drawdown / max daily loss ;
- mapping agressivité 1–10 ;
- valeurs de référence expérimentales pour fee/spread/slippage PAPER ;
- éventuelle évolution vers un modèle de fill plus riche ;
- méthode de base de coût si nécessaire aux analytics ;
- frontière de journée ;
- ORM/migrations ;
- politique de rétention ;
- auth du cockpit ;
- stratégie de déploiement ;
- politique de reprise après panne ;
- versionnement explicite des schémas si nécessaire.

---

## 5. Changelog

### 2026-09-20 — Batch 05 Portfolio State + Paper Broker

**État : validation locale complète réussie ; intégration Git en attente.**

- Resynchronisation confirmée : GitHub `main` est au HEAD `73acc4758427ea7575ddf0a43505e1c95fab5e9c` (`feat: add deterministic market state`).
- Correction documentaire intégrée au patch : le Batch 04 est désormais enregistré comme intégré à ce HEAD.
- Ajout de validations d'unicité et de non-chevauchement des rôles d'actifs dans `PortfolioState`.
- Ajout de `ai_spot_trader.portfolio` et du `PaperPortfolioLedger` mémoire.
- L'état initial du portefeuille est injecté ; aucun capital ou actif de référence global n'est créé.
- Ajout de `ai_spot_trader.broker` et du `PaperBroker`.
- Évolution du port `Broker` pour recevoir explicitement le `MarketState` de pricing.
- Modèle full-fill immédiat, déterministe et sans ordre réseau.
- Modèle de coûts injecté : taux de frais + impact spread par côté + slippage par côté.
- BUY débite exactement notional + frais et crédite la position base.
- SELL débite uniquement une quantité disponible et crédite notional - frais.
- Rejets explicites et atomiques pour cash insuffisant, position insuffisante/non détenue, quote balance absente, symbole incompatible, prix futur ou configuration invalide.
- `Fill` enrichi pour rendre prix de référence, coûts et contexte de pricing auditables.
- Aucun `float`, aucune quantification fournisseur, aucune base de coût/P&L complet, aucune persistance, aucun Risk Engine parallèle.
- Aucune dépendance runtime, variable d'environnement ou lifecycle FastAPI ajouté.
- Validation locale Windows finale : `pytest backend` **92/92**, Ruff **All checks passed**, mypy **Success: no issues found in 40 source files**, `git diff --check` sans erreur.
- Seuls les warnings LF → CRLF habituels et 2 warnings de dépréciation FastAPI/Starlette sont présents, sans échec.
- Validation complémentaire dans l'environnement ChatGPT : Python `3.13.5`, suite ciblée domaine/clock/Market State/portfolio/broker **64/64**, `compileall` OK, lignes Python du patch `<= 100` OK.
- Aucun test réseau Kraken exécuté ou requis.

### 2026-09-20 — Batch 04 Market State

**État : intégré sur `main` au commit `73acc4758427ea7575ddf0a43505e1c95fab5e9c` (`feat: add deterministic market state`).**

- Ajout de `MarketObservation`, `MarketContext`, `MarketWindowStats` et `MarketObservationSource`.
- `MarketState` reste unique et reçoit un contexte optionnel.
- Extension de `KrakenMarketDataSource` avec `observation()` sans fuite de structure Kraken.
- Ajout de `ai_spot_trader.market` avec builder mémoire borné, mono-symbole et déterministe.
- Horizons 5 min / 30 min par défaut ; statistiques `Decimal` ; fenêtres partielles/vides explicites.
- Âge des données et stale technique optionnel ; aucune règle Risk globale.
- No look-ahead testé ; aucun signal stratégique, Risk Engine, Paper Broker ou persistance.
- Validation locale Windows finale : Python `3.13.14`, `pytest` 59/59, Ruff All checks passed, mypy OK sur 24 fichiers source, `git diff --check` sans erreur.
- Uniquement les warnings LF → CRLF habituels et 2 warnings FastAPI/Starlette sans échec ; aucun test réseau requis.

### 2026-09-20 — Batch 03 Kraken Market Data

**État : intégré sur `main` au commit `e7ac37955f08853024528fa9b9e10b5a75e05e3b` (`feat: add Kraken public market data`).**

- Ajout de `ai_spot_trader.integrations.kraken` et d'une implémentation publique de `MarketDataSource`.
- REST `AssetPairs?assetVersion=1`, WebSocket Spot v2 `ticker`, normalisation des alias, reconnexion bornée et stale technique optionnel.
- Aucun endpoint privé, ordre, Risk Engine fonctionnel, Paper Broker, LLM, PostgreSQL ou LIVE.
- Validation locale Windows finale : Python `3.13.14`, `pytest` 40/40, Ruff OK, mypy OK sur 21 fichiers source, `git diff --check` sans erreur.

### 2026-09-20 — Batch 02 contrats de domaine et configuration

**État : intégré sur `main` au commit `bff0f8b03740da4a01072af90111a2e5d9f208ef` (`feat: add domain contracts and configuration`).**

- Ajout des enums, contrats Pydantic stricts, UUID, timestamps UTC aware, horloge injectable et ports externes.
- PAPER uniquement, Luna par défaut, Sol sélectionnable, agressivité 1–10.
- Validation locale Windows : Python `3.13.14`, `pytest` 20/20, Ruff OK et mypy OK.

### 2026-09-20 — Batch 01 bootstrap du projet

**État : intégré sur `main` au commit `d9af0ca293dd9f2712969b246e394c4a8c188b5e`.**

- Backend Python/FastAPI installable, configuration typée, lifecycle asynchrone, healthcheck et tests.
- Frontend Next.js + TypeScript + Tailwind + socle shadcn/ui, géré avec `pnpm`.
- Validation locale backend et frontend réussie.

### 2026-09-20 — Batch 00 documentation initiale

**État : intégré sur `main`.**

- Documentation initiale et README établis.
- Formalisation des invariants fonctionnels et techniques.
- Définition d'une roadmap par batches testables.
