# 00 — État actuel

## Référence GitHub vérifiée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD GitHub vérifié        : 59f92938bf5159004783ae004fe99c808cb2c8c2
HEAD                        : docs: distinguish functional baseline from branch head
Dernier commit fonctionnel : 463850d8281faebe86a6ee733d58781c349015d0
Commit fonctionnel          : refactor: make strategic agent cost aware
Vérifié                     : 2026-09-28
```

Le recalibrage stratégique net/cost-aware est **intégré** à GitHub `main` dans `463850d`. Des commits documentaires sont postérieurs sans modifier cet état fonctionnel ; le HEAD exact de `main` doit être revérifié en direct à chaque reprise.

## Batch 25 — historique économique par Session

Le checkout courant contient le batch d'observabilité **historique économique par Session**, construit sur la base GitHub `59f92938bf5159004783ae004fe99c808cb2c8c2` et validé localement le 28 septembre 2026.

Il ajoute une projection de lecture seule au-dessus des faits canoniques déjà persistés :

- sélection Session → Campaign/run économique dans le cockpit ;
- opérations économiques exécutées distinctes des `HOLD` / `REJECT` ;
- distinction SPOT / PERPETUAL et effet économique des BUY/SELL PERPETUAL à partir des positions avant/après ;
- coûts d'exécution, funding, P&L réalisé fourni par les fills, notional et turnover ;
- fills/heure, rotations entre marchés, ouvertures/augmentations/réductions/clôtures/flips ;
- export JSON du run ;
- aucun nouveau ledger, aucune migration SQL, aucun changement Agent/Risk/Broker.

Les métriques de P&L, equity, drawdown, exposition et funding restent issues de `PaperAnalyticsReport`. La nouvelle projection n'est pas une seconde comptabilité.

Voir `docs/25_BATCH_HISTORIQUE_ECONOMIQUE_SESSION.md`.

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

Ces résultats concernent le commit intégré `463850d`. La validation complète du Batch 25 est documentée séparément ci-dessous et dans `docs/25_BATCH_HISTORIQUE_ECONOMIQUE_SESSION.md`.


## Validation du Batch 25

Validation locale complète réalisée le 28 septembre 2026 après correctif :

- tests backend ciblés : `11/11` passés ;
- suite backend complète `pytest -q` : `100 %` passée, sans échec ;
- frontend `pnpm test` : `39/39` passés ;
- frontend `pnpm lint` : passé ;
- frontend `pnpm typecheck` : passé ;
- deux avertissements de dépréciation Starlette/AnyIO restent présents et sont hors périmètre ;
- les avertissements Node `MODULE_TYPELESS_PACKAGE_JSON` observés pendant les tests frontend sont non bloquants et hors périmètre.

La référence GitHub immédiatement antérieure au Batch 25 reste `59f92938bf5159004783ae004fe99c808cb2c8c2`; le HEAD GitHub doit être revérifié après intégration.

## Fichiers principaux concernés

État intégré cost-aware :

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

Correctif Batch 25 validé localement :

- désérialisation JSON stricte corrigée dans la projection économique ;
- effets React de l’écran Historique rendus conformes au lint ;
- correctif lint-only de l’inspecteur LLM inclus pour débloquer `pnpm lint` global ;
- aucune modification des règles Agent / Risk / Broker.

Batch 25 historique économique :

- `backend/src/ai_spot_trader/economic_history.py`
- `backend/src/ai_spot_trader/api/economic_history_schemas.py`
- `backend/src/ai_spot_trader/api/routes/analytics.py`
- `backend/tests/test_economic_history.py`
- `frontend/src/lib/economic-history.ts`
- `frontend/src/components/cockpit/history-panel.tsx`
- `docs/01_PROJECT_MASTER.md`
- `docs/10_DECISIONS_ET_CHANGELOG.md`
- `docs/25_BATCH_HISTORIQUE_ECONOMIQUE_SESSION.md`
