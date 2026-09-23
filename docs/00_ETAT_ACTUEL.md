# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié après intégration du Batch 18.6 : `9642ec394357fe1e1807b538a2353bdc6d062f46`
- Commit HEAD/code : `feat: add durable PAPER ledger recovery`
- Batch 18.6 : **intégré** après migration PostgreSQL, validation locale complète, commit et push.
- Prompt stratégique : `agent-strategy-v4`, inchangé par 18.6.

Référence de démarrage du Batch 18.6 : `70457125c5a238fe9b798463081c8769d8879d5e`
(`docs: record batch 18.5 integration`), avec `84548d23...` comme dernier commit code intégré à ce
moment-là.

## État intégré

Le même Agent stratégique sélectionne un marché dans l'univers PAPER typé, reçoit le
`MarketState` canonique exact, puis propose `BUY`, `SELL` ou `HOLD`. Risk garde l'autorité finale et
le Broker n'est appelé qu'après `ExecutionIntent`.

Le runtime supporte désormais aussi le recovery/restart durable du ledger PAPER multi-actifs via
`paper-ledger-recovery-v1` :

- un nouveau `paper_run_id` reste créé pour chaque lifetime backend ;
- `resumed_from_paper_run_id` relie explicitement une session reprise à sa précédente ;
- `initial_portfolio_payload` et `current_portfolio_payload` rendent l'état du ledger durable ;
- le snapshot courant est mis à jour dans la **même transaction** que le cycle durable ;
- au restart, le ledger est restauré depuis le dernier `PortfolioState` durable sans rejouer LLM,
  Risk, `ExecutionIntent` ni `Fill` ;
- SPOT détenu, cash, positions PERPETUAL, marge, P&L et funding sont restaurés ;
- un cycle `FAILED`, une erreur d'audit ou un replay idempotent restaure le checkpoint mémoire ;
- l'analytics suit la lignée `resumed_from_paper_run_id` pour préserver P&L, frais, funding,
  drawdown et compteurs cumulés à travers les restarts ;
- univers incompatible, payload invalide ou état legacy terminal ambigu => démarrage fail-closed.

Migration intégrée : `0005_paper_run_recovery`.

## Validation Batch 18.6

Validation locale opérateur confirmée avant intégration :

```text
Alembic 0004_multi_market_selection -> 0005_paper_run_recovery sur PostgreSQL : OK
pytest ciblé recovery/persistence/trading/broker : 75 passed
pytest backend : 468 passed, 2 warnings
ruff check backend : All checks passed!
mypy --config-file backend/pyproject.toml backend/src : Success, 79 source files
git diff --check : aucune erreur, uniquement warnings LF -> CRLF
```

Les deux warnings Starlette/AnyIO sont les warnings de dépendances non bloquants déjà connus.

## Frontières conservées

- un seul Agent IA ; Kraken ; PAPER uniquement ;
- SPOT sans short, levier ni marge ;
- PERPETUAL linéaire seulement, marge ISOLATED et protections déterministes ;
- aucune présélection algorithmique stratégique ;
- aucun tool -> Broker/Risk ; aucun LLM -> Broker ;
- aucune décision historique n'est régénérée au restart ;
- causalité/no-look-ahead ; décisions, HOLD et sélections auditables ;
- `paper-experiment-v1/v2/v3` et `experiment_manifest=None` restent compatibles ;
- LIVE séparé et ultérieur.

Principe : **l'Agent cherche, sélectionne et propose ; le Risk Engine autorise, modifie ou refuse.**

## Suite à auditer

Après 18.6 : robustesse réseau/observabilité bornée des erreurs transitoires, enrichissement mesuré
des données de recherche puis campagnes Luna/Sol multi-marchés sous protocole v3. Multi-quote/FX,
FUTURE daté et LIVE restent séparés et non décidés sans besoin mesuré.
