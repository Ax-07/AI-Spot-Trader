# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` vérifié au démarrage du Batch 19.9A :
  `97a95ef7e91f6fb66577b7c399ac17af676cd146`
  (`docs: sync post-19.8 session fix state`).
- Référence fonctionnelle intégrée : `0d964624a641aad509f5728264f873c1a837af97`
  (`fix: preserve session creation FK ordering`).
- Batch 19.8 et son correctif PostgreSQL sont intégrés et validés.
- **Batch 19.9A : patch proposé non intégré à GitHub** dans ce lot de livraison.

## État fonctionnel intégré

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- comptabilité/mark-to-market backend, modes `NORMAL` / `MANAGEMENT`, discovery dynamique et watchlist auditée ;
- explicabilité Agent/Risk/exécution, candles backend, streaming cockpit, vue Marchés, markers persistés et overlays de position canoniques ;
- frontend = cockpit uniquement ; fermer le frontend n'arrête pas le moteur backend ;
- **Session** est le concept principal du parcours utilisateur.

## Batch 19.8 — Sessions v1

Architecture retenue :

```text
Session UX
-> Strategy = identité technique stable
-> StrategyRevision(s) immuables
-> Campaign(s) immuables/versionnées
-> paper_run(s) / recovery
```

Périmètre intégré :

- façade backend `/api/v1/sessions` ;
- création atomique Strategy + révision 1 + Campaign ;
- listing/détail, modification versionnée, duplication indépendante et archivage logique ;
- statuts dérivés : `Brouillon`, `Prête`, `En cours`, `Arrêtée`, `À reprendre`, `Archivée` ;
- start/stop/resume/run-cycle via les mécanismes canoniques ;
- arrêt de Session = fermeture explicite du runtime actif et du `paper_run` ;
- navigation `Accueil | Sessions | Marchés | Positions | Historique | Réglages` ;
- création/édition simple + avancée ;
- modes marchés `Automatique — IA` et `Manuel` ;
- contrat TypeScript aligné sur `market_discovery` optionnel et `risk_allowed_pairs` nullable ;
- aucune nouvelle table SQL `sessions`.

## Validation locale Batch 19.8

Exécuté par l'opérateur avant intégration du Batch 19.8 :

- backend complet : **606 tests passés**, 2 warnings de dépendances ;
- frontend : **21/21 tests passés** ;
- `pnpm lint` : **passé** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé** ;
- `git diff --check` : **aucune erreur de whitespace**.

## Correctif post-19.8 — création Session PostgreSQL

Cause confirmée :

- `CampaignRecord` référence `(strategy_id, strategy_revision)` via la FK composite `fk_campaigns_strategy_revision` ;
- `CampaignRecord` n'a pas de relation ORM vers `StrategyRevisionRecord` permettant d'exprimer directement cette dépendance d'insertion ;
- le flush unique de Strategy + Revision + Campaign pouvait envoyer la Campaign avant la Revision sur PostgreSQL ;
- PostgreSQL rejetait alors la création et l'API répondait `HTTP 409 · session creation conflicted`.

Correction intégrée :

- Strategy + Revision sont flushées avant l'ajout de Campaign ;
- Campaign est ensuite flushée dans **la même transaction**, donc l'atomicité de création reste intacte ;
- le test de persistence Session active les foreign keys SQLite pour couvrir explicitement l'ordre de dépendance ;
- le configurateur Session affiche les erreurs backend au lieu de laisser un échec silencieux.

Validation opérateur du correctif :

- tests ciblés Session persistence + lifecycle : **3 tests passés** ;
- backend complet : **607 tests passés**, 2 warnings de dépendances ;
- frontend : **21/21 tests passés** ;
- `pnpm lint` : **passé** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé** ;
- `git diff --check` : aucune erreur de whitespace, uniquement avertissements LF → CRLF ;
- validation fonctionnelle manuelle : **Créer et démarrer une Session fonctionne après redémarrage backend**.

Commit intégré :
`0d964624a641aad509f5728264f873c1a837af97`
(`fix: preserve session creation FK ordering`).

## Documentation consolidée

Les modifications documentaires locales héritées de 19.6B ont été auditées et fusionnées avec l'état intégré 19.7/19.8 dans :

- `docs/02_ARCHITECTURE_TECHNIQUE.md` ;
- `docs/03_AGENT_TRADING_RISK.md` ;
- `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Batch 19.9A — Trading Style canonique (patch proposé)

Fondations ajoutées sans migration SQL ni rupture de `agent-contract-v1` :

- `TradingStyle` canonique : `SCALP` / `SWING` ;
- `CampaignConfiguration.trading_style` + `trading_style_mapping_version`, omis du JSON canonique lorsqu'absents afin de préserver les digests historiques ;
- `TradingStyleContext` versionné (`trading-style-map-v1`) et `ExecutionCostContext` ;
- style et coûts propagés vers Discovery, Market Selection et `AgentInput`, y compris via le runner dynamique ;
- style et agressivité restent indépendants ; aucun mapping style → Risk, aucun ranking déterministe, aucune fermeture par timer ;
- coûts PAPER visibles par l'Agent sans devenir un score algorithmique ;
- `SCALP` : `1m/5m/15m/30m` ; `SWING` : `1h/4h/1d`.

Le contexte candles multi-timeframes réellement opérationnel reste le **Batch 19.9B**. Aucune UI ne doit présenter SWING comme pleinement opérationnel avant ce batch.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, lire ce document et distinguer clairement état intégré GitHub, modifications locales et patch proposé.
