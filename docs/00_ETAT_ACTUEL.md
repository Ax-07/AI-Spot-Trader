# 00 — État actuel

## Référence GitHub intégrée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD réel  : 78607ce6ab9f2b9459de2b1e1a7127509475283a
Commit     : docs: finalize batch 32 integration status
HEAD fonctionnel Batch 32 : 5a2d07b3fc5208475c1a136690da6648797efde9
```

État revérifié le 29/09/2026 au démarrage du Batch 33. Le commit `78607ce` est documentaire uniquement ; il finalise dans la documentation l'intégration fonctionnelle du Batch 32.

## État des batches Market Attention

- Batch 28 — Radar v1 : intégré ;
- Batch 29 — observabilité : intégré ;
- Batch 30 — robustesse activité : intégré ;
- Batch 31 — notionnel USD SPOT et régimes de liquidité : intégré ;
- Batch 32 — couverture équilibrée SPOT/PERPETUAL : intégré dans `5a2d07b` ;
- Batch 33 — runtime hardening : **patch proposé/local, non intégré à GitHub**.

## État intégré confirmé

Le Radar reste strictement informatif et n'alimente ni l'Agent, ni Market Discovery, ni le Risk Engine, ni le Broker/order flow.

Le pipeline intégré conserve :

- `CandleStreamService` comme source canonique de candles ;
- rotation déterministe Batch 32 avec curseurs SPOT/PERPETUAL indépendants ;
- `scan_limit = 120` ;
- `candidate_limit = 20` ;
- `max_web_searches_per_refresh = 8` ;
- seuils d'activité `1.40 / 1.75 + 0.25 / 2.50 + 0.50` ;
- notionnel SPOT directement coté USD via `SPOT_BASE_VOLUME_X_5M_CLOSE_ESTIMATE` ;
- notionnel SPOT non USD à `null` ;
- notionnel PERPETUAL à `null` et liquidité `UNKNOWN` tant que l'unité économique du volume n'est pas reliée canoniquement au contrat ;
- faible liquidité descriptive et jamais utilisée comme exclusion.

## Batch 33 proposé

Le patch Batch 33 durcit uniquement le runtime Market Attention :

- cache lazy et verrouillé du `KrakenPairRegistry` dans `KrakenCandleProvider`, avec refresh contrôlé sur symbole absent ;
- suppression du chargement `AssetPairs` par historique SPOT ;
- distinction sécurisée entre erreurs réseau/HTTP, throttling explicite, erreur API Kraken et payload structurel invalide ;
- classification `VERY_HIGH / ACCELERATING` fondée sur ratio + accélération du **même horizon** ;
- Structured Output web aligné sur les limites Pydantic canoniques ;
- `ValidationError` Pydantic auxiliaires encapsulées en erreur de recherche bornée ;
- réduction des sources publiques exposées lorsque leur usage est démontrable par références structurées/citations provider, avec repli conservateur sinon.

Aucun seuil, budget, prompt Agent, calcul de liquidité, notionnel PERPETUAL, sizing, mode PAPER/LIVE ou chemin d'ordre n'est modifié.

## Working tree utilisateur connu avant Batch 33

```text
?? trades_9h_analysis.json
```

Ce fichier reste strictement hors périmètre : il ne doit être ni modifié, ni supprimé, ni versionné, ni inclus dans le ZIP Batch 33.

## Validation du patch

Voir `docs/33_BATCH_MARKET_ATTENTION_RUNTIME_HARDENING.md` pour la liste exacte des tests exécutés dans l'environnement ChatGPT et les validations complètes restant à exécuter localement avant intégration.
