# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique et factuelle.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité après intégration du Batch 18.9B :
  `1eb94e79c3b14fea04faca67d6b2c695b9a27f51`
  (`feat: add PAPER control plane cockpit`).
- Dernier commit code intégré :
  `1eb94e79c3b14fea04faca67d6b2c695b9a27f51`
  (`feat: add PAPER control plane cockpit`).
- Batch 18.9A : **intégré et validé**.
- Batch 18.9B : **intégré et validé localement** (`lint`, `typecheck`, `build`, `git diff --check`).

## État intégré

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

## Validation Batch 18.9B

```text
Validation ChatGPT avant livraison :
harness source frontend : 50 assertions passées
Node --experimental-strip-types --check : 3 fichiers .ts OK
typecheck ciblé avec stubs de dépendances : OK

Validation locale opérateur après correctif ESLint :
pnpm lint : OK
pnpm typecheck : OK
pnpm build : OK (Next.js 16.3.3)
git diff --check : OK hors avertissements LF -> CRLF
backend : non modifié, suite pytest/ruff/mypy non rejouée pour 18.9B
```

## Suite

Ouvrir le **Batch 18.9C** dans une nouvelle discussion pour la validation comportementale réelle via
frontend : Strategy/révisions, preview, Campaign SPOT/PERPETUAL, activation/reprise, cycles moteur,
lineage recovery, digests et refus backend fail-closed.
