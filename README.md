# AI Spot Trader

AI Spot Trader est une application expérimentale de **trading crypto SPOT pilotée par un agent IA unique**.

Le projet étudie jusqu'où un agent IA peut prendre des décisions de trading autonomes à partir d'un état de marché et de portefeuille structurés, tout en restant encadré par un **Risk Engine déterministe** qui conserve l'autorité finale avant toute exécution.

> **Statut du projet :** le Batch 07 — Agent Luna est intégré sur `main` au commit `caff3851d8299630f328b955c69eb31eb11baef0` (`feat: add Luna agent provider`). Le Batch 08 — Boucle autonome est la prochaine étape prévue. Les premières versions restent exclusivement en **PAPER trading**.

## Principes du projet

- Exchange initial : **Kraken**.
- Trading **SPOT uniquement**.
- Aucun short, levier, margin, future ou perpetual.
- Actions stratégiques de l'agent : `BUY`, `SELL`, `HOLD`.
- Impossible de vendre un actif non détenu.
- Un seul agent IA conserve la décision stratégique et propose aussi la taille des BUY/SELL.
- Le Risk Engine ne crée aucun signal et ne choisit jamais spontanément un actif ou un sens de trade.
- Le **Risk Engine déterministe** peut autoriser, réduire ou refuser une proposition avant exécution.
- Aucune sortie LLM ne peut déclencher directement un ordre Kraken ou un appel Broker.
- Toutes les décisions, y compris `HOLD`, doivent être journalisées.
- Les frais, le spread et le slippage sont explicitement modélisés dans l'exécution PAPER.
- Le passage au **LIVE** sera explicite, séparé du PAPER et traité dans une phase ultérieure.

Principe central : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Agent IA

Les premiers tests utilisent **GPT-5.6 Luna** (`gpt-5.6-luna`) afin de réduire les coûts d'expérimentation. La même implémentation permet de sélectionner **GPT-5.6 Sol** (`gpt-5.6-sol`) par configuration sans modifier le moteur métier ni dupliquer l'agent.

Le port canonique reste :

```python
LLMProvider.generate_decision(agent_input: AgentInput) -> DecisionCandidate
```

Le Batch 07 garde une frontière fournisseur étroite. Le modèle ne produit que :

```text
action = BUY | SELL | HOLD
symbol
proposed_quantity   # nombre > 0 pour BUY/SELL, null pour HOLD
rationale           # texte optionnel, jamais une commande
```

Les métadonnées techniques restent contrôlées par l'application : `decision_id` via une factory UUID injectable, `cycle_id` recopié depuis `AgentInput` et `created_at` via `Clock`.

L'agent est limité au symbole de `agent_input.market_state.symbol`. Une sortie proposant un autre actif est rejetée avant création d'un `DecisionCandidate` utilisable.

Le prompt système est versionné sous `agent-luna-v1`. Il rappelle SPOT/PAPER uniquement, l'interdiction du short/levier/margin/futures/perpetuals, le SELL couvert, l'absence de données inventées, le caractère non obligatoire de la cible expérimentale +4 %/jour et l'absence de chemin d'exécution direct.

L'adapter OpenAI utilise la **Responses API** avec **Structured Outputs** (`json_schema`, `strict=true`). La sortie est reparsée et revalidée côté application sans réparation ou coercition stratégique silencieuse.

Le niveau d'agressivité est prévu sur une échelle configurable de **1 à 10**. Son mapping exact reste à définir. Aucune valeur d'agressivité ne pourra contourner les invariants absolus SPOT/PAPER ou une limite Risk active.

## Configuration OpenAI

La clé OpenAI n'est jamais versionnée :

```text
AI_SPOT_TRADER_LLM_MODEL=gpt-5.6-luna
AI_SPOT_TRADER_OPENAI_API_KEY=
AI_SPOT_TRADER_OPENAI_BASE_URL=https://api.openai.com/v1
AI_SPOT_TRADER_OPENAI_TIMEOUT_SECONDS=30
```

`AI_SPOT_TRADER_OPENAI_API_KEY` est chargé comme `SecretStr`. Aucun secret n'est inclus dans les prompts, les exceptions ou les tests. Aucun appel OpenAI réel n'est requis par la suite automatisée.

Aucun retry automatique n'est ajouté au Batch 07. Les erreurs transport, les réponses fournisseur incomplètes/refusées et les sorties stratégiques invalides restent explicites.

## Objectif expérimental

Le projet conserve une cible expérimentale de **+4 % de rendement journalier** comme objectif de recherche et de mesure. Cette cible n'est ni une promesse ni une garantie ; les résultats doivent être mesurés honnêtement, sans look-ahead ni sélection rétrospective.

Cette cible n'est jamais une obligation de trader.

## Architecture

Le **backend constitue l'application de trading**. Il doit fonctionner indépendamment du frontend.

Le frontend est uniquement un cockpit de contrôle et de visualisation : le fermer ou le redémarrer ne doit jamais arrêter le moteur de trading.

Stack décidée :

- **Backend** : Python, `asyncio`, FastAPI, Pydantic.
- **Frontend** : Next.js, TypeScript, shadcn/ui, Tailwind CSS.
- **Communication** : REST et WebSocket selon le besoin.
- **Base cible** : PostgreSQL.
- **Intégrations externes** : Kraken et le fournisseur LLM derrière des interfaces dédiées.

Rust ne sera introduit que si un besoin mesuré ou une décision architecturale explicite le justifie.

```text
Kraken public data
        |
        v
normalized observations
        |
        v
   Market State --------+
                        |
 Portfolio State -------+--> Agent Luna/Sol
                              BUY / SELL / HOLD
                         + quantité proposée BUY/SELL
                                     |
                                     v
                                Risk Engine
                         ALLOW / MODIFY / REJECT
                                     |
                         +-----------+-----------+
                         |                       |
                  aucun intent              ExecutionIntent
                   si REJECT                 PAPER seulement
                                                 |
                                      Market State pricing
                                                 |
                                                 v
                                           Paper Broker
                                                 |
                                        Fill + Portfolio
                                                 |
                                                 v
                                        Journal / Analytics
```

Aucun chemin direct entre l'agent IA et Kraken ne doit exister. Le package `agent` ne connaît ni Risk, ni Broker, ni Kraken, ni FastAPI. Le Paper Broker n'interroge pas Kraken : le `MarketState` utilisé pour le pricing lui est fourni explicitement.

## État backend actuel

Le backend intégré contient notamment :

```text
backend/
  src/ai_spot_trader/
    agent/
      __init__.py
      errors.py
      openai_client.py
      prompt.py
      provider.py
    api/
    broker/
      errors.py
      paper.py
      pricing.py
    core/
      clock.py
      config.py
      runtime.py
    domain/
      enums.py
      models.py
      ports.py
      symbols.py
    integrations/kraken/
    market/
      errors.py
      state.py
    portfolio/
      errors.py
      ledger.py
    risk/
      __init__.py
      engine.py
      errors.py
      policy.py
    main.py
  tests/
  pyproject.toml
```

Composants disponibles :

- contrats Pydantic stricts et timestamps UTC aware ;
- données publiques Kraken normalisées ;
- `MarketStateBuilder` déterministe multi-horizon avec no look-ahead ;
- `PaperPortfolioLedger` mémoire avec état initial explicitement injecté ;
- `PaperBroker` full-fill déterministe avec frais, spread et slippage auditables ;
- `DecisionCandidate.proposed_quantity` comme sizing stratégique avant Risk ;
- `RiskPolicy` injectée sans limites produit cachées ;
- `RiskEngine` déterministe avec `ALLOW`, `MODIFY`, `REJECT` ;
- `RiskAssessment` avec quantités demandée/autorisée, `RiskLimit` évaluées et `RiskReason` ;
- `ExecutionIntent` PAPER créé uniquement après autorisation Risk ;
- `OpenAIDecisionProvider` derrière le port `LLMProvider` ;
- `OpenAIResponsesClient` testable, sans tool-calling et sans exécution ;
- aucune API Kraken privée, aucun ordre réel et aucun LIVE.

FastAPI expose toujours uniquement le healthcheck `GET /health` à ce stade. Le frontend reste un cockpit bootstrap sans orchestration du moteur. La boucle autonome reste au Batch 08.

## Risk Engine initial

Le Batch 06 conserve une frontière volontairement étroite :

- aucune limite chiffrée produit n'est codée en dur ;
- `max_order_notional`, whitelist de paires et seuil métier stale sont optionnels et injectés ;
- la réduction de quantité est désactivée par défaut et doit être explicitement autorisée par la policy ;
- un `MODIFY` peut uniquement **réduire** une quantité ; il ne change jamais action ni symbole ;
- BUY vérifie le cash nécessaire en anticipant les mêmes frais/spread/slippage que le Paper Broker ;
- SELL vérifie la quantité réellement disponible ;
- les snapshots marché et portefeuille postérieurs à la décision sont refusés ;
- HOLD reste une décision stratégique valide et ne crée jamais d'`ExecutionIntent` ;
- drawdown, daily loss, VaR, corrélations et exposition multi-actifs ne sont pas fabriqués sans données adaptées.

## Modèle PAPER initial

Le Paper Broker utilise un modèle simple et reproductible :

- une intention BUY/SELL donne un fill complet immédiat ou un rejet explicite ;
- aucune simulation d'order book, partial fill, ordre limite ou hasard ;
- calculs financiers en `Decimal` ;
- `spread_bps` = impact adverse **par côté** ;
- `slippage_bps` = impact adverse additionnel par côté ;
- frais calculés sur le notional exécuté ;
- aucun capital initial, quote asset ou niveau de frais produit n'est codé en dur : ils sont injectés explicitement.

Le Risk Engine anticipe les coûts prévisibles pour la solvabilité d'un BUY, mais le Paper Broker reste la dernière frontière d'intégrité et réalise seul la mutation du portefeuille.

## Démarrage local

### Backend

Toutes les commandes de développement sont prévues pour être exécutées depuis la racine du repository sous PowerShell.

```powershell
uv venv --python 3.13.14 --seed backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
backend\.venv\Scripts\python.exe -m pytest backend
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m mypy backend\src backend\tests
git diff --check
```

Le package backend accepte Python `>=3.12`. Aucun smoke test OpenAI réel n'est requis pour valider le Batch 07.

### Frontend

Dans un second terminal, toujours depuis la racine :

```powershell
pnpm --dir frontend install
pnpm --dir frontend dev
```

Checks frontend utiles :

```powershell
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

`pnpm` est le gestionnaire de paquets frontend canonique du projet.

## Documentation

- [`docs/00_ETAT_ACTUEL.md`](docs/00_ETAT_ACTUEL.md) — mémoire courte pour reprendre le projet rapidement.
- [`docs/01_PROJECT_MASTER.md`](docs/01_PROJECT_MASTER.md) — spécification fonctionnelle et principes généraux.
- [`docs/02_ARCHITECTURE_TECHNIQUE.md`](docs/02_ARCHITECTURE_TECHNIQUE.md) — architecture et frontières techniques.
- [`docs/03_AGENT_TRADING_RISK.md`](docs/03_AGENT_TRADING_RISK.md) — responsabilités de l'agent, du trading et du Risk Engine.
- [`docs/09_ROADMAP_DEVELOPPEMENT.md`](docs/09_ROADMAP_DEVELOPPEMENT.md) — roadmap par batches cohérents et testables.
- [`docs/10_DECISIONS_ET_CHANGELOG.md`](docs/10_DECISIONS_ET_CHANGELOG.md) — décisions architecturales et changelog.

## Sécurité

- Aucun secret ou clé API ne doit être versionné, journalisé ou injecté dans les prompts.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- PAPER et LIVE doivent rester explicitement séparés.
- Toute exécution LIVE future devra passer par des garde-fous dédiés et une activation volontaire.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et de développement. Il ne constitue pas un conseil financier et ne garantit aucun résultat de trading.
