# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` revérifié après intégration du Batch 19.10 :
  `8643b9412bd19791e3cfd60884126ca0c300dc33`
  (`feat: add strategic position management and capital rotation`).
- Commit précédent :
  `105aaae47efbeed4a2208fcf036c09aa096f9351`
  (`docs: sync post-19.9C state`).
- Références fonctionnelles précédentes :
  - 19.9C : `b59020a4b354d9d56d593f3e39bcd608824bcd42` (`feat: add session trading style UX`) ;
  - 19.9B : `88be7d50111c2e6210225071d3f1af3f7f07b4f0` (`feat: add strategic multi-timeframe context`) ;
  - 19.9A : `4b6a851addea74d72af2c433827c935a87d4bc04` (`feat: add canonical scalp swing trading style`).

## État fonctionnel intégré après Batch 19.10

- un seul Agent IA stratégique ; pipeline Risk déterministe inchangé ;
- Session = concept principal du parcours utilisateur ;
- Discovery dynamique, Market Selection puis `BUY` / `SELL` / `HOLD` par le même Agent ;
- Trading Style canonique `SCALP` / `SWING` avec `trading-style-map-v1` ;
- contexte stratégique multi-timeframes `strategic-mtf-v1` opérationnel côté données ;
- les positions ouvertes restent des opportunités stratégiques explicites en mode `NORMAL` comme en `MANAGEMENT` ;
- `CapacityAssessment.management_markets` expose les marchés correspondant aux positions ouvertes même lorsque de la capacité d'ouverture subsiste ;
- mapping position ouverte -> marché centralisé et réutilisé par Capacity et Dynamic Discovery ;
- contexte factuel versionné `position-management-v1`, sans score ni trigger automatique ;
- estimation économique de sortie SPOT fondée sur les coûts PAPER canoniques (frais, spread, slippage) et le coût de revient restant, sans double comptage des coûts d'entrée ;
- le même Agent peut conserver, réduire/clôturer une position, privilégier une autre opportunité ou finir sur `HOLD` ;
- aucune règle P&L, timer, style ou indicateur ne déclenche automatiquement `SELL` ;
- `risk_max_order_notional` reste un plafond par ordre, y compris pour un SELL SPOT réducteur ; une grosse clôture peut nécessiter plusieurs cycles ;
- protections SPOT inchangées : aucune vente d'un actif non détenu ni au-delà de la quantité disponible ;
- rotation du capital multi-cycle : un SELL peut libérer du capital réévalué lors d'un cycle ultérieur, sans BUY forcé ;
- frontière Agent préservée : le calcul économique canonique vit côté trading, sans dépendance directe `agent -> broker` ;
- aucune migration SQL, aucun second Agent et aucune logique de prise de profit déterministe cachée.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Validation Batch 19.10

Validation locale opérateur après correctif et avant push du commit fonctionnel :

- tests ciblés : `11 passed` ;
- backend complet : `638 passed, 2 warnings` ;
- les deux warnings sont des dépréciations FastAPI/Starlette préexistantes ;
- `git diff --cached --check` : PASS ;
- `git diff --check` : aucune erreur, uniquement des warnings Windows LF -> CRLF.

Détails : `docs/21_BATCH_19_10_POSITION_MANAGEMENT_CAPITAL_ROTATION.md`.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer clairement l'état intégré GitHub, les éventuelles modifications locales fournies par l'opérateur et tout patch proposé non encore intégré.
