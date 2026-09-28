# 00 â€” Ã‰tat actuel

## RÃ©fÃ©rence GitHub vÃ©rifiÃ©e

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD       : 282267b1f491bb07b2644f6b9c5dca01c539697f
Commit     : refactor: recalibrate strategic LLM prompts
VÃ©rifiÃ©    : 2026-09-28
```

La dÃ©rive documentaire prÃ©cÃ©dente est corrigÃ©e dans ce patch : `282267b` est bien **intÃ©grÃ©** Ã  GitHub `main`. Le prÃ©sent recalibrage net/cost-aware est un patch proposÃ© **au-dessus de `282267b`** et n'est pas intÃ©grÃ© Ã  GitHub tant que l'opÃ©rateur ne l'a pas appliquÃ©, validÃ© et poussÃ©.

## Ã‰tat fonctionnel Ã  prÃ©server

- un seul Agent IA stratÃ©gique ;
- PAPER uniquement ;
- SPOT + PERPETUAL linÃ©aire ; FUTURE datÃ© interdit ;
- BUY / SELL / HOLD ; SPOT sans short ; PERPETUAL LONG/SHORT ;
- plan multi-marchÃ©s / multi-dÃ©cisions ordonnÃ© ;
- Risk Engine dÃ©terministe = autoritÃ© finale ;
- aucune sortie LLM -> ordre direct ;
- dÃ©cisions sÃ©quentielles et causales ;
- `HOLD` journalisÃ© ; `management_mode` conservÃ© ;
- historique expÃ©rimental/replays prÃ©servÃ© ;
- `AGENT_SYSTEM_PROMPT` historique `agent-strategy-v4` et `aggressiveness-map-v1` inchangÃ©s.

## Recalibrage stratÃ©gique proposÃ©

Le prompt Campaign courant est rendu explicitement orientÃ© vers la **progression de l'equity nette aprÃ¨s coÃ»ts** plutÃ´t que vers l'activitÃ© brute. Frais, spread, slippage et funding lorsqu'il est disponible dans les faits fournis font partie du rÃ©sultat Ã©conomique.

L'Agent doit raisonner en allocation et coÃ»t d'opportunitÃ© entre cash, positions existantes et nouvelles opportunitÃ©s. `HOLD`, conserver du cash et conserver une position sont des allocations valides. Une rotation doit Ãªtre justifiÃ©e face aux coÃ»ts cumulÃ©s des rÃ©ductions/clÃ´tures et nouvelles ouvertures ; aucune rÃ¨gle dÃ©terministe de profit, cooldown, durÃ©e minimale, quota de trades ou score d'opportunitÃ© n'est ajoutÃ©e.

Le mapping LLM courant devient `aggressiveness-map-v3` : davantage d'initiative aux niveaux Ã©levÃ©s lorsque l'opportunitÃ© est convaincante, mais aucune obligation de turnover, micro-trades, frÃ©quence minimale ou taille maximale.

## Constat PAPER motivant le patch

Une session rÃ©elle d'environ 9 h a montrÃ© un turnover Ã©levÃ© (`1 246` fills / `395` cycles), un P&L brut positif (~`+0,727`) mais un P&L net nÃ©gatif (~`-2,287`) aprÃ¨s coÃ»ts, pour une equity finale ~`97,713` depuis `100`.

Ce run motive le recalibrage cost-aware. **Il ne prouve pas la performance gÃ©nÃ©rale de la stratÃ©gie.**

## Audit SELL / SHORT PERPETUAL

- **confirmÃ©** : BUY/SELL PERPETUAL, planner, sÃ©lection multi-marchÃ©s et Risk sont directionnellement symÃ©triques ; aucune cause centrale n'impose SHORT ;
- **confirmÃ©** : le mapping d'agressivitÃ© `v2` pouvait pousser le turnover global ;
- **confirmÃ©** : la formulation gÃ©nÃ©rique Â« signal automatique de vente Â» Ã©tait asymÃ©trique pour la rÃ©duction d'un SHORT ; le patch la neutralise ;
- **obsolÃ¨te** : rÃ©fÃ©rence documentaire Ã  `5fdd9a3` comme HEAD courant et statut Â« non intÃ©grÃ© Â» de `282267b` ;
- **manquant avant ce patch** : objectif net-equity, coÃ»t d'opportunitÃ© et coÃ»ts de rotation explicites ;
- **Ã  dÃ©cider** : existence d'un biais SHORT persistant du modÃ¨le sur plusieurs runs comparables.

Aucun quota LONG/SHORT ni modification du Risk Engine n'est introduit.

## Fichiers principaux du patch

- `backend/src/ai_spot_trader/agent/prompt.py`
- `backend/src/ai_spot_trader/agent/strategy_client.py`
- `backend/src/ai_spot_trader/domain/experiments.py`
- `backend/tests/test_control_plane_prompt.py`
- `backend/tests/test_multi_market_provider.py`
- `docs/00_ETAT_ACTUEL.md`
- `docs/01_PROJECT_MASTER.md`
- `docs/03_AGENT_TRADING_RISK.md`
- `docs/10_DECISIONS_ET_CHANGELOG.md`
- `docs/24_BATCH_19_13_CYCLE_STRATEGIQUE_MULTI_MARCHES.md`

## Validation

Les rÃ©sultats du prÃ©sent patch doivent Ãªtre distinguÃ©s des validations historiques. Aucun rÃ©sultat de test n'est dÃ©clarÃ© ici avant exÃ©cution rÃ©elle.

