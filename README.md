# AI Spot Trader

AI Spot Trader est une application expérimentale de **trading crypto SPOT pilotée par un agent IA unique**.

Le projet étudie jusqu'où un agent IA peut prendre des décisions de trading autonomes à partir d'un état de marché et de portefeuille structurés, tout en restant encadré par un **Risk Engine déterministe** qui conserve l'autorité finale avant toute exécution.

> **Statut du projet :** le Batch 09 — Persistance et journal d'audit est intégré sur `main` au commit `c53d04f14bcda82359d11c2e14fc1eb601ed14e0` (`feat: add durable audit persistence`). La prochaine étape prévue est le Batch 10 — API FastAPI de contrôle. Les premières versions restent exclusivement en **PAPER trading**.

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
- Toutes les décisions, y compris `HOLD`, sont auditables et peuvent être persistées durablement.
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

Le niveau d'agressivité est un entier de **1 à 10**. Son mapping stratégique exact reste volontairement ouvert ; l'orchestrateur le transmet tel quel à `AgentInput` et ne modifie jamais la quantité stratégique en fonction de cette valeur.

## Objectif expérimental

Le projet conserve une cible expérimentale de **+4 % de rendement journalier** comme objectif de recherche et de mesure. Cette cible n'est ni une promesse ni une garantie et n'impose jamais de trader.

## Architecture

Le **backend constitue l'application de trading**. Le frontend est uniquement un cockpit de contrôle et de visualisation : le fermer ou le redémarrer ne doit jamais arrêter le moteur.

Stack décidée :

- **Backend** : Python, `asyncio`, FastAPI, Pydantic.
- **Persistance** : PostgreSQL, SQLAlchemy 2 async, `asyncpg`, Alembic.
- **Frontend** : Next.js, TypeScript, shadcn/ui, Tailwind CSS.
- **Communication** : REST et WebSocket selon le besoin.
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
                                                       |
                                                       v
                                             TradingCycleResult
                                                       |
                                                       v
                                      AuditedTradingCycleRunner
                                                       |
                                                       v
                                   PostgreSQL durable audit journal
```

Aucun chemin direct entre l'agent IA et Kraken n'existe. Le Paper Broker n'interroge pas Kraken : le `MarketState` utilisé pour le pricing lui est fourni explicitement. La persistance n'est jamais une source de stratégie ; elle conserve les faits produits par les composants canoniques.

## Batch 08 — Boucle autonome PAPER

`TradingCycleRunner.run_cycle()` exécute exactement un cycle PAPER et `TradingEngine` répète ce runner strictement séquentiellement.

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

Les erreurs techniques Market, Portfolio/Input, Agent, Risk, Broker ou snapshot post-exécution restent des résultats `FAILED`, jamais des HOLD synthétiques.

## Batch 09 — Persistance et journal d'audit

Le package `ai_spot_trader.persistence` introduit une frontière de persistance dédiée sans modifier Agent, Risk ou Broker.

### Stack

- SQLAlchemy 2 async ;
- `asyncpg` pour PostgreSQL ;
- Alembic pour les migrations ;
- `aiosqlite` uniquement dans les tests offline de persistance ;
- PostgreSQL 18 de développement fourni par `docker-compose.yml`.

### Journal durable

`SqlAlchemyCycleAuditRepository` persiste atomiquement le graphe atteint par un `TradingCycleResult` :

```text
audit_cycles
    |
    +--> audit_decisions
    |
    +--> audit_risk_assessments
    |
    +--> audit_execution_intents   # seulement si Risk a produit un intent
             |
             +--> audit_fills      # seulement si exécution
```

Le cycle conserve également les snapshots nécessaires disponibles dans `AgentInput`, le snapshot portfolio post-exécution éventuel, les IDs, timestamps et les métadonnées d'erreur technique sanitizées.

Les modèles métier Pydantic restent canoniques. La base stocke leur représentation JSON/JSONB pour audit et ajoute uniquement les colonnes relationnelles/indexables utiles.

### Idempotence et atomicité

- `cycle_id` est l'identité métier du journal.
- Un replay exactement identique est idempotent et n'ajoute pas de doublon.
- La réutilisation du même `cycle_id` avec un contenu différent déclenche `CycleAuditConflictError`.
- L'écriture d'un graphe de cycle est transactionnelle : une erreur d'écriture provoque un rollback complet.
- `AuditedTradingCycleRunner` enveloppe le runner canonique puis persiste son résultat ; il ne duplique aucune orchestration et ne change aucune décision.

### Limite de reprise après crash

Le Batch 09 **ne garantit pas** un exactly-once global entre mutation du `PaperPortfolioLedger` mémoire et commit PostgreSQL. Un crash dans cette fenêtre peut nécessiter une réconciliation ultérieure.

Le journal durable fournit le socle nécessaire à cette future reprise, mais la reconstruction automatique du ledger, la réconciliation et la politique exacte de recovery restent différées.

## PostgreSQL local avec Docker Desktop

Depuis la racine du repository :

```powershell
docker compose up -d
docker compose ps
```

La configuration versionnée crée un PostgreSQL de développement local avec volume persistant. Le mot de passe présent dans `docker-compose.yml` est uniquement une valeur locale de développement et ne doit pas être réutilisé en production.

Configurer ensuite l'URL SQLAlchemy dans la session PowerShell :

```powershell
$env:AI_SPOT_TRADER_DATABASE_URL="postgresql+asyncpg://ai_spot_trader:local_dev_password@localhost:5432/ai_spot_trader"
```

Appliquer les migrations :

```powershell
python -m alembic -c backend\alembic.ini upgrade head
```

Arrêter PostgreSQL sans supprimer les données :

```powershell
docker compose down
```

`docker compose down -v` supprime le volume et doit être réservé à une réinitialisation volontaire de la base locale.

## Validation du Batch 09

Validation locale Windows confirmée avant intégration fonctionnelle :

```text
pytest backend                    209 tests passés
ruff check backend                All checks passed
mypy backend\src backend\tests  Success, 63 fichiers
git diff --check                  aucune erreur
```

Deux warnings de dépréciation FastAPI/Starlette restent non bloquants.

Validation PostgreSQL réelle confirmée avec Docker Desktop :

- conteneur `ai-spot-trader-postgres` : `healthy` ;
- PostgreSQL : `18.6-bookworm` ;
- Alembic `upgrade head` : réussi ;
- révision appliquée : `0001_audit_journal` ;
- tables créées : `audit_cycles`, `audit_decisions`, `audit_risk_assessments`, `audit_execution_intents`, `audit_fills` et `alembic_version`.

Le commit fonctionnel intégré est :

```text
c53d04f14bcda82359d11c2e14fc1eb601ed14e0
feat: add durable audit persistence
```

## État backend après intégration du Batch 09

```text
backend/
  alembic.ini
  alembic/
    env.py
    versions/
      0001_create_audit_journal.py
  src/ai_spot_trader/
    agent/
    api/
    broker/
    core/
    domain/
    integrations/kraken/
    market/
    persistence/
      __init__.py
      audit.py
      db.py
      models.py
      repository.py
    portfolio/
    risk/
    trading/
    main.py
  tests/
    test_persistence.py
    ...
docker-compose.yml
```

Le Batch 09 n'ajoute aucune API Kraken privée, aucun LIVE, aucune route FastAPI de contrôle trading et aucune logique stratégique déterministe.

## Configuration

Les réglages OpenAI/Kraken restent inchangés. Batch 09 ajoute `AI_SPOT_TRADER_DATABASE_URL`, qui reste optionnelle tant qu'une composition runtime avec persistance n'est pas activée.

Les secrets et mots de passe réels restent uniquement dans l'environnement local ou `.env` non versionné.

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
- `docs/03_AGENT_TRADING_RISK.md` — responsabilités Agent/Risk/Trading/Persistence.
- `docs/09_ROADMAP_DEVELOPPEMENT.md` — roadmap.
- `docs/10_DECISIONS_ET_CHANGELOG.md` — ADR et changelog.

## Sécurité

- Aucun secret ou clé API réel ne doit être versionné, journalisé ou injecté dans les prompts.
- Une future clé Kraken ne devra jamais disposer du droit de retrait.
- PAPER et LIVE restent explicitement séparés.
- Toute exécution future doit continuer à passer par Risk ; aucune sortie LLM ne doit atteindre directement un Broker.
- PostgreSQL est un journal d'audit et une base de données applicative, jamais une source de stratégie.

## Avertissement

AI Spot Trader est un projet expérimental de recherche et de développement. Il ne constitue pas un conseil financier et ne garantit aucun résultat de trading.
