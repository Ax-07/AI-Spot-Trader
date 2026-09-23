# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité au démarrage du Batch 18.9B :
  `efe5a0f162a69e50bd6e5f5cd7aa61039792e911`
  (`docs: finalize batch 18.9A integration reference`).
- Dernier commit code intégré :
  `11a04be33bf209552e6337e28318d039b775b264`
  (`feat: add PAPER control plane`).
- Batch 18.9A : **intégré et validé**.
- Batch 18.9B : **patch frontend préparé sur cette base ; non intégré tant que l'opérateur ne l'a pas extrait, validé, committé et poussé**.

## État intégré + patch 18.9B

- un seul Agent IA ; Kraken ; PAPER ; SPOT + PERPETUAL linéaire ;
- Risk autorité finale ; aucun LLM/tool -> Broker/Risk ;
- Control Plane backend persistant Strategy/StrategyRevision/Campaign ;
- `paper-experiment-v4` et recovery `paper-ledger-recovery-v1` ;
- cockpit 18.9B réutilisant le client API `/backend` existant ;
- gestion Strategy : création, renommage, archivage, révisions immuables, comparaison ;
- prompt preview canonique séparant contrat protégé, stratégie, agressivité et input dynamique futur ;
- builder Campaign PAPER SPOT/PERPETUAL avec Luna/Sol, capital, coûts, Risk, levier et marge `ISOLATED` ;
- activation fraîche / reprise explicite ;
- commandes moteur canoniques `run-cycle`, `start`, `stop` ;
- affichage `campaign_id`, `paper_run_id`, `resumed_from_paper_run_id`, `recovery_version` ;
- aucune Campaign, stratégie ou secret persisté par le nouveau cockpit dans `localStorage`/`sessionStorage` ;
- aucune logique de trading ou Risk dupliquée dans le frontend.

## Validation ChatGPT du patch 18.9B

```text
harness source frontend : 50 assertions passées
Node --experimental-strip-types --check : 3 fichiers .ts OK
typecheck ciblé avec stubs de dépendances : OK
pnpm lint/typecheck/build : non exécutés (pnpm absent ; Corepack sans accès registre)
backend : non modifié, suite pytest/ruff/mypy non rejouée
```

## Suite

Après extraction : exécuter `pnpm lint`, `pnpm typecheck`, `pnpm build`, puis valider les parcours
réels Control Plane. Après intégration de 18.9B, ouvrir le **Batch 18.9C** pour la validation
comportementale réelle via frontend.
