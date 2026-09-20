# 00 — État actuel

> Mémoire courte de reprise. Ce fichier doit rester synthétique et être mis à jour après chaque batch important.

## Référence intégrée auditée

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité le 20 septembre 2026 : `d3271d6404ea2af38a42ff09e5a1df1eed5e141e`
- Commit : `feat: add deterministic risk engine`
- Batch 06 intégré sur `main`.

## Validation finale connue du Batch 06 avant intégration

Validation locale Windows confirmée par l'utilisateur :

- `pytest backend` : **131 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 47 source files** ;
- `git diff --check` : aucune erreur ;
- uniquement les warnings habituels LF → CRLF sous Windows ;
- 2 warnings de dépréciation FastAPI/Starlette sans échec.

## État intégré avant Batch 07

- Backend Python/FastAPI/Pydantic, Kraken public, Market State et Portfolio State PAPER.
- Paper Broker déterministe avec frais, spread et slippage en `Decimal`.
- `DecisionCandidate.proposed_quantity` obligatoire pour BUY/SELL et interdite pour HOLD.
- Risk Engine déterministe canonique avec `ALLOW`, `MODIFY`, `REJECT`.
- Risk ne peut jamais augmenter une quantité ni changer action/symbole.
- Seul un `ExecutionIntent` autorisé peut atteindre le Paper Broker.
- Aucun LIVE, aucune API Kraken privée, aucune persistance et aucune boucle autonome.

## Patch Batch 07 préparé dans cette livraison

- Nouveau package `ai_spot_trader.agent` derrière le port `LLMProvider` existant.
- Provider unique Luna/Sol : `OpenAIDecisionProvider` ; aucun agent parallèle pour Sol.
- Prompt versionné `agent-luna-v1`, minimal et auditable.
- OpenAI Responses API + Structured Outputs JSON Schema stricts.
- Modèle initial exact : `gpt-5.6-luna` ; `gpt-5.6-sol` reste sélectionnable via `Settings`.
- Schéma fournisseur limité à `action`, `symbol`, `proposed_quantity`, `rationale`.
- `decision_id`, `cycle_id` et `created_at` restent contrôlés par l'application.
- Le symbole LLM doit être exactement celui de `AgentInput.market_state.symbol`.
- Aucun enrichissement marché, lookup Kraken, appel Risk/Broker ou tool-calling depuis l'agent.
- Erreurs distinctes : transport, enveloppe fournisseur, sortie structurée invalide, invariant Agent.
- Aucun retry automatique dans ce batch.
- Clé OpenAI optionnelle dans `Settings` via `SecretStr` et environnement uniquement.
- Aucun nouveau package runtime : l'adapter REST réutilise `httpx` déjà présent.

## Validation du Batch 07

Validation ChatGPT ciblée :

- suite Agent/OpenAI/configuration : **42 tests passés** ;
- aucun appel réseau réel ; OpenAI simulé via `httpx.MockTransport` ;
- `compileall`, longueur des lignes et espaces de fin de ligne : OK.

Validation locale Windows finale confirmée par l'utilisateur :

- `pytest backend` : **168 tests passés** ;
- Ruff : **All checks passed** ;
- mypy : **Success: no issues found in 54 source files** ;
- `git diff --check` : aucune erreur ;
- uniquement les warnings habituels LF → CRLF sous Windows ;
- 2 warnings de dépréciation FastAPI/Starlette sans échec.

## Dernier batch intégré

**Batch 06 — Risk Engine** : intégré sur `main` au HEAD `d3271d6404ea2af38a42ff09e5a1df1eed5e141e`.

## Batch en cours

**Batch 07 — Agent Luna** : patch préparé et validation locale finale réussie, **non encore intégré**.

## Prochaine étape après intégration

**Batch 08 — Boucle autonome** : orchestration explicite `MarketState + PortfolioState -> Agent -> Risk -> Paper Broker`.

## Points encore à décider

- Capital PAPER initial et devise de référence produit.
- Univers initial de paires Kraken.
- Cadence de la boucle de décision.
- Valeurs produit des limites Risk.
- Mapping exact de l'agressivité 1–10.
- Valeurs de référence fee/spread/slippage PAPER.
- Persistance, frontière de journée et analytics P&L/drawdown.
