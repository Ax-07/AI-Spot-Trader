# Batch 19.11 — Kraken Derivatives Margin Tiers

## Statut

Patch proposé localement à partir du HEAD GitHub `main` :

`47e12798f54c3686b59faf339315ff39d9191b44`

Le batch ne commit ni ne push GitHub directement.

## Cause racine

Le parseur Kraken intégré avant ce batch validait plusieurs niveaux publics de marge puis réduisait l'ensemble à :

```text
initial_margin_rate = max(initialMargin publics)
maintenance_margin_rate = max(maintenanceMargin publics)
max_leverage = 1 / initial_margin_rate
```

Cette représentation était conservatrice mais perdait la dimension « taille de position ». Une petite nouvelle position pouvait donc hériter artificiellement du dernier palier réservé aux grosses positions et être rejetée par `DERIVATIVE_LEVERAGE_EXCEEDED`.

Le problème est distinct du correctif `47e12798`, qui autorise une réduction `reduce_only` d'une position legacy déjà au-dessus des caps courants.

## Vérification publique Kraken

La documentation publique Kraken décrit des exigences IM/MM croissantes avec la taille de position. Pour les clients EEA, la Class E commence actuellement à 10 % IM / 5 % MM, soit 10x, avant de se durcir à 20 % / 10 %, 30 % / 15 %, puis 50 % / 25 % sur les paliers supérieurs.

Les tables publiques de spécifications classent actuellement `PF_ACEUSD`, `PF_2ZUSD` et `PF_AIXBTUSD` en Class E (10x au premier niveau). Les paramètres Kraken pouvant évoluer, aucun symbole ni classe de marge n'est hardcodé dans le code.

## Architecture retenue

Nouveau module provider-agnostic :

`backend/src/ai_spot_trader/domain/derivative_margin.py`

Il contient :

- `DerivativeMarginTier` ;
- `TieredDerivativeInstrument`, compatible avec `DerivativeInstrument` ;
- `ApplicableDerivativeMargin` ;
- `resolve_derivative_margin(...)`, fonction canonique unique utilisée par Risk et le ledger.

Un tier contient :

```text
threshold
threshold_basis = CONTRACTS | POSITION_NOTIONAL
initial_margin_rate
maintenance_margin_rate
```

Les courbes doivent :

- commencer à zéro ;
- être triées et sans doublon ;
- utiliser une seule base de seuil ;
- avoir des taux IM/MM valides ;
- ne pas voir IM ou MM diminuer lorsque la taille augmente.

Les instruments historiques ne disposant que d'un taux scalaire restent compatibles.

## Sélection du schedule Kraken

Le parseur traite les schedules comme des courbes distinctes. Il ne concatène jamais des schedules mutuellement exclusifs.

Politique PAPER v1 :

1. si `retailMarginLevels` est présent et valide, il est utilisé comme schedule public retail explicite ;
2. sinon `marginLevels` peut être utilisé lorsqu'aucun `marginSchedules` incompatible n'est exposé ;
3. un `marginSchedules` nommé peut être utilisé si une seule courbe unique est identifiable ;
4. si plusieurs schedules nommés incompatibles subsistent et qu'aucun schedule explicite prioritaire n'est disponible, le runtime reste fail-closed avec le fallback scalaire conservateur historique.

Cette politique ne prétend pas connaître un tier privé ni les droits d'un compte Kraken. Aucune API privée n'est ajoutée.

## Risk Engine

Pour une nouvelle exposition ou une augmentation :

```text
position courante éventuelle
+ quantité autorisée de l'ordre
= quantité projetée totale

quantité/notional projeté
→ resolve_derivative_margin(...)
→ max leverage Kraken applicable

max leverage effectif
= min(cap Session, cap Kraken applicable)
```

Le rejet `DERIVATIVE_LEVERAGE_EXCEEDED` est conservé lorsqu'il est réellement applicable.

Une augmentation d'une position choisit donc le tier sur la position totale projetée. Exemple : une position à 240 000 plus un ordre de 20 000 est évaluée à 260 000, pas à 20 000.

Le calcul de cash/marge tient également compte du remargement éventuel de l'ensemble de la position lorsque le nouvel ordre franchit un palier.

## Ledger PAPER

Le ledger utilise le même `resolve_derivative_margin(...)` que Risk.

À l'ouverture ou à l'augmentation :

- le tier est sélectionné sur la position totale projetée ;
- la marge cible de la position totale est recalculée ;
- seule la marge additionnelle réellement nécessaire est débitée ;
- `DerivativePosition.initial_margin_rate` et `maintenance_margin_rate` sont mis à jour avec le tier retenu ;
- `maintenance_margin` reste cohérente avec le notional marqué.

La réduction/clôture conserve le comportement existant : marge libérée au prorata et aucune nouvelle contrainte d'ouverture n'emprisonne une position legacy.

## Point d’attention de sérialisation

Le modèle tier-aware est conservé comme sous-type runtime de `DerivativeInstrument` pendant le flux `MarketState -> Risk -> PaperBroker/Ledger`, qui est le chemin d’exécution corrigé par ce batch.

Pydantic sérialise toutefois un champ déclaré comme `DerivativeInstrument` selon le schéma du type de base par défaut. Une sérialisation générique de `MarketState` peut donc omettre les champs additionnels `margin_tiers` et `margin_schedule_source`, même si l’objet runtime les conserve. Le batch ne réhydrate pas un `MarketState` sérialisé pour décider/exécuter un ordre ; l’exécution reste donc tier-aware.

Avant d’utiliser ultérieurement ces tiers comme contrat persistant ou payload d’audit rehydratable, il faudra faire une décision dédiée sur la sérialisation polymorphe (`SerializeAsAny` ou intégration directe des tiers au modèle canonique) et ajouter un test JSON round-trip tier-aware. Ne pas considérer ce point comme résolu silencieusement par ce batch.

## Invariants préservés

- un seul Agent IA stratégique ;
- PAPER uniquement ;
- Risk Engine déterministe et autorité finale ;
- aucun levier choisi librement par le LLM ;
- aucune sortie LLM directement vers Kraken ;
- aucune clé/API Kraken privée ;
- aucune modification LIVE ;
- aucune modification frontend ;
- aucune logique automatique d'entrée/sortie ;
- HOLD reste valide.

## Tests ajoutés / renforcés

### Parser

- schedule unique ;
- tiers multiples ;
- normalisation de l'ordre ;
- seuils dupliqués ;
- taux décroissants/incohérents ;
- `maintenanceMargin > initialMargin` ;
- `marginLevels`, `retailMarginLevels`, `marginSchedules` ;
- schedules nommés incompatibles sans fusion silencieuse.

### Risk

- petite position à levier compatible avec le premier tier ;
- rejet au-dessus du tier applicable ;
- franchissement de tier sur augmentation ;
- tier basé sur la position totale projetée ;
- cap Session plus strict toujours prioritaire ;
- réduction legacy `reduce_only` toujours autorisable ;
- augmentation legacy hors cap toujours refusée.

### Ledger

- marge calculée avec le même tier canonique ;
- taux de position cohérents ;
- remargement de la position totale lors d'un franchissement ;
- réduction/clôture inchangée.

## Validation locale opérateur attendue

```powershell
cd backend
pytest tests/test_kraken_derivatives.py -q
pytest tests/test_derivatives_domain.py -q
pytest tests/test_derivatives_risk.py -q
pytest tests/test_derivatives_paper.py -q
pytest

ruff check .
mypy --config-file pyproject.toml src

cd ..
git diff --check
git status --short
```

Ne déclarer comme réussi que ce qui a réellement été exécuté.

## Tests réellement exécutés par ChatGPT

L'environnement de travail n'a pas pu résoudre `github.com` depuis le conteneur, donc le clone complet du repository et le `pytest` backend intégral n'ont pas pu être exécutés directement.

Un harness local fidèle aux contrats Pydantic/enum/policy/broker nécessaires a été construit à partir du HEAD audité et les quatre suites modifiées ont été exécutées ensemble :

```text
49 passed in 0.12s
```

`python -m py_compile` a également réussi sur :

- `domain/derivative_margin.py` ;
- `integrations/kraken/derivatives.py` ;
- `risk/engine.py` ;
- `portfolio/ledger.py`.

`ruff` n'était pas installé dans l'environnement ChatGPT. Le backend complet, `ruff`, `mypy`, `git diff --check` et la validation PAPER réelle ACE restent donc à exécuter localement par l'opérateur.

## Correctif post-validation locale

La première validation locale opérateur a identifié deux catégories de défauts propres au Batch 19.11 :

- `mypy` : réutilisation du nom local `maintenance` avec deux types différents dans le parseur Kraken, produisant deux erreurs aux anciennes lignes 623/626 ;
- `ruff` : quatre lignes `E501` dans la fixture multi-tiers de `test_kraken_derivatives.py`.

Le correctif renomme le tuple en `maintenance_rates` et reformate la fixture sans modifier la sémantique.

Les autres erreurs affichées par les commandes globales `ruff check .` et `mypy --config-file pyproject.toml src` concernent des fichiers ou du code préexistants hors périmètre de ce correctif. Elles ne sont pas déclarées résolues par le Batch 19.11.
