# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié après intégration du Batch 18.7 : `0886216324106d941c3df0e30f074e24dbe1d33a`
- Commit HEAD : `feat: add bounded network retry resilience`
- Dernier commit code intégré : `0886216324106d941c3df0e30f074e24dbe1d33a`
  (`feat: add bounded network retry resilience`).
- Batch 18.6 : **intégré**.
- Batch 18.7 : **intégré**.
- Prompt stratégique : `agent-strategy-v4`, inchangé par 18.7.

## État intégré

Le même Agent stratégique sélectionne un marché dans l'univers PAPER typé, reçoit le
`MarketState` canonique exact, puis propose `BUY`, `SELL` ou `HOLD`. Risk garde l'autorité finale et
le Broker n'est appelé qu'après `ExecutionIntent`.

Le recovery/restart durable du ledger PAPER multi-actifs reste `paper-ledger-recovery-v1` :

- un nouveau `paper_run_id` par lifetime backend ;
- `resumed_from_paper_run_id` relie explicitement une reprise à sa session précédente ;
- `initial_portfolio_payload` et `current_portfolio_payload` rendent l'état du ledger durable ;
- un cycle `FAILED`, une erreur d'audit ou un replay idempotent restaure le checkpoint mémoire ;
- aucune décision, Risk, intent ou fill historique n'est rejoué au restart ;
- univers incompatible, payload invalide ou état terminal ambigu => fail-closed.

Migration intégrée : `0005_paper_run_recovery`.

## Batch 18.7 — intégré

L'audit réseau confirme trois frontières différentes :

- Kraken WebSocket SPOT possède déjà un reconnect borné et ne doit pas recevoir une seconde boucle
  de retry ;
- les appels REST publics Kraken SPOT/Derivatives sont read-only et peuvent être réessayés avant
  toute mutation du ledger ;
- les appels Responses API peuvent être réessayés uniquement au niveau transport avant qu'une
  `MarketSelection` ou un `DecisionCandidate` durable n'existe.

Le Batch 18.7 intégré ajoute :

- une politique de retry commune bornée avec backoff exponentiel déterministe ;
- 3 tentatives maximum pour les lectures REST publiques Kraken ;
- 2 tentatives maximum pour un appel Responses API ;
- retry uniquement sur timeout/transport, HTTP 408, HTTP 429 et HTTP 5xx ;
- aucun retry sur 4xx permanent, JSON/payload invalide ou contrat provider invalide ;
- sous-types d'erreurs sans données sensibles pour distinguer timeout, réseau, rate-limit, 5xx
  et HTTP permanent dans `failure_error_type` sans persister de payload ni secret ;
- logs de retry structurés contenant opération, tentative, type d'erreur, statut HTTP et délai,
  sans corps de réponse, URL sensible ou clé ;
- wrappers Kraken placés sur les méthodes REST read-only, pas autour de `snapshot()`, afin de ne
  jamais répéter `mark_derivative_market()` ou un accrual funding ;
- aucun retry autour de Risk, Broker, persistance ou recovery.

Les deadlines `MARKET`/`AGENT` du runner restent les plafonds absolus : les retries ne prolongent
jamais un cycle. Un timeout de stage peut donc couper le budget de retry si le timeout transport
configuré est plus long.

Aucun jitter n'est introduit dans ce batch : un seul runtime/Agent est actuellement visé et le
backoff déterministe simplifie les tests. À réévaluer uniquement si une contention concurrente
réelle est mesurée.

## Validation du Batch 18.7

Validation locale opérateur confirmée après application du correctif statique :

```text
pytest backend/tests/test_network_resilience.py backend/tests/test_openai_client.py : 27 passed
pytest backend/tests/test_trading_engine.py backend/tests/test_market_selection_runner.py backend/tests/test_paper_recovery.py : 55 passed
pytest backend : 487 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 81 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Les deux warnings pytest proviennent de `fastapi/starlette` et de leurs dépendances `httpx/anyio` ;
ils ne signalent pas un échec du batch. Aucune migration PostgreSQL n'est introduite par 18.7.

Les validations ChatGPT antérieures sur harness déterministes restent complémentaires, mais la
validation de référence avant intégration est désormais la suite locale ci-dessus.

## Frontières conservées

- un seul Agent IA ; Kraken ; PAPER uniquement ;
- SPOT sans short, levier ni marge ;
- PERPETUAL linéaire seulement, marge ISOLATED et protections déterministes ;
- aucune présélection algorithmique stratégique ;
- aucun tool -> Broker/Risk ; aucun LLM -> Broker ;
- aucune panne réseau n'est convertie silencieusement en `HOLD` ;
- aucune décision historique n'est régénérée au restart ;
- causalité/no-look-ahead ; décisions, HOLD et sélections auditables ;
- `paper-experiment-v1/v2/v3`, `agent-strategy-v4` et `paper-ledger-recovery-v1` restent compatibles ;
- LIVE séparé et ultérieur.

Principe : **l'Agent cherche, sélectionne et propose ; le Risk Engine autorise, modifie ou refuse.**

## Suite

Après intégration de 18.7 : mesurer les taux réels de retries/erreurs sur plusieurs
cycles PAPER avant d'ajuster les budgets ou d'introduire du jitter. L'enrichissement des données de
recherche et les campagnes Luna/Sol multi-marchés restent des travaux séparés.
