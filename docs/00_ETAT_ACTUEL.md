# 00 — État actuel

## Référence GitHub vérifiée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 463850d8281faebe86a6ee733d58781c349015d0
Commit     : refactor: make strategic agent cost aware
Vérifié    : 2026-09-28
```

Le recalibrage stratégique net/cost-aware est **intégré** à GitHub `main` dans `463850d`.

## État fonctionnel à préserver

- un seul Agent IA stratégique ;
- PAPER uniquement ;
- SPOT + PERPETUAL linéaire ; FUTURE daté interdit ;
- BUY / SELL / HOLD ; SPOT sans short ; PERPETUAL LONG/SHORT ;
- plan multi-marchés / multi-décisions ordonné ;
- Risk Engine déterministe = autorité finale ;
- aucune sortie LLM -> ordre direct ;
- décisions séquentielles et causales ;
- `HOLD` journalisé ; `management_mode` conservé ;
- historique expérimental/replays préservé ;
- `AGENT_SYSTEM_PROMPT` historique `agent-strategy-v4` et `aggressiveness-map-v1` inchangés.

## Recalibrage stratégique intégré

Les prompts Campaign courants sont explicitement orientés vers la **progression de l'equity nette après coûts** plutôt que vers l'activité brute. Frais, spread, slippage et funding lorsqu'il est disponible dans les faits fournis font partie du résultat économique.

L'Agent raisonne en allocation et coût d'opportunité entre cash, positions existantes et nouvelles opportunités. `HOLD`, conserver du cash et conserver une position sont des allocations valides. Une rotation doit être justifiée face aux coûts cumulés des réductions/clôtures et nouvelles ouvertures ; aucune règle déterministe de profit, cooldown, durée minimale, quota de trades ou score d'opportunité n'est ajoutée.

Le mapping LLM courant est `aggressiveness-map-v3` : davantage d'initiative aux niveaux élevés lorsque l'opportunité est convaincante, mais aucune obligation de turnover, micro-trades, fréquence minimale ou taille maximale.

## Constat PAPER motivant le recalibrage

Une session réelle d'environ 9 h a montré un turnover élevé (`1 246` fills / `395` cycles), un P&L brut positif (~`+0,727`) mais un P&L net négatif (~`-2,287`) après coûts, pour une equity finale ~`97,713` depuis `100`.

Ce run motive le recalibrage cost-aware. **Il ne prouve pas la performance générale de la stratégie.**

## Audit SELL / SHORT PERPETUAL

- **confirmé** : BUY/SELL PERPETUAL, planner, sélection multi-marchés et Risk sont directionnellement symétriques ; aucune cause centrale n'impose SHORT ;
- **confirmé** : le mapping d'agressivité `v2` pouvait pousser le turnover global ;
- **confirmé** : la formulation générique « signal automatique de vente » était asymétrique pour la réduction d'un SHORT ; elle a été neutralisée ;
- **corrigé** : objectif net-equity, coût d'opportunité et coûts de rotation sont désormais explicites dans les instructions courantes ;
- **à décider** : existence d'un biais SHORT persistant du modèle sur plusieurs runs comparables.

Aucun quota LONG/SHORT ni modification du Risk Engine n'a été introduit.

## Validation du commit `463850d`

Validation locale réalisée le 28 septembre 2026 :

- tests ciblés du recalibrage stratégique : `47/47` passés ;
- suite backend complète `pytest -q` : `100 %` passée, sans échec ;
- deux avertissements de dépréciation Starlette/AnyIO restent présents et sont hors périmètre de ce batch.

## Fichiers principaux concernés

- `backend/src/ai_spot_trader/agent/prompt.py`
- `backend/src/ai_spot_trader/agent/strategy_client.py`
- `backend/src/ai_spot_trader/domain/experiments.py`
- `backend/tests/test_control_plane_prompt.py`
- `backend/tests/test_multi_market_provider.py`
- `backend/tests/test_position_management_rotation.py`
- `README.md`
- `docs/01_PROJECT_MASTER.md`
- `docs/03_AGENT_TRADING_RISK.md`
- `docs/10_DECISIONS_ET_CHANGELOG.md`
- `docs/24_BATCH_19_13_CYCLE_STRATEGIQUE_MULTI_MARCHES.md`
