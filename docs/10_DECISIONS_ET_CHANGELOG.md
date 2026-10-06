# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent disponibles dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les références nécessaires à la reprise.

## Principes actifs

Un seul Agent IA stratégique. Le Risk Engine déterministe conserve l'autorité finale. Aucune sortie LLM ne déclenche directement Broker/Kraken.

L'exécution courante est **PAPER uniquement** : SPOT et PERPETUAL linéaire selon l'univers intégré ; FUTURE daté non exécutable ; LIVE indisponible sans batch explicite.

Le Market Attention Radar priorise l'attention et fournit un univers/contexte causal au même Agent. Il ne décide jamais BUY/SELL/HOLD et n'a aucune autorité Risk/Broker.

La mémoire de thèse stratégique 50.1 reste structurée, causale, bornée et durable. L'observabilité 49.4/50.2 reste read-only et ne revient jamais dans le pipeline Agent/Risk/Broker.

Depuis 51.1, le même Agent peut utiliser `OPENAI` ou `OLLAMA` derrière `StructuredDecisionClient`, sans fallback. Depuis 51.1.1, le Structured Output est borné aux couples exacts `(symbol, market_type)` du cycle et Ollama utilise `think:false` sans exposition de `thinking`.

Depuis 51.2, les nouvelles Sessions peuvent persister leur provider stratégique. Les Campaigns historiques sans champ 51.2 restent compatibles et héritent du provider process.

Depuis 51.3, les appels Ollama possèdent une observabilité live best-effort dans les logs backend : départ, succès/échec, corrélation Session/cycle, `call_id`, tentative et latence, puis résumé BUY/SELL/HOLD du plan validé. Aucun contenu décisionnel brut ou secret n'est journalisé par cette couche.

Le Batch 51.4 proposé fait de la frontière UTC le trigger unique du scheduler CANDLE_CLOSE. Les données restent causales via `history_as_of()` dans le cycle ; le scheduler ne pré-résout plus Radar et ne bloque plus l'appel du runner sur les candles bootstrap. Le runtime normal rend INFO visibles pour Agent/Ollama/cadence tout en gardant `httpx`/`httpcore` et Kraken normal silencieux à INFO.

## Référence courante

```text
HEAD GitHub intégré audité        : 5d24185ac1eefe9be3c21e31e62831228c73fea9
Batch 51.1 intégré                : aeaf04f — feat: add local Ollama LLM provider
Batch 51.1.1 intégré              : 7e2ce28 — fix: harden causal Ollama decision contract
Batch 51.2 intégré                : 36491d4 — feat: configure LLM provider per session
Batch 51.3 intégré                : 5d24185 — feat: add live Ollama agent observability
Batch 51.4                        : patch livré — non intégré
```

---

## Changelog — 2026-10-07 — Batch 51.4 scheduler CANDLE_CLOSE / logging runtime — patch livré

### Diagnostic confirmé

`ScheduledTradingEngine._run_candle_close_loop()` appelait `CandleCloseReadinessGate.wait_until_ready()` avant le runner. Le gate vérifiait une candle finale exacte pour tous les marchés reçus et retournait `False` dès qu'un seul `history_as_of()` levait une exception.

`campaign_composition.py` lui fournissait `config.paper_executable_markets`. En Campaign dynamique Radar, ce tuple est le bootstrap ; l'univers réellement utilisé n'est résolu qu'ensuite dans `DynamicMarketTradingCycleRunner` à partir de Radar/Discovery, positions existantes et capacity. Le scheduler bloquait donc le cycle sur un proxy d'univers qu'il ne possède pas.

`CandleCloseReadinessGate.last_error_type` n'était pas remonté par la boucle. Une erreur provider telle que `Kraken payload validation failed operation=OHLC stage=OHLC_NUMERIC` pouvait ainsi produire des polls silencieux puis la suppression d'une frontière, sans appel Agent. Le run manuel fonctionne parce qu'il appelle directement le runner et contourne ce gate.

### Options comparées

1. **Tous les bootstrap markets prêts** : rejeté ; c'est précisément le couplage défectueux.
2. **Readiness sur l'univers Radar** : rejeté au niveau scheduler ; cela demanderait de dupliquer la résolution d'univers hors du runner canonique et créerait un risque de split-brain.
3. **Frontière temporelle comme trigger, disponibilité dans les services causaux** : adopté.

### Scheduler retenu

En CANDLE_CLOSE, `CandleCloseSchedule` fournit une frontière UTC strictement future. À la frontière, le scheduler démarre exactement un cycle canonique. Il ne requête plus Kraken/candles et ne résout aucun marché.

Après un cycle, la prochaine cible est recalculée depuis l'horloge. Un cycle long ou un réveil suffisamment tardif saute les frontières obsolètes au lieu de produire un catch-up burst.

`CandleCloseReadinessGate` reste présent uniquement comme helper de diagnostic/test sur un ensemble de marchés explicitement connu ; il n'est plus composé dans le scheduler Campaign.

### Causalité préservée

`CandleStreamService.history_as_of()` reste l'autorité de disponibilité temporelle : `open_time`, `close_time`, `updated_at`, finalité et backfill sont tous filtrés relativement à `as_of`. Retirer le gate pré-cycle ne permet donc aucune lecture future.

La disponibilité reste interprétée par les services consommateurs : le contexte multi-timeframe peut rester `AVAILABLE`, `PARTIAL` ou `MISSING`; une erreur technique provider produit un échec canonique auditable. Aucun fallback de donnée ou de marché n'est introduit, et la prochaine tentative automatique reste bornée par la politique de frontières du scheduler.

### Observabilité scheduler

Le scheduler journalise de manière bornée :

```text
scheduler_next_close
scheduler_boundary_reached
scheduler_readiness_validated mode=TEMPORAL_ONLY causal_data=DELEGATED_TO_CYCLE
scheduler_cycle_started trigger=AUTO_CANDLE_CLOSE
scheduler_cycle_completed
scheduler_boundary_skipped reason=SCHEDULER_LATE|CYCLE_ELAPSED
```

Il n'existe plus de polling readiness dans le chemin production ; aucun log à 0,5 s ne peut donc spammer le terminal.

### Logging runtime normal

`create_app()` appelle une configuration de logging idempotente. Avec `log_level=INFO` :

- `ai_spot_trader.agent.ollama` : INFO ;
- `ai_spot_trader.agent.planner` : INFO ;
- `ai_spot_trader.trading.cadence` : INFO ;
- `httpx` / `httpcore` : WARNING ;
- `ai_spot_trader.integrations.kraken` : WARNING.

Les warnings/errors Kraken restent visibles ; les requêtes normales Kraken ne sont pas promues à INFO. Aucun prompt, payload brut, réponse LLM brute, secret ou CoT n'est ajouté.

### Timeouts Ollama

Le HEAD audité utilise un défaut transport Ollama de 60 s tandis que le configurateur initialisait le timeout Agent à 35 s. La validation backend 51.2 refusait déjà `Agent <= transport`, mais l'UX pouvait créer cette combinaison incohérente avant soumission.

Le contrat backend reste inchangé : `cycle_agent_timeout_seconds` doit être strictement supérieur au timeout transport Ollama effectif. Le cockpit ajoute une recommandation dérivée `2 × transport` uniquement lorsque le passage vers Ollama rencontre une enveloppe Agent absente/invalide/incompatible. Ainsi le défaut 60 s propose 120 s sans coder en dur un couple 120/300. Une valeur Agent déjà supérieure est conservée. Cette recommandation ne garantit pas le budget d'une tool-loop multi-appels.

### Validation dans l'environnement ChatGPT

```text
python -m py_compile (6 fichiers Python)                    : PASS
pytest scheduler dans harness isolé                         : PASS — 26/26
pytest configuration logging runtime                        : PASS — 2/2
node tests session-config 51.2 + 51.4                       : PASS — 11/11
parse/transpile TypeScript ciblé session-config + TSX       : PASS
contrôle espaces finaux / arborescence de livraison         : PASS
```

La suite repository complète n'a pas été exécutée dans cet environnement, faute de checkout complet disponible. Elle reste obligatoire localement avec `pytest`, `pnpm typecheck`, `pnpm test`, `git diff --check` et un smoke réel Ollama CANDLE_CLOSE.

## ADR-398 — CANDLE_CLOSE est un trigger temporel, pas un gate de disponibilité multi-marchés

**ADOPTÉ — patch 51.4.** Le scheduler possède le temps ; les services du cycle possèdent les données et appliquent la causalité via `history_as_of()`.

## ADR-399 — La résolution de l'univers Radar reste exclusivement dans le runner dynamique

**ADOPTÉ — patch 51.4.** Le scheduler ne réplique ni Discovery, ni positions, ni capacity pour construire un pseudo-univers de readiness.

## ADR-400 — Le logging runtime est ciblé par namespace

**ADOPTÉ — patch 51.4.** Agent/Ollama/cadence sont visibles à INFO dans le lancement normal ; `httpx`/`httpcore` et Kraken restent à WARNING afin de conserver les anomalies sans bruit de requêtes normales.

## ADR-401 — La recommandation timeout Ollama est dérivée, la validation backend reste stricte

**ADOPTÉ — patch 51.4.** L'UI recommande `2 × transport` seulement lorsqu'elle doit corriger une enveloppe incompatible ; le backend conserve la règle de sûreté minimale `Agent > transport` et n'impose pas de couple fixe.

---

## Changelog — 2026-10-06 — Batch 51.3 observabilité live Ollama — intégré `5d24185`

### Diagnostic confirmé

L'audit LLM existant permettait de consulter les appels terminés, et 51.2 corrélait déjà `session_id` et `cycle_id`, mais le transport Ollama ne produisait aucun signal live lisible pendant l'attente d'un `/api/chat`. Un cycle long pouvait donc être impossible à distinguer d'une absence complète d'appel Agent depuis le terminal backend.

### Architecture retenue

Aucun système d'audit parallèle n'est ajouté. `OllamaStructuredDecisionClient` lit le `llm_audit_context` déjà actif et utilise le `logging` Python existant.

Chaque tentative HTTP réelle reçoit un `call_id` éphémère propre au tour Ollama logique et un numéro `attempt` :

```text
llm_request_started   provider=OLLAMA model=... session_id=... cycle_id=... call_id=... attempt=...
llm_request_succeeded provider=OLLAMA model=... session_id=... cycle_id=... call_id=... attempt=... latency_ms=...
llm_request_failed    provider=OLLAMA model=... session_id=... cycle_id=... call_id=... attempt=... error_type=... latency_ms=...
```

Un retry conserve le même `call_id` et incrémente `attempt`. Un nouveau tour de tool loop crée un nouveau `call_id`. Les warnings/errors de retry historiques restent émis par `ai_spot_trader.retry`; leur comportement n'est pas modifié.

Le succès live n'est journalisé qu'après validation de l'enveloppe provider Ollama (`JSON object`, `done=true`). Un corps invalide ou incomplet est donc visible comme `llm_request_failed` avec `LLMProviderError`.

### Résumé stratégique

Le wrapper canonique `StrategicThesisContextDecisionProvider` journalise, après retour réussi du delegate stratégique et donc après construction/validation du `CycleDecisionPlan`, uniquement les compteurs d'actions :

```text
agent_plan_completed session_id=<uuid> cycle_id=<uuid> decisions=6 buy=0 sell=0 hold=6
```

Ce log permet d'identifier immédiatement un cycle sans trade parce que l'Agent a proposé uniquement HOLD. Il ne journalise ni rationale, ni thèse détaillée, ni réponse brute.

### Confidentialité et isolation

Les nouveaux logs ne contiennent jamais le prompt, les messages, la réponse brute, `thinking`, l'URL Ollama, les erreurs transport brutes, les clés ou autres secrets. Seules des métadonnées opérationnelles bornées sont émises.

Les helpers de logging sont best-effort et absorbent leurs propres erreurs. Une panne du handler de logging ne modifie ni la réponse Ollama, ni les retries, ni le plan stratégique, ni Risk/Broker.

### Couverture de tests

Le test 51.3 dédié couvre : ordre start/success, latence, corrélation Session/cycle/modèle, timeout/réseau/provider error, absence de prompt/réponse brute/`thinking`/secret/URL, retries avec `call_id` stable et `attempt` croissant, tool rounds avec `call_id` distincts, résumé BUY/SELL/HOLD et neutralité d'une panne de logging.

L'absence de fallback Ollama → OpenAI reste également couverte par les tests 51.1.1/51.2 existants ; aucun code de sélection provider n'est modifié dans 51.3.

### Validation dans l'environnement ChatGPT

```text
python -m py_compile fichiers Python 51.3            : PASS
pytest ciblé 51.3 dans un harness isolé              : PASS — 8/8
contrôle des espaces finaux des fichiers livrés       : PASS
```

La suite backend repository complète, `pnpm typecheck`, `pnpm test`, `git diff --check` sur le vrai checkout et le smoke Ollama réel restent des validations locales obligatoires.

## ADR-395 — L'observabilité live Ollama reste transport-level et best-effort

**ADOPTÉ — intégré 51.3.** Les logs live s'appuient sur le transport canonique et `llm_audit_context`; aucune nouvelle persistance ni voie décisionnelle n'est créée.

## ADR-396 — `call_id` est éphémère et les retries réutilisent le même identifiant

**ADOPTÉ — intégré 51.3.** Un appel logique Ollama conserve son `call_id` entre tentatives et incrémente `attempt`; un nouveau round/tool loop obtient un nouveau `call_id`. Rien n'est persisté pour ce besoin opérateur.

## ADR-397 — Le résumé BUY/SELL/HOLD est émis uniquement après validation du plan

**ADOPTÉ — intégré 51.3.** Le résumé est dérivé du `CycleDecisionPlan` déjà retourné par le provider canonique. Il ne peut ni créer ni transformer une décision.

---

## Changelog — 2026-10-06 — Batch 51.2 provider LLM par Session — intégré `36491d4`

### Diagnostic confirmé

Le choix du transport stratégique restait global : `campaign_composition.py` lisait `settings.llm_provider`, tandis que `CampaignConfiguration` ne persistait que `llm_model`. Le modèle/timeout Ollama provenaient également de `Settings`.

La persistence Campaign stocke déjà un JSON canonique avec digest et sait charger des champs optionnels historiques absents. Aucun changement de schéma SQL n'est donc nécessaire.

### Architecture retenue

`CampaignConfiguration` ajoute de façon rétrocompatible :

```text
llm_provider: OPENAI | OLLAMA | null
ollama_model: string | null
ollama_timeout_seconds: positive float | null
```

Les trois champs sont exclus du payload canonique quand ils valent `null`. Une Campaign historique reste donc byte-for-byte équivalente au niveau JSON canonique utile au digest.

La résolution est centralisée :

```text
provider explicite Campaign -> provider Campaign
provider absent legacy       -> Settings.llm_provider
```

Le provider process n'écrase jamais un choix 51.2 explicite.

### Absence de fallback

```text
Campaign OLLAMA -> Ollama ou erreur
Campaign OPENAI -> OpenAI ou erreur
```

Une Campaign Ollama peut fonctionner sans clé OpenAI. Une Campaign OpenAI sans clé échoue fermée. La présence d'une clé OpenAI n'autorise aucun fallback d'une Campaign Ollama.

### Timeouts

`ollama_timeout_seconds` borne un appel transport. `cycle_agent_timeout_seconds` borne le stade Agent complet. Le contrat refuse une Campaign Ollama lorsque le timeout Agent est inférieur ou égal au timeout transport effectif. Cette garde ne prétend pas garantir le budget d'une boucle multi-appels/tools.

### Compatibilité legacy

- ancienne Campaign : `llm_provider`, `ollama_model`, `ollama_timeout_seconds` restent absents ;
- digest historique préservé ;
- runtime legacy utilise les valeurs process ;
- édition frontend legacy affiche « hérité du runtime » et ne force pas OpenAI ;
- duplication de Session réutilise le snapshot source existant ;
- nouvelle Session 51.2 : provider explicite requis par le contrat API.

### Operator Chat

Le chat opérateur reste OpenAI-only dans ce batch. Il est composé seulement lorsque le provider **effectif de la Campaign** est OpenAI. Aucune voie OpenAI cachée n'est créée pour une Campaign Ollama.

### UX

La surface canonique `SimpleConfigurator` expose OpenAI/Ollama, Luna/Sol sous OpenAI, modèle local et timeout transport sous Ollama, et conserve `cycle_agent_timeout_seconds` dans les paramètres avancés avec une explication de portée.

### Validation dans l'environnement ChatGPT

```text
python -m py_compile fichiers Python 51.2                       : PASS
node --test --experimental-strip-types session-config-batch51_2.test.mjs : PASS — 9/9
```

Après intégration locale, la validation utilisateur communiquée pour 51.2 est : suite backend complète PASS, `pnpm typecheck` PASS et frontend `101/101` PASS. Le smoke réel Ollama `qwen3.5:9b` a confirmé un cycle `COMPLETED`, audit `provider=OLLAMA`, `status=SUCCESS`, corrélation Session/cycle et aucun fallback OpenAI.

## ADR-390 — Le provider explicite Campaign est prioritaire sur le provider process

**ADOPTÉ — intégré 51.2.** `Settings.llm_provider` reste uniquement la valeur de compatibilité pour les snapshots legacy sans `llm_provider`.

## ADR-391 — Les champs 51.2 sont additifs et exclus lorsqu'ils sont null

**ADOPTÉ — intégré 51.2.** Cette forme conserve le payload et le digest des Campaigns historiques sans réécriture/migration.

## ADR-392 — `ollama_base_url` et les secrets restent process-level

**ADOPTÉ — intégré 51.2.** La Campaign porte le choix opérateur provider/modèle/budget transport, pas l'adresse de l'infrastructure ni les secrets.

## ADR-393 — Aucun fallback inter-provider n'est autorisé

**ADOPTÉ — intégré 51.2.** Un provider explicite défaillant produit une erreur du provider choisi.

## ADR-394 — Le chat opérateur suit le provider effectif sans portage Ollama

**ADOPTÉ — intégré 51.2.** Chat présent pour Campaign OpenAI, absent pour Campaign Ollama. Aucun second Agent.

---

## Changelog — 2026-10-06 — Batch 51.1.1 durcissement du contrat Ollama — intégré `7e2ce28`

Le schema multi-marché est désormais généré depuis les couples causaux exacts de `CycleDecisionPlanInput.market_states`. BUY/SELL conservent une quantité strictement positive, HOLD conserve `null`. Pydantic et le contrôle métier post-schema restent fail-closed.

Les appels Ollama structurés utilisent `think:false`; `message.content` reste la seule sortie décisionnelle et toute clé `thinking` reçue est retirée de l'audit public. `LLM audit SUCCESS` reste un état provider/transport, distinct du statut Agent/Risk/Broker.

Smoke réel validé après intégration : `OLLAMA / qwen3.5:9b`, OpenAI key absente, cycle `COMPLETED`, aucune failure, audit `provider=OLLAMA`, aucun appel OpenAI, aucun `thinking` exposé.

ADR actifs : `ADR-387` à `ADR-389`.

---

## Changelog — 2026-10-06 — Batch 51.1 provider LLM local Ollama — intégré `aeaf04f`

`LLMProviderKind` porte `OPENAI|OLLAMA`. `LLMModel` reste Luna/Sol ; le modèle Ollama est une chaîne séparée. `OllamaStructuredDecisionClient` réutilise la frontière `StructuredDecisionClient`, les validateurs et les tools read-only existants. Aucun fallback Ollama vers OpenAI.

Le choix provider était process/runtime dans 51.1 ; 51.2 ajoute la persistance par Session sans invalider ce comportement legacy.

ADR actifs : `ADR-381` à `ADR-386`.

---

## Changelog — Batch 50.2 observabilité des thèses stratégiques — intégré `e5887da`

Endpoint read-only dédié `/api/v1/strategic-theses`, dérivé des faits persistés et de la lineage PAPER. Les états futurs ne requalifient jamais une révision passée. Une proposition non activée reste distincte d'une thèse active. Le cockpit ne reconstruit aucune stratégie.

ADR actifs : `ADR-377` à `ADR-380`.

## Changelog — Batch 50.1 mémoire de thèse stratégique — intégré `ebb859c4`

Snapshot des thèses actives dans les cycles `COMPLETED`, révisions dans le plan du même Agent, activation uniquement après exposition économique réelle, legacy explicitement `UNAVAILABLE_LEGACY`, aucun ordre automatique dérivé du statut de thèse.

ADR actifs : `ADR-371` à `ADR-376`.

## Changelog — Batches 49.1 à 49.4 — intégrés

- 49.1 : PERPETUAL PAPER linéaire sous contrôle Risk ;
- 49.2 : Radar shortlist vers univers candidat Agent ;
- 49.3 : contexte Radar/Analytics causal ;
- 49.4 : observabilité décisions/performance PAPER read-only.

Les décisions détaillées et les validations historiques restent disponibles dans Git et dans `docs/47_5_MULTI_ANALYTICS_RANKING.md`, `docs/48_OBSERVABILITE_RANKING_ANALYTICS.md`, ainsi que les documents 49.x/50.x correspondants.
