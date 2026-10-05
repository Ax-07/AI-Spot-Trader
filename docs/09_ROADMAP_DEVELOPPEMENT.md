# 09 — Roadmap de développement

## Référence de reprise

```text
Repository                  : Ax-07/AI-Spot-Trader
Branche                     : main
Base GitHub auditée 49.1    : 8704eec57de09792d0a51e080fdeb7b2a39d2381
Batch 45                    : intégré via 45d41b7
Batch 46 / 46.1             : intégré via b219365
Batch 47.1                  : intégré via 842e6bd7
Batch 47.2                  : intégré via c09dd14
Batch 47.3                  : intégré via 12051a7
Batch 47.4                  : intégré via 472f3ad
Clôture documentaire 47.4   : e972fd9
Batch 47.5                  : intégré via d988de4
Clôture documentaire 47.5   : 4278a5c
Batch 48 fonctionnel        : intégré via ebb664c
Clôture documentaire 48     : 8704eec
Batch 49.1                  : patch proposé, non intégré à la livraison
```

Le HEAD GitHub réel doit être revérifié au démarrage de chaque nouveau batch.

## Invariants de roadmap

AI Spot Trader conserve :

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- Risk Engine comme autorité finale ;
- backend indépendant du frontend ;
- PAPER avant tout LIVE ;
- exécution PAPER SPOT + PERPETUAL Kraken linéaire ;
- SPOT sans short/levier/marge ;
- LONG/SHORT PERPETUAL autorisés sous contrôle Risk ;
- FUTURE daté non exécutable ;
- aucune sortie LLM directement exécutable ;
- aucun secret versionné ;
- aucune optimisation post-hoc.

Le Market Attention Radar reste un **outil de priorisation d'attention**, jamais un moteur BUY/SELL/HOLD. Le Batch 49.1 ne le raccorde pas à l'univers Agent.

## État intégré récent

### Batch 45 — Structure en amont

**Intégré via `45d41b7`.** Rotation/cache Structure séparés, événements BOS/CHOCH, filtres tendance/Structure et `UNKNOWN` fail-closed. Contrat `market-attention-radar-v6` conservé.

### Batch 46 / 46.1 — baseline adaptative

**Intégré via `b219365`.** Médiane + MAD normalisé, cible 12 périodes et fallback ratio uniquement pour les métriques où cette sémantique est justifiée.

### Batch 47.1 — fondations Futures ticker

**Intégré via `842e6bd7`.** Snapshot bulk `/tickers` partagé pour volume/liquidité/contexte Futures, sans impact stratégique à ce stade historique.

### Batch 47.2 — historique Open Interest

**Intégré via `c09dd14`.** Infrastructure Analytics historique canonique avec rotation/cache/concurrence bornés et causalité explicite.

### Batch 47.3 — Funding historique + Liquidation Volume

**Intégré via `12051a7`.** Funding relatif signé et Liquidation Volume agrégé réutilisent le même scanner Analytics.

### Batch 47.4 — CVD + Aggressor Differential

**Intégré via `472f3ad`, clôturé documentairement via `e972fd9`.** CVD sur variation, Aggressor signé, MAD robuste, aucun fallback ratio pour les séries signées. Cinq séries partagent le même scanner/cache/cursor/sémaphore.

### Batch 47.5 — influence multi-analytics bornée sur le ranking

**Intégré via `d988de4`, clôturé documentairement via `4278a5c`.**

Décision architecturale :

```text
score séparé 0..4
= OI 0/1
+ Funding 0/1
+ Liquidations 0/1
+ Order Flow 0/1
```

CVD et Aggressor Differential forment une seule composante `ORDER_FLOW`. Ils ne peuvent jamais fournir +2.

Règles intégrées :

- score calculé uniquement sur les PERP déjà retenus ;
- `interest_level` inchangé ;
- `candidate_limit` inchangé ;
- aucune création/suppression de candidat ;
- données absentes/dégradées neutres ;
- signes positifs/négatifs symétriques pour l'attention ;
- priorité : intérêt -> Structure -> Analytics -> reste de la clé ;
- `SPOT` inchangé ;
- en `ALL`, positions SPOT figées ;
- contrat API v6 étendu additivement ;
- diagnostics cockpit explicites ;
- aucun impact direct Agent/Risk/Broker dans ce batch historique.

Voir `docs/47_5_MULTI_ANALYTICS_RANKING.md`.

### Batch 48 — observabilité du ranking Analytics

**Intégré fonctionnellement via `ebb664c`, clôturé documentairement via `8704eec`.**

Objectif : mesurer le comportement réel du ranking 47.5 avant toute nouvelle pondération ou toute exposition à l'Agent.

Décision architecturale intégrée :

```text
historique Radar borné existant
-> agrégation read-only à la demande
-> endpoint observability dédié
-> cockpit compact
```

Pas de nouvelle persistence et pas de second buffer. La persistence SQL actuelle reste réservée à ses responsabilités PAPER/audit économique.

Mesures intégrées :

- distribution score `0..4` ;
- contribution des quatre familles ;
- statuts des cinq séries ;
- fréquence de reranking applicable/effectif ;
- snapshots applicables sans mouvement ;
- distribution exacte de `rank_change`, moyenne et maximum de `abs(rank_change)` ;
- candidats montés/descendus/inchangés ;
- déduplications et conflits CVD/Aggressor ;
- PERP sans Analytics exploitable ;
- ventilation par scope ;
- couverture descriptive par marché ;
- fenêtre et taille d'échantillon explicites.

Route additive :

```text
GET /api/v1/market-attention/observability?limit=96
```

Le score, l'admission, `interest_level`, `candidate_limit`, Agent, Risk et Broker n'ont pas été modifiés par le Batch 48.

Voir `docs/48_OBSERVABILITE_RANKING_ANALYTICS.md`.

## Batch 49.1 — activation officielle du PERPETUAL PAPER

**Patch proposé sur `8704eec`, non intégré à GitHub à la livraison.**

L'audit confirme que la majorité de la capacité était déjà présente et testée avant le batch :

- univers `ExecutableMarket` typé SPOT/PERPETUAL ;
- routage marché exécutable SPOT/derivatives ;
- JSON Schema Agent conservant `market_type` ;
- `RiskEngine` dérivés linéaires ;
- levier/marge/caps/buffer liquidation déterministes ;
- `PaperBroker` PERPETUAL ;
- ledger LONG/SHORT, funding, P&L et liquidation théorique ;
- Market Discovery capable de conserver `PERPETUAL` ;
- configuration/cockpit déjà capables de représenter les paramètres dérivés.

Le batch ne construit donc pas un second moteur dérivés. Il :

1. remplace le dernier contrat opérateur actif encore SPOT-only par `operator-chat-v2` ;
2. officialise dans la documentation active l'univers PAPER SPOT + PERPETUAL linéaire ;
3. ajoute une preuve d'intégration Agent -> Risk -> Broker -> `DerivativePosition` ;
4. verrouille la règle de retournement : fermeture/réduction d'abord, ouverture opposée ensuite ;
5. laisse Radar et ranking inchangés.

### Règle de retournement 49.1

```text
LONG + SELL surdimensionné  -> clamp/reject à la fermeture, jamais SHORT direct
SHORT + BUY surdimensionné  -> clamp/reject à la fermeture, jamais LONG direct
```

Avec `risk_allow_quantity_reduction=true`, Risk borne la quantité à la position courante et émet `reduce_only=true`. Sinon l'ordre opposé surdimensionné est rejeté. Cette règle évite un changement de sens implicite dans un seul intent et préserve l'audit séquentiel.

## Validation intégrée du Batch 48

```text
backend python -m pytest -q : PASS — 1155 passed, 2 warnings
frontend pnpm typecheck     : PASS
frontend pnpm test          : PASS — 86/86
git diff --check            : PASS — avertissements LF/CRLF uniquement
push GitHub main            : PASS — ebb664c puis clôture 8704eec
```

Ces résultats appartiennent au Batch 48 intégré et ne valent pas validation du patch 49.1.

Warnings connus, non bloquants et hors périmètre :

- dépréciations FastAPI/Starlette dans les dépendances de test ;
- warning Node `MODULE_TYPELESS_PACKAGE_JSON`.

## Suite après validation de 49.1

```text
49.2 — Radar shortlist -> univers Agent SPOT + PERPETUAL
49.3 — contexte Radar/Analytics fourni à l'Agent
49.4 — observabilité des décisions et performances PAPER SPOT/PERP
```

Le Batch 49.2 devra être lancé dans une nouvelle discussion après resynchronisation avec le HEAD `main` alors courant. Il ne faut pas connecter silencieusement le Radar à l'Agent dans 49.1.

Le LIVE, l'authentification Kraken Futures privée et l'exécution réelle restent des décisions séparées et ultérieures.
