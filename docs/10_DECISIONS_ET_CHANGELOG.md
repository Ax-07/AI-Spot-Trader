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

## 2. Décisions initiales

### ADR-001 — Un agent IA unique

- **Statut : ACCEPTÉE**
- AI Spot Trader utilise un seul agent IA de trading.
- Une architecture multi-agents est hors périmètre tant qu'une décision explicite ne la remplace pas.

### ADR-002 — SPOT uniquement

- **Statut : ACCEPTÉE**
- Le projet opère uniquement en crypto SPOT.
- Short, levier, margin, futures et perpetuals sont interdits dans le périmètre actuel.
- Une vente ne peut porter que sur un actif réellement détenu.

### ADR-003 — Kraken comme exchange initial

- **Statut : ACCEPTÉE**
- Kraken est l'exchange initial.
- L'intégration Kraken doit rester derrière une interface afin de ne pas contaminer le domaine avec des détails fournisseurs.

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
- Les calculs déterministes peuvent produire contexte, statistiques, indicateurs et contraintes.
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
- GPT-5.6 Luna est utilisé pour les premiers tests pour limiter les coûts.
- L'architecture doit permettre de sélectionner GPT-5.6 Sol par configuration.
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
- Les performances doivent être rapportées sans cherry-picking ni look-ahead.

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

---

## 3. Propositions non encore décidées

### ADR-P001 — Contrats Pydantic versionnés entre composants

- **Statut : PROPOSÉE**
- Utiliser des contrats explicites pour `MarketState`, `PortfolioState`, `DecisionCandidate`, `RiskAssessment`, etc.
- À confirmer lors du bootstrap / batch contrats.

### ADR-P002 — Horloge injectable

- **Statut : PROPOSÉE**
- Introduire une abstraction d'horloge pour tests et replay sans look-ahead.
- À confirmer avant les premiers composants temporels.

### ADR-P003 — Architecture modulaire dans un backend unique

- **Statut : PROPOSÉE**
- Démarrer par un backend déployable comme une application/service unique avec modules internes clairs.
- Ne pas introduire de microservices sans besoin.

### ADR-P004 — Logs structurés corrélés

- **Statut : PROPOSÉE**
- Utiliser `cycle_id`, `decision_id` et timestamps pour reconstruire un cycle.
- Format et bibliothèque à décider.

---

## 4. Décisions encore ouvertes

À consigner comme ADR lorsqu'elles sont tranchées :

- capital PAPER initial ;
- devise de référence ;
- univers de paires Kraken ;
- cadence de décision ;
- horizons/indicateurs ;
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
- contrat final de `DecisionCandidate`.

---

## 5. Changelog

### 2026-09-20 — Batch 00 documentation initiale

**État : patch proposé, non intégré au moment de sa génération.**

- Audit du HEAD GitHub `main` : `f5b967d8736075781d8142c8cc80a99cbd96fae3`.
- Repository observé avant batch : `README.md` uniquement.
- Création de la documentation initiale sous `docs/`.
- Formalisation des invariants fonctionnels et techniques.
- Définition d'une roadmap par batches testables.
- Correction prévue du placeholder du repository dans `README.md`.

Aucune implémentation Kraken, LLM, Risk Engine, Paper Broker ou moteur de trading n'est introduite par ce batch.
