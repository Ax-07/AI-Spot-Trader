# 27 — Batch — Trading Reasoning Doctrine v1

## 1. Base auditée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : b46f463c474e25a38da7ddcaebf588753922031b
Commit     : feat: add session economic history
Date       : 2026-09-28
```

La référence documentaire précédente `59f92938bf5159004783ae004fe99c808cb2c8c2` était dépassée d'un commit. Le diff `59f92938..b46f463c` concerne le Batch 25 d'historique économique et ne modifie pas les prompts Agent audités.

## 2. Objectif

Ajouter une méthode de raisonnement stratégique concise au LLM sans transformer AI Spot Trader en stratégie déterministe. Le modèle conserve le jugement stratégique ; le backend continue de fournir les faits et contraintes, puis Risk conserve l'autorité finale.

Principe inchangé : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## 3. Doctrine canonique

La constante `TRADING_REASONING_DOCTRINE`, versionnée `trading-reasoning-doctrine-v1`, demande au modèle :

- de construire une thèse à partir des faits réellement fournis ;
- d'interpréter régime, structure et cohérence entre horizons disponibles ;
- de distinguer, seulement lorsque les données le permettent, tendance, range, breakout, pullback et mouvement trop étendu ;
- d'examiner direction, momentum et volatilité sans inventer d'indicateur ;
- de ne jamais traiter un indicateur/pattern/signal isolé comme justification suffisante ;
- de comparer nouvelle opportunité, cash et positions ouvertes en tenant compte du potentiel restant, du risque de retournement, des coûts et du coût d'opportunité ;
- d'expliciter les faits qui soutiennent la thèse et ceux qui l'invalideraient ;
- de considérer cette invalidation comme du raisonnement, pas comme un stop ou ordre automatique ;
- d'accepter `HOLD` ou le cash lorsque la thèse n'est pas suffisamment convaincante après coûts.

## 4. Composition des prompts

La doctrine est centralisée dans `backend/src/ai_spot_trader/agent/prompt.py` et n'est pas dupliquée textuellement dans plusieurs contrats.

Elle est injectée :

- dans `compose_agent_instructions()` pour le chemin singleton Campaign courant ;
- dans la composition `strategic-multi-market-plan-v1` pour la planification multi-marchés.

Elle n'est pas injectée dans `market-discovery-v1`. Cette phase ne produit pas `BUY`/`SELL`/`HOLD`, mais une watchlist à partir d'un univers de candidats ; ses garde-fous existants « tradable != opportunité intéressante », net-cost-aware et no-invention restent suffisants et évitent de polluer la phase avec un protocole de décision final.

## 5. Compatibilité historique

Inchangés :

- `AGENT_PROMPT_VERSION = agent-strategy-v4` ;
- texte de `AGENT_SYSTEM_PROMPT` historique ;
- `aggressiveness-map-v1` utilisé par les manifests/replays ;
- `aggressiveness-map-v3` des prompts courants ;
- digests de stratégie opérateur, qui restent calculés sur le texte opérateur normalisé ;
- contrats Structured Outputs et validation Pydantic.

La doctrine est une section courante ajoutée à la composition runtime ; elle ne réécrit aucun historique.

## 6. Invariants vérifiés par conception/tests

- SPOT : aucun short, levier ou marge ;
- PERPETUAL : BUY/LONG et SELL/SHORT restent symétriques, y compris réduction de position opposée ;
- FUTURE daté interdit ;
- `HOLD` reste valide et exige `proposed_quantity=null` sur le plan multi-marchés ;
- frais, spread, slippage et funding disponible restent intégrés au raisonnement économique ;
- aucune obligation de turnover ;
- aucune sortie LLM n'appelle directement Broker/Kraken ;
- Risk reste final ;
- `management_mode` n'est pas modifié.

## 7. Interdictions explicites

Ce batch n'introduit aucun :

- `RSI < X => BUY` / `RSI > X => SELL` ;
- croisement MACD déclencheur ;
- seuil fixe de profit/perte ;
- stop-loss/take-profit mécanique ;
- timer/durée de clôture ;
- score technique ou ranking déterministe ;
- quota de trades ou quota LONG/SHORT ;
- modification du Risk Engine ;
- indicateur ou donnée absent des inputs canoniques.

## 8. Fichiers du batch

Runtime :

- `backend/src/ai_spot_trader/agent/prompt.py`
- `backend/src/ai_spot_trader/agent/strategy_client.py`

Tests :

- `backend/tests/test_control_plane_prompt.py`
- `backend/tests/test_trading_reasoning_doctrine.py`
- `backend/tests/test_trading_style.py` — attente de composition mise à jour dans le correctif après validation locale

Documentation :

- `docs/00_ETAT_ACTUEL.md`
- `docs/03_AGENT_TRADING_RISK.md`
- `docs/10_DECISIONS_ET_CHANGELOG.md`
- `docs/27_BATCH_TRADING_REASONING_DOCTRINE.md`

`docs/01_PROJECT_MASTER.md`, `docs/24_BATCH_19_13_CYCLE_STRATEGIQUE_MULTI_MARCHES.md` et `README.md` ont été audités ; aucune modification n'est nécessaire pour ce batch, car les invariants d'architecture et de cycle qu'ils décrivent restent inchangés et la doctrine est documentée dans les documents Agent/changelog dédiés.

## 9. Validation

Exécuté par ChatGPT avant livraison initiale :

```text
python -m py_compile <4 fichiers Python modifiés/ajoutés>  -> succès
harness local de composition des prompts                 -> PASS
pytest du test doctrine dans le harness isolé             -> 3 passed
```

Le harness vérifie notamment : présence unique de la doctrine sur les chemins singleton/multi-marchés, absence sur discovery/historique, maintien de `agent-strategy-v4`, `aggressiveness-map-v3`, net-cost-aware, SPOT + PERPETUAL, FUTURE interdit et `HOLD=null`.

Validation locale fournie par l'utilisateur sur le checkout réel :

```text
pytest ciblé doctrine/contrats : 44/44 passés
pytest -q                     : 1 échec, uniquement dans test_trading_style.py
```

L'échec ne révèle pas un défaut runtime : `test_prompt_composition_adds_canonical_style_and_cost_sections_only_when_configured` reconstruisait l'ancienne chaîne `PROTECTED_AGENT_CONTRACT + stratégie + agressivité` et n'avait pas été adaptée à l'insertion désormais canonique de `TRADING_REASONING_DOCTRINE`. Le correctif ajoute la doctrine à l'attente exacte et vérifie qu'elle n'apparaît qu'une fois, sans modifier le code runtime.

À rerun localement après extraction du ZIP correctif :

```powershell
cd backend
pytest tests/test_trading_style.py tests/test_trading_reasoning_doctrine.py -q
pytest -q
```
