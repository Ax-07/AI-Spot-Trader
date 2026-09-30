# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 4a516fde33853fe84d18bd8c4780753c0db58214
Commit     : fix: harden market attention runtime
```

État revérifié le 29/09/2026 au démarrage du Batch 35. Le précédent HEAD documenté `78607ce6ab9f2b9459de2b1e1a7127509475283a` est obsolète ; GitHub `main` contient désormais le hardening Market Attention du Batch 33.

## État local distinct de GitHub

La discussion courante confirme des correctifs Batch 34 / 34.1 / 34.2 présents localement mais non intégrés à GitHub. Ils constituent l'état courant utilisateur et ne doivent pas être écrasés par un patch construit depuis `main`.

Le Batch 35 livré ici est lui aussi un **patch proposé/local non intégré**.

## Runtime confirmé avant Batch 35

La dernière erreur persistée connue est :

```text
2026-09-28T12:16:02.248841Z · AGENT · TimeoutError · timed_out=true
```

Un cycle plus récent a ensuite réussi :

```text
2026-09-28T14:22:57.386534Z · COMPLETED · failure=null
```

Le runtime courant renvoie également `engine.last_cycle_failure = null`. L'erreur AGENT est donc un fait historique d'audit, pas une panne actuelle démontrée.

## Batch 35 — UX des erreurs historiques

Le correctif est frontend-only :

- le dernier cycle `FAILED` reste une alerte active ;
- `latestError` n'est plus présenté comme alerte active lorsqu'un cycle plus récent existe ;
- une erreur dépassée par un cycle plus récent est affichée séparément comme `Dernière erreur historique` avec horodatage ;
- une erreur identique au dernier cycle en échec n'est pas dupliquée ;
- `LLMTimeoutError` reste un timeout fournisseur IA, tandis qu'un `TimeoutError` global de stage est libellé comme dépassement du délai du stage.

Aucun changement backend, Agent, Risk Engine, Broker, PAPER, Kraken, Market Attention, sizing, prompt ou timeout n'est introduit.

Voir `docs/35_BATCH_COCKPIT_HISTORICAL_ERRORS_UX.md` pour l'audit, les fichiers et les validations du batch.
