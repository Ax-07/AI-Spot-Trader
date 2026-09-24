# 10 — Décisions et changelog

> Les décisions détaillées antérieures restent dans Git. Ce document conserve les principes actifs
> et les décisions récentes nécessaires à la reprise.

## Principes historiques conservés

Un seul Agent stratégique, PAPER, Risk autorité finale, aucune sortie LLM/tool directe vers
Broker/Risk, SPOT sans short/levier, PERPETUAL avec protections déterministes, audit durable,
no-look-ahead, backend indépendant du frontend, HOLD valide, aucun secret versionné et LIVE séparé.

## Référence après Batch 18.13

```text
HEAD main courant            : 4cb0567cae6ff100c5ad9ad1df9e3f68b8f7ffd7
Commit fonctionnel 18.13     : 4cb0567cae6ff100c5ad9ad1df9e3f68b8f7ffd7
Batch 18.13                  : INTÉGRÉ / VALIDÉ
```

## Décisions historiques toujours actives

- ADR-173 à ADR-181 : StrategyRevision immuable, contrat Agent protégé, digests, Campaign snapshot,
  identité expérimentale v4, distinction Campaign/paper_run, runtime backend et recovery ;
- ADR-182 à ADR-188 : frontend client du Control Plane, API unique, validators backend, preview
  canonique, pas de draft sensible persistant, activation et reprise distinctes ;
- ADR-189/190 : adaptation JSON `market_type` à la frontière API et typing sans changement runtime ;
- ADR-191/192 : Vue d'ensemble comme surface principale et réutilisation des panneaux canoniques ;
- ADR-193 à ADR-195 : aide progressive, règles métier au backend et guide opérateur versionné ;
- ADR-196 à ADR-200 : navigation orientée tâches, orchestration des objets canoniques, profils Risk UX,
  absence de comptabilité SPOT parallèle et bloc `Action suivante` comme porte d'entrée.

## Décisions Batch 18.13 — intégrées

### ADR-201 — Utiliser `next-themes` comme couche unique de sélection de thème

**INTÉGRÉE.** Le cockpit supporte `light`, `dark` et `system` via `next-themes`. Le thème est
appliqué par classe sur `<html>`, persiste côté navigateur et ne crée aucun système parallèle à
Tailwind/shadcn.

### ADR-202 — Centraliser les contrastes dans des tokens sémantiques

**INTÉGRÉE.** Les variantes partagées utilisent des couples explicites :
`primary/primary-foreground`, `secondary/secondary-foreground`, `destructive`, `success`, `warning`,
`info`, `muted`, `border`, `input`, `ring` et tokens de sidebar. Les écrans métier consomment ces
tokens autant que possible.

Les anciennes utilities rouge/ambre/vert/bleu encore présentes dans les panneaux avancés reçoivent
une compatibilité dark globale afin d'éviter une duplication de patch écran par écran.

### ADR-203 — Ne jamais encoder un état métier par la couleur seule

**INTÉGRÉE.** Les valeurs financières conservent un signe `+`/`−`; BUY/SELL/HOLD et
ALLOW/MODIFY/REJECT restent textuels ; l'Historique affiche explicitement `Exécuté` ou
`Non exécuté`. La couleur reste un renfort visuel et non l'unique information.

### ADR-204 — Moderniser sans réintroduire de complexité opérateur

**INTÉGRÉE.** La navigation 18.12 reste inchangée. La modernisation porte sur hiérarchie,
espacements, rayons, bordures, ombres légères, focus et états interactifs. Aucun dashboard parallèle,
aucun effet néon et aucune logique de trading ne sont ajoutés.

## Changelog — 2026-09-24 — Batch 18.13 intégré / validé

Commit fonctionnel : `4cb0567cae6ff100c5ad9ad1df9e3f68b8f7ffd7`
(`feat: add dark mode and modernize cockpit UI`).

- ajout de `next-themes` et d'un `ThemeProvider` ;
- sélecteur Clair / Sombre / Système dans la barre supérieure et Réglages ;
- nouveaux tokens light/dark et sémantiques ;
- Button/Badge/Card modernisés et contrastés ;
- Accueil modernisé avec `Action suivante` dominante ;
- P&L signé en plus de la couleur ;
- Positions et Historique modernisés ;
- états d'exécution explicites dans Historique ;
- compatibilité dark des états historiques dans les vues avancées ;
- aucun changement backend.

Validation locale réellement exécutée avec succès avant commit/push : `pnpm install`, `pnpm lint`,
`pnpm typecheck`, `pnpm build`, `git diff --check` et `git status --short`. Le statut Git final après
commit/push était propre.
