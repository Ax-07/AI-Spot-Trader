# 00 — État actuel

## Référence GitHub vérifiée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD GitHub vérifié : b46f463c474e25a38da7ddcaebf588753922031b
HEAD                : feat: add session economic history
Vérifié              : 2026-09-28
```

Le HEAD `b46f463c` est à un commit devant la référence documentaire précédente `59f92938` et intègre le Batch 25 d'historique économique Session/run. Le recalibrage stratégique net/cost-aware reste issu de `463850d8281faebe86a6ee733d58781c349015d0`.

## État fonctionnel intégré à préserver

- un seul Agent IA stratégique ;
- PAPER uniquement ;
- SPOT + PERPETUAL linéaire ; FUTURE daté interdit ;
- BUY / SELL / HOLD ; SPOT sans short ; PERPETUAL LONG/SHORT ;
- plan multi-marchés / multi-décisions ordonné ;
- Risk Engine déterministe = autorité finale ;
- aucune sortie LLM -> ordre direct ;
- décisions séquentielles et causales ;
- `HOLD` journalisé ; `management_mode` conservé ;
- historique expérimental et replays préservés ;
- `AGENT_SYSTEM_PROMPT` historique `agent-strategy-v4` et `aggressiveness-map-v1` inchangés ;
- mapping LLM courant `aggressiveness-map-v3` ;
- objectif stratégique courant = progression de l'equity nette après coûts, sans obligation de turnover.

## Patch local — Trading Reasoning Doctrine v1

Le présent batch ajoute aux **prompts stratégiques courants** une doctrine qualitative versionnée `trading-reasoning-doctrine-v1`.

Elle demande au LLM de construire une thèse à partir des faits fournis, d'interpréter régime/structure/cohérence multi-timeframe, d'examiner direction, momentum et volatilité lorsque les données le permettent, de comparer cash/positions/opportunités et coûts, puis d'identifier ce qui soutient ou invaliderait la thèse.

La doctrine n'est pas un moteur de signaux : aucun seuil RSI/MACD, score technique, règle profit/stop/timer, quota de trades ou logique BUY/SELL déterministe n'est ajouté. `HOLD` et conserver le cash restent valides lorsqu'aucune thèse suffisamment convaincante après coûts n'est disponible.

Composition auditée :

- singleton Campaign courant : doctrine injectée une fois ;
- plan multi-marchés courant : doctrine injectée une fois ;
- market discovery : doctrine non injectée, car cette phase construit seulement une watchlist ;
- `AGENT_SYSTEM_PROMPT` historique : inchangé ;
- Risk Engine, Broker, planner, mappings d'agressivité et contrats action/quantité : inchangés.

Voir `docs/03_AGENT_TRADING_RISK.md` et `docs/27_BATCH_TRADING_REASONING_DOCTRINE.md`.

## Batch 25 — historique économique Session/run

Le Batch 25 est désormais intégré au HEAD GitHub `b46f463c`. Il fournit une projection de lecture seule des opérations économiques, coûts, turnover et effets SPOT/PERPETUAL à partir des analytics et faits persistés existants, sans second ledger ni modification Agent/Risk/Broker.

## Validation du patch local doctrine

Exécuté dans l'environnement ChatGPT :

- compilation Python des fichiers runtime/tests modifiés : succès ;
- harness de composition des prompts : succès, avec vérification de la doctrine présente une fois sur singleton et plan multi-marchés, absente de discovery et du prompt historique, et maintien des garde-fous SPOT/PERPETUAL/HOLD/net-cost-aware ;
- test doctrine isolé : `3/3` passés.

Validation locale fournie par l'utilisateur après extraction du premier ZIP :

- suite ciblée `test_control_plane_prompt.py + test_multi_market_provider.py + test_position_management_rotation.py + test_trading_reasoning_doctrine.py` : `44/44` passés ;
- suite backend complète : un seul échec dans `test_trading_style.py::test_prompt_composition_adds_canonical_style_and_cost_sections_only_when_configured` ;
- cause confirmée : le test reconstruisait encore l'ancienne composition exacte sans la nouvelle section canonique `TRADING_REASONING_DOCTRINE` ; le runtime n'est pas en cause.

Le ZIP correctif met uniquement à jour cette attente de test et la documentation de validation. Le rerun de `test_trading_style.py` puis de `pytest -q` reste à effectuer localement.
