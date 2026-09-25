# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- Référence d'audit avant la fusion documentaire des anciens changements locaux :
  `a254df4d56208c4472bb97b9b80077ad0856f9cd`
  (`docs: sync Batch 19.8 post-push state`).
- Référence fonctionnelle intégrée courante : Batch 19.8.
- Batch 19.8 est **intégré à GitHub `main` et validé localement**.

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

Exécuté par l'opérateur :

- backend complet : **606 tests passés**, 2 warnings de dépendances ;
- frontend : **21/21 tests passés** ;
- `pnpm lint` : **passé** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé** ;
- `git diff --check` : **aucune erreur de whitespace**.

## Documentation consolidée

Les modifications documentaires locales héritées de 19.6B ont été auditées et fusionnées avec l'état intégré 19.7/19.8 dans :

- `docs/02_ARCHITECTURE_TECHNIQUE.md` ;
- `docs/03_AGENT_TRADING_RISK.md` ;
- `docs/11_AMELIORATIONS_PLANIFIEES.md`.

Cette fusion conserve les ajouts utiles 19.6B, marque les overlays 19.7 et Sessions 19.8 comme intégrés, et retire les formulations devenues obsolètes.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, lire ce document et distinguer clairement état intégré GitHub, modifications locales et patch proposé.
