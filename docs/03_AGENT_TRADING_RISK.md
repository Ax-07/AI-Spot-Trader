# 03 — Agent, trading et Risk

## 1. Principe d'autorité

**L'Agent propose. Le Risk Engine autorise, modifie ou refuse.**

Le Batch 19.4 ne change pas cette hiérarchie. Le déterministe décrit et borne l'univers ; l'Agent conserve le jugement stratégique ; Risk conserve l'autorité finale.

## 2. Un seul Agent, trois phases possibles

```text
DISCOVERY (cadence lente)
MarketDiscoveryInput -> même Agent -> WatchlistSelection

NORMAL (cycle stratégique)
MarketSelectionInput -> select_market() -> MarketSelection
AgentInput           -> generate_decision() -> DecisionCandidate

MANAGEMENT
MarketSelectionInput -> select_management_market() -> MarketSelection
AgentInput           -> generate_management_decision() -> DecisionCandidate
```

La phase discovery utilise un adaptateur sur le même `OpenAIDecisionProvider`, le même modèle et le même client. Elle ne constitue pas un second Agent.

## 3. Contrat de découverte

L'input discovery contient uniquement des candidats déjà validés factuellement par le backend. Pour chaque candidat, l'Agent reçoit l'adresse de marché et un snapshot public normalisé.

Le contrat exige :

- choisir de 1 à `watchlist_limit` marchés ;
- choisir uniquement parmi `candidates` ;
- ne jamais inventer un symbole ou un type ;
- fournir une justification structurée ;
- comprendre que la watchlist est une liste de surveillance et ne déclenche aucun ordre.

La sortie est validée fail-closed. Un marché hors candidat, un doublon, une liste vide ou une sortie structurée invalide provoque un fallback audité.

## 4. Ce que fait le déterministe

Il peut éliminer un marché pour raisons objectives : type non supporté, quote incompatible, statut non tradable, contrat non linéaire, snapshot manquant/trop ancien, historique insuffisant ou whitelist Risk explicite.

Il ne calcule pas de score d'opportunité, ne recommande pas BUY/SELL et ne choisit pas la watchlist à la place de l'Agent.

## 5. NORMAL et MANAGEMENT

### NORMAL

Lorsque la capacité de nouvelle exposition est théoriquement disponible :

- la discovery peut renouveler la watchlist si sa cadence est échue ;
- le cycle de trading sélectionne ensuite **un** marché dans l'univers effectif ;
- l'Agent produit BUY/SELL/HOLD ;
- Risk évalue la décision sur le `MarketState` exact.

### MANAGEMENT

Lorsque la capacité est indisponible ou incertaine :

- aucun refresh de discovery destiné à ouvrir de nouvelles expositions ;
- aucun appel LLM de watchlist ;
- le même Agent choisit seulement parmi les positions ouvertes ;
- HOLD/réduction/clôture restent stratégiques ;
- Risk rejette toute hausse d'exposition avec la barrière 19.3.

Le statut `SKIPPED_MANAGEMENT` est audité pour la discovery.

## 6. Watchlist + positions ouvertes

Invariant :

```text
univers effectif = watchlist IA actuelle + toutes les positions ouvertes
```

Un retrait de watchlist n'est donc jamais une clôture forcée et ne rend jamais une position ingérable. Une position peut continuer à être sélectionnée en MANAGEMENT ou dans l'univers effectif NORMAL jusqu'à sa clôture.

## 7. SPOT

`BUY` acquiert la base ; `SELL` réduit uniquement un actif réellement détenu. Aucun short, levier ou margin SPOT.

La discovery n'affaiblit pas ces règles. Une paire SPOT dynamique doit utiliser le settlement asset de la Campaign et exister réellement via la source Kraken canonique avant toute décision finale.

## 8. PERPETUAL

Seuls les PERPETUAL linéaires sont admissibles dynamiquement. Le LLM ne choisit toujours jamais levier, marge ou `reduce_only`. Risk conserve le contrôle de taille, levier, marge, notional, exposition, liquidation et anti-reversal.

## 9. Risk whitelist dynamique

Une whitelist `risk_allowed_pairs` explicite reste un filtre déterministe fort et réduit aussi l'univers discovery. Pour une Campaign dynamique, elle peut être omise (`null`) afin d'autoriser la découverte Kraken au-delà du bootstrap ; cela ne désactive aucune autre règle Risk.

Une Campaign statique continue d'exiger une whitelist.

## 10. Rationale et audit

Deux rationales restent conceptuellement distincts :

- rationale de watchlist : pourquoi l'Agent souhaite surveiller ce marché ;
- rationale de décision : pourquoi l'Agent propose BUY/SELL/HOLD sur le marché sélectionné.

Les raisons Risk sont encore une troisième catégorie, déterministe. Le Batch 19.5 traitera leur exposition UI dédiée.

Le cycle auditera la watchlist précédente/effective, les ajouts/maintiens/retraits, les rationales et les erreurs/fallbacks sans prétendre qu'une sélection de watchlist est un ordre.

## 11. Causalité / no-look-ahead

Aucun candidat ne peut contenir un snapshot ou une observation postérieure à `MarketDiscoveryInput.created_at`. Le `MarketSelection` et le `AgentInput` conservent leurs contrôles chronologiques existants. Aucun choix n'est réécrit après observation du futur.

## 12. Recovery

Le recovery ne rejoue jamais une ancienne sélection IA. Les positions sont restaurées par le ledger durable. En reprise dynamique, leurs marchés sont réintroduits dans l'univers du run pour rester gérables. La watchlist est reconstruite plus tard lorsque le mode NORMAL et la cadence le permettent.

## 13. Économie IA

La discovery possède une cadence lente indépendante. Les erreurs sont temporisées. En MANAGEMENT, elle est explicitement sautée. Aucune économie de tokens chiffrée n'est inventée tant que l'infrastructure ne persiste pas de métriques d'usage canoniques.

## 14. Interdits maintenus

- aucun LIVE ;
- aucun second Agent ;
- aucun ranking déterministe remplaçant le jugement stratégique ;
- aucun ordre direct LLM/tool ;
- aucun contournement Risk ;
- aucun look-ahead ;
- aucune obligation de trader ;
- aucun calcul stratégique ou financier canonique déporté dans le frontend.
