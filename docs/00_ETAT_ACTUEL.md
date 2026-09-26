# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` vérifié au lancement du correctif PAPER PERPETUAL : `1408a74f5256ff3674b154d3a64794f4ffd012c2` (`docs: sync post-19.12 state`).
- Ce HEAD ne modifie que la documentation par rapport à `f8397d207be67309db083e49e113253fe88b3624` (`fix: handle OpenAI rate limits and quota errors robustly`).
- Le correctif PAPER PERPETUAL décrit ci-dessous est un patch proposé, non intégré à GitHub au moment de cette mise à jour.

## État intégré et correctif proposé

- un seul Agent IA stratégique ; Risk Engine déterministe avec autorité finale ;
- versions actuelles en PAPER ; aucune sortie LLM directe vers Broker/Kraken ;
- Trading Style `SCALP` / `SWING`, contexte multi-timeframes et gestion stratégique des positions intégrés ;
- erreurs LLM techniques fail-closed et classifiées depuis le Batch 19.12 ;
- correctif proposé : arithmétique PAPER `Decimal` canonique pour garantir les égalités exactes du `Fill` même avec prix Kraken haute précision et spread/slippage ;
- correctif proposé : toute quantité PERPETUAL autorisée par Risk est rabattue vers le bas sur le quantum dérivé de `DerivativeInstrument.min_order_quantity` ; pour Kraken, ce champ provient de `contractValueTradePrecision` et représente à la fois le minimum positif et le pas de quantité ;
- une normalisation ne peut jamais augmenter l'exposition et les minimums/plafonds sont revérifiés avant création de l'`ExecutionIntent` ;
- l'atomicité `AuditedTradingCycleRunner` reste inchangée : un cycle `FAILED`, notamment au stage `BROKER`, restaure le checkpoint PAPER.

Principe central : **L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Diagnostic différé

La persistance d'un diagnostic structuré détaillé pour les `ValidationError` internes n'est pas incluse dans ce correctif ciblé : le contrat actuel ne persiste que `stage`, `error_type` et `timed_out`. Une extension sûre devra utiliser des champs allow-listés et bornés (modèle, chemin de champ, code de validation), sans message brut ni input externe.

## Validation

Le ZIP du correctif contient les régressions PAPER/Risk correspondantes. Les tests backend ciblés et le `pytest` complet doivent être exécutés dans le repository local après extraction ; ne pas considérer ce patch intégré avant cette validation et le commit explicite de l'opérateur.

## Règle de reprise

À chaque nouvelle tâche : revérifier le HEAD GitHub réel, relire ce document et distinguer l'état intégré GitHub, les éventuelles modifications locales fournies par l'opérateur et tout patch proposé non encore intégré.
