# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec la base GitHub auditée et le patch local en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` audité avant le Batch 19.2 :
  `01ca1e857947d969556481e5593c5712d137f5ad`
  (`docs: finalize Batch 19.1 integration state`).
- Le HEAD de référence encore écrit dans ce document au début du batch était `4e19381b093df81a947397f90a858f5f1b42886a` ; l'écart était uniquement le commit documentaire de clôture 19.1.
- Batch 19.1 intégré ; Batch 19.2 livré ici comme patch local, non intégré à GitHub par ChatGPT.

## État fonctionnel après application du patch Batch 19.2

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- comptabilité SPOT 19.1 conservée comme source canonique du coût moyen, coût restant et P&L réalisé ;
- chaque position SPOT peut désormais porter un mark causal `LAST_PRICE`, son timestamp, sa valeur de marché et son P&L latent ;
- `P&L latent SPOT = market_value - remaining_cost_basis` uniquement lorsque comptabilité et mark sont disponibles ;
- un mark absent ou périmé rend la valorisation indisponible au lieu de réutiliser silencieusement un ancien prix ;
- une position legacy `accounting_complete=false` peut afficher une valeur de marché si un mark existe, mais aucun P&L latent n'est inventé ;
- `PortfolioState` expose cash, coût restant SPOT, valeur SPOT, P&L réalisé/latent SPOT, equity et exposition lorsque calculables proprement ;
- des monitors backend SPOT/PERPETUAL indépendants du LLM rafraîchissent les marks (SPOT 5 s, PERPETUAL 15 s, timeout 5 s, staleness 30 s par défaut) ;
- le chemin d'exécution et le monitor alimentent le ledger via la source de marché canonique ; le `PaperBroker` ne déclenche pas lui-même de re-mark après un fill ;
- Agent et Risk consomment le même `PortfolioState` enrichi ; ils ne recalculent pas un P&L latent parallèle ;
- l'API expose les valeurs du backend ; le cockpit Positions ne recalcule plus le prix courant ni le P&L latent côté TypeScript ;
- frontend indépendant du moteur ; LIVE reste indisponible.

## Prochaine priorité

1. Batch 19.3 — mode gestion lorsque l'exposition interdit toute nouvelle ouverture ;
2. Batch 19.4 — découverte dynamique des marchés et watchlist auditée ;
3. Batch 19.5 — explicabilité dédiée IA / Risk ;
4. Batch 19.6A/19.6B — candles/WebSocket puis vue Marchés et charts.

Le cadrage détaillé reste centralisé dans `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, puis distinguer clairement état intégré, modifications locales et patch proposé.
