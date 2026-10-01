# 10 — Décisions et changelog

> Les décisions détaillées plus anciennes restent dans Git. Ce document conserve les principes actifs, les décisions structurantes récentes et les éléments nécessaires à la reprise.

## Principes actifs

Un seul Agent stratégique, Risk autorité finale, aucune sortie LLM directe vers Broker/Kraken, SPOT sans vente d'actif non détenu, audit durable, no-look-ahead, backend indépendant du frontend, `HOLD` valide, aucun secret versionné et LIVE séparé.

Market Attention Radar reste strictement observationnel et ne prend aucune décision de trading.

## Référence courante

```text
HEAD GitHub audité : 5bff583b47acf2b3a2a112611c40e0046c78cc3e
Commit              : feat: make market attention radar kraken-only
Batch 38            : intégré
Batch 39            : intégré
```

## Changelog — 2026-10-01 — Batch 39 Radar Kraken sans IA

- correction de `docs/00_ETAT_ACTUEL.md`, qui pointait encore vers `c699e7c` et décrivait Batch 38 comme non intégré ;
- conservation du pipeline canonique `CandleStreamService` / OHLCV 5m ;
- conservation des horizons 5m / 15m / 1h / 4h et des caractéristiques Batch 38 ;
- maintien du niveau d'intérêt déterministe `LOW/MEDIUM/HIGH/VERY_HIGH` ;
- suppression du wiring OpenAI du Market Attention Radar ;
- suppression du chemin de recherche publique, de son cache, TTL, cooldown et budget ;
- suppression des décisions et compteurs de recherche Web du contrat API ;
- passage du contrat Radar à `market-attention-radar-v2` ;
- cockpit recentré sur intérêt, caractéristiques, raisons, liquidité, fraîcheur, qualité et erreurs Kraken ;
- conservation de `informative_only=True` ;
- aucune modification du Risk Engine, Broker, Agent stratégique ou politique d'exécution ;
- trades Kraken et carnet L2 explicitement reportés au Batch 40.

## ADR-291 — Préfiltrage déterministe Batch 38

**INTÉGRÉ dans `2776fc6`.**

Le Radar calcule des faits descriptifs Kraken avant toute éventuelle recherche externe. Les caractéristiques et le niveau d'intérêt ne sont pas des signaux de trading.

## ADR-292 — Politique Web Batch 38

**HISTORIQUE — SUPPLANTÉ PAR ADR-295.**

Le Batch 38 avait introduit budget, TTL et cooldown de recherche publique. Batch 39 supprime entièrement ce mécanisme du Radar.

## ADR-293 — Isolation du Radar

**ACTIF.**

Le module Market Attention ne dépend pas d'Agent, Risk, Broker ou Market Discovery. `informative_only=True` reste un invariant de modèle.

## ADR-294 — Modèle auxiliaire Radar

**CLOS / SANS OBJET.**

La question d'un modèle OpenAI auxiliaire distinct n'a plus lieu d'être puisque le Radar v2 n'utilise plus de LLM.

## ADR-295 — Market Attention Radar v2 est Kraken-only et déterministe

**INTÉGRÉ dans `5bff583`.**

Le Radar répond uniquement à la question : « quels marchés présentent actuellement un comportement suffisamment inhabituel ou intéressant pour mériter l'attention ? ». Il ne recherche plus d'explication narrative ou de news.

## ADR-296 — Suppression de la couche Public Attention

**INTÉGRÉ dans `5bff583`.**

`PublicAttentionResearcher`, `PublicAttentionSnapshot`, `PublicResearchDecision`, l'adaptateur OpenAI dédié et les métriques Web disparaissent du contrat courant. Aucun compteur artificiellement nul n'est conservé.

## ADR-297 — Contrat API Radar v2

**INTÉGRÉ dans `5bff583`.**

Le protocole `market-attention-radar-v2` expose directement l'activité Kraken, les caractéristiques, l'intérêt, les raisons, la liquidité, la qualité/fraîcheur et les diagnostics. Une rupture de contrat explicite est préférée au maintien de champs trompeurs.

## Points explicitement non décidés

- utilisation du Radar comme contexte de l'Agent stratégique ;
- réaction stratégique intra-bougie ;
- LIVE.
