# 09 — Roadmap de développement

## Règle de lecture

Un batch est **intégré** uniquement après validation locale, commit et push confirmés sur GitHub `main`. Un ZIP livré par ChatGPT reste un patch proposé tant que ces étapes ne sont pas réalisées.

## Historique intégré synthétique

- Batches 00–15.3 : socle SPOT PAPER, Agent, Risk, Broker, PostgreSQL, API/cockpit, analytics et expériences.
- Batch 16 : Kraken Derivatives PAPER, LONG/SHORT, marge ISOLATED, levier déterministe, funding, P&L et anti-reversal.
- Batch 16.2 : isolation durable par `paper_run_id`.
- Batch 16.3 : smokes LONG/SHORT contrôlés.
- Batch 16.5 : contexte PERPETUAL causal via `MarketStateBuilder` et bougies mark publiques.
- Batch 16.6 : validation comportementale Luna sans forcer BUY/SELL.
- Prompt `agent-strategy-v4` : localisation française.
- Batch 17 : durcissement fail-closed de la frontière Kraken Derivatives publique.

Référence intégrée actuelle avant Batch 18.1 : `main = ca5077af00293ccca9794132ee0dd53a5b339911`; `baseline-batch17` pointe sur ce commit.

## Batch 18.1 — Socle Agent tools read-only et tool loop OpenAI bornée

**État : patch proposé, non intégré.**

### Objectif

Permettre au même Agent stratégique de rechercher des faits marché de façon volontaire et bornée avant sa décision, sans déplacer l'autorité de Risk et sans encore rendre un autre symbole exécutable.

### Périmètre proposé

- `MarketResearchService` provider-agnostic ;
- tools `list_markets` et `get_market_snapshot` uniquement ;
- sources Kraken de recherche séparées des sources de trading ;
- SPOT + PERPETUAL snapshots ; catalogue pouvant inclure FUTURE ;
- Responses API `store=false`, strict functions, `parallel_tool_calls=false` ;
- max calls, timeout et taille de résultat configurables ;
- erreurs fournisseur sanitizées ;
- traces causales complètes avec digest ;
- migration `0003_agent_tool_traces` ;
- persistance des traces même lors d'un échec Agent avant décision finale ;
- digest de cycle intégrant les traces.

### Ce que 18.1 ne fait pas

- pas de ranking/scanner/momentum score ;
- pas de second Agent ;
- pas d'order tool ;
- pas de LIVE/private Kraken ;
- pas de remplacement du `MarketState` de Risk/Broker par un snapshot recherché ;
- pas de décision exécutable sur un symbole différent du `paper_symbol`.

### Critère de sortie

Après validation locale complète : l'Agent peut décider sans tool, appeler un ou plusieurs tools, recevoir des résultats bornés/auditables, puis produire un `DecisionCandidate` toujours limité au symbole initial du cycle.

## Batch 18.2 — Vrai choix de marché exécutable

**À concevoir séparément après intégration/validation de 18.1.**

Le problème à résoudre n'est pas seulement d'autoriser `DecisionCandidate.symbol != AgentInput.market_state.symbol`. Il faut réorganiser causalement le cycle pour que :

1. l'Agent choisisse un marché à partir de faits disponibles ;
2. le backend acquière/valide le `MarketState` exact de ce marché ;
3. le portefeuille complet reste visible ;
4. Risk évalue la bonne paire/le bon type ;
5. Broker utilise exactement le snapshot autorisé ;
6. l'audit relie sélection, snapshot final, décision, Risk et fill sans look-ahead.

Aucun raccourci consistant à réutiliser le `MarketState` du `paper_symbol` pour une autre décision n'est acceptable.

## Après 18.2 — pistes à décider

- protocole expérimental versionnant explicitement la politique de tools ;
- univers multi-marché configurable et politique de coûts/cache ;
- snapshots FUTURE génériques si l'exécution datée devient réellement supportée ;
- enrichissements mesurés : order book, volume, recent trades ou funding historique uniquement si un besoin empirique le justifie ;
- recovery durable du ledger PAPER ;
- LIVE toujours en batch séparé.
