# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec la base GitHub auditée et le patch local en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` intégré après le Batch 19.1 :
  `4e19381b093df81a947397f90a858f5f1b42886a`
  (`feat: add canonical SPOT position accounting`).
- Batch 19.1 intégré et validé localement : backend `516 passed`, frontend `pnpm lint`, `pnpm typecheck` et `pnpm build` réussis.

## État fonctionnel après application du Batch 19.1

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- `paper_executable_markets` reste un univers statique configuré par Campaign ;
- le portefeuille SPOT canonique expose désormais quantité, disponibilité, prix moyen d'entrée, coût de revient restant, P&L réalisé et `accounting_complete` ;
- les BUY SPOT successifs utilisent un coût économique moyen pondéré (`coût restant / quantité`) ; le coût de revient utilise le débit cash réel incluant les frais ;
- les ventes partielles libèrent le coût au prorata et réalisent le P&L à partir du crédit cash net ;
- spread/slippage sont déjà incorporés au prix du fill et ne sont pas ajoutés une seconde fois au coût ;
- les anciens snapshots sans base de coût restent récupérables avec `accounting_complete=false`, sans reconstruction rétrospective ;
- le P&L latent SPOT reste à implémenter par le monitoring/mark-to-market du Batch 19.2 ;
- le cockpit affiche les champs SPOT canoniques disponibles et ne reconstruit aucun calcul financier ;
- PERPETUAL conserve sa comptabilité, sa marge, liquidation et son funding existants ;
- frontend indépendant du moteur ; LIVE reste indisponible.

## Prochaine priorité

1. Batch 19.2 — monitoring / mark-to-market déterministe indépendant de l'IA ;
2. Batch 19.3 — mode gestion lorsque l'exposition interdit toute nouvelle ouverture ;
3. Batch 19.4 — découverte dynamique des marchés et watchlist auditée ;
4. Batch 19.5 — explicabilité dédiée IA / Risk ;
5. Batch 19.6A/19.6B — candles/WebSocket puis vue Marchés et charts.

Le cadrage détaillé reste centralisé dans `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, puis distinguer clairement état intégré, modifications locales et patch proposé.
