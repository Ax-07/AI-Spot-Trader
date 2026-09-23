# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié au démarrage du Batch 18.6 : `70457125c5a238fe9b798463081c8769d8879d5e`
- Commit HEAD : `docs: record batch 18.5 integration`
- Dernier commit code intégré : `84548d23efda0b0a8e2c1350bacc830c1de34140`
- Commit code : `feat: version multi-market experiment protocol`
- Batch 18.5 : **intégré**.
- Batch 18.6 : **patch proposé, non intégré**.
- Prompt stratégique : `agent-strategy-v4`, inchangé par 18.6.

## État intégré avant 18.6

Le même Agent stratégique sélectionne un marché dans l'univers PAPER typé, reçoit le
`MarketState` canonique exact, puis propose `BUY`, `SELL` ou `HOLD`. Risk garde l'autorité finale et
le Broker n'est appelé qu'après `ExecutionIntent`.

Le runtime multi-marché SPOT/PERPETUAL, les tools read-only, la sélection causale, le journal
PostgreSQL, `paper-analytics-v3` et `paper-experiment-v3` sont intégrés.

Limitation confirmée avant 18.6 : chaque démarrage backend créait un nouveau `paper_run_id` avec un
ledger PAPER frais en mémoire. Aucun recovery durable du portefeuille n'était câblé.

## Batch 18.6 — patch proposé

Le patch proposé introduit `paper-ledger-recovery-v1` sans modifier la stratégie Agent/Risk :

- un nouveau `paper_run_id` reste créé pour chaque lifetime backend ;
- `resumed_from_paper_run_id` relie explicitement la nouvelle session à la précédente ;
- `initial_portfolio_payload` et `current_portfolio_payload` rendent l'état du ledger durable ;
- le snapshot courant est mis à jour dans la **même transaction** que le cycle durable ;
- au restart, le ledger est restauré depuis le snapshot courant durable, sans replay de décision,
  d'intent ou de fill ;
- l'analytics du run courant rejoue aussi la chaîne explicite `resumed_from_paper_run_id`, afin de
  préserver P&L, frais, funding et compteurs cumulés à travers les restarts ;
- SPOT détenu, cash, positions PERPETUAL, marge, P&L et funding ouverts sont restaurés via
  `PortfolioState` ;
- un cycle `FAILED` ne fait pas avancer le ledger : la frontière d'audit restaure le checkpoint
  mémoire ;
- si l'audit échoue après mutation PAPER, le checkpoint mémoire est restauré et le runner reste
  fail-closed ;
- un replay audit idempotent (`record() == False`) ne double pas l'exposition mémoire ;
- univers incompatible, payload invalide ou état legacy terminal ambigu => démarrage fail-closed.

Migration proposée : `0005_paper_run_recovery`.

## Validation ChatGPT du patch 18.6

Réellement exécuté dans l'environnement ChatGPT :

```text
python -m py_compile fichiers Python modifiés : OK
contrôle lignes > 100 sur fichiers Python modifiés : OK
smoke local PortfolioState JSON -> recovery validation -> PaperPortfolioLedger.restore : OK
```

Non exécuté ici faute de checkout complet et de dépendances dev disponibles hors réseau :

```text
pytest tests ciblés recovery/persistence/trading/broker
pytest backend
ruff check backend
mypy --config-file backend/pyproject.toml backend/src
migration Alembic réelle sur PostgreSQL
git diff --check dans le checkout opérateur
```

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

## Suite

Avant intégration de 18.6 : appliquer le ZIP sur un checkout propre, exécuter la migration et la
suite complète, puis seulement commit/push. Après 18.6, restent candidats la robustesse
réseau/observabilité, l'enrichissement research et les campagnes Luna/Sol multi-marchés v3.
