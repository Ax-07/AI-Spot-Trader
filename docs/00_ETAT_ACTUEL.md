# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub réel vérifié post-push Batch 19.8 :
  `f3a8eae8528648c07723aa97350852428254acc7`
  (`feat: add user-facing Sessions workflow`).
- Référence fonctionnelle intégrée courante : Batch 19.8.
- Batch 19.8 est **intégré à GitHub `main` et validé localement**.

## État fonctionnel intégré

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- comptabilité/mark-to-market backend, modes `NORMAL` / `MANAGEMENT`, discovery dynamique et watchlist auditée ;
- explicabilité Agent/Risk/exécution, candles backend, streaming cockpit, vue Marchés et overlays de position canoniques ;
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

## Modifications locales hors Batch 19.8

Au moment du push 19.8, les fichiers suivants restent modifiés localement et ne font pas partie du commit `f3a8eae` :

- `docs/02_ARCHITECTURE_TECHNIQUE.md` ;
- `docs/03_AGENT_TRADING_RISK.md` ;
- `docs/11_AMELIORATIONS_PLANIFIEES.md`.

Ils doivent être audités séparément avant intégration.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, lire ce document et distinguer clairement état intégré GitHub, modifications locales et patch proposé.
