# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié au lancement du correctif post-Batch 19.13 : `29316d7521accfe46316cb2bc6dfcf7652ba04bf` (`feat: add multi-market multi-decision trading cycles`).
- Le Batch 19.13 multi-marchés / multi-décisions est donc **intégré** à GitHub `main` à cette référence.
- Le présent fichier fait partie d'un **patch correctif proposé, non encore intégré à GitHub**.

## Correctif post-Batch 19.13

Le patch corrige la régression `AGENT · LLMOutputValidationError` du nouveau chemin de planification :

- le JSON Schema Structured Outputs encode désormais explicitement les variantes `BUY` / `SELL` / `HOLD` : quantité strictement positive pour `BUY`/`SELL`, `null` obligatoire pour `HOLD` ;
- la validation Pydantic reste une seconde barrière fail-closed ; aucun résultat invalide n'est transformé en ordre valide ;
- `StrategyInstructionsClient` reconnaît le protocole `strategic-multi-market-plan-v1` et injecte un contrat protégé multi-marchés explicite au lieu du protocole final singleton historique ;
- un seul Agent et un seul appel stratégique de planification restent utilisés par cycle ;
- les erreurs de plan sont catégorisées sans journaliser la sortie LLM brute ;
- le runtime PAPER canonique refuse désormais l'activation d'une Session comportant un bootstrap ou une discovery non-SPOT.

Le code historique PERPETUAL reste présent pour compatibilité de lecture et pour éviter une suppression hors périmètre, mais il n'est plus activable par le runtime canonique tant que l'invariant courant reste **SPOT uniquement**.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Validation du patch

Les fichiers Python modifiés et le nouveau test ciblé sont compilés syntaxiquement par ChatGPT. L'environnement de travail de ChatGPT ne contient pas un checkout exécutable complet du repository ; les suites `pytest` ciblée et complète doivent donc être exécutées localement après extraction du ZIP.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer explicitement l'état intégré GitHub, les modifications locales fournies par l'opérateur et tout patch proposé non encore intégré.
