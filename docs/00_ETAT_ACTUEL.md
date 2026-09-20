# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité le 20 septembre 2026 : `caff3851d8299630f328b955c69eb31eb11baef0`
- Commit : `feat: add Luna agent provider`
- Batch 07 intégré sur `main`.

## Validation finale connue du Batch 07 avant intégration

Validation locale Windows confirmée par l'utilisateur :

- `pytest backend` : **168 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 54 source files** ;
- `git diff --check` : aucune erreur ;
- uniquement les warnings habituels LF → CRLF sous Windows ;
- 2 warnings de dépréciation FastAPI/Starlette sans échec.

## État courant intégré

- Backend Python/FastAPI/Pydantic, Kraken public, Market State et Portfolio State PAPER.
- Paper Broker déterministe avec frais, spread et slippage en `Decimal`.
- Risk Engine déterministe canonique avec `ALLOW`, `MODIFY`, `REJECT`.
- `DecisionCandidate.proposed_quantity` obligatoire pour BUY/SELL et interdite pour HOLD.
- Agent canonique derrière `LLMProvider` avec `OpenAIDecisionProvider` commun Luna/Sol.
- Prompt versionné `agent-luna-v1` et Structured Outputs stricts via OpenAI Responses API.
- Le LLM ne produit que action, symbole, quantité proposée et rationale ; IDs/timestamps restent applicatifs.
- L'Agent est limité au symbole du `MarketState` fourni.
- Aucun chemin direct LLM → Risk/Broker/Kraken ; aucune exécution hors `ExecutionIntent` autorisé par Risk.
- Aucun LIVE, aucune API Kraken privée, aucune persistance et aucune boucle autonome.

## Dernier batch intégré

**Batch 07 — Agent Luna** : intégré sur `main` au HEAD `caff3851d8299630f328b955c69eb31eb11baef0`.

## Prochain batch

**Batch 08 — Boucle autonome** : orchestration explicite `MarketState + PortfolioState -> Agent -> Risk -> Paper Broker`.

## Points encore à décider

- Capital PAPER initial et devise de référence produit.
- Univers initial de paires Kraken.
- Cadence de la boucle de décision.
- Valeurs produit des limites Risk.
- Mapping exact de l'agressivité 1–10.
- Valeurs de référence fee/spread/slippage PAPER.
- Persistance, frontière de journée et analytics P&L/drawdown.
