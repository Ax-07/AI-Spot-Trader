# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité, base du Batch 05 : `73acc4758427ea7575ddf0a43505e1c95fab5e9c`
- Commit : `feat: add deterministic market state` — 20 septembre 2026
- Batch 04 intégré sur `main`.

## État courant intégré

- Projet expérimental de trading crypto SPOT piloté par un agent IA unique.
- Kraken comme exchange initial ; premières versions exclusivement en PAPER.
- Backend Python + `asyncio` + FastAPI + Pydantic ; frontend Next.js indépendant du moteur.
- Agent stratégique ; Risk Engine déterministe avec autorité finale.
- Adapter public Kraken Spot intégré, sans API privée ni ordre.
- `MarketObservation`, `MarketStateBuilder`, `MarketContext` et fenêtres 5 min / 30 min intégrés.
- Market State déterministe en `Decimal`, historique mémoire borné, ordre temporel strict et no look-ahead.
- Aucun secret, aucun LIVE, aucune persistance, aucun Risk Engine fonctionnel ni agent LLM réel à ce stade.

## Validation finale du Batch 04 avant intégration

Validation locale Windows confirmée :

- Python `3.13.14` ;
- `pytest` : **59 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **OK sur 24 fichiers source** ;
- `git diff --check` : aucune erreur ;
- uniquement les warnings habituels LF → CRLF sous Windows ;
- 2 warnings de dépréciation FastAPI/Starlette dans les dépendances de test, sans échec ;
- aucun test réseau requis ;
- working tree propre après commit/push.

## Patch Batch 05 préparé dans cette livraison

- `PortfolioState` conserve des rôles d'actifs explicites et non chevauchants : `balances` pour les actifs de règlement disponibles, `positions` pour les actifs détenus/vendables.
- Nouveau package `ai_spot_trader.portfolio` avec ledger PAPER mémoire, déterministe, sans persistance et mutations copy-on-write atomiques.
- État initial obligatoirement injecté ; aucun capital PAPER ou devise globale n'est imposé.
- Nouveau package `ai_spot_trader.broker` avec `PaperBroker` derrière le port canonique `Broker`.
- Le port `Broker` reçoit explicitement le `MarketState` utilisé comme contexte de pricing ; aucun lookup Kraken caché.
- Fill immédiat et complet ou rejet explicite ; aucun order book simulé, partial fill, ordre limite, pending order ou aléatoire.
- Modèle de coûts injecté : fee rate, spread en bps comme impact adverse par côté et slippage en bps additionnel.
- BUY : débit quote = notional exécuté + frais ; crédit exact de la position base.
- SELL : débit exact de la position disponible ; crédit quote = notional exécuté - frais.
- Rejets atomiques pour cash insuffisant, position insuffisante/non détenue, quote balance absente, symbole incompatible, pricing futur ou configuration invalide.
- `Fill` enrichi avec `market_state_id`, timestamp de pricing, prix de référence, prix exécuté, notional, frais, coût spread et coût slippage.
- Aucun arrondi Kraken, aucune quantification silencieuse, aucun `float`, aucun P&L complet et aucune base de coût introduite.
- Aucun paramètre Batch 05 ajouté à `Settings` ou `.env.example` : capital, devise et coûts restent injectés explicitement.

## Validation finale du Batch 05 avant intégration

Validation locale Windows confirmée après application du correctif mypy :

- `pytest backend` : **92 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 40 source files** ;
- `git diff --check` : aucune erreur ;
- uniquement les warnings habituels LF → CRLF sous Windows ;
- 2 warnings de dépréciation FastAPI/Starlette dans les dépendances de test, sans échec ;
- aucun test réseau requis.

Validation complémentaire dans l'environnement ChatGPT : Python `3.13.5`, suite ciblée **64/64**, `compileall` OK et contrôle des lignes Python du patch `<= 100` OK.

## Dernier batch intégré

**Batch 04 — Market State** : intégré sur `main` au HEAD `73acc4758427ea7575ddf0a43505e1c95fab5e9c`.

## Batch en cours

**Batch 05 — Portfolio State + Paper Broker** : validation locale complète réussie ; intégration Git par l'utilisateur encore à effectuer.

## Prochain batch recommandé

**Batch 06 — Risk Engine**, uniquement après extraction, validation locale et intégration du Batch 05.

## Points encore à décider

- Capital PAPER initial et devise de référence produit.
- Univers d'actifs/paires Kraken initial.
- Cadence de la boucle de décision.
- Seuil métier global de fraîcheur/stale du futur Risk Engine.
- Représentation du sizing stratégique dans `DecisionCandidate`.
- Limites chiffrées du Risk Engine et traduction exacte de l’agressivité 1–10.
- Barème de frais PAPER de référence pour les expériences ; le moteur accepte déjà un taux injecté.
- Valeurs de spread/slippage PAPER de référence pour les expériences ; le moteur accepte déjà des bps injectés.
- Frontière journalière des statistiques et politique de rétention/persistance.
