# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et les éventuelles modifications locales en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub vérifié au lancement du Batch 19.6B :
  `321ce2d19105046af1f11295d67130402c09f2c5`
  (`docs: finalize Batch 19.6A integration state`).
- Référence fonctionnelle intégrée du Batch 19.6A :
  `3c53af3bdb1ef53c574e26afe9b6178a374d9f06`
  (`feat: add backend candle cache and streaming`).
- Batch 19.5 : **intégré** au commit `07050faea54bbed89cf250b34f8e97bd10d94bd3`.
- Batch 19.6A : **intégré sur GitHub `main`**.
- Batch 19.6B : **patch proposé, non intégré** tant que la validation opérateur, le commit et le push ne sont pas réalisés.

## État fonctionnel intégré

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- `NORMAL` / `MANAGEMENT`, discovery dynamique et watchlist auditée sont intégrés ;
- l'explicabilité 19.5 expose séparément contexte/discovery, sélection de marché, Agent, Risk et exécution PAPER depuis les faits persistés ;
- backend candles 19.6A : historique, cache process-local, recovery et WebSocket cockpit partagé ;
- frontend sans autorité trading, calcul Risk ou P&L parallèle.

## Batch 19.6B — patch proposé

Le patch frontend ajoute :

- navigation visible `Accueil | Marchés | Positions | Historique | Réglages` ;
- vue Marchés alimentée en priorité par la watchlist effective, avec ajout des positions ouvertes ;
- onglets marchés responsive et chargement du seul marché actif ;
- TradingView Lightweight Charts pour chandeliers OHLC et volume ;
- historique initial REST 19.6A puis mises à jour WebSocket cockpit, reconnexion et cleanup ;
- timeframes bornés aux capacités backend SPOT/PERPETUAL ;
- petit cache client non persistant ;
- contexte de position affiché uniquement depuis les faits portefeuille backend ;
- markers construits uniquement depuis les fills PAPER persistés ; `reduce_only` est affiché lorsqu'il existe, sans déduire une clôture ;
- sélection d'un fill -> chargement de l'explicabilité 19.5 du cycle corrélé ;
- aucune connexion frontend directe à Kraken et aucune candle/fill/causalité inventée.

Validation ChatGPT du patch : **6 tests frontend ciblés passés** ; parsing/transpilation TypeScript des nouveaux/modifiés `.ts/.tsx` passé. `pnpm lint`, `pnpm typecheck`, `pnpm build`, la validation WebSocket avec backend réel et la revue visuelle light/dark desktop/mobile restent à exécuter localement par l'opérateur.

## Prochaine priorité

1. extraire le ZIP 19.6B à la racine ;
2. installer/mettre à jour les dépendances frontend et le lockfile ;
3. exécuter tests, lint, typecheck et build ;
4. réaliser la revue visuelle et runtime ;
5. seulement après validation réelle, commit/push et clôture documentaire de 19.6B.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, puis distinguer clairement état intégré, modifications locales et patch proposé.
