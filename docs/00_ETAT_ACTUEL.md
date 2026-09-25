# 00 — État actuel

> Mémoire courte de reprise. À garder synthétique, factuelle et alignée avec GitHub `main` et le patch local en cours.

## Référence technique

- Repository : `Ax-07/AI-Spot-Trader`
- Branche : `main`
- HEAD GitHub `main` audité avant le Batch 19.4 :
  `bfef06d78dc34089541272c2944518499d4a1530`
  (`feat: add deterministic capacity management mode`).
- Batch 19.3 **intégré** sur GitHub à ce HEAD.
- Validation locale communiquée pour 19.3 : `tests/test_capacity_management.py` = 18 tests passés ; suite backend complète = 552 tests passés ; frontend inchangé.
- Batch 19.4 livré ici comme **patch local proposé**, non intégré à GitHub par ChatGPT.

## État fonctionnel visé après application du patch Batch 19.4

- un seul Agent IA stratégique ; Kraken ; PAPER uniquement ; SPOT + PERPETUAL linéaire ;
- Risk Engine déterministe = autorité finale ; aucune sortie LLM ne déclenche directement un ordre ;
- Batch 19.3 `NORMAL` / `MANAGEMENT` conservé ; `MANAGEMENT` est évalué avant tout renouvellement de watchlist et évite donc l'appel IA de discovery destiné aux nouvelles ouvertures ;
- `paper_executable_markets` reste un bootstrap/garde-fou immuable de Campaign, utile notamment en fallback ;
- un `MarketDiscoveryPolicy` optionnel active la découverte dynamique sans casser les Campaigns statiques existantes ;
- le catalogue Kraken est lu via le `MarketResearchService` canonique et mis en cache ;
- filtrage déterministe : type autorisé, quote settlement, statut exploitable, PERPETUAL linéaire, snapshot disponible/frais au sens de fraîcheur et historique causal suffisant ;
- aucun score d'opportunité déterministe n'est calculé ; la présélection réduit seulement l'univers factuel ;
- le **même** `OpenAIDecisionProvider` fournit le modèle/client/horloge à l'adaptateur de sélection de watchlist ; aucun second Agent n'est créé ;
- la watchlist IA est multi-marchés, bornée et validée strictement comme sous-ensemble de l'univers candidat ;
- l'univers effectif d'un cycle normal = watchlist IA + marchés des positions ouvertes ;
- les positions ouvertes restent gérables même si leur marché a quitté la nouvelle watchlist ;
- en panne Kraken ou LLM de discovery, la dernière watchlist valide est conservée ; sans watchlist précédente, le bootstrap de Campaign sert de fallback explicite ;
- les échecs de discovery sont temporisés par la cadence de renouvellement et ne provoquent pas un nouvel appel à chaque cycle ;
- la watchlist reste un cache process-local : après restart, `NORMAL` la reconstruit au premier renouvellement utile ; `MANAGEMENT` gère d'abord les positions restaurées sans relancer la discovery ;
- le recovery canonique de Campaign est réutilisé ; une sous-classe élargit uniquement l'univers de reprise aux marchés des positions durables avant les validations existantes ;
- l'audit de cycle transporte le statut de discovery, catalogue/candidats avec faits candidats, watchlist effective, ajouts/maintiens/retraits, rationale structuré et erreur éventuelle, sans nouvelle table SQL ;
- le configurateur simple active la discovery par défaut : l'opérateur fournit seulement une paire bootstrap/secours au lieu de saisir toute la watchlist ;
- frontend toujours sans autorité trading ni calcul financier parallèle.

## Décisions Batch 19.4

- catalogue canonique : `MarketResearchService` + adaptateurs Kraken existants ;
- cache catalogue par défaut : 15 min ;
- renouvellement watchlist par défaut : 15 min, déclenché par un cycle `NORMAL`, refresh borné à 45 s ;
- probe factuel max : 24 marchés par renouvellement ; candidats IA max : 12 ; watchlist max : 6 ;
- pas de persistence mutable dédiée de watchlist en 19.4 : audit durable par cycle + reconstruction après restart ;
- `risk_allowed_pairs=null` est permis uniquement pour une Campaign dynamique ; une whitelist non nulle reste un garde-fou déterministe additionnel ;
- aucun ranking algorithmique d'opportunité, aucun second Agent, aucun LIVE, aucun chart/candle cockpit dans ce batch.

## Prochaine priorité

1. Batch 19.5 — explicabilité dédiée IA / Risk ;
2. Batch 19.6A — backend candles/cache/streaming ;
3. Batch 19.6B — vue Marchés/charts/markers.

Le cadrage détaillé reste centralisé dans `docs/11_AMELIORATIONS_PLANIFIEES.md`.

## Règle de reprise

À chaque nouveau batch : revérifier le HEAD GitHub réel, puis distinguer clairement état intégré, modifications locales et patch proposé.
