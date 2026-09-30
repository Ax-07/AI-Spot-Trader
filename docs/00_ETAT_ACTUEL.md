# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 58b59ba0cab25e9011d26014c51005aac1365af2
Commit     : fix: recover market attention runtime and clarify historical errors
```

État revérifié le 30/09/2026 au démarrage du Batch 36. Le HEAD documenté précédent `4a516fde33853fe84d18bd8c4780753c0db58214` est obsolète.

## État intégré confirmé

Le commit `58b59ba0cab25e9011d26014c51005aac1365af2` intègre désormais les Batches 34 / 34.1 / 34.2 / 35 :

- récupération du runtime Market Attention et diagnostics bornés associés ;
- correction de la cause SPOT Kraken liée aux réponses OHLC de `721` lignes ;
- clarification cockpit entre erreur courante et erreur historique dépassée.

Ces éléments ne doivent plus être décrits comme des correctifs locaux non intégrés.

## Batch 36 — simplification UX du terme financier « notionnel »

**État : patch proposé/local non intégré.**

Le Batch 36 est frontend/documentation uniquement :

- les libellés visibles utilisent désormais `Montant max par ordre`, `Valeur de la position`, `Valeur max d’une position` ou `valeur échangée estimée en USD` selon le contexte ;
- l’Historique utilise `Montant de l’ordre` / `montant échangé` pour ses libellés économiques visibles ;
- les identifiants techniques (`risk_max_order_notional`, `position.notional`, `current_notional_usd`, etc.) restent inchangés ;
- aucun comportement Agent, Risk Engine, Broker, PAPER, Kraken, Market Discovery, Market Attention, pricing, coûts, sizing, exposition, API ou persistence n’est modifié.

Aucun `git status` local utilisateur n’a été fourni au démarrage de ce batch ; le patch est donc construit strictement depuis le HEAD GitHub ci-dessus et doit être appliqué sans écraser d’éventuelles modifications locales plus récentes.

Voir `docs/36_BATCH_UX_TERMINOLOGIE_FINANCIERE.md` pour l’audit et les validations du batch.
