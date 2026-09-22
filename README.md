# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **SPOT + Kraken Derivatives** en mode **PAPER**, pilotée par **un seul Agent IA stratégique**. L'Agent propose `BUY`, `SELL` ou `HOLD`; un **Risk Engine déterministe** garde l'autorité finale et seul Risk peut créer un `ExecutionIntent`.

## Référence de développement

La base intégrée auditée avant le Batch 18.1 est GitHub `main` au commit :

```text
ca5077af00293ccca9794132ee0dd53a5b339911
```

Le tag annoté `baseline-batch17` pointe sur ce même commit. Le Batch 18.1 livré sous forme de ZIP est un **patch proposé non intégré** tant que sa validation locale, son commit et son push ne sont pas confirmés.

## Principes

- Kraken comme exchange initial ;
- PAPER uniquement ;
- SPOT sans short, levier ou marge ;
- Derivatives avec LONG/SHORT seulement sur produits compatibles ;
- levier et `reduce_only` déterministes, jamais choisis par le LLM ;
- aucune sortie LLM ni aucun tool ne déclenche directement un ordre ;
- frais, spread, slippage et funding pris en compte ;
- audit durable des décisions, HOLD, erreurs et recherches causales ;
- aucun secret dans prompts/logs/Git ;
- backend indépendant du frontend ;
- cible +4 %/jour = objectif expérimental, jamais garantie.

Principe : **l'Agent cherche et propose ; Risk autorise, modifie ou refuse.**

## Architecture Batch 18.1

```text
Kraken public data
      |
      +--> sources research dédiées --> MarketResearchService
      |                                  |
      |                        list_markets / get_market_snapshot
      |                                  |
      v                                  v
Trading MarketState + PortfolioState --> AgentInput --> Agent
                                                   BUY/SELL/HOLD
                                                         |
                                                         v
                                                    Risk Engine
                                                         |
                                                   ExecutionIntent
                                                         |
                                                         v
                                                    Paper Broker
```

Les sources de recherche sont isolées des sources de trading. En Derivatives elles n'ont aucun `market_sink`, donc explorer un marché ne modifie pas le ledger.

## Tools read-only

Le socle 18.1 expose seulement :

- `list_markets` : catalogue factuel, tri/pagination déterministes, aucun classement stratégique ;
- `get_market_snapshot` : snapshot SPOT/PERPETUAL normalisé, réutilisant le contexte et les calculs canoniques existants.

L'Agent peut décider sans tool, effectuer une ou plusieurs recherches et choisir lui-même quand conclure. Les budgets de tool sont uniquement techniques.

### Limitation volontaire

La recherche peut examiner d'autres symboles, mais l'exécution reste liée au symbole initial du cycle :

```text
DecisionCandidate.symbol == AgentInput.market_state.symbol
```

Le vrai choix multi-symbole exécutable est réservé au Batch 18.2 afin de conserver une corrélation causale correcte entre sélection, `MarketState`, Risk et Broker.

## Audit des recherches

Chaque appel conserve : nom, arguments validés, timestamps, statut, type d'erreur sanitizé, résultat borné et digest SHA-256. Les traces sont persistées au niveau du cycle, y compris si l'Agent échoue après une recherche et avant sa décision finale.

Le digest global du cycle inclut les traces.

## Configuration technique des tools

Valeurs par défaut proposées :

```text
AI_SPOT_TRADER_AGENT_TOOL_MAX_CALLS=6
AI_SPOT_TRADER_AGENT_TOOL_TIMEOUT_SECONDS=5
AI_SPOT_TRADER_AGENT_TOOL_MAX_RESULT_BYTES=32768
AI_SPOT_TRADER_AGENT_TOOL_LIST_MARKETS_MAX_LIMIT=50
```

Mettre `AI_SPOT_TRADER_AGENT_TOOL_MAX_CALLS=0` désactive la boucle et conserve le chemin direct historique.

## Migrations PostgreSQL

Après extraction du patch et configuration de `AI_SPOT_TRADER_DATABASE_URL` :

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

La chaîne devient :

```text
0001_audit_journal -> 0002_paper_runs -> 0003_agent_tool_traces
```

La migration 0003 ajoute un JSONB nullable pour les traces Agent ; les cycles historiques restent compatibles.

## Validation du patch

Exécuté par ChatGPT dans l'environnement de livraison partiel :

```text
47 tests ciblés/non-régression : passés
compileall code/test/migration    : OK
```

Ruff, mypy, la suite complète du repository, Alembic sur votre PostgreSQL et les contrôles Git restent à exécuter localement.

## Sécurité / LIVE

- aucune API Kraken privée nécessaire ;
- aucune clé avec droit de retrait ;
- aucun tool d'ordre ;
- LIVE reste un batch séparé avec permissions minimales, idempotence, réconciliation, recovery et activation explicite.

## Documentation

- `docs/00_ETAT_ACTUEL.md` : reprise courte ;
- `docs/01_PROJECT_MASTER.md` : spécification principale ;
- `docs/02_ARCHITECTURE_TECHNIQUE.md` : architecture ;
- `docs/03_AGENT_TRADING_RISK.md` : responsabilités Agent/Risk ;
- `docs/09_ROADMAP_DEVELOPPEMENT.md` : roadmap ;
- `docs/10_DECISIONS_ET_CHANGELOG.md` : ADR/changelog.
