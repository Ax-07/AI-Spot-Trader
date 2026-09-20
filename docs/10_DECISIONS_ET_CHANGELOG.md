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
- L'évaluation PAPER doit intégrer frais, spread et slippage.
- Le P&L net doit être mesuré séparément du P&L brut.

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
- Les frontières externes initiales sont `MarketDataSource`, `LLMProvider` et `Broker`.
- Elles dépendent des contrats de domaine, pas des SDK fournisseurs.

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
- Le Batch 04 introduit `MarketObservation` comme fait fournisseur-agnostique minimal : timestamp, symbole canonique et dernier prix positif.
- `MarketObservationSource` formalise la frontière d'observation ; l'adapter Kraken l'implémente tout en conservant `MarketDataSource.snapshot()` pour compatibilité.
- Il n'existe qu'un seul `MarketState` canonique. Il peut porter un `MarketContext` optionnel construit par la couche `market`.
- `MarketStateBuilder` travaille sur un seul symbole par instance et conserve un historique mémoire borné à 10 000 observations par défaut, valeur technique surchargeable.
- Les observations doivent être strictement ordonnées ; doublons temporels, données hors ordre et changement de symbole sont rejetés.
- Deux horizons descriptifs sont définis par défaut : 5 minutes et 30 minutes. Ils sont surchargeables et ne représentent ni cadence de décision, ni signal de trading.
- Les statistiques retenues sont : nombre d'observations, min, max, amplitude absolue, return simple et volatilité réalisée simple.
- La volatilité réalisée est l'écart-type population des returns simples consécutifs et n'est calculée qu'à partir de trois observations.
- Les calculs financiers/statistiques utilisent `Decimal` ; aucune dépendance NumPy/Pandas/TA-Lib n'est introduite.
- Les valeurs indisponibles restent explicitement absentes ; aucune interpolation n'est effectuée.
- La fraîcheur expose âge et seuil technique éventuellement évalué. Aucun seuil métier global Risk n'est fixé.
- Pour un snapshot à `T`, seules les observations `observed_at <= T` sont utilisées, même si des observations futures sont déjà présentes dans l'historique d'un replay.
- Les statistiques restent descriptives et ne produisent aucun `BUY`, `SELL`, `HOLD`, score ou label stratégique.

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

- capital PAPER initial ;
- devise de référence ;
- univers de paires Kraken ;
- cadence de décision ;
- éventuelle évolution des horizons 5 min / 30 min ;
- données supplémentaires du Market State : bid/ask, spread, volume, bougies, profondeur, etc. ;
- stratégie de streaming/caching persistant du futur moteur marché ;
- seuil métier global de fraîcheur/stale ;
- représentation du sizing stratégique dans `DecisionCandidate` ;
- taille et exposition maximales ;
- max drawdown / max daily loss ;
- mapping agressivité 1–10 ;
- modèle de fill/slippage ;
- barème de frais de référence ;
- frontière de journée ;
- ORM/migrations ;
- politique de rétention ;
- auth du cockpit ;
- stratégie de déploiement ;
- politique de reprise après panne ;
- versionnement explicite des schémas si nécessaire.

---

## 5. Changelog

### 2026-09-20 — Batch 04 Market State

**État : patch préparé et testé offline ; intégration Git en attente.**

- Resynchronisation confirmée : GitHub `main` est au HEAD `e7ac37955f08853024528fa9b9e10b5a75e05e3b` (`feat: add Kraken public market data`).
- Correction documentaire : le Batch 03 est désormais enregistré comme intégré à ce HEAD.
- Ajout de `MarketObservation`, `MarketContext`, `MarketWindowStats` et du port `MarketObservationSource`.
- `MarketState` reste unique et reçoit un contexte optionnel, sans dupliquer le snapshot canonique.
- Extension minimale de `KrakenMarketDataSource` avec `observation()` ; le parsing Kraken reste exclusivement dans `integrations/kraken`.
- Ajout de `ai_spot_trader.market` avec un builder mémoire borné, mono-symbole et déterministe.
- Horizons par défaut : 5 min / 30 min, surchargeables sans variable d'environnement.
- Statistiques : count, min/max, amplitude, return simple et volatilité réalisée simple, en `Decimal`.
- Fenêtres partielles/vides explicitement représentées ; aucune donnée inventée ou interpolée.
- Âge des données et évaluation stale optionnelle ; aucune règle Risk globale.
- No look-ahead testé : les observations futures déjà injectées sont exclues d'un snapshot historique à `T`.
- Aucun signal stratégique, agent, Risk Engine, Paper Broker, persistance ou tâche autonome n'est introduit.
- Aucune dépendance runtime ajoutée.
- Tests exécutés dans l'environnement ChatGPT : Python `3.13.5`, `pytest` 59/59, `compileall` OK.
- Ruff et mypy non disponibles dans cet environnement ; validation locale Windows requise.
- Aucun test réseau Kraken n'est exécuté ni requis par défaut.

### 2026-09-20 — Batch 03 Kraken Market Data

**État : intégré sur `main` au commit `e7ac37955f08853024528fa9b9e10b5a75e05e3b` (`feat: add Kraken public market data`).**

- Base intégrée avant Batch 03 : `bff0f8b03740da4a01072af90111a2e5d9f208ef`.
- Ajout de `ai_spot_trader.integrations.kraken` et d'une implémentation publique de `MarketDataSource`.
- REST `AssetPairs?assetVersion=1` pour découvrir les paires Spot et normaliser leurs alias.
- WebSocket Spot v2 `ticker`, parsing `last`/`symbol`/`timestamp`, heartbeat ignoré et fermeture propre.
- Reconnexion bornée/configurable avec réabonnement.
- Stale detection technique via `Clock`, sans seuil métier global par défaut.
- `httpx` et `websockets` comme dépendances runtime directes.
- Aucun endpoint privé, ordre, Risk Engine fonctionnel, Paper Broker, LLM, PostgreSQL ou LIVE.
- Validation locale Windows finale avant intégration : Python `3.13.14`, `pytest` 40/40, Ruff OK, mypy OK sur 21 fichiers source, `git diff --check` sans erreur.
- Deux warnings de dépréciation FastAPI/Starlette observés sans échec.
- Aucun test réseau Kraken requis par défaut.

### 2026-09-20 — Batch 02 contrats de domaine et configuration

**État : intégré sur `main` au commit `bff0f8b03740da4a01072af90111a2e5d9f208ef` (`feat: add domain contracts and configuration`).**

- Base intégrée : `d9af0ca293dd9f2712969b246e394c4a8c188b5e`.
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
