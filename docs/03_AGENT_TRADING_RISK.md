# 03 — Agent, trading et Risk

## 1. Principe d'autorité

**L'Agent propose. Le Risk Engine autorise, modifie ou refuse.**

Le cycle multi-marchés change la cardinalité d'un cycle, pas la hiérarchie d'autorité. Le déterministe prépare les faits et applique les contraintes ; l'Agent conserve le jugement stratégique ; Risk conserve l'autorité finale sur chaque décision.

## 2. Un seul Agent, phases distinctes

```text
DISCOVERY
MarketDiscoveryInput -> même Agent -> WatchlistSelection

CYCLE STRATÉGIQUE
CycleDecisionPlanInput -> même Agent -> CycleDecisionPlan ordonné

EXÉCUTION DU PLAN
D1 -> Risk -> Broker éventuel
D2 -> Risk -> Broker éventuel
...
Dn -> Risk -> Broker éventuel
```

La discovery utilise toujours le même Agent stratégique et ne constitue pas un second Agent. Au stade décisionnel du cycle, un seul appel stratégique produit la trajectoire ordonnée plutôt qu'une succession d'appels opportunistes.

Le protocole protégé courant de ce stade est `strategic-multi-market-plan-v1`. Le contrat singleton historique (`MarketSelectionInput -> AgentInput`) reste conservé pour compatibilité et replay, mais il n'est plus injecté comme contrat final du nouveau chemin de planification.

## 3. Contrat de plan multi-décisions

Le plan peut contenir plusieurs `BUY`, `SELL` et `HOLD` sur des marchés distincts de l'univers causal du cycle.

Contraintes :

- ordre explicite ;
- symboles/types limités aux `market_states` fournis ;
- pas de marché inventé ;
- pas de doublon `symbol + market_type` ;
- `max_decisions_per_cycle` configurable ;
- défaut `6` ;
- limite dure `20` ;
- sortie structurée validée fail-closed.

Le schéma Structured Outputs et la validation Pydantic portent le même contrat quantité/action :

```text
BUY  -> proposed_quantity > 0
SELL -> proposed_quantity > 0
HOLD -> proposed_quantity = null
```

Une sortie qui ne respecte pas ce contrat est un échec Agent. Elle n'est jamais réparée silencieusement, convertie en `HOLD`, ni envoyée à Risk.

L'ordre du plan a un sens causal : il détermine l'ordre d'évaluation Risk et d'exécution éventuelle.

## 4. Recalibrage stratégique cost-aware

Le chemin Session/Campaign courant ne reçoit pas la cible expérimentale `+4 %/jour` dans ses instructions LLM. Cette cible reste un objectif expérimental documenté et non garanti ; elle ne doit pas agir comme un signal implicite de sur-trading.

Le contrat courant rend désormais explicite que l'objectif économique stratégique est la **progression de l'equity nette après coûts**, et non le volume de trades ou le turnover. Les frais, le spread, le slippage et le funding lorsqu'il est présent dans les faits fournis font partie du résultat économique.

Le mapping durable `aggressiveness-map-v1` reste figé pour les manifests/replays historiques. Le chemin LLM courant utilise `aggressiveness-map-v3`, toujours sur l'échelle 1–10 :

- niveaux bas : sélectivité et retenue accrues ;
- niveaux élevés : davantage d'initiative lorsque l'opportunité est convaincante et économiquement préférable à l'allocation actuelle ;
- tous niveaux : `HOLD`, conserver du cash ou conserver une position existante restent valides.

Le mapping courant ne doit plus transformer l'agressivité en obligation de fréquence, turnover, micro-trades ou rotation. Une faible conviction ne doit pas être convertie mécaniquement en petite position « pour essayer ».

Invariant de sizing :

> Un niveau d'agressivité élevé, y compris 10/10, n'implique jamais d'utiliser la quantité maximale. La quantité proposée doit rester proportionnée à la qualité et à la conviction de la thèse, aux faits réellement fournis, aux coûts, à l'exposition existante et au capital déjà engagé.

Le contrat protégé courant rappelle également :

- ne jamais trader simplement pour produire de l'activité ;
- ne jamais trader pour atteindre une cible de rendement ;
- une opportunité n'est pas intéressante simplement parce qu'elle est tradable ;
- qualité économique nette attendue > activité brute ;
- agressivité != relâchement de Risk ;
- aucune règle déterministe de seuil de profit, cooldown, durée minimale, quota de trades ou score d'opportunité.

La section `CONTEXTE D'AGRESSIVITE CANONIQUE` est composée par un helper partagé entre le chemin singleton courant, la discovery et le plan multi-marchés. Le champ reste `niveau=<1..10>/10`.

Le `AGENT_SYSTEM_PROMPT` `agent-strategy-v4` reste volontairement figé pour préserver l'identité des protocoles expérimentaux historiques v1/v2/v3 et leurs replays. Il ne constitue pas le contrat injecté par les Sessions/Campaigns actuelles via `StrategyInstructionsClient`.

## 5. Allocation du capital et coût d'opportunité

Le même Agent doit raisonner sur l'allocation globale entre :

- cash disponible ;
- positions existantes ;
- nouvelles opportunités.

Conserver du cash est une allocation stratégique. Conserver une position existante l'est également.

Une rotation de capital peut nécessiter plusieurs exécutions : réduire/fermer une position, puis ouvrir/augmenter une autre. Ces étapes cumulent frais, spread, slippage et, selon le contexte PERPETUAL, effets de funding. Le contrat demande donc une justification stratégique suffisamment forte pour préférer la rotation à la conservation de l'allocation actuelle après coûts.

Cette comparaison reste qualitative. Aucun seuil chiffré de rentabilité ou score algorithmique n'est introduit.

## 6. Ce que fait le déterministe

Le déterministe peut :

- filtrer type de marché, quote, statut tradable, fraîcheur des données et whitelist ;
- calculer contexte candles, coûts, portefeuille, exposition et contraintes ;
- appliquer Risk ;
- exécuter/persister en PAPER lorsqu'un `ExecutionIntent` autorisé existe.

Il ne calcule pas un ranking stratégique destiné à remplacer le plan Agent, ne force pas BUY/SELL et ne choisit pas une rotation automatique.

## 7. NORMAL et MANAGEMENT

### NORMAL

Lorsque la capacité de nouvelle exposition existe, l'univers peut contenir watchlist et positions ouvertes. Le plan Agent peut arbitrer entre plusieurs marchés et plusieurs actions dans le même cycle.

### MANAGEMENT

Lorsque la capacité d'ouverture est indisponible ou incertaine :

- pas de refresh discovery destiné à de nouvelles ouvertures ;
- les positions ouvertes restent l'univers de gestion ;
- réduction, clôture ou `HOLD` restent stratégiques ;
- Risk refuse toute augmentation d'exposition incompatible.

Le contexte de gestion est descriptif. Sa formulation courante est directionnellement neutre : sur PERPETUAL, `SELL` réduit un LONG et `BUY` réduit un SHORT ; aucune direction n'est privilégiée.

Le passage au multi-décisions n'autorise pas une décision à sortir de l'univers de marché ou des contraintes de capacité.

## 8. Watchlist + positions ouvertes

Invariant :

```text
univers effectif = watchlist IA actuelle + toutes les positions ouvertes gérables
```

Un retrait de watchlist n'est jamais une clôture forcée. Une position ouverte reste gérable jusqu'à sa clôture.

Un candidat techniquement admissible n'est pas automatiquement une opportunité économiquement intéressante. La discovery ne produit aucun signal BUY/SELL/HOLD et ne contourne pas le plan stratégique.

## 9. SPOT — règles spécifiques

Le runtime PAPER canonique autorise les marchés `SPOT` et `PERPETUAL` linéaires. Les règles SPOT restent strictes : `BUY` acquiert la base et `SELL` réduit uniquement un actif effectivement détenu. Aucun short, levier ni margin n'est autorisé sur SPOT.

Dans un plan multi-décisions, Risk réévalue la quantité disponible après chaque exécution. Un SELL SPOT ne peut donc pas être autorisé à partir d'un inventaire obsolète.

## 10. PERPETUAL — support PAPER canonique

Les marchés `PERPETUAL` linéaires sont supportés dans les Sessions PAPER et dans la discovery dynamique lorsque le type est présent dans l'univers autorisé.

Sémantique stratégique :

- `BUY` exprime ou augmente une exposition LONG, ou réduit une position SHORT existante ;
- `SELL` exprime ou augmente une exposition SHORT, ou réduit une position LONG existante ;
- l'Agent ne choisit jamais le levier, la marge, `reduce_only` ni les limites d'exposition.

Le Risk Engine déterministe conserve l'autorité finale : marge isolée, levier configuré, plafond de levier, notionnel par position, exposition dérivés totale, buffer de liquidation et logique `reduce_only` restent contrôlés hors LLM. Une décision opposée ne peut pas inverser librement une position.

`FUTURE` daté reste interdit à l'exécution et à la discovery.

### Audit du biais SELL / SHORT observé sur un run

Le run d'environ 9 h étudié présente davantage de SELL et une forte exposition SHORT PERPETUAL. L'audit du code courant ne confirme pas de biais directionnel structurel dans le mapping BUY/SELL, le planner, la sélection multi-marchés ou Risk : ces composants traitent LONG/SHORT symétriquement.

Deux éléments sont néanmoins corrigés :

- le mapping d'agressivité courant `v2` encourageait explicitement plus de rotation/fréquence aux niveaux élevés, ce qui peut contribuer au turnover global mais ne démontre pas un biais SHORT ;
- la phrase générique « signal automatique de vente » dans le contexte de gestion était asymétrique pour un SHORT ; elle devient « réduction ou clôture » avec rappel de la symétrie BUY/SELL PERPETUAL.

Aucun quota LONG/SHORT, préférence LONG artificielle ni modification Risk n'est ajouté. L'existence d'un biais SHORT persistant reste **à décider sur plusieurs runs**.

## 11. Évaluation Risk séquentielle

Pour chaque décision `Di`, Risk reçoit le portefeuille courant après `D1 ... D(i-1)`.

```text
P0 -> Risk(D1) -> exécution éventuelle -> P1
P1 -> Risk(D2) -> exécution éventuelle -> P2
...
```

Cette règle empêche le plan de réserver implicitement plusieurs fois le même cash ou le même inventaire.

Un `REJECT` n'arrête pas le reste du plan. Un `HOLD` n'arrête pas non plus le reste du plan. Les décisions suivantes continuent avec le portefeuille réellement courant.

## 12. Rotation du capital

La gestion stratégique des positions et la rotation peuvent s'étaler sur plusieurs cycles ou apparaître dans le même plan ordonné, par exemple :

```text
SELL marché A
-> Risk + fill PAPER
-> cash libéré
-> BUY marché B plus tard dans le même plan
-> Risk réévalué sur le nouveau portefeuille
```

Cet exemple n'est pas une règle. Il n'existe aucun automatisme `SELL -> BUY`, aucun take-profit fixe et aucun seuil P&L déterministe imposant la rotation.

Le présent recalibrage ajoute seulement le raisonnement stratégique suivant : fermer/réduire puis réouvrir ailleurs cumule plusieurs coûts ; la nouvelle allocation doit donc être préférée à la conservation après prise en compte de ces coûts, sans seuil imposé.

## 13. HOLD, REJECT et audit

Toutes les décisions du plan sont auditables, y compris :

- `HOLD` ;
- `BUY`/`SELL` rejeté par Risk ;
- `BUY`/`SELL` modifié par Risk ;
- décisions ayant produit une intention/fill ;
- trajectoires interrompues par une erreur technique.

La rationale Agent et les raisons Risk restent deux catégories distinctes. L'UI ne fabrique aucune causalité absente.

## 14. Échec Agent et diagnostic sécurisé

Un plan vide, un JSON invalide, une violation du contrat action/quantité, un dépassement de limite, un doublon ou un marché hors univers échoue avant Risk.

Les erreurs sont catégorisées pour l'opérateur sans persister la réponse LLM brute, un secret, une clé API ou un prompt secret. Il n'existe aucun retry LLM sémantique destiné à « réparer » une décision invalide ; l'invariant d'un seul appel stratégique de planification par cycle est maintenu.

## 15. Échec technique et rollback PAPER

Une erreur technique Risk ou Broker transforme le cycle en `FAILED`.

Le runner audité restaure le checkpoint du ledger PAPER pris au début du cycle afin qu'aucune mutation économique partielle de la trajectoire ne subsiste.

Le rollback économique ne supprime pas l'information d'audit nécessaire pour comprendre l'échec.

## 16. Causalité / no-look-ahead

Aucun candidat, snapshot, candle ou contexte ne peut introduire une donnée postérieure au temps de décision concerné. `history_as_of(...)` reste la primitive de lecture causale pour les candles stratégiques.

L'ordre intra-cycle est causal mais n'autorise aucun accès au futur : la décision suivante observe uniquement les effets déjà produits par les étapes précédentes et les faits disponibles dans le contexte du cycle.

## 17. Fraîcheur et SCALP

Le style `SCALP` correspond ici à un horizon minute / intraday, pas à du HFT sub-milliseconde. Son usage avec le LLM reste donc supporté.

Le Risk Engine possède déjà un contrôle fail-closed de fraîcheur : absence de timestamp exploitable -> `MARKET_FRESHNESS_UNAVAILABLE`, dépassement de `RiskPolicy.stale_after` -> `MARKET_DATA_STALE`.

La configuration provider `kraken_stale_after_seconds` reste optionnelle et vaut `None` par défaut. Ce réglage concerne la qualification de fraîcheur du MarketState provider ; il ne doit pas être confondu avec la politique Risk ni avec le `paper_mark_to_market_stale_after_seconds` du portefeuille PAPER. Au HEAD audité, `campaign_composition.py` construit la `RiskPolicy` sans renseigner `stale_after` : le mécanisme Risk existe donc, mais n'est pas activé par défaut dans les Campaigns courantes.

Aucun seuil SCALP supplémentaire n'est imposé dans ce batch. Un futur durcissement doit d'abord mesurer la latence réelle `MarketState -> LLM -> Risk` et ses distributions avant de choisir un seuil.

## 18. Persistence 1:N et compatibilité

Migration :

```text
0006_paper_control_plane
-> 0007_multi_decision_cycles
```

Un cycle peut posséder plusieurs décisions, plusieurs évaluations Risk et plusieurs intentions d'exécution ordonnées.

Les anciens cycles mono-décision restent lisibles sans réécriture de leur historique.

## 19. Analytics et constat expérimental

Le nombre de décisions n'est pas le nombre de trades. Les analytics utilisent les fills/trades économiques réellement exécutés.

Un `HOLD` ou un `REJECT` reste important pour l'audit mais n'incrémente pas artificiellement les métriques d'exécution.

Le run PAPER d'environ 9 h ayant motivé ce batch montre `1 246` fills sur `395` cycles, un P&L brut d'environ `+0,727` mais un P&L net d'environ `-2,287` après coûts, pour une equity finale d'environ `97,713` depuis `100`. Ce constat motive le recalibrage cost-aware ; **il ne prouve pas la performance générale de la stratégie ni un biais directionnel durable**.

## 20. Frontend

Le frontend peut afficher :

- watchlist effective ;
- contexte de marché ;
- trajectoire ordonnée des décisions ;
- rationale de chaque décision ;
- résultat Risk ;
- intentions/fills réellement persistés ;
- portefeuille/P&L backend.

Il ne peut pas produire un ranking, recalculer Risk, inventer un fill ou réordonner la causalité.

## 21. Interdits maintenus

- aucun LIVE implicite ;
- aucun second Agent ;
- aucun second appel stratégique de « réparation » du plan ;
- aucun ranking déterministe remplaçant le jugement stratégique ;
- aucun ordre direct LLM/tool ;
- aucun contournement Risk ;
- aucun `FUTURE` daté ; aucun short/levier/margin sur SPOT ; aucun contournement des contrôles de levier, marge ou exposition PERPETUAL ;
- aucun look-ahead ;
- aucune obligation de trader ;
- aucune taille maximale ni fréquence minimale imposée par l'agressivité ;
- aucun seuil de profit, cooldown, durée minimale ou quota LONG/SHORT introduit par ce recalibrage ;
- aucun calcul financier canonique déporté dans le frontend ;
- aucun effacement d'historique ;
- aucune promesse de rendement.
