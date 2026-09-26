# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` vérifié au lancement du Batch 19.11 :
  `47e12798f54c3686b59faf339315ff39d9191b44`
  (`fix: allow derivative risk reduction above current caps`).
- Commit précédent :
  `2d763fe839b7bbb79d55303f4b29089a8d1dbc8a`
  (`fix: use compatible colors for market chart`).
- Le document était encore référencé sur `8643b9412bd19791e3cfd60884126ca0c300dc33` au lancement ; trois commits étaient intervenus depuis cette référence.
- Références fonctionnelles précédentes :
  - 19.10 : `8643b9412bd19791e3cfd60884126ca0c300dc33` (`feat: add strategic position management and capital rotation`) ;
  - 19.9C : `b59020a4b354d9d56d593f3e39bcd608824bcd42` (`feat: add session trading style UX`) ;
  - 19.9B : `88be7d50111c2e6210225071d3f1af3f7f07b4f0` (`feat: add strategic multi-timeframe context`) ;
  - 19.9A : `4b6a851addea74d72af2c433827c935a87d4bc04` (`feat: add canonical scalp swing trading style`).

## État intégré GitHub avant Batch 19.11

- un seul Agent IA stratégique ; pipeline Risk déterministe ;
- Session = concept principal du parcours utilisateur ;
- Discovery dynamique, Market Selection puis `BUY` / `SELL` / `HOLD` par le même Agent ;
- Trading Style canonique `SCALP` / `SWING` avec contexte stratégique multi-timeframes ;
- gestion stratégique des positions et rotation du capital intégrées depuis le Batch 19.10 ;
- en dérivés PAPER, une position existante au-dessus des caps courants peut être réduite/clôturée depuis `47e12798` ;
- une augmentation d'exposition reste soumise aux caps Session/Kraken et peut être rejetée par `DERIVATIVE_LEVERAGE_EXCEEDED`.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Modifications locales proposées — Batch 19.11

Le patch Batch 19.11 corrige le faux plafond global de levier dérivé causé par la réduction des niveaux de marge publics Kraken au taux le plus sévère :

- modèle provider-agnostic `DerivativeMarginTier` et instrument tier-aware ;
- conservation d'une courbe de marge ordonnée lorsque le schedule public applicable peut être sélectionné explicitement ;
- politique PAPER v1 explicite : `retailMarginLevels` prioritaire lorsqu'il est exposé ; `marginLevels` utilisé lorsqu'il n'entre pas en conflit avec des schedules nommés ; ambiguïtés `marginSchedules` conservées en fallback scalaire fail-closed ;
- sélection du tier sur la position totale projetée, pas uniquement sur le nouvel ordre ;
- même résolveur canonique utilisé par Risk et le Paper Ledger ;
- remarge déterministe de la position totale lors d'un franchissement de palier ;
- `reduce_only` de `47e12798` préservé ;
- aucune API privée Kraken, aucun changement LIVE, aucun changement frontend ;
- point restant explicitement documenté : la sérialisation générique d’un `MarketState` typé sur le `DerivativeInstrument` de base n’embarque pas automatiquement les champs propres au sous-type tier-aware ; le chemin d’exécution runtime est corrigé, mais un contrat persistant tier-aware devra être cadré séparément.

Détails : `docs/22_BATCH_19_11_KRAKEN_MARGIN_TIERS.md`.

## Validation Batch 19.11

Validation exécutée par ChatGPT dans un harness local fidèle aux contrats concernés, le conteneur ne pouvant pas cloner GitHub directement :

- tests ciblés parser/domain/Risk/ledger : `49 passed` ;
- `py_compile` sur les quatre fichiers source principaux : PASS ;
- `ruff` : non exécuté (`ruff` absent de l'environnement) ;
- backend complet réel : non exécuté, à valider sur le clone opérateur.

Commandes opérateur de référence :

```powershell
cd backend
pytest tests/test_kraken_derivatives.py -q
pytest tests/test_derivatives_domain.py -q
pytest tests/test_derivatives_risk.py -q
pytest tests/test_derivatives_paper.py -q
pytest
```

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer clairement l'état intégré GitHub, les éventuelles modifications locales fournies par l'opérateur et tout patch proposé non encore intégré.
