# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec la base GitHub auditée et le patch local en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` audité avant le Batch 19.3 :
  `44670a249ba662b2afd50a0a9e2a0e63ea4ed76d`
  (`feat: add canonical mark-to-market and unrealized pnl`).
- Le HEAD de référence encore écrit dans ce document au début du batch était `01ca1e857947d969556481e5593c5712d137f5ad` ; le Batch 19.2 a donc été intégré à GitHub depuis cette référence documentaire.
- Batches 19.1 et 19.2 intégrés ; Batch 19.3 livré ici comme patch local, non intégré à GitHub par ChatGPT.

## État fonctionnel après application du patch Batch 19.3

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- comptabilité SPOT 19.1 et mark-to-market/equity/exposition 19.2 restent les sources canoniques ;
- un `CapacityEvaluator` déterministe partage la même instance `RiskPolicy` que le `RiskEngine` ;
- chaque cycle multi-marchés recalcule un mode `NORMAL` ou `MANAGEMENT` depuis le `PortfolioState` courant et les limites déjà connues avant sélection ;
- `NORMAL` conserve la sélection stratégique existante et les tools read-only ;
- `MANAGEMENT` limite la sélection du même Agent aux marchés correspondant aux positions réellement ouvertes et désactive les tools de recherche d'ouverture ;
- HOLD, réduction partielle et clôture restent proposés par le même Agent puis soumis à Risk ;
- Risk refuse explicitement toute action qui augmenterait l'exposition pendant un cycle `MANAGEMENT` ;
- une valorisation incomplète ne crée aucune capacité fictive : le mode devient `MANAGEMENT` avec raison explicite ;
- les contraintes nécessitant le `MarketState` exact (minimum d'ordre, marge effective, levier instrument, liquidation) restent exclusivement évaluées par Risk ;
- le mode n'est pas persisté comme état mutable : il est recalculé après recovery à chaque cycle ;
- le mode, sa raison et le fait que la recherche d'ouverture a été évitée sont intégrés à l'audit JSON du cycle ;
- aucune métrique de tokens n'est inventée : l'infrastructure actuelle n'expose pas d'usage tokens canonique ;
- frontend inchangé pour 19.3 ; aucune nouvelle dépendance du moteur au cockpit.

## Prochaine priorité

1. Batch 19.4 — découverte dynamique des marchés et watchlist auditée ;
2. Batch 19.5 — explicabilité dédiée IA / Risk ;
3. Batch 19.6A/19.6B — candles/WebSocket puis vue Marchés et charts.

Le cadrage détaillé reste centralisé dans `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, puis distinguer clairement état intégré, modifications locales et patch proposé.
