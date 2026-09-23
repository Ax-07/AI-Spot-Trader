# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié après intégration du Batch 18.8 : `36e6f46dd7c427d40426c98ee57f30ed4fd466c2`
  (`docs: record batch 18.8 behavioral validation`).
- Dernier commit code intégré : `0886216324106d941c3df0e30f074e24dbe1d33a`
  (`feat: add bounded network retry resilience`).
- Batch 18.6 : **intégré**.
- Batch 18.7 : **intégré**.
- Batch 18.8 : **intégré** — validation comportementale réelle, sans changement code requis.
- Prompt stratégique : `agent-strategy-v4`, inchangé.
- Protocole expérimental : `paper-experiment-v3`, inchangé.
- Recovery : `paper-ledger-recovery-v1`, inchangé.

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

## Résilience réseau intégrée — Batch 18.7

- lectures REST publiques Kraken : 3 tentatives maximum ;
- Responses API : 2 tentatives maximum par requête transport ;
- retry uniquement sur timeout/transport, HTTP 408, HTTP 429 et HTTP 5xx ;
- aucun retry sur 4xx permanent, JSON/payload invalide ou contrat provider invalide ;
- backoff exponentiel déterministe, sans jitter ;
- aucun retry autour de Risk, Broker, persistance, recovery ou du snapshot PERPETUAL complet ;
- erreurs finales typées et logs de retry sanitizés ;
- deadlines `MARKET`/`AGENT` restent les plafonds absolus et peuvent couper un budget de retry.

Validation locale de référence du Batch 18.7 :

```text
pytest backend/tests/test_network_resilience.py backend/tests/test_openai_client.py : 27 passed
pytest backend/tests/test_trading_engine.py backend/tests/test_market_selection_runner.py backend/tests/test_paper_recovery.py : 55 passed
pytest backend : 487 passed, 2 warnings de dépréciation dépendances
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 81 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

## Batch 18.8 — validation comportementale réelle

Campagnes PAPER réelles avec `gpt-5.6-luna`, sans forcer `BUY`/`SELL`.

### Recovery

- un démarrage avec univers différent du dernier run a été refusé fail-closed par
  `PaperRunRecoveryError` ;
- avec l'univers parent restauré, la lignée durable a été confirmée :
  `9a6bea62-d0c3-425d-b0f8-99229fc5a2ed`
  -> `fc5c87ef-3bb6-41cf-a1de-cd4b820f2b24` ;
- le successeur porte `recovery_version = paper-ledger-recovery-v1` ;
- le parent a reçu un `ended_at` lors du handoff ;
- aucun artefact stratégique historique n'a été régénéré par le recovery.

### Campagne multi-marché

Univers : `SPOT:BTC/USD + PERPETUAL:ETH/USD`.

- 10/10 cycles `COMPLETED`, HTTP 200 ;
- 7 sélections `BTC/USD SPOT` ;
- 3 sélections `ETH/USD PERPETUAL` ;
- 10 décisions naturelles `HOLD` ;
- durées observées : 13,0 s à 22,1 s ; moyenne ~15,6 s ; médiane ~15,0 s ;
- aucun retry naturel observé ;
- aucun doublon détecté dans les contrôles décisions/exécutions/fills ;
- aucun motif de secret détecté par le scan de logs.

### Campagne mono-marché

Univers isolé : `PERPETUAL:BTC/USD`, sur base PostgreSQL dédiée migrée jusqu'à
`0005_paper_run_recovery`.

- 10/10 cycles `COMPLETED`, HTTP 200 ;
- 10 décisions naturelles `HOLD` ;
- durées observées : 5,9 s à 10,1 s ; moyenne ~7,9 s ; médiane ~7,4 s ;
- aucun retry naturel observé ;
- aucun doublon détecté dans les contrôles décisions/exécutions/fills ;
- aucun motif de secret détecté par le scan de logs.

### Conclusions

Sur 20 cycles PAPER réels : 20/20 `COMPLETED`, zéro retry naturel, zéro panne réseau/LLM naturelle
et zéro timeout de stage observé.

Les budgets 18.7 ne sont pas modifiés :

- aucune donnée ne justifie plus de tentatives ;
- aucun jitter n'est justifié ;
- aucune exposition des budgets dans `Settings` n'est justifiée ;
- aucun backend métrique durable dédié n'est justifié par cet échantillon.

Les deadlines actives observées (`MARKET=20s`, `AGENT=35s`, Kraken transport `10s`, OpenAI transport
`30s`) suffisent au nominal, mais ne permettent pas d'épuiser les budgets théoriques lorsque chaque
tentative atteint son timeout transport maximal. Le deadline de stage reste volontairement
l'autorité supérieure.

Limite honnête : les 20 décisions naturelles étaient `HOLD`. Les campagnes réelles n'ont donc pas
exercé un nouveau `ExecutionIntent`, appel Broker ou fill. Ces branches restent couvertes par les
tests déterministes 18.7 et ne doivent pas être déclarées validées par la campagne 18.8.

Dette d'observabilité identifiée mais non corrigée : les champs durables
`resumed_from_paper_run_id` et `recovery_version` existent dans `PaperRunView`/PostgreSQL mais ne
sont pas exposés par la réponse API `/api/v1/paper-runs`.

Aucun test automatisé n'a été rejoué spécifiquement pendant 18.8, aucun code n'ayant été modifié.

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

Ne pas ajuster les retries sur la base du Batch 18.8. Réévaluer budgets, jitter ou métriques
durables seulement si une campagne plus longue observe des retries/pannes réelles ou un besoin
opérationnel mesuré.

Travaux séparés possibles : exposer la lignée recovery dans l'API, enrichir les données de
recherche et lancer des campagnes Luna/Sol multi-marchés sous `paper-experiment-v3`.
