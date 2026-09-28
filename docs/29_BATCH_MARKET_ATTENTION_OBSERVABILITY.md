# Batch 29 — Market Attention Observability

## 1. Référence de départ

```text
Repository : Ax-07/AI-Spot-Trader
Branche    : main
HEAD GitHub vérifié : 3c609c7499dbef37a917046d6e70ae5112e0ad4c
Commit              : feat: add market attention radar v1
```

Aucun commit n'est intervenu entre la référence fournie au lancement du batch et la vérification directe de `main`.

`docs/00_ETAT_ACTUEL.md` était en retard : il mentionnait encore `d011faa` et qualifiait Market Attention Radar v1 de patch proposé. Cette dérive est corrigée dans ce batch.

Le fichier local éventuel `trades_9h_analysis.json` est hors périmètre et n'est pas inclus dans la livraison.

## 2. Objectif

Améliorer l'observabilité et le diagnostic du **Market Attention Radar v1** sans recalibrer ses seuils et sans modifier son influence sur le trading.

Le besoin principal est de distinguer une absence normale de candidat d'une couverture d'activité réellement dégradée.

## 3. Audit de l'existant

### Confirmé

- le Radar intégré tourne indépendamment de l'Agent stratégique ;
- la rotation du catalogue et le cache d'activité sont déjà présents ;
- `CandleStreamService` est la source OHLCV canonique ;
- `MarketActivitySnapshot` et `ActivityHorizonSnapshot` portent déjà les données nécessaires au diagnostic ;
- `_candidates()` filtre exclusivement `status=AVAILABLE` et les états `ELEVATED / ACCELERATING / VERY_HIGH` ;
- `_public_attention()` ne reçoit que ces candidats ;
- l'API est read-only ;
- le cockpit affiche déjà catalogue, cache, scan, candidats, recherches et shortlist.

### Obsolète / trompeur

`_overview_status()` retournait systématiquement `PARTIAL` lorsqu'une shortlist était vide. Une absence d'événement inhabituel était donc indiscernable d'un Radar réellement dégradé.

### Manquant

- distribution des statuts des snapshots frais ;
- distribution des états d'activité ;
- diagnostic des marchés `AVAILABLE + NORMAL` proches du seuil ;
- message cockpit explicite pour « Radar opérationnel, aucun candidat ».

### Audité sans modification nécessaire

- `backend/src/ai_spot_trader/api/routes/market_attention.py` : transporte déjà le modèle `MarketAttentionOverview`, donc les champs additifs sont exposés automatiquement ;
- `backend/src/ai_spot_trader/main.py` : composition/lifecycle inchangés ;
- `backend/tests/test_openai_market_attention.py` : contrat web_search inchangé ;
- `frontend/src/app/page.tsx` : le dock existant reste le point d'intégration ;
- `docs/01_PROJECT_MASTER.md`, `docs/02_ARCHITECTURE_TECHNIQUE.md`, `docs/09_ROADMAP_DEVELOPPEMENT.md`, `docs/10_DECISIONS_ET_CHANGELOG.md` : aucun invariant architectural, roadmap ou contrat stratégique n'est changé par ce batch. Les détails du patch sont concentrés ici et l'état court est corrigé dans `docs/00_ETAT_ACTUEL.md`.

## 4. Choix de statut global

Aucune nouvelle valeur d'enum n'est introduite.

Les enums existantes suffisent :

- `AVAILABLE` = le service Radar possède au moins une activité fraîche exploitable ; une shortlist vide est alors une conclusion valide sur les données disponibles ;
- `PARTIAL` = aucune activité `AVAILABLE` n'est disponible, ou l'enrichissement public d'une shortlist existante est incomplet ;
- `STALE` = toutes les activités fraîches du cache sont elles-mêmes `STALE` ;
- `ERROR` = toutes les activités fraîches sont en erreur, ou le refresh global échoue ;
- `NOT_CONFIGURED` reste utilisé pour l'absence de composition/configuration prévue par le contrat existant.

Les compteurs détaillés permettent de voir immédiatement si un état global `AVAILABLE` repose sur une couverture majoritairement saine ou sur un sous-ensemble limité. Aucun ratio arbitraire de « santé minimale » n'est ajouté.

## 5. Diagnostic du cache d'activité

`MarketAttentionOverview` expose deux structures additives :

```text
activity_status_counts
  AVAILABLE
  PARTIAL
  STALE
  ERROR

activity_state_counts
  UNKNOWN
  NORMAL
  ELEVATED
  ACCELERATING
  VERY_HIGH
```

Les comptes sont calculés uniquement à partir de `_fresh_activities(now)`, donc exactement selon le TTL d'activité déjà canonique.

Aucun snapshot expiré du cache ne contribue aux compteurs.

## 6. Activités sous seuil

Le backend expose un tableau borné :

```text
subthreshold_activity
```

Chaque entrée contient uniquement :

- `market` ;
- `peak_volume_ratio` ;
- `peak_timeframe`.

Éligibilité :

```text
status = AVAILABLE
activity_state = NORMAL
```

Le meilleur horizon est choisi parmi les `ActivityHorizonSnapshot` complets possédant un `volume_ratio`. Le tri réutilise `_activity_sort_key`, donc le même ordre descriptif ratio / accélération / mouvement que le Radar existant.

La limite est `diagnostic_market_limit`, défaut `10`, hard limit `30`.

Cette limite est purement d'affichage/diagnostic et ne modifie aucun seuil d'activité.

## 7. Séparation stricte du chemin candidat

Le refresh calcule désormais explicitement :

```text
fresh activities
    ├─ compteurs diagnostic
    ├─ subthreshold_activity (AVAILABLE + NORMAL)
    └─ candidates (AVAILABLE + ELEVATED/ACCELERATING/VERY_HIGH)
              ↓
         public web research
              ↓
            shortlist
```

Ainsi un marché sous seuil :

- ne devient pas candidat ;
- n'entre pas dans `_public_attention()` ;
- ne dépense aucun appel web ;
- n'entre pas dans la shortlist ;
- n'est fourni à aucun Agent ;
- ne change ni Market Discovery, ni Risk, ni Broker.

## 8. Cockpit

Le dock existant reste compact et affiche :

```text
Catalogue
Marchés frais
Scannés refresh
Candidats
Recherches web

Données
AVAILABLE / PARTIAL / STALE / ERROR

Activité
NORMAL / ELEVATED / ACCELERATING / VERY_HIGH / UNKNOWN

Plus fortes activités sous seuil
market + type + meilleur ratio + horizon
```

Un message humain distingue notamment :

```text
Radar opérationnel — aucun événement inhabituel détecté.
```

et :

```text
Radar partiellement disponible — aucune activité inhabituelle confirmée sur les données exploitables.
```

Le badge `INFORMATIF — N’INFLUENCE PAS LE TRADING` reste visible. Le statut est rendu dans un badge séparé afin d'éviter la concaténation visuelle du type `TRADINGPARTIAL`.

## 9. Périmètre préservé

Aucun changement sur :

- seuils `1.40 / 1.75 / 2.50` ;
- sélection Candidate ;
- OpenAI `web_search` et sa limite ;
- Agent et prompts ;
- Market Discovery ;
- Risk Engine ;
- Broker ;
- ordres ;
- persistence SQL ;
- source de candles ;
- PAPER/LIVE.

## 10. Fichiers modifiés / créés

```text
backend/src/ai_spot_trader/market/attention.py
backend/tests/test_market_attention_observability.py
frontend/src/components/cockpit/market-attention-dock.tsx
frontend/src/lib/market-attention.ts
frontend/src/lib/market-attention.test.mjs
docs/00_ETAT_ACTUEL.md
docs/29_BATCH_MARKET_ATTENTION_OBSERVABILITY.md
```

## 11. Tests réellement exécutés par ChatGPT

### Python — compilation

```text
python -m py_compile backend/src/ai_spot_trader/market/attention.py
python -m py_compile backend/tests/test_market_attention_observability.py
```

Résultat : succès.

### Tests backend ciblés en environnement isolé

Le nouveau fichier de tests a été exécuté avec `pytest` contre un package isolé contenant le module réel modifié et des stubs minimaux des dépendances canoniques :

```text
7 passed
```

Un harness complémentaire a exécuté le module réel modifié et vérifié :

- shortlist vide + activités normales disponibles -> `AVAILABLE` ;
- compteurs `AVAILABLE` et `NORMAL` ;
- classement sous seuil `1.31 > 1.27` ;
- meilleur horizon identifié ;
- marchés sous seuil -> zéro recherche web ;
- marché `ELEVATED` seul envoyé à la recherche publique ;
- données uniquement partielles -> statut global `PARTIAL`.

Résultats : `7/7` tests ciblés passés et `isolated radar observability harness: PASS`.

### Frontend isolé

```text
node --test --experimental-strip-types frontend/src/lib/market-attention.test.mjs
```

Résultat : `6/6` passés.

Couverture :

- helpers existants ;
- nouveau message `AVAILABLE` sans candidat ;
- message `PARTIAL` réel ;
- mapping des compteurs ;
- mapping du diagnostic sous seuil.

## 12. Validations restant à exécuter localement

L'environnement ChatGPT ne possède pas le checkout complet ni les dépendances installées du repository. Les commandes suivantes ne sont donc pas déclarées réussies :

```powershell
cd backend
pytest -q

cd ..\frontend
pnpm test
pnpm lint
pnpm typecheck
pnpm build

cd ..
git diff --check
```

Les nouveaux tests backend sont conçus pour couvrir :

1. comptage `AVAILABLE / PARTIAL / STALE / ERROR` ;
2. comptage des états d'activité ;
3. exclusion des snapshots expirés du cache actif ;
4. classement des marchés `NORMAL` sous seuil ;
5. identification du meilleur horizon ;
6. absence de promotion en candidat ;
7. absence de recherche web pour le diagnostic sous seuil ;
8. shortlist vide + données saines -> état opérationnel ;
9. données non exploitables -> `PARTIAL` ;
10. API toujours GET-only avec champs additifs.

## 13. Migration

Aucune.

## 14. Extraction

Le ZIP du batch est root-relative. Extraire directement à la racine du repository. Il ne contient ni dossier parent `AI-Spot-Trader`, ni `.git`, `.env`, secret, venv, cache, dépendance installée ou `trades_9h_analysis.json`.
