# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité, base du Batch 06 : `c24551d36a863abbb5fdb86b79658b235c852772`
- Commit : `feat: add paper portfolio and broker` — 20 septembre 2026
- Batch 05 intégré sur `main`.

## Validation finale du Batch 05 avant intégration

Validation locale Windows confirmée :

- `pytest backend` : **92 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 40 source files** ;
- `git diff --check` : aucune erreur ;
- uniquement les warnings habituels LF → CRLF sous Windows ;
- 2 warnings de dépréciation FastAPI/Starlette dans les dépendances de test, sans échec ;
- aucun test réseau requis.

## État courant intégré

- Projet expérimental de trading crypto SPOT piloté par un agent IA unique.
- Kraken comme exchange initial ; premières versions exclusivement en PAPER.
- Backend Python + `asyncio` + FastAPI + Pydantic ; frontend Next.js indépendant du moteur.
- Adapter public Kraken Spot, Market State déterministe, Portfolio State PAPER et Paper Broker intégrés.
- `PaperPortfolioLedger` est l'état mutable PAPER ; `PaperBroker` fait un full-fill immédiat ou rejette.
- Frais, spread et slippage PAPER sont injectés, calculés en `Decimal` et audités dans les `Fill`.
- Aucun secret, aucun LIVE, aucune persistance et aucun appel LLM réel à ce stade.

## Patch Batch 06 préparé dans cette livraison

- `DecisionCandidate` porte une `proposed_quantity` obligatoire pour BUY/SELL et interdite pour HOLD.
- Nouveau package `ai_spot_trader.risk` avec `RiskPolicy`, `RiskEngine` et `RiskResult`.
- Résultats explicites `ALLOW`, `MODIFY` ou `REJECT`, avec codes `RiskReason` stables et auditables.
- `RiskAssessment` enregistre quantité demandée, quantité autorisée et `evaluated_limits`.
- Un `ExecutionIntent` PAPER n'est créé que pour un BUY/SELL autorisé ; HOLD reste valide mais sans intention.
- Les réductions de quantité sont désactivées par défaut et nécessitent `allow_quantity_reduction=True`.
- Contrôles implémentés : symbole/snapshot cohérents, whitelist optionnelle, fraîcheur métier optionnelle, max notional, cash BUY et disponibilité SELL.
- Le cash BUY anticipe les mêmes frais/spread/slippage que le Paper Broker grâce à une estimation PAPER factorisée et sans effet de bord.
- Max notional = notional de référence `last_price * quantity`; les coûts d'exécution restent traités séparément pour la solvabilité BUY.
- Aucun seuil chiffré produit n'est ajouté à `Settings` ; toutes les limites restent injectées.
- Aucun drawdown/daily loss, VaR, corrélation, exposition multi-actifs, stratégie, LLM, scheduler, Kraken ou LIVE dans Risk.
- No look-ahead : `MarketState.as_of` et `PortfolioState.as_of` ne peuvent pas être postérieurs à `DecisionCandidate.created_at`.

## Validation effectuée dans l'environnement ChatGPT pour le Batch 06

- Python `3.13.5` ;
- suite ciblée domaine + Risk + régression Paper Broker : **77 tests passés** ;
- `compileall` : OK ;
- contrôle des lignes Python du patch `<= 100` : OK ;
- aucun test réseau requis ou exécuté ;
- Ruff et mypy non disponibles dans cet environnement : validation locale requise.

## Dernier batch intégré

**Batch 05 — Portfolio State + Paper Broker** : intégré sur `main` au HEAD `c24551d36a863abbb5fdb86b79658b235c852772`.

## Batch en cours

**Batch 06 — Risk Engine** : patch préparé et tests ciblés réussis ; validation locale Windows et intégration Git restent à effectuer.

## Prochain batch recommandé

**Batch 07 — Agent Luna**, uniquement après extraction, validation locale et intégration du Batch 06.

## Points encore à décider

- Capital PAPER initial et devise de référence produit.
- Univers d'actifs/paires Kraken initial.
- Cadence de la boucle de décision.
- Valeurs produit des limites Risk (`max_order_notional`, stale métier, whitelist, etc.).
- Mapping exact de l’agressivité 1–10.
- Exposition portefeuille globale lorsque plusieurs prix canoniques seront disponibles simultanément.
- Max drawdown / daily loss lorsque l'historique P&L requis existera.
- Valeurs de référence fee/spread/slippage PAPER pour les expériences.
- Frontière journalière des statistiques et politique de rétention/persistance.
