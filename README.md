# AI Spot Trader — Instructions permanentes

AI Spot Trader est une application expérimentale de trading crypto SPOT pilotée par un agent IA unique.

## Source de vérité

Source de vérité technique :

* GitHub : `Ax-07/AI-Spot-Trader`
* Branche : `main`

GitHub `main` représente l'état intégré. La documentation versionnée complète cette source de vérité.

Ne pas utiliser les anciennes conversations, souvenirs du modèle ou anciennes pièces jointes comme source de vérité technique.

Le dépôt local de l'utilisateur peut contenir des modifications non commitées plus récentes. Si l'utilisateur fournit `git status`, `git diff`, logs, fichiers ou résultats locaux, les considérer comme l'état courant du travail.

Toujours distinguer :

* état intégré GitHub ;
* modifications locales ;
* patch proposé non intégré.

## Début d'une nouvelle discussion

Pour toute nouvelle tâche :

1. consulter le HEAD actuel de GitHub `main` ;
2. lire `docs/00_ETAT_ACTUEL.md` ;
3. comparer son HEAD de référence au HEAD GitHub ;
4. si nécessaire, inspecter les commits intervenus depuis ;
5. consulter uniquement les documents/fichiers utiles à la tâche.

Ne pas demander à l'utilisateur des informations déjà disponibles dans GitHub, la documentation ou la conversation courante.

## Méthode de travail

Auditer l'existant avant toute modification importante.

Préserver les composants canoniques et éviter les implémentations parallèles inutiles.

Privilégier des batches cohérents, limités et testables.

Ne jamais déclarer un test réussi s'il n'a pas réellement été exécuté.

Distinguer clairement les tests exécutés par ChatGPT des tests restant à exécuter dans l'environnement utilisateur.

Ne jamais modifier GitHub directement sauf demande explicite.

## LIVRAISON DU CODE — RÈGLE PRIORITAIRE

Pour tout batch comportant plusieurs fichiers, fournir par défaut un **ZIP prêt à extraire à la racine du repository**.

L'utilisateur ne doit pas avoir à recopier manuellement de nombreux blocs de code.

Le ZIP doit être **root-relative** et conserver exactement l'arborescence du repository.

Exemple du contenu du ZIP :

```text id="fgksag"
src/
  market/
    kraken_ws.py
tests/
  test_kraken_ws.py
docs/
  ...
```

Ne PAS encapsuler ces fichiers dans un dossier parent portant le nom du projet.

Le ZIP doit pouvoir être extrait directement à la racine.

Inclure uniquement les fichiers créés ou réellement modifiés par le batch.

Les fichiers livrés doivent être complets et directement utilisables. Ne jamais utiliser de placeholders du type « reste du fichier inchangé ».

Ne jamais inclure :

* `.git/` ;
* `.env` avec secrets ;
* clés API ;
* environnement virtuel ;
* caches ;
* dépendances installées ;
* fichiers temporaires inutiles.

Nommer les ZIP clairement, par exemple :

`batch_01_project_bootstrap.zip`
`batch_02_kraken_websocket.zip`
`batch_03_paper_broker.zip`

Après génération, fournir un lien de téléchargement.

Pour chaque ZIP, indiquer brièvement :

1. objectif du batch ;
2. fichiers principaux créés/modifiés ;
3. extraction à la racine ;
4. commandes exactes de validation ;
5. résultat attendu.

Si une correction touche plusieurs fichiers, fournir également un ZIP correctif plutôt qu'une longue série de modifications manuelles.

Les petits snippets restent acceptables pour une commande, quelques lignes, un diagnostic ou une modification triviale.

## Validation

Après une modification, fournir les commandes pertinentes, par exemple :

```bash id="frd9gn"
git status
git diff
pytest
```

Si un test nécessite Kraken, Internet, une clé API ou l'environnement local et n'a pas pu être exécuté par ChatGPT, le préciser.

Ne jamais inventer un résultat de test.

## Documentation

Documentation en français. Code et identifiants techniques de préférence en anglais.

Maintenir notamment :

* `docs/00_ETAT_ACTUEL.md` : mémoire courte de l'état courant ;
* `docs/01_PROJECT_MASTER.md` : spécification principale ;
* `docs/09_ROADMAP_DEVELOPPEMENT.md` : roadmap ;
* `docs/10_DECISIONS_ET_CHANGELOG.md` : décisions/ADR/changelog.

Après un batch important, vérifier les documents concernés.

`00_ETAT_ACTUEL.md` doit rester court et actuel, pas devenir un changelog cumulatif.

## Invariants fonctionnels

Sauf décision explicite contraire :

* un seul agent IA de trading ;
* Kraken comme exchange initial ;
* trading SPOT uniquement ;
* aucun short, levier, margin, future ou perpetual ;
* Luna pour les premiers tests afin de réduire les coûts ;
* architecture permettant de remplacer Luna par Sol par configuration ;
* cible expérimentale : +4 % de rendement journalier ;
* agressivité configurable de 1 à 10 ;
* BUY, SELL et HOLD sont les actions de trading ;
* impossible de vendre un actif non détenu ;
* l'agent IA prend les décisions stratégiques ;
* le Risk Engine déterministe reste l'autorité finale ;
* aucune sortie LLM ne déclenche directement un ordre Kraken ;
* premières versions exclusivement en PAPER ;
* frais, spread et slippage doivent être simulés ;
* toutes les décisions, y compris HOLD, sont journalisées ;
* aucune clé/secrets dans prompts, logs ou fichiers versionnés ;
* aucune clé Kraken avec droit de retrait ;
* passage au LIVE explicite et séparé du PAPER.

## Philosophie

Ne pas transformer silencieusement le projet en bot algorithmique traditionnel.

Les systèmes déterministes peuvent calculer données, statistiques, indicateurs et contraintes de risque, mais l'objectif est que l'agent IA conserve la décision stratégique.

La cible +4 %/jour est un objectif expérimental, jamais une garantie.

Mesurer honnêtement P&L net, drawdown, frais, slippage, exposition et nombre de trades. Aucun look-ahead ou sélection rétrospective des résultats.

## Style de collaboration

Répondre en français sauf demande contraire.

Être concret et orienté implémentation.

Pour les audits, distinguer :

* confirmé ;
* obsolète ;
* manquant ;
* à décider.

Ne pas transformer silencieusement une hypothèse en décision architecturale.

Si plusieurs solutions ont des conséquences importantes, présenter brièvement les options avant implémentation.

## Règle de travail essentielle

Pour un batch multi-fichiers :

**resynchroniser → auditer → modifier → tester autant que possible → créer un ZIP root-relative → fournir les commandes de validation.**
