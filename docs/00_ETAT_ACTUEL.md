# 00 — État actuel

## Référence intégrée GitHub

```text
Repository          : Ax-07/AI-Spot-Trader
Branche             : main
HEAD GitHub observé : b2193654ed3ba9db890c6129545acd90e238b0f1
Commit              : feat: add adaptive statistical radar baseline
```

Le **Batch 46 et son correctif de compatibilité 46.1 sont intégrés** dans `main` via `b219365`. Les documents qui les présentaient encore comme « proposés » étaient obsolètes et sont réconciliés par la préparation du Batch 47.1.

Décisions désormais intégrées :

```text
Batch 46 => intégré via b219365
ADR-328  => ADOPTÉ
ADR-329  => ADOPTÉ
ADR-330  => ADOPTÉ
```

L'intégration GitHub confirme la présence du code. Elle ne permet pas d'inventer une suite locale complète non observée.

## État intégré — Batch 46

Le Market Attention Radar reste `market-attention-radar-v6`, strictement informatif, déterministe, causal et read-only.

Pipeline intégré :

```text
catalogue Kraken
-> scope SPOT / PERPETUAL / ALL
-> métadonnées / filtre capitalisation
-> rotation OHLCV et volume 24h
-> activité adaptative / tendance / liquidité / microstructure canonique
-> pool Structure borné et rotatif
-> cache Structure causal
-> filtres tendance / Structure
-> shortlist finale bornée
-> cockpit
```

La Market Structure Batch 45 reste inchangée : timeframes natives `5m / 15m / 1h / 4h`, candles finalisées, pivots confirmés, événements `BOS / CHOCH` descriptifs et filtres `UNKNOWN` fail-closed.

Le Batch 46 utilise une baseline robuste propre à chaque marché et horizon :

```text
baseline = médiane des périodes historiques causales
MAD      = médiane(|x - baseline|)
dispersion robuste = 1,4826 * MAD
score adaptatif = (courant - baseline) / dispersion robuste
```

La cible par défaut est `12` périodes. Le plancher de compatibilité à `6` périodes est intégré : H4 utilise le plus grand nombre causal de périodes complètes disponible entre le plancher et la cible. `MAD == 0` ne produit aucun pseudo-score infini : le Radar bascule explicitement vers `LEGACY_RATIO_FALLBACK` lorsque le ratio est exploitable, sinon `UNAVAILABLE`.

Le contrat v6 reste additif et les sources volume 24h/liquidité Batch 43.2/44 ne sont pas modifiées par le Batch 46.

## Batch 47.1 — patch préparé, non intégré

Le Batch 47.1 construit le socle canonique des données Futures instantanées du Radar :

```text
1 appel public bulk Kraken Futures /tickers
-> volumeQuote existant
-> Open Interest courant
-> fundingRate courant brut
-> fundingRatePrediction Kraken
-> markPrice / indexPrice
-> serverTime
```

Le client canonique `KrakenDerivativesPublicClient` expose désormais dans le patch une méthode publique `fetch_tickers()` et un modèle `KrakenDerivativesTickerSnapshot`. `KrakenAttentionCatalogue` n'accède plus directement à `_derivatives._get_json()`.

Le même snapshot alimente le volume 24h PERP, la référence de liquidité PERP et un nouveau `PerpetualTickerContext` descriptif. Aucun second client Futures et aucune requête bulk séparée pour OI/funding ne sont introduits.

Le contexte Futures est additif au candidat v6 et porte un statut explicite :

```text
AVAILABLE / PARTIAL / NOT_APPLICABLE / TECHNICAL_ERROR
```

Il ne modifie ni `interest_level`, ni `candidate_limit`, ni ranking canonique/Structure, ni baseline adaptative Batch 46.

Le cockpit ajoute uniquement dans le détail des candidats PERPETUAL une section `Futures Kraken` ; la ligne principale reste inchangée. Open Interest et funding brut/prédit n'utilisent aucun suffixe ou format `%` non démontré.

Voir `docs/47_1_FONDATIONS_FUTURES_TICKER.md`.

## Validation connue

Batch 46 — validations observées avant intégration :

```text
Python py_compile backend ciblé                 : PASS
exécution helpers robustes extraits du code     : PASS
frontend market-attention.test.mjs ciblé        : PASS — 19/19
typecheck TypeScript ciblé market-attention.ts  : PASS
parse TypeScript/TSX ciblé cockpit              : PASS
```

Validation locale de la première livraison Batch 46 : frontend `pnpm typecheck` PASS, `pnpm test` PASS 65/65, `git diff --check` sans erreur ; backend `pytest -q` avait révélé 7 régressions de shortlist dues à l'exigence rigide de 12 périodes H4. Le code intégré `b219365` contient le correctif 46.1 avec plancher à 6 périodes. Aucune exécution locale complète post-commit n'est inventée ici.

Batch 47.1 — validations exécutées par ChatGPT sur le patch préparé :

```text
Python py_compile sources/tests Python modifiés        : PASS
pytest parser/client bulk vrai module + dépendances stub : PASS — 23/23
smoke local catalogue partagé                          : PASS
frontend market-attention.test.mjs ciblé               : PASS — 22/22
typecheck ciblé market-attention.ts                    : PASS
parse/transpile ciblé market-attention-dock.tsx : PASS
```

Validation locale utilisateur du Batch 47.1 après extraction : `pnpm typecheck` PASS, `pnpm test` PASS **68/68**, `git diff --check` sans erreur (uniquement des avertissements LF/CRLF). La suite backend `pytest -q` a atteint 100 % avec **3 échecs, tous dans le nouveau fichier de tests Batch 47.1**, avant l'exécution de la logique testée : les scénarios construisaient un `MarketAttentionFilters` générique alors que `StructureAwareFilteredMarketAttentionRadar.set_filters()` attend depuis le Batch 45 un `StructureAwareMarketAttentionFilters`. Le correctif 47.1.1 remplace uniquement le type de filtre des tests ; aucune logique de production n'est élargie. La suite backend complète doit être relancée après extraction du correctif.
