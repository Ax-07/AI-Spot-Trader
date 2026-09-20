# AI Spot Trader

AI Spot Trader est une application expérimentale de **trading crypto SPOT pilotée par un agent IA unique**.

Le projet étudie jusqu'où un agent IA peut prendre des décisions de trading autonomes à partir d'un état de marché et de portefeuille structurés, tout en restant encadré par un **Risk Engine déterministe** qui conserve l'autorité finale avant toute exécution.

> **Statut du projet :** le Batch 08 — Boucle autonome est intégré sur `main` au commit `8deb72faeeaa1ac065189480c64ba16410c0d451` (`feat: add autonomous trading loop`). La prochaine étape prévue est le Batch 09 — Persistance et journal d'audit. Les premières versions restent exclusivement en **PAPER trading**.

## Principes du projet

- Exchange initial : **Kraken**.
- Trading **SPOT uniquement**.
- Aucun short, levier, margin, future ou perpetual.
- Actions stratégiques : `BUY`, `SELL`, `HOLD`.
- Impossible de vendre un actif non détenu.
- Un seul agent IA conserve la décision stratégique et propose la taille des BUY/SELL.
- Le Risk Engine ne crée aucun signal et ne choisit jamais spontanément un actif ou un sens de trade.
- Le **Risk Engine déterministe** peut autoriser, réduire ou refuser une proposition avant exécution.
- Aucune sortie LLM ne déclenche directement un appel Broker ou un ordre Kraken.
- Toutes les décisions, y compris `HOLD`, doivent pouvoir être journalisées.
- Frais, spread et slippage sont explicitement modélisés dans l'exécution PAPER.
- Le passage au **LIVE** sera explicite, séparé du PAPER et traité dans une phase ultérieure.

Principe central : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Agent IA

Les premiers tests utilisent **GPT-5.6 Luna** (`gpt-5.6-luna`). La même implémentation permet de sélectionner **GPT-5.6 Sol** (`gpt-5.6-sol`) par configuration sans dupliquer l'agent.

Le port canonique reste :

```python
LLMProvider.generate_decision(agent_input: AgentInput) -> DecisionCandidate
```

Le modèle produit uniquement :

```text
action = BUY | SELL | HOLD
symbol
proposed_quantity   # nombre > 0 pour BUY/SELL, null pour HOLD
rationale           # texte optionnel, jamais une commande
```

`decision_id`, `cycle_id` et `created_at` restent sous contrôle applicatif. Le symbole doit être exactement celui du `MarketState` fourni. Le prompt système est versionné sous `agent-luna-v1` et l'adapter OpenAI utilise la Responses API avec Structured Outputs stricts.

Le niveau d'agressivité est un entier de **1 à 10**. Son mapping stratégique exact reste volontairement ouvert ; l'orchestrateur du Batch 08 le transmet tel quel à `AgentInput` et ne modifie jamais la quantité stratégique en fonction de cette valeur.

## Objectif expérimental

Le projet conserve une cible expérimentale de **+4 % de rendement journalier** comme objectif de recherche et de mesure. Cette cible n'est ni une promesse ni une garantie et n'impose jamais de trader.

## Architecture

Le **backend constitue l'application de trading**. Le frontend est uniquement un cockpit de contrôle et de visualisation : le fermer ou le redémarrer ne doit jamais arrêter le moteur.

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
   Market State --------+
                        |
 Portfolio State -------+--> AgentInput --> Agent Luna/Sol
                                           BUY / SELL / HOLD
                                           + quantité proposée
                                                   |
                                                   v
                                              Risk Engine
                                       ALLOW / MODIFY / REJECT
                                                   |
                           REJECT/HOLD ------------+---- tradable
                           aucun Broker                  |
                                                       v
                                              ExecutionIntent
                                                créé par Risk
                                                       |
                                              même MarketState
                                                       |
                                                       v
                                                Paper Broker
                                                       |
                                              Fill(s) + Portfolio
```

Aucun chemin direct entre l'agent IA et Kraken n'existe. Le Paper Broker n'interroge pas Kraken : le `MarketState` utilisé pour le pricing lui est fourni explicitement.

## Batch 08 — Boucle autonome PAPER

Le patch ajoute deux niveaux d'orchestration dans `ai_spot_trader.trading` :

```text
TradingCycleRunner.run_cycle()
        |
        v
un cycle exact et testable

TradingEngine
        |
        v
répète run_cycle séquentiellement
```

### Sémantique d'un cycle

Un cycle :

1. génère un `cycle_id` via une factory UUID injectable ;
2. capture exactement un `MarketState` pour le symbole configuré ;
3. capture le `PortfolioState` PAPER courant ;
4. crée `AgentInput` avec ces deux snapshots et l'agressivité injectée ;
5. appelle l'agent ;
6. passe la décision et **les mêmes snapshots** au Risk Engine ;
7. n'appelle le Broker que si Risk a produit un `ExecutionIntent` ;
8. passe **le même `MarketState`** au Broker ;
9. capture un `PortfolioState` post-exécution après des fills valides.

Aucun refresh marché caché n'a lieu entre Agent, Risk et Broker. L'orchestrateur ne construit jamais d'`ExecutionIntent`, ne modifie jamais action/symbole/quantité et ne contient aucune stratégie de trading déterministe.

### HOLD, REJECT, MODIFY et ALLOW

- `HOLD` suit Agent -> Risk -> `ALLOW + HOLD_NO_EXECUTION` et n'appelle jamais le Broker.
- `REJECT` est un résultat métier normal, sans intent ni Broker.
- `MODIFY` transmet exactement l'intent et la quantité produits par Risk.
- `ALLOW` transmet exactement l'intent produit par Risk.

### Erreurs et timeouts

Les erreurs techniques Market, Portfolio/Input, Agent, Risk, Broker ou snapshot post-exécution sont représentées par un résultat de cycle `FAILED` avec étape et type d'erreur. Une erreur LLM n'est jamais convertie en `HOLD`.

Les I/O Market, Agent et Broker sont entourées de timeouts explicitement injectés et strictement positifs. Risk reste synchrone et déterministe, sans timeout artificiel. Les messages d'exception distants ne sont pas recopiés dans le résultat d'orchestration.

### Séquentialité et cadence

Le runner possède un verrou de cycle. Un appel manuel et la boucle autonome utilisant le même runner ne peuvent donc jamais se chevaucher.

La boucle respecte :

```text
cycle N terminé
    |
attente cadence
    |
cycle N+1
```

Elle ne tente jamais de rattraper une cadence dépassée. La valeur de cadence est injectée au `TradingEngine` et doit être positive ; aucune valeur produit n'est codée en dur ni ajoutée à `Settings` dans ce batch.

`start()` refuse une seconde loop simultanée. `stop()` réveille immédiatement l'attente de cadence et attend coopérativement le cycle borné déjà en cours. `AppRuntime` peut posséder un moteur injecté et l'arrête lors du shutdown FastAPI. Aucun moteur réel n'est démarré automatiquement à l'import ou à la création de l'application.

## État backend après intégration du Batch 08

```text
backend/
  src/ai_spot_trader/
    agent/
    api/
    broker/
    core/
      clock.py
      config.py
      runtime.py
    domain/
    integrations/kraken/
    market/
    portfolio/
    risk/
    trading/
      __init__.py
      engine.py
    main.py
  tests/
    test_trading_engine.py
```

Le Batch 08 n'ajoute ni PostgreSQL, ni route FastAPI de contrôle trading, ni WebSocket cockpit, ni frontend, ni scanner multi-paires, ni API Kraken privée, ni LIVE.

## Configuration

Le patch n'invente aucune nouvelle valeur produit. Les réglages existants OpenAI/Kraken restent inchangés. La cadence et les timeouts du cycle sont des dépendances explicites de composition ; la paire, le capital PAPER, la RiskPolicy et les coûts PAPER restent eux aussi explicitement fournis par l'appelant.

## Démarrage et validation locale

Toutes les commandes sont prévues depuis la racine du repository sous PowerShell :

```powershell
backend\.venv\Scripts\python.exe -m pytest backend
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m mypy backend\src backend\tests
git diff --check
```

Aucun appel OpenAI ou Kraken réel n'est requis pour les tests automatisés.

## Documentation

- `docs/00_ETAT_ACTUEL.md` — mémoire courte de reprise.
- `docs/01_PROJECT_MASTER.md` — spécification principale.
- `docs/02_ARCHITECTURE_TECHNIQUE.md` — architecture et frontières techniques.
- `docs/03_AGENT_TRADING_RISK.md` — responsabilités Agent/Risk/Trading.
- `docs/09_ROADMAP_DEVELOPPEMENT.md` — roadmap.
- `docs/10_DECISIONS_ET_CHANGELOG.md` — ADR et changelog.

## Sécurité

- Aucun secret ou clé API ne doit être versionné, journalisé ou injecté dans les prompts.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- PAPER et LIVE restent explicitement séparés.
- Toute exécution future doit continuer à passer par Risk ; aucune sortie LLM ne doit atteindre directement un Broker.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et de développement. Il ne constitue pas un conseil financier et ne garantit aucun résultat de trading.
