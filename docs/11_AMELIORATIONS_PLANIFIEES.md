# 11 — Améliorations planifiées

> Document de référence pour les améliorations à implémenter après le Batch 18.13. Ce document
> distingue l'état **confirmé** de `main`, ce qui est **obsolète**, ce qui est **manquant** et ce qui
> reste **à décider**. Il ne constitue pas une déclaration d'implémentation.

## 1. Référence et périmètre de l'audit

```text
Repository                    : Ax-07/AI-Spot-Trader
Branche                       : main
HEAD GitHub main audité       : 9a312040eb671976b44e5f50077ca11a9d9213b3
Commit fonctionnel 18.13      : 4cb0567cae6ff100c5ad9ad1df9e3f68b8f7ffd7
Commit documentaire post-18.13: 9a312040eb671976b44e5f50077ca11a9d9213b3
Date de cadrage                : 2026-09-24
```

Le commit `9a312040...` est un commit documentaire postérieur au commit fonctionnel 18.13. Aucun code
applicatif n'a été introduit entre les deux.

## 2. Invariants transverses

Toutes les améliorations ci-dessous doivent préserver :

- un seul Agent IA stratégique ;
- Kraken comme exchange initial ;
- PAPER uniquement à ce stade ;
- SPOT + PERPETUAL linéaire selon l'état intégré ;
- aucune sortie LLM ne déclenche directement Broker/Kraken ;
- Risk Engine déterministe = autorité finale ;
- IA = choix stratégique ;
- monitoring, calculs, statistiques et contraintes = déterministes lorsque pertinent ;
- frontend indépendant du moteur et jamais source de vérité trading ;
- aucun secret dans prompts, logs, docs ou versionnement ;
- aucune clé Kraken avec droit de retrait ;
- frais, spread, slippage et funding pris en compte sans double comptage ;
- toutes les décisions, y compris HOLD, auditables ;
- aucune sélection rétrospective, look-ahead ou modification post-hoc d'une décision.

Principe central :

**L'IA propose. Le Risk Engine autorise, modifie ou refuse.**

## 3. Vue d'ensemble des trois cadences cibles

Le système doit cesser de traiter « actualiser les prix », « décider » et « choisir les marchés à
surveiller » comme un seul rythme implicite.

| Cadence | But | LLM | Autorité stratégique |
| --- | --- | --- | --- |
| Monitoring / mark-to-market | prix, marks, P&L, exposition, marge, liquidation, funding | non | aucune |
| Cycle stratégique | BUY / SELL / HOLD sur le contexte courant | oui | Agent unique, puis Risk final |
| Découverte / révision watchlist | réévaluer périodiquement les marchés intéressants | oui | même Agent unique |

Les durées définitives ne sont pas fixées ici. Le monitoring doit être sensiblement plus rapide que
le cycle stratégique ; la découverte doit être beaucoup plus lente. Une plage de l'ordre de 30–60
minutes pour la découverte est une hypothèse de départ configurable, pas un invariant.

---

# 4. Comptabilité SPOT par position

## Statut d'audit

**Confirmé**

- `AssetPosition` expose aujourd'hui `asset`, `quantity`, `available` uniquement.
- `PaperPortfolioLedger.apply_buy()` et `apply_sell()` mutent quantités/cash sans conserver de base de
  coût ou P&L réalisé SPOT.
- les positions PERPETUAL possèdent déjà prix moyen, mark, P&L réalisé/latent, marge, funding et
  liquidation ; ce modèle constitue une référence de maturité, pas un contrat à recopier tel quel.
- le frontend respecte actuellement cette limite et n'invente pas de coût moyen SPOT.

**Obsolète**

- considérer l'absence de coût moyen/P&L SPOT comme un simple manque d'affichage. Le manque est dans
  le contrat canonique backend, donc une correction frontend seule serait incorrecte.

**Manquant**

- coût/base de coût canonique SPOT ;
- prix moyen d'entrée ;
- P&L réalisé par position ;
- P&L latent par position au prix courant ;
- règles de buys successifs et ventes partielles ;
- persistence/recovery de ces données ;
- exposition typée aux API, Agent et cockpit.

**À décider**

- forme exacte des champs persistés ;
- méthode comptable détaillée et règles d'arrondi ;
- politique de compatibilité/migration des anciens snapshots ;
- référence de prix exacte pour le P&L latent SPOT.

## Problème actuel confirmé

Une position SPOT peut être détenue et vendue correctement en quantité, mais son état ne suffit pas
à répondre de manière canonique à « combien a coûté la position ? », « quel est son P&L latent ? » ou
« quel P&L a été réalisé lors d'une réduction ? ». Les analytics globaux ne remplacent pas une
comptabilité par position.

## Comportement cible

Pour chaque position SPOT ouverte, le backend doit pouvoir fournir au minimum :

- quantité totale et disponible ;
- coût/base de coût restant ;
- prix/coût moyen d'entrée ;
- prix de valorisation courant et timestamp ;
- P&L latent ;
- P&L réalisé cumulé ou une information équivalente réconciliable ;
- coûts d'exécution pertinents sans double comptage.

Un achat successif doit mettre à jour la base de coût de façon déterministe. Une vente partielle doit
libérer la fraction de base de coût correspondant à la quantité cédée, constater le P&L réalisé et
conserver un coût cohérent sur le solde. Une vente totale doit fermer proprement la position sans
perdre les faits de réalisation dans l'audit/ledger durable.

## Architecture envisagée

Étendre le domaine SPOT canonique et `PaperPortfolioLedger`, puis faire propager l'état enrichi par :

```text
Fill PAPER
-> ledger SPOT canonique
-> PortfolioState durable
-> recovery
-> AgentInput / monitoring / analytics
-> API
-> cockpit
```

La base de coût doit se réconcilier avec le **prix réel du fill et le cash réellement débité/crédité**.
Les champs analytiques frais/spread/slippage restent séparés afin d'expliquer la performance, mais ne
doivent pas être ajoutés une seconde fois à une valeur qui les contient déjà via le prix de fill.

Une approche au coût moyen pondéré est recommandée pour la première version car elle est compatible
avec le modèle de position agrégée existant. Le choix final et les règles de frais doivent toutefois
être figés par des tests comptables avant implémentation.

## Invariants

- aucune reconstruction de portefeuille parallèle dans le frontend ;
- impossible de vendre plus que la quantité disponible ;
- aucune quantité/cash négatif après mutation valide ;
- snapshot et recovery doivent reproduire exactement l'état comptable ;
- les faits historiques/fills restent immuables ;
- aucun recalcul rétrospectif à partir de prix futurs.

## Dépendances

- modèles domaine ;
- ledger/broker PAPER ;
- persistence et recovery ;
- schemas/API portfolio ;
- analytics ;
- AgentInput lorsque l'Agent doit connaître le coût/P&L des positions.

## Risques / pièges

- double comptage des frais, spread ou slippage ;
- divergence entre cash, coût restant et P&L réalisé ;
- arrondis Decimal incohérents ;
- migration d'anciens snapshots sans base de coût ;
- ambiguïté entre P&L réalisé de la position courante et historique complet après fermeture/réouverture.

## Critères d'acceptation

- plusieurs BUY successifs produisent un coût moyen attendu ;
- une vente partielle constate un P&L réalisé correct et conserve une base de coût cohérente ;
- une vente totale ferme la position et réconcilie cash + coûts + P&L ;
- les coûts PAPER ne sont comptés qu'une fois ;
- persistence/recovery donnent le même état avant/après restart ;
- API/Agent reçoivent les champs canoniques ;
- le frontend n'effectue aucun calcul métier alternatif.

## Fichiers/composants probablement concernés

- `backend/src/ai_spot_trader/domain/models.py` ;
- `backend/src/ai_spot_trader/portfolio/ledger.py` ;
- `backend/src/ai_spot_trader/broker/paper.py` ;
- persistence/recovery (`backend/src/ai_spot_trader/persistence/*`) ;
- `backend/src/ai_spot_trader/api/schemas.py` et route portfolio ;
- analytics PAPER ;
- tests portfolio/broker/recovery/analytics ;
- frontend positions/types uniquement après stabilisation du contrat backend.

## Ordre recommandé d'implémentation

**1 — fondation prioritaire.** Ce chantier doit précéder le mark-to-market SPOT riche et les charts de
position afin d'empêcher des calculs concurrents.

---

# 5. Mark-to-market indépendant des cycles IA

## Statut d'audit

**Confirmé**

- le PERPETUAL possède déjà une revalorisation déterministe `mark_derivative_market()` avec P&L,
  marge, liquidation et funding ;
- cette revalorisation est actuellement liée à l'acquisition de certains `MarketState`/cycles et non
  à un service de monitoring autonome de toutes les positions ;
- le SPOT n'a pas encore de P&L latent canonique par position ;
- le cockpit poll actuellement plusieurs endpoints HTTP toutes les 10 secondes, ce qui n'est pas un
  moteur de mark-to-market.

**Obsolète**

- assimiler « cadence du cycle Agent » à « fraîcheur nécessaire de l'état portefeuille ».

**Manquant**

- boucle/service déterministe de monitoring ;
- rafraîchissement multi-position indépendant du LLM ;
- snapshot de valorisation cohérent ;
- diffusion efficace vers API/cockpit ;
- métriques de fraîcheur/erreur du monitor.

**À décider**

- cadence exacte ;
- référence de valorisation SPOT ;
- politique de persistence des marks ;
- comportement précis en cas de trou de données Kraken.

## Problème actuel confirmé

Le P&L et plusieurs métriques ne se rafraîchissent pas comme un état vivant indépendant : leur
fraîcheur est attachée aux acquisitions/cycles existants. Une position ouverte doit pouvoir évoluer
visuellement et comptablement sans consommer de tokens IA.

## Comportement cible

Une boucle rapide doit :

- récupérer les prix/marks nécessaires auprès de Kraken ;
- revaloriser toutes les positions ouvertes ;
- calculer P&L latent et exposition ;
- maintenir marge, maintenance margin, liquidation et funding PERPETUAL lorsque pertinent ;
- publier un snapshot cohérent ;
- fonctionner sans LLM et sans décision BUY/SELL/HOLD.

## Architecture envisagée

```text
Kraken prix/marks publics
-> Market Monitor déterministe
-> PaperPortfolioLedger / Position Valuation
-> snapshot mark-to-market canonique
-> Risk context + AgentInput futur + analytics/API
-> cockpit
```

Le monitor n'appelle ni `select_market()` ni `generate_decision()`. Il peut préparer les faits
nécessaires au prochain cycle IA mais ne choisit jamais une action stratégique.

Pour éviter les races, l'architecture d'implémentation devra définir une frontière atomique entre
mutation du ledger par fills et revalorisation par le monitor.

## Invariants

- aucun appel LLM ;
- aucune décision stratégique ;
- Risk reste l'autorité finale sur toute future intention d'exécution ;
- aucune valeur frontend ne remplace le snapshot backend ;
- données datées, fraîches et sans look-ahead ;
- funding PERPETUAL non compté deux fois.

## Dépendances

- comptabilité SPOT enrichie ;
- sources Kraken SPOT/PERP existantes ;
- ledger ;
- runtime backend ;
- API/analytics ;
- future diffusion WebSocket cockpit.

## Risques / pièges

- double accrual du funding ;
- contention monitor vs fill ;
- mélange de timestamps issus de marchés différents dans un snapshot présenté comme atomique ;
- surcharge Kraken si la cadence ou les subscriptions sont mal conçues ;
- persistence excessive de chaque tick.

## Critères d'acceptation

- le P&L d'une position ouverte évolue sans cycle Agent ;
- le compteur d'appels LLM reste inchangé durant un rafraîchissement de monitoring seul ;
- toutes les positions ouvertes sont revalorisées ;
- les données PERPETUAL restent cohérentes avec marge/liquidation/funding ;
- les erreurs/staleness Kraken sont visibles et ne produisent pas de décision implicite ;
- tests concurrents/recovery confirment l'absence de corruption ledger.

## Fichiers/composants probablement concernés

- `portfolio/ledger.py` ;
- `integrations/kraken/market_data.py`, `derivatives.py`, `websocket.py` ;
- runtime/composition ;
- API portfolio/analytics ;
- persistence selon politique retenue ;
- tests derivatives/portfolio/runtime.

## Ordre recommandé d'implémentation

**2 — après la comptabilité SPOT.** Le monitoring devient ensuite une dépendance du mode gestion et du
cockpit temps réel.

---

# 6. Explicabilité des décisions IA

## Statut d'audit

**Confirmé**

- `DecisionCandidate`/provider produisent déjà un `rationale` ;
- le contrat Agent précise que ce rationale est explicatif, en français, et non exécutable ;
- l'historique cockpit expose aujourd'hui surtout une phrase générique et le payload JSON technique ;
- le résultat Risk est déjà un artefact séparé.

**Obsolète**

- traiter le rationale comme une fonctionnalité Agent à inventer. Il existe déjà ; le manque est
  principalement son exposition produit et son rattachement ergonomique.

**Manquant**

- affichage dédié sur Accueil ;
- historique lisible par position ;
- exposition dans les markers charts ;
- séparation UX systématique rationale vs raisons Risk.

**À décider**

- profondeur de l'historique affiché sur une position ;
- contrat API spécialisé ou réutilisation des endpoints d'audit existants ;
- wording final et niveau de troncature UI.

## Problème actuel confirmé

L'explication stratégique existe dans l'audit mais n'est pas une information de premier niveau dans
le cockpit. L'opérateur doit ouvrir du JSON technique pour retrouver le détail.

## Comportement cible

- **Accueil → Dernière décision** : action, marché, timestamp, rationale synthétique ;
- **Positions** : chronologie des décisions/fills liés à la position ;
- **Historique** : rationale lisible sans ouvrir le payload brut ;
- **Chart** : rationale associé à un marker lorsqu'un événement dispose d'une décision liée ;
- Risk montré séparément avec statut et raisons déterministes.

## Architecture envisagée

Réutiliser les décisions/audits persistés comme source canonique. Ajouter, si nécessaire, une vue API
de lecture/corrélation sans dupliquer les faits :

```text
DecisionCandidate.rationale
+ RiskAssessment
+ Execution / Fill
+ identités cycle/symbol/market_type
-> projection API de lecture
-> Accueil / Positions / Historique / Chart markers
```

## Invariants

- ne pas présenter le rationale comme une preuve de raisonnement interne caché ;
- ne jamais mélanger texte Agent et décision Risk ;
- aucune modification post-hoc du rationale ;
- HOLD doit rester explicable et auditable ;
- le frontend ne dérive pas une nouvelle justification métier.

## Dépendances

- audit existant ;
- corrélation décision/risk/exécution ;
- identité de position suffisamment stable pour l'historique riche ;
- markers chart pour le dernier point d'intégration.

## Risques / pièges

- confusion entre rationale Agent et motif de modification/refus Risk ;
- UI trop verbeuse ;
- corrélation erronée d'un événement par symbole seul alors que `market_type` est nécessaire ;
- exposition involontaire de payloads qui ne devraient pas être rendus tels quels.

## Critères d'acceptation

- la dernière décision affiche explicitement « Pourquoi l'IA ? » ;
- Risk a son bloc distinct ;
- un HOLD affiche également son rationale ;
- une position permet de retrouver ses événements corrélés ;
- un marker peut ouvrir le rationale et le résultat Risk correspondants ;
- aucun nouveau calcul de trading n'est introduit dans le frontend.

## Fichiers/composants probablement concernés

- routes/schemas audit ;
- persistence audit si requête spécialisée nécessaire ;
- `frontend/src/components/cockpit/cockpit-shell.tsx` ;
- `positions-panel.tsx` ;
- `history-panel.tsx` ;
- `frontend/src/lib/api/types.ts` et client/hook associés ;
- futur composant chart.

## Ordre recommandé d'implémentation

**5 — après les fondations moteur/watchlist**, sauf sous-batch purement présentationnel plus tôt. Le
rattachement complet aux positions/markers bénéficie des identités stabilisées.

---

# 7. Mode gestion lorsque l'exposition maximale est atteinte

## Statut d'audit

**Confirmé**

- Risk calcule/refuse déjà des expositions dépassant les limites ;
- la sélection multi-marchés actuelle demande néanmoins au même Agent de sélectionner un marché à
  chaque cycle ;
- l'univers de sélection provient actuellement des marchés exécutables statiques.

**Obsolète**

- laisser l'Agent rechercher de nouvelles ouvertures lorsque le backend sait déjà qu'aucune nouvelle
  exposition ne peut être autorisée.

**Manquant**

- état déterministe « capacité de nouvelle exposition disponible / indisponible » ;
- branche de cycle management ;
- limitation des tools/recherches d'ouverture ;
- métriques consommation IA et phases évitées ;
- retour automatique au mode normal.

**À décider**

- nom exact des états/modes ;
- granularité du calcul de capacité (globale vs par type/asset) ;
- format exact des métriques tokens/coûts selon ce que le provider expose.

## Problème actuel confirmé

Une saturation d'exposition peut rendre impossible toute nouvelle ouverture, mais le pipeline peut
encore consommer un appel de sélection/research avant que Risk n'arrête une action. Cette dépense ne
fournit pas de valeur lorsque le périmètre d'action acceptable est déjà connu : gérer l'existant.

## Comportement cible

Quand aucune nouvelle exposition n'est possible :

- ne pas rechercher de nouvelle opportunité d'ouverture ;
- ne pas appeler les tools dédiés à cette recherche ;
- présenter au même Agent les positions déjà ouvertes et leur contexte courant ;
- autoriser HOLD, réduction et clôture ;
- empêcher une augmentation de l'exposition incompatible avec le mode ;
- laisser Risk autoriser/modifier/refuser la proposition ;
- revenir au mode normal dès qu'une capacité suffisante est libérée.

## Architecture envisagée

```text
Portfolio mark-to-market + Risk limits
-> CapacityEvaluator déterministe
   -> capacité disponible : cycle NORMAL
   -> capacité saturée    : cycle MANAGEMENT

MANAGEMENT
-> univers stratégique = positions ouvertes
-> même Agent : choix de la position/action
-> RiskEngine : autorité finale
-> Broker PAPER éventuel
```

Le `CapacityEvaluator` n'effectue aucun ranking et ne choisit aucune position. Il ne répond qu'à une
question structurelle : une **nouvelle exposition** est-elle admissible en principe ?

Pour SPOT et PERPETUAL, l'implémentation doit également empêcher qu'une action présentée comme
« gestion » augmente l'exposition absolue en contournant cette restriction.

## Invariants

- aucun second Agent ;
- le déterministe ne choisit pas quelle position fermer ;
- HOLD valide ;
- réduction/clôture permises sous réserve de Risk ;
- Risk final ;
- toutes les transitions de mode auditables ;
- sortie automatique du mode gestion quand la capacité revient.

## Dépendances

- mark-to-market fiable ;
- exposition courante fiable ;
- limites Risk ;
- AgentInput capable de présenter les positions concernées ;
- métriques provider/outillage.

## Risques / pièges

- considérer « exposition totale au max » comme unique condition alors qu'une nouvelle position peut
  être impossible pour une autre limite ;
- empêcher par erreur une réduction ;
- autoriser un BUY SPOT/une augmentation PERP sous prétexte que le symbole est déjà détenu ;
- inventer un nombre de tokens « économisés » sans baseline observable.

## Critères d'acceptation

- avec capacité saturée, aucune phase IA de recherche d'ouverture n'est lancée ;
- le même Agent reçoit les positions ouvertes et peut HOLD/réduire/clôturer ;
- une tentative d'augmentation reste bloquée déterministiquement ;
- après une réduction libérant de la capacité, le prochain cycle peut revenir au mode normal ;
- les compteurs d'appels/tools/tokens réels sont audités ;
- les « économies » non directement mesurables sont présentées comme estimations ou phases évitées,
  jamais comme faits exacts.

## Fichiers/composants probablement concernés

- `risk/engine.py` / policy ou service de capacité dédié ;
- `trading/engine.py` ;
- `domain/models.py` ;
- Agent prompt/provider ;
- persistence audit/analytics ;
- control plane/config pour les paramètres pertinents ;
- tests trading/risk/agent.

## Ordre recommandé d'implémentation

**3 — après le monitoring.** Le mode doit décider son périmètre à partir d'une exposition réellement
actuelle, pas d'une valeur seulement rafraîchie au dernier cycle IA.

---

# 8. Découverte automatique périodique des marchés

## Statut d'audit

**Confirmé**

- `paper_executable_markets` est actuellement un univers statique de Campaign fourni par
  configuration opérateur ;
- le même Agent sait déjà sélectionner un marché au sein d'un univers exécutable pendant un cycle ;
- le backend possède déjà des sources Kraken publiques et des filtres/contrats de marché.

**Obsolète**

- assimiler `paper_executable_markets` à une watchlist dynamique choisie périodiquement par l'Agent.
  Aujourd'hui, il s'agit d'une configuration statique.

**Manquant**

- construction périodique d'un univers techniquement admissible ;
- contrat de découverte/watchlist du même Agent ;
- cadence séparée ;
- persistence/versionnement ;
- mode automatique/manuellement reproductible.

**À décider**

- taille maximale de l'univers admissible et de la watchlist ;
- facteurs strictement structurels de filtrage ;
- contrat Campaign : snapshot vs configuration autorisant une watchlist évolutive ;
- stratégie de recovery d'une révision de watchlist en cours.

## Problème actuel confirmé

L'opérateur doit renseigner lui-même les marchés exécutables. Le système n'a pas de mécanisme
périodique permettant au même Agent de réévaluer les marchés intéressants sans confondre cette
sélection stratégique avec un filtre algorithmique déterministe.

## Comportement cible

Deux étapes doivent rester distinctes :

1. **backend déterministe** : produire l'ensemble des marchés techniquement admissibles ;
2. **Agent stratégique** : choisir la watchlist à surveiller parmi cet ensemble.

Le filtrage backend peut vérifier notamment :

- marché actif/tradable ;
- quote/règlement compatible avec la Campaign ;
- SPOT ou PERPETUAL linéaire supporté ;
- métadonnées de contrat requises disponibles ;
- contraintes structurelles incompatibles avec Risk/runtime.

Il ne peut pas attribuer un score d'opportunité ou classer les marchés à la place de l'Agent.

## Architecture envisagée

```text
Kraken market metadata
-> EligibilityService déterministe
-> admissible_markets
-> même Agent / phase discovery
-> WatchlistRevision durable
-> effective monitored universe
```

La phase discovery possède son propre timestamp, ses entrées et sa sortie auditables. Elle n'est pas
réexécutée à chaque cycle de trading.

Le **mode manuel** reste un chemin canonique : une Campaign/test peut conserver une liste fixée afin
de rendre une expérience reproductible.

## Invariants

- un seul Agent ;
- aucun ranking stratégique déterministe ;
- aucune paire hors univers admissible ne peut devenir exécutable ;
- `market_type` fait partie de l'identité du marché ;
- aucun look-ahead ;
- mode manuel conservé.

## Dépendances

- métadonnées Kraken ;
- contrats `ExecutableMarket` ;
- control plane/Campaign ;
- persistence audit ;
- future watchlist dynamique.

## Risques / pièges

- introduire silencieusement un scanner algorithmique qui décide à la place de l'IA ;
- créer un univers trop large entraînant prompts/tools coûteux ;
- changer une Campaign immuable sans définir clairement quelle partie est configuration et quelle
  partie est état runtime versionné ;
- retirer un marché qui porte encore une position ouverte.

## Critères d'acceptation

- le backend peut produire un univers admissible sans score stratégique ;
- le même Agent produit une watchlist valide et bornée ;
- la révision est durable/auditable ;
- la fréquence de découverte est indépendante de la fréquence de trading ;
- le mode manuel donne une expérience déterministe/reproductible ;
- une sortie Agent hors univers est rejetée avant toute exécution.

## Fichiers/composants probablement concernés

- intégrations Kraken metadata/symbols/derivatives ;
- domaine `ExecutableMarket` et nouveaux contrats discovery ;
- Agent provider/prompt ;
- `control_plane.py`, `campaign_composition.py` ;
- persistence/migration éventuelle ;
- API/control plane ;
- tests sélection/contrats/persistence/runtime.

## Ordre recommandé d'implémentation

**4 — conjointement avec la watchlist dynamique.** Le mécanisme n'a de sens que si sa sortie devient un
état versionné distinct de l'univers techniquement admissible.

---

# 9. Watchlist dynamique + positions ouvertes

## Statut d'audit

**Confirmé**

- aucune watchlist IA dynamique versionnée n'existe actuellement ;
- les positions ouvertes sont présentes dans `PortfolioState` ;
- le runtime connaît aujourd'hui un univers statique de marchés exécutables.

**Obsolète**

- considérer qu'une nouvelle sélection de watchlist peut faire disparaître un marché ouvert du
  périmètre de monitoring.

**Manquant**

- état `WatchlistRevision` ou équivalent ;
- union canonique avec les positions ouvertes ;
- audit/versionnement ;
- propagation au monitor et cockpit.

**À décider**

- schéma exact de la révision ;
- durée de conservation ;
- gestion d'une position dont le marché cesse d'être techniquement admissible pour une ouverture mais
  reste nécessaire à la réduction/clôture.

## Problème actuel confirmé

Une watchlist révisable introduit le risque qu'une paire disparaisse de la prochaine sélection alors
qu'une position y est toujours ouverte. Le monitor ne doit jamais perdre cette position.

## Comportement cible

Définition canonique :

```text
univers surveillé = watchlist IA actuelle + toutes les positions ouvertes
```

L'union doit être faite côté backend. Une position ouverte force la présence du marché dans le
monitoring et dans la vue Marchés jusqu'à clôture complète.

## Architecture envisagée

```text
WatchlistRevision.current_markets
        +
PortfolioState.open_markets
        |
        v
MonitoredMarketSet déterministe
        |
        +-> monitor
        +-> API/WS cockpit
        +-> onglets Marchés
```

La watchlist reste l'expression stratégique de l'Agent. L'union avec les positions ouvertes est une
contrainte de sûreté/observabilité déterministe, pas un choix stratégique.

## Invariants

- aucune position ouverte non surveillée ;
- unicité par `(symbol, market_type)` ;
- ordre déterministe pour audit/reproductibilité ;
- historique des révisions conservé ;
- aucun retrait de surveillance avant fermeture effective.

## Dépendances

- découverte automatique ;
- comptabilité/portfolio capable d'identifier tous les marchés ouverts ;
- monitor multi-marchés ;
- persistence watchlist.

## Risques / pièges

- déduire un marché SPOT uniquement de l'asset sans quote explicite ;
- collision SPOT/PERP sur le même symbole ;
- suppression prématurée lors d'une vente partielle ;
- divergence entre watchlist affichée et monitored set réel.

## Critères d'acceptation

- retirer BTC/USD de la nouvelle watchlist ne retire pas sa surveillance si une position BTC/USD est
  encore ouverte ;
- après clôture totale et absence dans la watchlist, le marché peut quitter le monitored set ;
- chaque révision est historisée ;
- API et cockpit exposent la différence watchlist / position forcée lorsque utile.

## Fichiers/composants probablement concernés

- nouveaux modèles/persistence watchlist ;
- runtime monitoring ;
- portfolio/domaine pour marché de position explicite si nécessaire ;
- API ;
- frontend futur Marchés ;
- tests persistence/recovery/union.

## Ordre recommandé d'implémentation

**4 — même batch logique que la découverte**, ou sous-batch immédiatement suivant avant toute UI
Marchés dynamique.

---

# 10. Nouvel espace « Marchés »

## Statut d'audit

**Confirmé**

- navigation actuelle : `Accueil | Configurer | Positions | Historique | Réglages` ;
- aucune vue Marchés principale avec onglets watchlist n'existe ;
- le frontend est déjà un cockpit Next.js indépendant du moteur.

**Obsolète**

- conserver `Configurer` comme entrée principale permanente si l'expérience cible place la
  configuration dans le parcours d'accueil/réglages et donne la priorité à l'observation des marchés.

**Manquant**

- destination Marchés ;
- onglets dynamiques ;
- état actif ;
- intégration chart/position/decision context.

**À décider**

- emplacement final de l'assistant `Configurer` (Accueil, Réglages, action dédiée) ;
- comportement mobile des onglets ;
- limites d'affichage lorsque la watchlist est grande.

## Problème actuel confirmé

Le cockpit ne fournit pas de surface centrale pour passer rapidement d'un marché surveillé à l'autre
et comprendre son contexte, sa position éventuelle et son activité récente.

## Comportement cible

Navigation principale :

```text
Accueil | Marchés | Positions | Historique | Réglages
```

La vue Marchés liste en onglets au minimum :

- marchés de la watchlist IA ;
- marchés forcés par positions ouvertes.

L'onglet actif charge son chart, ses métriques et ses événements. Les autres restent légers.

## Architecture envisagée

La vue consomme un endpoint/flux backend exposant le `MonitoredMarketSet`, puis charge les données par
`(symbol, market_type)`.

Le frontend peut mémoriser l'onglet visuel actif, mais cette préférence n'a aucune autorité sur le
monitored set, la watchlist ou le moteur.

## Invariants

- aucune logique de sélection stratégique dans le frontend ;
- fermeture du cockpit sans effet sur le moteur ;
- position ouverte toujours accessible ;
- thème light/dark existant respecté ;
- chargement paresseux.

## Dépendances

- watchlist dynamique ;
- monitored set ;
- API candles/events ;
- architecture WebSocket cockpit.

## Risques / pièges

- trop d'onglets/charts montés en parallèle ;
- état frontend considéré à tort comme watchlist canonique ;
- mauvaise distinction SPOT/PERP pour un même symbole.

## Critères d'acceptation

- navigation cible disponible ;
- chaque marché surveillé possède un onglet ;
- toute position ouverte est représentée même hors watchlist ;
- changement d'onglet ne déclenche aucune décision de trading ;
- seules les données nécessaires à l'onglet actif sont chargées prioritairement.

## Fichiers/composants probablement concernés

- `frontend/src/components/cockpit/cockpit-shell.tsx` ;
- nouveau panneau/composants Marchés ;
- hooks/client/types API ;
- routes backend monitored markets/candles/events.

## Ordre recommandé d'implémentation

**6B — après la couche backend candles/streaming.** La coquille Marchés peut exister avant, mais le
batch complet doit reposer sur des données canoniques prêtes.

---

# 11. Charts chandeliers

## Statut d'audit

**Confirmé**

- le backend Spot possède déjà une acquisition OHLC REST pour construire du contexte ;
- le cockpit n'a pas de chart chandeliers interactif ;
- `next-themes` fournit déjà clair/sombre ;
- Kraken/backend doivent rester source de vérité.

**Obsolète**

- utiliser un iframe TradingView externe comme source du moteur ou comme référentiel de prix.

**Manquant**

- contrat candle frontend ;
- renderer ;
- timeframes ;
- overlays position/mark/liquidation ;
- cache/lazy loading.

**À décider**

- liste des timeframes proposés ;
- quantité initiale de candles par timeframe ;
- volume et autres séries optionnelles ;
- granularité de persistence.

## Problème actuel confirmé

L'opérateur voit des métriques mais ne peut pas contextualiser visuellement un marché, une entrée ou
une sortie sur des chandeliers.

## Comportement cible

Chaque onglet Marchés doit pouvoir afficher :

- chandeliers OHLC ;
- prix courant ;
- timeframes utiles ;
- thème clair/sombre ;
- volume si disponible et utile ;
- prix/coût moyen d'entrée ;
- mark price PERPETUAL ;
- prix de liquidation PERPETUAL ;
- événements BUY/SELL/réduction/clôture.

## Architecture envisagée

**TradingView Lightweight Charts** est privilégié comme librairie de rendu locale au frontend. Il
reçoit des données normalisées du backend :

```text
backend candle/event DTOs -> Lightweight Charts
```

Il ne fait pas de requêtes directes vers une source tierce pour définir la vérité trading.

## Invariants

- Kraken/backend canonique ;
- aucun calcul Risk dans le chart ;
- aucune exécution depuis un marker sans passer par les contrats habituels ;
- thème cohérent avec `next-themes` ;
- performance maîtrisée par lazy loading.

## Dépendances

- historique candles + WebSocket ;
- comptabilité position ;
- monitored set ;
- événements audit/fills.

## Risques / pièges

- rendre 10–50 charts simultanément ;
- divergence entre prix affiché et prix canonique utilisé par le moteur ;
- mauvaise agrégation timeframe ;
- fuite mémoire lors des subscriptions/changements d'onglet.

## Critères d'acceptation

- chart de la paire active visible en light/dark ;
- historique initial puis updates temps réel sans doublons ;
- changement de timeframe cohérent ;
- overlays de position exacts et backend-sourced ;
- désabonnement/nettoyage correct au changement de paire ;
- aucun iframe TradingView nécessaire.

## Fichiers/composants probablement concernés

- `frontend/package.json` / lockfile pour `lightweight-charts` ;
- composants Marchés/chart ;
- hooks WebSocket ;
- types API ;
- backend candle/event routes et service de données.

## Ordre recommandé d'implémentation

**6B — après 6A backend candles/streaming.**

---

# 12. Trades et décisions sur le chart

## Statut d'audit

**Confirmé**

- décisions, Risk, exécutions et fills sont déjà des faits auditables liés par des identités de cycle ;
- les fills contiennent le prix réellement exécuté ;
- le rationale existe dans la décision ;
- aucun marker chart n'existe actuellement.

**Obsolète**

- placer un marker au seul prix théorique de décision lorsque le fill réel existe.

**Manquant**

- projection chronologique par marché ;
- type d'événement ouverture/augmentation/réduction/clôture ;
- marker visuel ;
- détail hover/clic.

**À décider**

- règles visuelles lorsque plusieurs événements ont le même timestamp/candle ;
- granularité de l'API événementielle ;
- présentation des HOLD sur chart (probablement optionnelle afin d'éviter le bruit).

## Problème actuel confirmé

L'audit permet de retrouver les faits, mais le cockpit ne les positionne pas sur l'évolution du prix.

## Comportement cible

Markers minimum :

- BUY ;
- SELL ;
- réduction partielle ;
- clôture ;
- prix réel du fill.

Au hover/clic :

- timestamp ;
- quantité ;
- prix ;
- frais/coûts disponibles ;
- P&L réalisé si disponible ;
- rationale IA ;
- résultat et raisons Risk.

## Architecture envisagée

Créer une projection de lecture backend à partir des faits immuables plutôt qu'une base de markers
indépendante :

```text
Decision + RiskAssessment + Execution + Fill + position accounting
-> MarketEvent DTO
-> chart markers
```

L'identité minimale doit inclure `symbol`, `market_type`, cycle/execution/fill IDs et timestamps afin
d'éviter les corrélations ambiguës.

## Invariants

- prix du marker d'exécution = prix du fill ;
- rationale non modifié ;
- statut Risk distinct ;
- aucune reconstruction de fill dans le navigateur ;
- aucune action rétroactive.

## Dépendances

- rationale UI ;
- comptabilité SPOT pour P&L réalisé précis ;
- API events ;
- chart.

## Risques / pièges

- utiliser timestamp de décision à la place du fill ;
- appeler « clôture » une simple réduction ;
- marker dupliqué après reconnect WebSocket ;
- perte d'événements historiques lors du lazy load.

## Critères d'acceptation

- chaque fill pertinent est représenté une seule fois ;
- réduction et clôture sont distinguées ;
- prix/quantité/coûts correspondent aux faits backend ;
- rationale et Risk affichés séparément ;
- reload/reconnect produit les mêmes markers.

## Fichiers/composants probablement concernés

- persistence/audit queries ;
- API event projection ;
- frontend chart/markers ;
- types/client ;
- tests de corrélation.

## Ordre recommandé d'implémentation

**6B — avec la vue chart**, après stabilisation de la projection backend.

---

# 13. Historique candles + WebSocket

## Statut d'audit

**Confirmé**

- le Spot `KrakenMarketDataSource` utilise déjà REST OHLC et WebSocket ticker ;
- `KrakenTickerWebSocketClient` sait maintenir une subscription ticker avec reconnexion bornée, mais
  `first_ticker()` ferme le flux après le premier ticker dans le chemin de snapshot actuel ;
- aucune pipeline persistante candles -> WebSocket cockpit n'existe ;
- Kraken Spot REST OHLC retourne au maximum 720 entrées récentes, donc ne permet pas de récupérer
  arbitrairement un historique ancien au premier démarrage.

**Obsolète**

- supposer que Kraken Spot REST permettra plus tard de recharger n'importe quelle profondeur passée.

**Manquant**

- client/stream OHLC temps réel pour l'usage chart ;
- service de normalisation/cache ;
- persistence/accumulation éventuelle ;
- API historique ;
- WebSocket backend -> cockpit ;
- stratégie de reconnect/backfill/idempotence.

**À décider**

- persistence permanente ou cache + rétention ;
- schéma DB ;
- timeframes persistés ou agrégés ;
- profondeur initiale (par exemple autour de 1000 candles uniquement si la source/persistence le
  permet) ;
- quotas/subscriptions maximums.

## Problème actuel confirmé

Le backend sait obtenir de l'OHLC pour son contexte de marché et un ticker Spot courant, mais ce
chemin n'est pas conçu comme une série historique durable et streamée au cockpit. Demander « 1000
candles » n'est pas toujours possible à partir du seul endpoint Spot REST lors d'un premier démarrage,
car sa profondeur est bornée à 720 entrées récentes.

## Comportement cible

Pipeline de référence :

```text
Kraken REST -> historique initial
Kraken WebSocket -> updates temps réel
backend -> normalisation/cache/persistence éventuelle
WebSocket cockpit -> frontend
Lightweight Charts -> rendu
```

Principes de fonctionnement :

- récupérer l'historique disponible sans inventer les données manquantes ;
- considérer la candle en cours comme mutable jusqu'à clôture ;
- rendre les upserts idempotents ;
- accumuler durablement les candles si le besoin dépasse la fenêtre Kraken ;
- après une coupure, effectuer un backfill des trous récupérables avant de reprendre le live ;
- charger prioritairement la paire active ;
- partager/cache les données plutôt que multiplier les connexions par composant React.

## Architecture envisagée

Une couche dédiée backend est préférable à une connexion Kraken ouverte directement par le navigateur :

```text
Kraken adapters
-> CandleService
   -> cache hot
   -> repository durable optionnel
   -> historical query API
   -> cockpit WebSocket broadcaster
-> frontend active market subscription
```

Le service doit normaliser au moins : `(symbol, market_type, timeframe, open_time, OHLC, volume si
présent, closed/updated_at)` selon le contrat finalement retenu.

## Invariants

- pas de look-ahead : seule une candle effectivement close est considérée historique finale ;
- données Kraken/backend canoniques ;
- aucun LLM dans cette pipeline ;
- reconnexion bornée et état de staleness explicite ;
- déduplication/idempotence ;
- frontend non requis au fonctionnement du service.

## Dépendances

- intégrations Kraken ;
- service runtime asynchrone ;
- persistence PostgreSQL si accumulation retenue ;
- API/WebSocket FastAPI ;
- monitored set pour gérer les subscriptions utiles.

## Risques / pièges

- écrire en base chaque tick sans besoin ;
- finaliser trop tôt la candle courante ;
- produire un trou silencieux après reconnexion ;
- confondre ticker et OHLC ;
- multiplier les streams Kraken pour plusieurs clients cockpit ;
- promettre 1000 candles au premier démarrage alors que seules 720 sont récupérables en Spot REST.

## Critères d'acceptation

- une requête historique renvoie les candles disponibles ordonnées et sans doublon ;
- la candle courante est mise à jour en temps réel ;
- reconnect + backfill ne dupliquent pas les candles ;
- si une persistence est activée, la profondeur accumulée survit au restart ;
- la paire active du cockpit reçoit les updates sans lancer un cycle IA ;
- une limitation de profondeur est explicitement signalée au lieu d'être comblée artificiellement.

## Fichiers/composants probablement concernés

- `integrations/kraken/rest.py`, `market_data.py`, `websocket.py`, `derivatives.py` ;
- nouveaux service/repository candles ;
- migration éventuelle ;
- FastAPI route historique et endpoint WebSocket ;
- runtime lifecycle ;
- tests Kraken/reconnect/cache/persistence/API ;
- frontend hooks WebSocket/chart.

## Ordre recommandé d'implémentation

**6A — avant le rendu chart.** Il s'agit de la source de données du batch 6B.

---

# 14. Découpage global recommandé

| Ordre | Batch proposé | Résultat principal | Nature dominante |
| ---: | --- | --- | --- |
| 1 | 19.1 — Comptabilité SPOT canonique | coût moyen, P&L, recovery | domaine/ledger |
| 2 | 19.2 — Monitoring & mark-to-market | état positions vivant sans LLM | backend runtime |
| 3 | 19.3 — Mode gestion | évite recherche IA inutile à exposition saturée | orchestration/Risk |
| 4 | 19.4 — Discovery & watchlist | univers dynamique, versionné, auditable | Agent + backend |
| 5 | 19.5 — Explicabilité UI | rationale visible et distinct de Risk | API/frontend |
| 6 | 19.6A — Candles & streaming backend | historique/cache/WS canonique | data/backend |
| 7 | 19.6B — Marchés & charts | onglets, Lightweight Charts, markers | frontend |

Le découpage 19.6A/19.6B est volontaire : il évite de construire d'abord une visualisation qui aurait
ensuite besoin de sa propre logique de données et préserve le backend comme source de vérité.

## 15. Dépendances entre chantiers

```text
19.1 Comptabilité SPOT
  |
  v
19.2 Monitoring / mark-to-market
  |
  +----------------------+
  v                      v
19.3 Mode gestion      19.4 Discovery + watchlist
                          |
                          v
                       monitored set
                          |
                 +--------+--------+
                 v                 v
              19.5 UI          19.6A candles/WS
                                   |
                                   v
                              19.6B Marchés/charts
```

19.5 peut commencer en partie avant 19.4 si son périmètre est strictement l'affichage du rationale
déjà persisté, mais son intégration complète aux positions et markers doit rester alignée avec les
contrats finaux.

## 16. Validation attendue par futurs batches

### 19.1

- tests unitaires ledger SPOT : buys successifs, ventes partielles/totales, coûts ;
- tests persistence/recovery ;
- analytics/réconciliation ;
- API contracts.

### 19.2

- tests monitor sans Agent ;
- tests multi-position SPOT/PERP ;
- funding/liquidation ;
- tests concurrence/restart/staleness.

### 19.3

- tests aucune recherche d'ouverture lorsque capacité saturée ;
- tests réduction/clôture/HOLD ;
- tests retour au mode normal ;
- métriques IA.

### 19.4

- tests eligibility sans ranking ;
- tests Agent watchlist bornée ;
- tests versionnement/recovery ;
- tests invariant watchlist + positions ouvertes ;
- mode manuel reproductible.

### 19.5

- tests API/audit ;
- lint/typecheck/build frontend ;
- tests affichage rationale vs Risk lorsque disponibles.

### 19.6A

- tests parsing OHLC, déduplication, reconnect/backfill ;
- tests persistence/cache ;
- tests WebSocket cockpit ;
- tests staleness/lifecycle.

### 19.6B

- lint/typecheck/build ;
- tests composants/hooks si la base de tests frontend le permet ;
- validation manuelle light/dark, changement onglet/timeframe et cleanup subscriptions.

## 17. Références externes Kraken à revalider au batch d'implémentation

Documentation officielle consultée lors de ce cadrage :

- Spot REST OHLC : `https://docs.kraken.com/api-reference/market-data/get-ohlc-data` — profondeur
  limitée aux 720 entrées les plus récentes ;
- Spot WebSocket v2 OHLC : `https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/ohlc`
  — canal `ohlc` temps réel avec intervalles supportés.

Les capacités, limites et schémas Kraken doivent être revérifiés au moment du batch concerné avant
d'implémenter un contrat dépendant d'elles.
