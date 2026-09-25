# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub réel vérifié au démarrage du Batch 19.8 :
  `130429eca6c7c8385c1caf4b2eb2870bef61ec3e`
  (`docs: sync Batch 19.7 post-push state`).
- Référence fonctionnelle intégrée Batch 19.7 :
  `8b969b434916d89f6b6aa127c3bac9c27e990966`
  (`feat: add canonical position overlays to market charts`).
- Le Batch 19.8 est un **patch proposé localement**, non intégré à GitHub tant que l'opérateur ne l'a pas validé et poussé.

## État fonctionnel intégré avant 19.8

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- comptabilité/mark-to-market backend, modes `NORMAL` / `MANAGEMENT`, discovery dynamique et watchlist auditée ;
- explicabilité Agent/Risk/exécution, candles backend, streaming cockpit, vue Marchés et overlays de position canoniques ;
- frontend = cockpit uniquement ; fermer le frontend n'arrête pas le moteur backend.

## Batch 19.8 — Sessions v1

Le patch 19.8 introduit **Session** comme concept principal du parcours utilisateur sans nouvelle table SQL :

```text
Session UX
-> Strategy = identité technique stable
-> StrategyRevision(s) immuables
-> Campaign(s) immuables/versionnées
-> paper_run(s) / recovery
```

Périmètre proposé :

- façade backend `/api/v1/sessions` ;
- création atomique Strategy + révision 1 + Campaign ;
- listing/détail, modification versionnée, duplication indépendante et archivage logique ;
- statuts dérivés : `Brouillon`, `Prête`, `En cours`, `Arrêtée`, `À reprendre`, `Archivée` ;
- start/stop/resume/run-cycle via les mécanismes canoniques ;
- arrêt de Session = fermeture explicite du runtime actif et du `paper_run` ;
- navigation `Accueil | Sessions | Marchés | Positions | Historique | Réglages` ;
- création/édition simple + avancée ;
- modes marchés `Automatique — IA` et `Manuel` ;
- contrat TypeScript aligné sur `market_discovery` optionnel et `risk_allowed_pairs` nullable.

## Validation du patch 19.8

Exécuté par ChatGPT sur le patch livré :

- `node --test --experimental-strip-types frontend/src/lib/session-config.test.mjs` : **4/4 tests passés** ;
- `python -m py_compile` sur les 6 modules backend modifiés/créés et les 2 tests backend ajoutés : **passé** ;
- transpilation syntaxique TypeScript/TSX des 7 fichiers modifiés/créés : **passée** ;
- contrôle whitespace du workspace de patch via `git diff --cached --check` : **passé**.

La suite `pytest` n'a pas été exécutée dans l'environnement ChatGPT car `aiosqlite` n'y est pas installé et le réseau d'installation est indisponible. Les commandes `pnpm test`, `pnpm lint`, `pnpm typecheck` et `pnpm build` restent également à exécuter dans le repository local complet.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, lire ce document et distinguer clairement état intégré GitHub, modifications locales et patch proposé.
