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
- Backend en Python.
- `asyncio` pour l'asynchrone.
- FastAPI pour l'API.
- Pydantic pour les modèles/validation.
- Rust n'est pas introduit sans besoin mesuré ou décision explicite.

### ADR-005 — Frontend cockpit Next.js

- **Statut : ACCEPTÉE**
- Next.js + TypeScript.
- shadcn/ui + Tailwind CSS.
- Le frontend est un cockpit de contrôle et visualisation, pas le moteur de trading.

### ADR-006 — Le backend est autonome vis-à-vis du frontend

- **Statut : ACCEPTÉE**
- Le backend constitue l'application de trading.
- Fermer ou redémarrer le frontend ne doit jamais arrêter le moteur.
- REST et WebSocket sont utilisés selon le besoin.

### ADR-007 — Agent stratégique, calculs déterministes de contexte

- **Statut : ACCEPTÉE**
- L'agent IA conserve la décision stratégique.
- Les calculs déterministes produisent contexte, statistiques, indicateurs et contraintes.
- Ils ne doivent pas devenir silencieusement une stratégie algorithmique parallèle.

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
- Le simple fait de posséder une clé privée ne doit pas activer le LIVE.

### ADR-011 — Frais, spread et slippage inclus

- **Statut : ACCEPTÉE**
- L'évaluation PAPER doit intégrer frais, spread et slippage.
- Le P&L net doit être mesuré séparément du P&L brut.

### ADR-012 — Luna initial, Sol configurable

- **Statut : ACCEPTÉE**
- GPT-5.6 Luna est utilisé pour les premiers tests afin de limiter les coûts.
- GPT-5.6 Sol doit être sélectionnable par configuration.
- Le fournisseur LLM est isolé derrière une interface.

### ADR-013 — Agressivité configurable de 1 à 10

- **Statut : ACCEPTÉE**
- Un paramètre d'agressivité de 1 à 10 existe.
- Son mapping chiffré exact reste **À DÉCIDER**.
- Aucune valeur ne contourne les invariants ou limites absolues du Risk Engine.

### ADR-014 — Cible expérimentale de +4 % par jour

- **Statut : ACCEPTÉE**
- +4 %/jour est une cible expérimentale.
- Ce n'est ni une garantie ni une hypothèse de rendement attendu.
- Le système ne doit pas forcer des trades pour atteindre la cible.
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
- La gestion opérationnelle exacte des secrets reste à définir.

### ADR-018 — Bootstrap en deux applications découplées

- **Statut : ACCEPTÉE**
- Le repository contient un backend sous `backend/` et un frontend sous `frontend/`.
- Le backend démarre comme une application/service Python unique avec modules internes clairs.
- Le frontend est un processus séparé et n'est jamais requis pour maintenir le backend en fonctionnement.
- Aucun microservice n'est introduit dans le bootstrap.

### ADR-019 — pnpm comme gestionnaire de paquets frontend

- **Statut : ACCEPTÉE**
- Le frontend utilise `pnpm` comme gestionnaire de paquets canonique.
- Les commandes de développement et validation sont documentées depuis la racine avec `pnpm --dir frontend ...`.
- Le Batch 01 a été validé avec pnpm `10.15.1`.

### ADR-020 — Contrats Pydantic stricts aux frontières du domaine

- **Statut : ACCEPTÉE**
- Les contrats critiques initiaux sont centralisés dans `backend/src/ai_spot_trader/domain/`.
- Ils utilisent Pydantic avec validation stricte et refusent les champs supplémentaires.
- Les contrats initiaux sont `MarketState`, `PortfolioState`, `AgentInput`, `DecisionCandidate`, `RiskAssessment`, `ExecutionIntent` et `Fill`.
- Les modèles restent minimaux et sont enrichis uniquement lorsqu'un besoin de batch le justifie.
- Le sizing stratégique de `DecisionCandidate` n'est pas figé par cette décision.

### ADR-021 — PAPER est le seul mode d'exécution actuellement représentable

- **Statut : ACCEPTÉE**
- `ExecutionMode` ne contient que `PAPER`.
- `LIVE` ne peut pas être activé par variable d'environnement ou configuration dans l'état actuel.
- Un futur LIVE nécessitera une décision et un batch dédiés.

### ADR-022 — Timestamps techniques aware normalisés en UTC

- **Statut : ACCEPTÉE**
- Les timestamps des contrats de domaine doivent être timezone-aware.
- Ils sont normalisés en UTC aux frontières Pydantic.
- Cette convention de stockage/échange ne tranche pas la frontière statistique d'une journée, qui reste ouverte.

### ADR-023 — Horloge injectable minimale

- **Statut : ACCEPTÉE**
- Le backend fournit une interface `Clock.now()` et une implémentation `SystemClock` UTC.
- L'objectif est de fournir un seam minimal pour tests déterministes, futurs replays et prévention du look-ahead.
- Aucun framework de simulation temporelle supplémentaire n'est introduit au Batch 02.

### ADR-024 — Ports externes minimaux via Protocol

- **Statut : ACCEPTÉE**
- Les frontières externes initiales sont `MarketDataSource`, `LLMProvider` et `Broker`.
- Elles sont définies comme `Protocol` et dépendent des contrats de domaine, pas des SDK fournisseurs.
- Aucun provider Kraken, LLM ou broker réel n'est implémenté au Batch 02.

### ADR-025 — Adapter Kraken Spot public minimal

- **Statut : ACCEPTÉE**
- La première intégration Kraken utilise uniquement les APIs publiques Spot et implémente `MarketDataSource` sans modifier `MarketState`.
- REST `/0/public/AssetPairs` avec `assetVersion=1` sert à découvrir les paires et à obtenir une représentation canonique slash-separated ainsi que les alias Kraken utiles.
- La normalisation est dérivée des métadonnées fournisseur ; aucune table dispersée `XBT/BTC` ou univers de trading codé en dur n'est introduit.
- WebSocket Spot v2 `ticker` est le flux temps réel initial car il fournit le dernier prix et un timestamp suffisants pour le contrat minimal du Batch 03.
- Les heartbeats et messages système non pertinents ne produisent pas de `MarketState`.
- La reconnexion WebSocket est bornée et configurable, avec réabonnement ; aucun retry infini ni circuit breaker n'est introduit.
- La stale detection existe derrière l'horloge injectable, mais son seuil reste optionnel et non défini par défaut afin de ne pas figer une règle métier prématurément.
- `httpx` et `websockets` sont les seules dépendances runtime ajoutées pour cette intégration ; aucun SDK Kraken lourd n'est utilisé.
- Le Batch 03 n'introduit ni clé Kraken, ni authentification privée, ni ordre, ni LIVE.

---

## 3. Propositions non encore décidées

### ADR-P001 — Contrats Pydantic versionnés entre composants

- **Statut : SUPERSEDÉE par ADR-020**
- Le principe de contrats Pydantic explicites est désormais confirmé.
- La nécessité d'un champ explicite de version de schéma par modèle reste à décider lorsqu'une compatibilité inter-version devient concrète.

### ADR-P002 — Horloge injectable

- **Statut : SUPERSEDÉE par ADR-023**
- L'abstraction minimale a été introduite au Batch 02.

### ADR-P003 — Architecture modulaire dans un backend unique

- **Statut : SUPERSEDÉE par ADR-018**
- La proposition a été concrétisée au bootstrap par un backend déployable comme application/service unique avec modules internes clairs.
- Les microservices restent hors périmètre sans besoin démontré.

### ADR-P004 — Logs structurés corrélés

- **Statut : PROPOSÉE**
- Les contrats portent désormais des UUID explicites, mais le format/bibliothèque de logs structurés n'est pas encore choisi.
- La proposition de corréler les logs par `cycle_id`, `decision_id` et autres IDs reste à confirmer lors du batch observabilité/persistance.

---

## 4. Décisions encore ouvertes

À consigner comme ADR lorsqu'elles sont tranchées :

- capital PAPER initial ;
- devise de référence ;
- univers de paires Kraken ;
- cadence de décision ;
- horizons/indicateurs ;
- enrichissement exact du `MarketState` ;
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

### 2026-09-20 — Batch 03 Kraken Market Data

**État : patch préparé et testé offline ; intégration Git en attente.**

- Resynchronisation confirmée : GitHub `main` est au HEAD `bff0f8b03740da4a01072af90111a2e5d9f208ef` (`feat: add domain contracts and configuration`).
- Correction documentaire : le Batch 02 est désormais indiqué comme intégré sur `main` à ce commit.
- Ajout de `ai_spot_trader.integrations.kraken` et d'une implémentation publique de `MarketDataSource`.
- Ajout d'un client REST public minimal sur `AssetPairs?assetVersion=1` pour découvrir les paires Spot et normaliser leurs alias.
- Ajout du flux WebSocket Spot v2 `ticker`, avec parsing `last`/`symbol`/`timestamp`, heartbeat ignoré, abonnement public et fermeture propre.
- Ajout d'une politique de reconnexion bornée/configurable avec réabonnement, sans boucle infinie.
- Ajout d'une stale detection technique testable via `Clock`; aucun seuil métier global n'est défini par défaut.
- Ajout d'erreurs fournisseur dédiées : connexion, payload invalide, symbole inconnu et donnée stale.
- `httpx` devient dépendance runtime directe ; `websockets` est ajouté comme dépendance runtime directe.
- Extension de `.env.example` avec uniquement des paramètres Kraken publics/techniques, sans clé ni secret.
- Aucun endpoint Kraken privé, ordre, Risk Engine fonctionnel, Paper Broker, LLM, PostgreSQL ou LIVE n'est introduit.
- Tests exécutés dans l'environnement ChatGPT : `pytest` 40/40 ; `compileall` OK.
- Ruff et mypy n'ont pas pu être exécutés dans l'environnement ChatGPT utilisé pour cette livraison car les modules ne sont pas installés ; validation locale Windows requise.
- Aucun test réseau Kraken n'est exécuté ni requis par la suite par défaut.

### 2026-09-20 — Batch 02 contrats de domaine et configuration

**État : intégré sur `main` au commit `bff0f8b03740da4a01072af90111a2e5d9f208ef` (`feat: add domain contracts and configuration`).**

- Base intégrée auditée avant Batch 02 : `d9af0ca293dd9f2712969b246e394c4a8c188b5e`.
- Correction documentaire : le Batch 01 est indiqué comme intégré sur `main`.
- Ajout des enums `TradingAction`, `ExecutionMode`, `RiskDecision` et `LLMModel`.
- Ajout des contrats stricts `MarketState`, `PortfolioState`, `AgentInput`, `DecisionCandidate`, `RiskAssessment`, `ExecutionIntent` et `Fill`.
- Ajout de modèles minimaux `AssetBalance` et `AssetPosition`.
- Ajout d'UUID de corrélation explicites.
- Rejet des timestamps naïfs et normalisation des timestamps aware en UTC.
- Ajout d'une horloge injectable minimale `Clock` / `SystemClock`.
- Ajout des ports `MarketDataSource`, `LLMProvider` et `Broker` sans implémentation fournisseur au Batch 02.
- Extension de la configuration : PAPER uniquement, Luna par défaut, Sol sélectionnable, agressivité optionnelle 1–10.
- Aucun Kraken réel, appel OpenAI, Risk Engine fonctionnel, Paper Broker fonctionnel, PostgreSQL ou LIVE n'est introduit au Batch 02.
- Validation locale Windows avant intégration : Python `3.13.14`, `pytest` 20/20, Ruff OK et mypy OK.
- Deux warnings de dépréciation Starlette/FastAPI ont été observés dans les dépendances de test, sans échec.

### 2026-09-20 — Batch 01 bootstrap du projet

**État : intégré sur `main` au commit `d9af0ca293dd9f2712969b246e394c4a8c188b5e`.**

- Base documentaire précédente : `c4d6aa6da9dde19a52b12dc54535af3b98aa1523`.
- Création du backend Python/FastAPI installable sous `backend/`.
- Ajout de la configuration typée via `pydantic-settings` et d'un `.env.example` sans secret.
- Ajout du cycle de vie asynchrone minimal et du healthcheck `GET /health`.
- Ajout des tests `pytest` et configuration Ruff/mypy.
- Création du frontend Next.js + TypeScript + Tailwind CSS v4 + socle shadcn/ui sous `frontend/`.
- Ajout des checks ESLint et TypeScript côté frontend.
- Validation locale frontend réussie via `pnpm 10.15.1` : install, lint, type-check et build Next.js.
- Validation locale backend réussie sous Python `3.13.14` : installation editable, `pytest` 4/4, Ruff et mypy.
- Standardisation des commandes de développement depuis la racine du repository.
- Aucune intégration Kraken, LLM, Risk Engine, Paper Broker, PostgreSQL ou logique de trading n'a été introduite.

### 2026-09-20 — Batch 00 documentation initiale

**État : intégré sur `main`.**

- Repository initial observé au commit `f5b967d8736075781d8142c8cc80a99cbd96fae3`.
- Documentation initiale intégrée au commit `bd58ec3502fecca6c8c693af6fe71daea22b9167`.
- README et état courant rafraîchis au commit `c4d6aa6da9dde19a52b12dc54535af3b98aa1523`.
- Formalisation des invariants fonctionnels et techniques.
- Définition d'une roadmap par batches testables.
