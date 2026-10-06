# AI Spot Trader

AI Spot Trader est une application expérimentale de trading crypto **PAPER** sur Kraken, pilotée par **un seul Agent IA stratégique**. Le Market Attention Radar détermine l'univers dynamique de marchés que cet Agent doit examiner ; l'Agent reçoit désormais aussi un contexte Radar/Analytics **causal, borné et descriptif** pour ces seuls marchés, puis produit un **plan ordonné** de décisions `BUY`, `SELL` ou `HOLD`. Le **Risk Engine déterministe** conserve l'autorité finale sur chaque décision avant toute exécution éventuelle par le `PaperBroker`.

Le runtime PAPER canonique accepte officiellement des marchés **SPOT** et des **PERPETUAL linéaires Kraken**. Sur PERPETUAL, l'Agent peut exprimer des expositions LONG ou SHORT avec les mêmes actions `BUY` / `SELL`, mais il ne choisit ni le levier, ni la marge, ni `reduce_only` : ces paramètres restent contrôlés par la configuration et le Risk Engine. Les `FUTURE` datés et toute exécution LIVE restent hors périmètre.

> Objectif expérimental : rechercher une performance élevée, avec une cible de travail de +4 %/jour. Ce n'est ni une promesse ni une garantie de rendement. Cette cible n'est pas injectée dans les instructions stratégiques courantes du LLM.

## Parcours utilisateur

Le concept principal du cockpit est la **Session** : l'utilisateur crée une Session, la configure, la démarre, l'arrête, la reprend, la duplique ou la retire de son parcours courant.

```text
Accueil | Sessions | Marchés | Positions | Historique | Réglages
```

Le cockpit expose également un panneau global **Market Attention**. Ce panneau décrit l'attention détectée et l'univers candidat ; il ne constitue jamais une recommandation `BUY`, `SELL` ou `HOLD` et n'a aucune autorité Risk.

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
- modèle IA Luna/Sol dans le snapshot Campaign ; le provider `OPENAI`/`OLLAMA` est configuré côté backend au niveau process/runtime dans le Batch 51.1 ;
- agressivité 1–10 ;
- profil Risk ;
- instructions IA/opérateur.

Deux modes de marchés sont disponibles :

- **Automatique — IA** : Kraken → Radar déterministe → shortlist bornée → univers typé `SPOT`/`PERPETUAL` → contexte Radar/Analytics causal → même Agent IA stratégique. Le Radar choisit où regarder et fournit des faits ; il ne choisit jamais quoi trader ;
- **Manuel** : `market_discovery = null`, l'univers exécutable est la liste fournie et la whitelist Risk est alignée sur cet univers.

La configuration avancée expose les valeurs réellement persistées : cadence, coûts PAPER, timeouts, paramètres Risk, limites PERPETUAL, paramètres de discovery et `max_decisions_per_cycle`.

## Provider LLM : OpenAI ou Ollama

Le Batch 51.1 introduit une frontière de transport LLM sans créer de second Agent. Le même pipeline stratégique, les mêmes contextes Radar/multi-timeframe/thèse et les mêmes validations métier restent utilisés.

Configuration backend :

```env
AI_SPOT_TRADER_LLM_PROVIDER=OPENAI
AI_SPOT_TRADER_LLM_MODEL=gpt-5.6-luna

# ou, pour exécuter le moteur LLM localement :
AI_SPOT_TRADER_LLM_PROVIDER=OLLAMA
AI_SPOT_TRADER_OLLAMA_BASE_URL=http://localhost:11434
AI_SPOT_TRADER_OLLAMA_MODEL=qwen3.5:9b
AI_SPOT_TRADER_OLLAMA_TIMEOUT_SECONDS=60
```

En mode `OLLAMA`, `AI_SPOT_TRADER_OPENAI_API_KEY` n'est pas requise et aucun fallback silencieux vers OpenAI n'existe. Le choix du provider est process/runtime dans 51.1 ; la Campaign conserve son champ `llm_model` Luna/Sol pour compatibilité des snapshots/digests. Un sélecteur UX/persisté est réservé au Batch 51.2.

Le client Ollama utilise `/api/chat`, transmet le JSON Schema canonique via `format`, puis laisse les providers existants appliquer exactement la même validation Pydantic. Les tools Agent read-only utilisent le même registre borné. Le chat opérateur reste volontairement désactivé en mode local pour ce premier batch afin de garantir l'absence d'appel OpenAI implicite.

Smoke test minimal PowerShell :

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

## Exécution PERPETUAL PAPER

La chaîne d'exécution PERPETUAL réutilise les composants canoniques existants :

```text
Agent
-> DecisionCandidate (market_type=PERPETUAL)
-> Risk Engine
-> ExecutionIntent PAPER
-> PaperBroker
-> DerivativePosition
-> mark-to-market / funding / P&L / liquidation théorique
-> audit
```

Sémantique stratégique :

- sans position : `BUY` ouvre LONG, `SELL` ouvre SHORT ;
- avec LONG : `BUY` augmente LONG, `SELL` réduit ou ferme LONG ;
- avec SHORT : `SELL` augmente SHORT, `BUY` réduit ou ferme SHORT ;
- `HOLD` ne produit aucun `ExecutionIntent` ;
- un ordre opposé surdimensionné ne retourne jamais silencieusement la position : le Risk Engine le borne à la fermeture (`reduce_only`) ou le rejette selon la policy. Un retournement exige donc une fermeture puis une décision ultérieure d'ouverture opposée.

Le levier exécutable est borné par la configuration, les métadonnées de marge de l'instrument et les limites Risk. Une sortie LLM ne peut pas imposer directement un levier, une marge ou un contournement de ces limites.

## Cycle stratégique multi-marchés

Le cycle décisionnel n'est plus limité à une seule décision. Après constitution du contexte causal, le même Agent effectue **un seul appel stratégique de planification** et retourne une trajectoire ordonnée bornée.

```text
Kraken / Market Attention Radar
-> filtres déterministes Radar
-> shortlist Radar bornée
-> validation contre le catalogue exécutable Kraken + Campaign/Risk
-> univers typé SPOT/PERPETUAL
-> projection causale Radar/Analytics pour cet univers
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

## Market Attention Radar

Le Radar indique où une activité inhabituelle commence potentiellement à émerger. Depuis le Batch 49.2 intégré via `f0d4f94`, sa shortlist alimente l'**univers candidat** présenté au même Agent stratégique. Le Batch 49.3 ajoute une projection causale et bornée de faits descriptifs, sans transformer le Radar en signal de trading.

```text
candles / données publiques Kraken
-> activité, liquidité, microstructure, structure et analytics Radar
-> filtres déterministes
-> shortlist bornée
-> projection identité 49.2 : {symbol, market_type}
-> validation exécutable
-> projection contexte 49.3 : faits causaux compacts
-> Agent stratégique unique
```

### Contexte 49.3

Le contexte stratégique Radar/Analytics est un contrat dédié, distinct du contexte candles multi-timeframes. Il ne peut contenir que des marchés déjà admis dans l'univers Agent et est filtré une dernière fois sur les `market_states` effectivement visibles par le plan.

Par marché, il expose de façon bornée :

- activité, tendance récente, fraîcheur, qualité et caractéristiques descriptives ;
- jusqu'à quatre horizons d'activité avec ratio/anomalie de volume et mouvement récent ;
- liquidité et microstructure SPOT compacte ;
- Market Structure globale + jusqu'à quatre timeframes ;
- pour PERPETUAL : score Analytics 47.5 `0..4`, composantes OI/Funding/Liquidations/ORDER_FLOW, Open Interest, Funding, Liquidation Volume, CVD et Aggressor Differential ;
- statuts explicites pour les données absentes ou dégradées.

Le score Analytics reste un **indice d'attention descriptif**. Il n'est ni une probabilité de hausse/baisse, ni une conviction imposée, ni une action `BUY`/`SELL`.

CVD et Aggressor Differential restent une seule famille `ORDER_FLOW`. Les poids/seuils 47.5 ne sont pas recalibrés.

Pour SPOT, les Analytics Futures sont explicitement `NOT_APPLICABLE`. Les diagnostics techniques internes, rangs avant/après, `rank_change`, historiques bruts, swings complets, erreurs brutes et métadonnées d'observabilité inutiles ne sont pas envoyés à l'Agent.

### Causalité et mode dégradé

Une identité issue de la shortlist n'entre dans l'univers Agent que si elle reste compatible avec le catalogue public Kraken et la configuration de la Campaign : type activé, quote de règlement compatible, statut tradable, PERPETUAL linéaire, whitelist Risk éventuelle et présence effective dans le catalogue. Les `FUTURE` datés restent non exécutables.

Le contexte 49.3 est construit uniquement si le snapshot relu porte exactement le même `observed_at` que celui utilisé par Discovery. Chaque timestamp imbriqué doit être antérieur ou égal à cette frontière, elle-même antérieure ou égale au `CycleDecisionPlanInput.created_at`. Aucun look-ahead n'est admis.

Une shortlist vide, un Radar `ERROR`/`NOT_CONFIGURED`, un snapshot stale, une shortlist sans candidat exécutable ou une incohérence de snapshot n'est jamais transformé en signal. Pour les **nouvelles ouvertures**, le runtime échoue fermé. Si des positions existent déjà, elles peuvent continuer à être présentées au même Agent en mode de gestion seulement ; aucune nouvelle exposition n'est autorisée par ce fallback.

Le Radar n'appelle jamais directement le Risk Engine ni le Broker.

## Invariants

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- PAPER uniquement ; LIVE séparé et ultérieur ;
- SPOT sans short/levier/marge ;
- PERPETUAL linéaire PAPER exécutable en LONG/SHORT sous autorité Risk ;
- FUTURE daté interdit ;
- aucune sortie LLM → Broker/Kraken ;
- Radar = source d'univers candidat et de faits descriptifs, jamais autorité `BUY`/`SELL`/`HOLD` ni autorité Risk ;
- Risk Engine déterministe = autorité finale ;
- exécution séquentielle et causale des décisions ;
- frais, spread, slippage, accounting, funding et mark-to-market canoniques côté backend ;
- toutes les décisions, y compris `HOLD` et les décisions rejetées par Risk, restent auditables ;
- aucun look-ahead ;
- aucun secret dans prompts, logs, réponses UI ou fichiers versionnés ;
- frontend = cockpit ; aucune logique Risk/P&L/Broker/discovery stratégique parallèle.

Principe : **le Radar propose les marchés à examiner. Les faits Radar/Analytics aident l'Agent à raisonner. L'IA propose l'action. Le Risk Engine autorise, modifie ou refuse.**

## Lifecycle et historique

La façade `/api/v1/sessions` conserve la création atomique, le versioning immuable, l'archivage logique et les actions `Démarrer`, `Arrêter`, `Reprendre`, `Tester 1 cycle`. Fermer le frontend ne stoppe jamais le backend.

Un cycle expose une trajectoire ordonnée 1:N : plusieurs décisions peuvent posséder leurs évaluations Risk et leurs intentions/fills associés. Les anciens cycles restent lisibles via la compatibilité historique.

Le `AGENT_SYSTEM_PROMPT` historique `agent-strategy-v4` reste figé pour préserver les protocoles expérimentaux existants ; le recalibrage courant s'applique via `StrategyInstructionsClient`.

Le Radar est backend-owned en composition PAPER et continue de fonctionner indépendamment du cockpit tant que le backend tourne. Les Campaigns dynamiques consomment sa dernière shortlist admissible via la frontière canonique `MarketDiscoveryCoordinator` et le même service fournit la projection causale 49.3 avant l'appel stratégique.

## Persistence

La persistence d'audit trading utilise la migration :

```text
0006_paper_control_plane
-> 0007_multi_decision_cycles
```

Les relations 1:N couvrent les décisions, `RiskAssessment` et `ExecutionIntent` d'un cycle, tout en conservant la lecture des historiques antérieurs.

Les Batches 49.2 et 49.3 n'ajoutent aucune migration. Le contexte 49.3 est une entrée causale du plan, pas une nouvelle voie d'exécution ou une nouvelle persistence Radar.

## Référence de travail

Base GitHub réellement auditée pour le Batch 51.1, le 6 octobre 2026 :

```text
e5887da5e8e6ebf0fa739a041c0226a6fed940dd
feat: add strategic thesis observability
```

Le Batch 50.2 est intégré sur cette base. Le Batch 51.1 conserve Risk, Broker, Radar, mémoire de thèse et contrats métier inchangés ; il ajoute uniquement la frontière de provider LLM et l'adaptateur Ollama associé.
