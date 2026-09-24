# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main`.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub audité au démarrage du batch documentaire :
  `9a312040eb671976b44e5f50077ca11a9d9213b3`
- Commit fonctionnel intégré du Batch 18.13 :
  `4cb0567cae6ff100c5ad9ad1df9e3f68b8f7ffd7`
  (`feat: add dark mode and modernize cockpit UI`).
- Commit documentaire suivant :
  `9a312040eb671976b44e5f50077ca11a9d9213b3`
  (`docs: sync batch 18.13 integrated state`).
- Batch 18.13 : **INTÉGRÉ / VALIDÉ**.

## État fonctionnel confirmé

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- navigation actuelle : **Accueil / Configurer / Positions / Historique / Réglages** ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- `paper_executable_markets` constitue actuellement un univers statique configuré par Campaign ;
- la sélection IA de marché est aujourd'hui liée au cycle stratégique multi-marchés ;
- le portefeuille SPOT canonique expose `asset`, `quantity`, `available`, sans coût moyen ni P&L par position ;
- les positions PERPETUAL exposent déjà coût moyen, mark, P&L, marge, liquidation et funding ;
- le `rationale` de la décision IA existe et est audité, mais n'est pas encore exposé comme information métier dédiée dans le cockpit ;
- Kraken Spot utilise déjà REST OHLC et WebSocket ticker côté backend, sans pipeline candles cockpit persistant ;
- frontend indépendant du moteur ; LIVE reste indisponible.

## Améliorations planifiées

Le cadrage détaillé des prochaines améliorations est centralisé dans :

`docs/11_AMELIORATIONS_PLANIFIEES.md`

Axes prioritaires proposés :

1. comptabilité SPOT canonique et P&L par position ;
2. monitoring / mark-to-market déterministe indépendant de l'IA ;
3. mode gestion lorsque l'exposition interdit toute nouvelle ouverture ;
4. découverte dynamique des marchés et watchlist auditée ;
5. explicabilité dédiée IA / Risk ;
6. pipeline candles/WebSocket puis vue **Marchés** et charts.

Les valeurs de cadence définitives et certains choix de persistence restent **à décider** pendant les batches d'implémentation correspondants.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel avant de considérer la référence ci-dessus comme courante.
