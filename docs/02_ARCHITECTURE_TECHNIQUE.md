# 02 — Architecture technique

## 1. Référence

Base GitHub auditée au démarrage du Batch 18.9B :

```text
HEAD GitHub : efe5a0f162a69e50bd6e5f5cd7aa61039792e911
Dernier code: 11a04be33bf209552e6337e28318d039b775b264
```

Le HEAD `efe5a0f` est le commit documentaire finalisant 18.9A ; aucun commit code n'est intervenu
après `11a04be` au moment de l'audit.

## 2. Architecture générale

```text
Next.js cockpit
  |
  +-- /backend rewrite -> FastAPI
        |
        +-- Control Plane persistence (PostgreSQL)
        |     +-- Strategy / StrategyRevision
        |     +-- Campaign
        |     +-- campaign_id -> paper_runs
        |
        +-- CampaignRuntimeManager
              |
              +-- runtime actif optionnel
                    +-- TradingEngine
                    +-- AuditedTradingCycleRunner
                    +-- TradingCycleRunner
                    +-- OpenAIDecisionProvider
                    +-- RiskEngine
                    +-- PaperBroker
                    +-- PaperPortfolioLedger
                    +-- Kraken public research/execution sources
```

Le frontend n'est pas dans la chaîne d'exécution. Le manager backend possède au plus un runtime
actif et délègue aux composants canoniques existants.

## 3. Modules backend Control Plane 18.9A

```text
agent/prompt.py
agent/strategy_client.py
control_plane.py
campaign_composition.py
core/control_plane_runtime.py
persistence/control_plane.py
persistence/campaign_runs.py
api/control_plane_schemas.py
api/routes/control_plane.py
alembic/versions/0006_paper_control_plane.py
```

Ces modules restent inchangés dans le patch 18.9B.

## 4. Modules frontend 18.9B

```text
frontend/src/lib/api/types.ts
  miroir TypeScript des réponses Pydantic utiles, incluant Control Plane et lineage recovery

frontend/src/lib/api/client.ts
  client HTTP canonique existant étendu ; aucune seconde couche API

frontend/src/hooks/use-control-plane.ts
  orchestration UI, polling read-only et commandes HTTP ; aucun calcul Risk/Trading

frontend/src/components/cockpit/control-plane-panel.tsx
  UI Strategy/Revision/preview/Campaign/runtime

frontend/src/app/page.tsx
  montage du nouveau panneau avec le cockpit existant
```

Le hook ne persiste aucun draft de Strategy/Campaign dans le navigateur. Les valeurs de formulaire
restent en mémoire React jusqu'au POST backend.

## 5. Flux Strategy / Revision

```text
GET /strategies
-> sélectionner Strategy
-> lire latest_revision
-> GET /strategies/{id}/revisions/1..latest_revision
```

La persistence 18.9A crée les révisions séquentiellement, sans trou. Il n'existe pas de route
`list revisions` dédiée ; le cockpit réutilise donc les GET unitaires canoniques sans créer un
contrat parallèle.

Éditer le texte déclenche uniquement :

```text
POST /strategies/{id}/revisions
```

Aucune révision existante n'est mutée.

## 6. Prompt preview

Le cockpit appelle `POST /prompt-preview`. Il ne recompose pas le prompt métier. Il découpe
uniquement la chaîne `instructions` retournée selon les marqueurs canoniques pour l'affichage :

```text
contrat Agent protégé
stratégie opérateur
contexte d'agressivité
input dynamique futur = null
```

Si les marqueurs ne sont pas trouvés, il affiche le contenu canonique sans inventer de section.

## 7. Builder Campaign

Le formulaire mappe les champs vers le modèle backend `CampaignConfiguration` :

```text
paper-control-plane-config-v1
llm_model / aggressiveness / trading_cadence_seconds
paper_initial_capital / paper_settlement_asset
paper_executable_markets
paper_fee_rate / paper_spread_bps / paper_slippage_bps
paper_derivative_leverage / paper_derivative_margin_mode=ISOLATED
risk_*
cycle_*_timeout_seconds
```

Le navigateur n'implémente pas les règles de cohérence : quote/règlement, whitelist Risk,
unicité, levier, limites PERPETUAL, spread+slippage, FUTURE, etc. Ces règles restent dans Pydantic
et le Control Plane backend. L'UI n'offre que `SPOT` et `PERPETUAL` et fixe visuellement
`ISOLATED`, puis affiche les refus 422/409/503 du backend.

Les valeurs préremplies sont un profil de saisie opérateur ; elles ne sont pas présentées comme des
valeurs par défaut `Settings` serveur, dont la majorité est volontairement `None`.

## 8. Activation / reprise / moteur

```text
POST /campaigns/{id}/activate   # frais
POST /campaigns/{id}/resume     # explicite
POST /engine/run-cycle
POST /engine/start
POST /engine/stop
```

Une activation/reprise pendant `RUNNING`, une activation fraîche d'une Campaign déjà exécutée ou
une reprise sans run parent restent refusées côté backend. L'UI affiche le conflit ; elle ne le
contourne pas.

Le polling du cockpit relit toutes les 10 secondes, lorsque l'onglet est visible :

```text
strategies
campaigns
campaigns/active
paper-runs (100 derniers)
engine
```

Fermer ou redémarrer Next.js n'envoie jamais `stop` au moteur backend.

## 9. Identités et recovery visibles

Le cockpit expose les identités fournies par le backend :

```text
strategy_prompt_digest
configuration_digest
experiment_protocol_version
experiment_digest
campaign_id
paper_run_id
resumed_from_paper_run_id
recovery_version
```

Aucun digest n'est recalculé dans le navigateur.

## 10. Erreurs et confidentialité

`ApiError` conserve le statut HTTP et un message opératoire. Pour les erreurs Pydantic, le client
n'affiche que `loc` + `msg` et n'inclut pas le champ `input`, afin d'éviter de refléter une valeur de
formulaire potentiellement sensible.

Le panneau Control Plane ne référence ni `localStorage`, ni `sessionStorage`, ni nom de secret
serveur. Les secrets restent exclusivement dans la configuration backend.

## 11. Persistence backend

Schéma canonique :

```text
strategies
strategy_revisions
campaigns
paper_runs.campaign_id NULLABLE
paper_runs.resumed_from_paper_run_id
```

Aucune migration n'est ajoutée par 18.9B.

## 12. Validation

Le patch frontend a fait l'objet d'un harness source et d'un typecheck ciblé avec stubs. Les
commandes canoniques `pnpm lint`, `pnpm typecheck` et `pnpm build` doivent être rejouées dans le
repository local avec les dépendances installées avant intégration.
