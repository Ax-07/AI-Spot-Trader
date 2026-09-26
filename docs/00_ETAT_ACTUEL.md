# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` revérifié au démarrage du Batch 19.10 :
  `105aaae47efbeed4a2208fcf036c09aa096f9351`
  (`docs: sync post-19.9C state`).
- Référence fonctionnelle Batch 19.9C :
  `b59020a4b354d9d56d593f3e39bcd608824bcd42`
  (`feat: add session trading style UX`).
- Référence fonctionnelle 19.9B :
  `88be7d50111c2e6210225071d3f1af3f7f07b4f0`
  (`feat: add strategic multi-timeframe context`).
- Référence fonctionnelle 19.9A :
  `4b6a851addea74d72af2c433827c935a87d4bc04`
  (`feat: add canonical scalp swing trading style`).

## État fonctionnel intégré après Batch 19.9C

- un seul Agent IA stratégique ; pipeline Risk déterministe inchangé ;
- Session = concept principal du parcours utilisateur ;
- Discovery dynamique, Market Selection puis BUY/SELL/HOLD par le même Agent ;
- Trading Style canonique `SCALP` / `SWING` avec `trading-style-map-v1` ;
- `SCALP` : `1m/5m/15m/30m` ; `SWING` : `1h/4h/1d` ;
- contexte stratégique multi-timeframes `strategic-mtf-v1` opérationnel côté données ;
- `CandleStreamService` backend partagé entre cockpit et Campaign runtimes, sans second pipeline/cache OHLC ;
- lecture causale `history_as_of(...)`, sans interpolation des gaps ni donnée candle indisponible à `as_of` ;
- snapshot construit pour Market Selection puis réutilisé inchangé pour la décision finale ;
- le configurateur Session expose le style dans la configuration simple et avancée ;
- `agent-contract-v1` et Campaigns historiques sans `trading_style` restent compatibles ;
- aucune règle technique déterministe `indicateur -> BUY/SELL/HOLD` et aucun timer de fermeture lié au style.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Patch local Batch 19.10 proposé — non intégré

Le patch Batch 19.10 ajoute la gestion stratégique explicite des positions ouvertes et la rotation du capital sans créer de second Agent ni de règle automatique de prise de profit :

- `CapacityAssessment.management_markets` reste renseigné aussi en mode `NORMAL` ;
- la détection position ouverte -> marché est centralisée et réutilisée par Capacity et Dynamic Discovery ;
- contexte factuel versionné `position-management-v1` injecté aux instructions Campaign 19.9A+ lorsque des positions ouvertes sont sélectionnables et que le contexte de coûts PAPER est disponible ;
- estimation SPOT de sortie sur quantité disponible via `PaperExecutionCostModel` / `estimate_paper_execution` ;
- coût de revient restant réutilisé tel quel, sans double comptage des frais d'entrée ;
- guidance Agent : gérer / réduire / clôturer une position reste une option stratégique même quand une nouvelle ouverture est possible ; HOLD reste valide ; aucun seuil P&L, timer ou indicateur ne force SELL ;
- le mapping SCALP/SWING et `strategic-mtf-v1` restent inchangés ;
- `risk_max_order_notional` conserve explicitement sa sémantique de plafond par ordre, y compris pour un SELL SPOT réducteur ; une clôture supérieure au plafond peut donc nécessiter plusieurs cycles ;
- le Risk Engine conserve l'interdiction de vendre un actif SPOT non détenu ou plus que la quantité disponible ;
- rotation multi-cycle : SELL peut libérer du cash puis un cycle ultérieur peut revenir à Discovery / Market Selection ; aucun BUY n'est imposé après SELL.

Détails : `docs/21_BATCH_19_10_POSITION_MANAGEMENT_CAPITAL_ROTATION.md`.

## Validation du patch Batch 19.10

Validation locale opérateur de la première livraison :

- test ciblé 19.10 : `6 passed, 1 failed` ;
- backend complet : `633 passed, 3 failed, 2 warnings` ;
- les trois échecs étaient bornés à deux causes : validation stricte de `ExecutableMarket` depuis le JSON transport et import interdit `agent -> broker` dans le nouveau module ;
- `git diff --check` n'a remonté que les warnings Windows LF -> CRLF.

Correctif local proposé après cet audit :

- parsing des marchés transportés via `ExecutableMarket.model_validate_json(...)`, compatible avec les enums strictes ;
- calcul `position-management-v1` déplacé dans `trading/position_management.py` ;
- `agent/position_management.py` devient une façade sans import direct `risk` / `broker` afin de préserver la frontière du package Agent ;
- contexte 19.10 non ajouté aux Campaigns legacy sans le couple `TradingStyleContext` + `ExecutionCostContext`, afin de préserver leurs instructions historiques ;
- tests 19.10 complétés pour la frontière d'import et la compatibilité legacy.

Validations réellement exécutées par ChatGPT sur ce correctif : compilation Python PASS, vérification ciblée du comportement Pydantic strict JSON PASS, frontière d'import Agent PASS et contrôle whitespace PASS. La suite `pytest` complète doit être rejouée localement après extraction du ZIP correctif.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer clairement état intégré GitHub, modifications locales fournies par l'opérateur et éventuel patch proposé. Ne jamais considérer le Batch 19.10 comme intégré tant que l'opérateur ne l'a pas validé, commit et push.
