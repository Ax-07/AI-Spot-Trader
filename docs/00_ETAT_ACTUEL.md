# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` observé au démarrage du Batch 19.5 :
  `e7e4c8248406516eada576b3907e77dc8b72a0e4`
  (`docs: synchronize Batch 19.4 completion`).
- Référence fonctionnelle du Batch 19.4 :
  `de65c6677ce01f9c75da5545fe81553a021f588d`
  (`feat: add dynamic audited market discovery`).
- Batch 19.4 **intégré** sur GitHub.
- Validation locale Batch 19.4 communiquée par l'opérateur : `tests/test_market_discovery.py` = 12 tests passés ; suite backend complète = 578 tests passés avec 2 warnings de dépréciation ; frontend = `pnpm lint`, `pnpm typecheck` et `pnpm build` passés.
- Batch 19.5 : **validation automatisée locale réussie ; prêt à intégrer, commit/push GitHub encore à effectuer**.

## État fonctionnel intégré avant Batch 19.5

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- Batch 19.3 `NORMAL` / `MANAGEMENT` conservé ; `MANAGEMENT` est évalué avant tout renouvellement de watchlist ;
- Batch 19.4 discovery dynamique conservé : catalogue Kraken canonique, watchlist IA bornée, fallback et audit durable sans table SQL dédiée ;
- les positions ouvertes restent gérables hors watchlist ;
- le configurateur simple active la discovery par défaut ;
- frontend toujours sans autorité trading ni calcul financier parallèle.

## Batch 19.5 — validation locale

- nouvelle projection backend d'explicabilité construite exclusivement depuis les faits déjà persistés ;
- aucune migration SQL, aucun nouveau ledger et aucun calcul stratégique/financier ;
- `/api/v1/cycles/latest` et `/api/v1/cycles/{cycle_id}` exposent une vue typée séparant contexte/discovery, sélection de marché, Agent IA, Risk, exécution PAPER et corrélation d'IDs ;
- HOLD, REJECT, MODIFY et FAILED restent sémantiquement distincts ;
- les anciens historiques incomplets restent explicites : aucune rationale ou causalité n'est inventée ;
- Accueil : dernière décision réellement explicable ;
- Historique : détail corrélé de cycle au lieu du croisement de pages décisions/Risk/exécutions ;
- Positions : activité auditée récente corrélée par symbole + type de marché, explicitement **sans** prétendre établir la provenance directe d'une position.

## Validation locale Batch 19.5

Exécuté par l'opérateur sur le repository complet le 2026-09-25 :

- `pytest tests/test_cycle_explainability.py` : **8 tests passés** ;
- `pytest` : **586 tests passés**, avec 2 warnings de dépréciation déjà connus ;
- `pnpm lint` : **passé** ;
- `pnpm typecheck` : **passé** ;
- `pnpm build` : **passé** ;
- `git diff --check` : aucune erreur de whitespace, uniquement des avertissements LF -> CRLF.

La revue visuelle ciblée light/dark, desktop/mobile, rationales longues/absentes, nombreuses raisons Risk et longs identifiants reste à distinguer de cette validation automatisée avant clôture documentaire définitive.

## Prochaine priorité

1. effectuer la revue visuelle ciblée puis committer/pousser le Batch 19.5 ;
2. Batch 19.6A — backend candles/cache/streaming ;
3. Batch 19.6B — vue Marchés/charts/markers.

Le cadrage détaillé reste centralisé dans `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, puis distinguer clairement état intégré, modifications locales et patch proposé.
