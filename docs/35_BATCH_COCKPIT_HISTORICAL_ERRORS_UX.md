# Batch 35 — UX / observabilité des erreurs historiques du cockpit

## Base auditée

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD GitHub: 4a516fde33853fe84d18bd8c4780753c0db58214
Commit     : fix: harden market attention runtime
```

`docs/00_ETAT_ACTUEL.md` pointait encore `78607ce6ab9f2b9459de2b1e1a7127509475283a`. Le compare GitHub confirme que `main` est un commit plus loin et que ce commit correspond au hardening Market Attention intégré.

La discussion courante confirme par ailleurs des correctifs Batch 34 / 34.1 / 34.2 déjà présents localement et non intégrés. Le Batch 35 ne modifie aucun fichier backend afin de ne pas interférer avec ces correctifs locaux.

## Audit

### Confirmé

- `/api/v1/cycles/latest` retourne le cycle le plus récent, avec `status`, `recorded_at` et `failure`.
- `/api/v1/errors/latest` retourne le dernier cycle `FAILED` disposant de métadonnées d'échec ; cette donnée est historique par nature et reste utile pour l'audit.
- le cockpit GitHub `main` affiche actuellement `latestCycle.failure` et `latestError.failure` comme deux blocs destructifs indépendants ; `latestError` porte le libellé `Erreur persistée` même lorsqu'un cycle plus récent a réussi.
- le contrat frontend contient déjà `cycle_id`, `status`, `recorded_at` et `failure` : aucune évolution API n'est nécessaire pour distinguer état courant et historique.
- `formatFailure()` utilisait `timed_out=true` comme synonyme de timeout fournisseur IA, alors que le cas observé `TimeoutError` correspond au timeout global du stage AGENT. `LLMTimeoutError` reste le timeout fournisseur explicite.

### Obsolète

- le HEAD de `docs/00_ETAT_ACTUEL.md` (`78607ce…`) n'est plus le HEAD GitHub réel.
- la roadmap GitHub `docs/09_ROADMAP_DEVELOPPEMENT.md` référence également encore `78607ce…` et marque le Batch 33 comme proposé alors que `4a516fde…` l'a intégré.
- le libellé `Erreur persistée` utilisé comme alerte rouge active pour tout `latestError` ne reflète pas correctement la sémantique de l'endpoint.

### Manquant

- une règle frontend canonique, pure et testée pour résoudre : échec actif du dernier cycle / dernière erreur historique ;
- la déduplication lorsque `latestCycle.failure` et `latestError.failure` décrivent le même cycle ;
- un horodatage visible pour l'erreur historique ;
- un libellé distinct entre `TimeoutError` de stage et `LLMTimeoutError` fournisseur.

### À décider

Aucune évolution backend n'est nécessaire dans ce batch. Un déplacement futur de l'historique d'erreurs vers une vue d'audit plus détaillée pourra être envisagé séparément si l'accueil devient trop chargé, sans modifier la sémantique retenue ici.

## Solution retenue

Le helper pur `resolveCockpitFailurePresentation()` reçoit `latestCycle` et `latestError` :

1. si le dernier cycle est `FAILED`, sa `failure` est l'alerte active ;
2. si `latestError.cycle_id` correspond à ce même cycle, aucune seconde alerte historique n'est produite ;
3. si `latestError.recorded_at` est strictement antérieur au dernier cycle chargé, il devient `historicalError` ;
4. si l'ordre temporel ne peut pas être démontré, l'erreur n'est pas artificiellement reclassée en historique.

Le composant d'accueil affiche alors :

- un bloc destructif `Dernier cycle en échec` uniquement pour l'échec actif ;
- le feedback d'action cockpit en destructif lorsqu'il existe ;
- un état vert `État courant normal` en l'absence d'erreur active ;
- un bloc neutre séparé `Dernière erreur historique`, avec timestamp, lorsque l'erreur a été dépassée par un cycle plus récent.

Le backend, la persistence et les endpoints restent inchangés.

## Fichiers du patch

```text
frontend/src/components/cockpit/cockpit-shell.tsx
frontend/src/lib/api/format.ts
frontend/src/lib/api/format.test.mjs
docs/00_ETAT_ACTUEL.md
docs/35_BATCH_COCKPIT_HISTORICAL_ERRORS_UX.md
```

`docs/09_ROADMAP_DEVELOPPEMENT.md` et `docs/10_DECISIONS_ET_CHANGELOG.md` ont été examinés. `docs/10` ne nécessite pas de nouvelle ADR pour ce correctif UX local. La copie GitHub de `docs/09` est elle-même obsolète sur le statut du Batch 33, mais elle n'est volontairement pas remplacée dans ce ZIP : la discussion confirme des correctifs Batch 34 / 34.1 / 34.2 locaux et leur version exacte de la roadmap n'est pas disponible dans l'environnement de préparation. Si la copie locale de `docs/09` est encore obsolète après extraction, elle devra être réalignée avant le commit d'intégration.

## Tests ciblés attendus

Le test frontend couvre :

- erreur historique + cycle plus récent `COMPLETED` -> aucune alerte active, historique exposé ;
- dernier cycle `FAILED` correspondant à `latestError` -> une seule alerte active ;
- absence d'erreur -> aucun état erreur ;
- erreur ancienne dépassée par plusieurs cycles réussis -> reste historique ;
- incohérence temporelle -> pas de reclassement historique abusif ;
- `LLMTimeoutError` -> timeout fournisseur IA ;
- `TimeoutError` global avec `timed_out=true` -> dépassement du délai du stage.

## Validation locale recommandée

Depuis `E:\AI-Spot-Trader` :

```powershell
cd frontend
node --test --experimental-strip-types src/lib/api/format.test.mjs
pnpm test
pnpm lint
pnpm typecheck
pnpm build

cd ..
git diff --check
git status --short
```

Avant extraction du ZIP, conserver les correctifs locaux Batch 34 / 34.1 / 34.2. En cas de modification locale concurrente d'un des trois fichiers frontend du Batch 35, comparer ce fichier avant remplacement plutôt que d'écraser la version locale.

## Tests réellement exécutés par ChatGPT

Exécutés sur les fichiers Batch 35 préparés :

```text
node --test --experimental-strip-types frontend/src/lib/api/format.test.mjs
-> 6 passed, 0 failed

TypeScript transpileModule syntax check
-> cockpit-shell.tsx : OK
-> format.ts         : OK

tsc --noEmit sur format.ts avec les contrats de types minimaux correspondant aux champs GitHub audités
-> succès
```

Contrôle de provenance du composant : après retrait mécanique des seules modifications Batch 35, le blob Git reconstruit de `cockpit-shell.tsx` est exactement `3295631cd8ad6a8dc15b6869ccdabea91a62d804`, identique au blob GitHub `main` audité. Cela confirme qu'aucune autre portion du composant GitHub n'a été altérée lors de la préparation.

Non exécutés dans l'environnement ChatGPT faute de repository frontend complet et de ses dépendances installées :

```text
pnpm test
pnpm lint
pnpm typecheck
pnpm build
```

Ces commandes restent à exécuter localement après extraction, sur l'arbre utilisateur qui contient déjà les correctifs Batch 34 / 34.1 / 34.2.
