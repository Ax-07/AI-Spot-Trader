# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent disponibles dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les références nécessaires à la reprise.

## Principes actifs

Un seul Agent IA stratégique. Le Risk Engine déterministe conserve l'autorité finale. Aucune sortie LLM ne déclenche directement Broker/Kraken.

L'exécution courante est **PAPER uniquement** : SPOT et PERPETUAL linéaire selon l'univers intégré ; FUTURE daté non exécutable ; LIVE indisponible sans batch explicite.

Le Market Attention Radar priorise l'attention et fournit un univers/contexte causal au même Agent. Il ne décide jamais BUY/SELL/HOLD et n'a aucune autorité Risk/Broker.

La mémoire de thèse stratégique 50.1 reste structurée, causale, bornée et durable. L'observabilité 49.4/50.2 reste read-only et ne revient jamais dans le pipeline Agent/Risk/Broker.

Depuis 51.1, le même Agent peut utiliser `OPENAI` ou `OLLAMA` derrière `StructuredDecisionClient`, sans fallback. Depuis 51.1.1, le Structured Output est borné aux couples exacts `(symbol, market_type)` du cycle et Ollama utilise `think:false` sans exposition de `thinking`.

Depuis 51.2, les nouvelles Sessions peuvent persister leur provider stratégique. Les Campaigns historiques sans champ 51.2 restent compatibles et héritent du provider process.

## Référence courante

```text
HEAD GitHub intégré audité        : 7e2ce2821660c9be7f5ffdfe053244d56fae7986
Batch 51.1 intégré                : aeaf04f — feat: add local Ollama LLM provider
Batch 51.1.1 intégré              : 7e2ce28 — fix: harden causal Ollama decision contract
Batch 51.2                        : patch livré — validation locale/intégration à faire
```

---

## Changelog — 2026-10-06 — Batch 51.2 provider LLM par Session — patch livré

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

`OPENAI_API_KEY`, secrets Kraken, `openai_base_url` et `ollama_base_url` restent des propriétés de `Settings`. `llm_model` reste Luna/Sol ; un modèle Ollama reste une chaîne indépendante.

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

La suite repository complète, `pnpm typecheck`, `pnpm test`, le smoke applicatif Ollama et `git diff --check` sur le vrai checkout restent des validations locales obligatoires.

## ADR-390 — Le provider explicite Campaign est prioritaire sur le provider process

**ADOPTÉ — patch 51.2.** `Settings.llm_provider` reste uniquement la valeur de compatibilité pour les snapshots legacy sans `llm_provider`.

## ADR-391 — Les champs 51.2 sont additifs et exclus lorsqu'ils sont null

**ADOPTÉ — patch 51.2.** Cette forme conserve le payload et le digest des Campaigns historiques sans réécriture/migration.

## ADR-392 — `ollama_base_url` et les secrets restent process-level

**ADOPTÉ — patch 51.2.** La Campaign porte le choix opérateur provider/modèle/budget transport, pas l'adresse de l'infrastructure ni les secrets.

## ADR-393 — Aucun fallback inter-provider n'est autorisé

**ADOPTÉ — patch 51.2.** Un provider explicite défaillant produit une erreur du provider choisi.

## ADR-394 — Le chat opérateur suit le provider effectif sans portage Ollama

**ADOPTÉ — patch 51.2.** Chat présent pour Campaign OpenAI, absent pour Campaign Ollama. Aucun second Agent.

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
