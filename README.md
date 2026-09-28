# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **PAPER** sur Kraken, pilotée par **un seul Agent IA stratégique**. L'Agent recherche/sélectionne les opportunités puis, au stade décisionnel du cycle, produit un **plan ordonné** de décisions `BUY`, `SELL` ou `HOLD` sur des marchés distincts. Le **Risk Engine déterministe** conserve l'autorité finale sur chaque décision avant toute exécution éventuelle par le `PaperBroker`.

> Objectif expérimental : rechercher une performance élevée, avec une cible de travail de +4 %/jour. Ce n'est ni une promesse ni une garantie de rendement. Cette cible n'est pas injectée dans les instructions stratégiques courantes du LLM.

## Parcours utilisateur

Le concept principal du cockpit est la **Session** : l'utilisateur crée une Session, la configure, la démarre, l'arrête, la reprend, la duplique ou la retire de son parcours courant.

```text
Accueil | Sessions | Marchés | Positions | Historique | Réglages
```

Les objets techniques historiques restent canoniques derrière cette façade :

```text
Session UX
  ↓
Strategy                         identité technique stable
  ↓
StrategyRevision(s)              instructions versionnées et immuables
  ↓
Campaign(s)                      configuration versionnée et immuable
  ↓
paper_run(s) / recovery         lifetime d'exécution PAPER
```

`Strategy`, `StrategyRevision`, `Campaign`, digests et IDs restent consultables dans **Réglages > Avancé** mais ne sont pas nécessaires au parcours normal.

## Configuration d'une Session

La configuration simple demande notamment :

- nom et capital PAPER ;
- `SPOT` ou `PERPETUAL` ;
- style `SCALP` ou `SWING` ;
- mode de marchés ;
- modèle IA Luna/Sol ;
- agressivité 1–10 ;
- profil Risk ;
- instructions IA/opérateur.

Deux modes de marchés sont disponibles :

- **Automatique — IA** : Kraken → admissibilité déterministe → candidats → même Agent IA → watchlist ; le bootstrap reste un fallback, pas une obligation de trader ;
- **Manuel** : `market_discovery = null`, l'univers exécutable est la liste fournie et la whitelist Risk est alignée sur cet univers.

La configuration avancée expose les valeurs réellement persistées : cadence, coûts PAPER, timeouts, paramètres Risk, limites PERPETUAL, paramètres de discovery et `max_decisions_per_cycle`.

## Cycle stratégique multi-marchés

Le cycle décisionnel n'est plus limité à une seule décision. Après constitution du contexte causal, le même Agent effectue **un seul appel stratégique de planification** et retourne une trajectoire ordonnée bornée.

```text
Kraken / données causales
-> admissibilité déterministe + watchlist éventuelle
-> même Agent IA : plan ordonné [décision 1 ... décision N]
-> pour chaque décision, dans l'ordre :
     portefeuille courant
     -> RiskEngine : ALLOW / MODIFY / REJECT
     -> ExecutionIntent éventuel
     -> PaperBroker éventuel
     -> ledger mis à jour
-> audit durable de la trajectoire complète
```

Règles principales :

- plusieurs `BUY`, `SELL` et `HOLD` peuvent coexister dans un même cycle sur des marchés distincts ;
- chaque décision suivante voit les effets PAPER des exécutions précédentes ;
- `HOLD` et `REJECT` n'arrêtent pas la trajectoire ;
- une erreur technique Risk/Broker fait échouer le cycle et restaure atomiquement le portefeuille PAPER au checkpoint de début de cycle ;
- `max_decisions_per_cycle` vaut `6` par défaut et ne peut pas dépasser `20` ;
- le nombre de décisions n'est pas assimilé au nombre de trades : les analytics comptent les fills/trades économiques réellement exécutés.

Le multi-décisions ne crée ni second Agent, ni ranking algorithmique stratégique, ni contournement Risk.

## Agressivité, coûts et allocation du capital

Les prompts Campaign courants utilisent `aggressiveness-map-v3`, tandis que le mapping historique `aggressiveness-map-v1` reste figé pour les identités expérimentales et replays existants.

L'agressivité 1–10 influence la volonté d'agir et le degré d'initiative lorsqu'une opportunité est convaincante. Elle ne relâche jamais Risk, n'impose jamais une taille maximale et ne doit pas être interprétée comme une obligation d'augmenter le turnover, la fréquence des trades ou les micro-trades.

L'objectif économique stratégique courant est la progression de l'**equity nette après coûts**. Frais, spread, slippage et funding lorsqu'il est disponible dans les faits fournis font partie du résultat économique.

L'Agent raisonne en allocation et coût d'opportunité entre cash, positions existantes et nouvelles opportunités. `HOLD`, conserver du cash ou conserver une position sont des allocations stratégiques valides. Une rotation doit être préférable à l'allocation actuelle après prise en compte des coûts cumulés, sans seuil de profit, cooldown, durée minimale ou score déterministe.

Une faible conviction ne doit pas être transformée mécaniquement en petite position « pour essayer ».

## Invariants

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- PAPER uniquement ; LIVE séparé et ultérieur ;
- SPOT sans short/levier/marge ; PERPETUAL selon les capacités intégrées ;
- FUTURE daté interdit ;
- aucune sortie LLM → Broker/Kraken ;
- Risk Engine déterministe = autorité finale ;
- exécution séquentielle et causale des décisions ;
- frais, spread, slippage, accounting et mark-to-market canoniques côté backend ;
- toutes les décisions, y compris `HOLD` et les décisions rejetées par Risk, restent auditables ;
- aucun look-ahead ;
- aucun secret dans prompts, logs, réponses UI ou fichiers versionnés ;
- frontend = cockpit ; aucune logique Risk/P&L/Broker/discovery stratégique parallèle.

Principe : **l'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## Lifecycle et historique

La façade `/api/v1/sessions` conserve la création atomique, le versioning immuable, l'archivage logique et les actions `Démarrer`, `Arrêter`, `Reprendre`, `Tester 1 cycle`. Fermer le frontend ne stoppe jamais le backend.

Un cycle expose une trajectoire ordonnée 1:N : plusieurs décisions peuvent posséder leurs évaluations Risk et leurs intentions/fills associés. Les anciens cycles restent lisibles via la compatibilité historique.

Le `AGENT_SYSTEM_PROMPT` historique `agent-strategy-v4` reste figé pour préserver les protocoles expérimentaux existants ; le recalibrage courant s'applique via `StrategyInstructionsClient`.

## Persistence

La persistence d'audit utilise la migration :

```text
0006_paper_control_plane
-> 0007_multi_decision_cycles
```

Les relations 1:N couvrent les décisions, `RiskAssessment` et `ExecutionIntent` d'un cycle, tout en conservant la lecture des historiques antérieurs.

## Référence de travail

HEAD GitHub intégré vérifié le 28 septembre 2026 :

```text
463850d8281faebe86a6ee733d58781c349015d0
refactor: make strategic agent cost aware
```

Le recalibrage net/cost-aware est intégré à GitHub `main` dans `463850d`. Les prompts Campaign courants utilisent donc l'objectif économique net après coûts et `aggressiveness-map-v3`, tandis que les identités historiques restent inchangées.
