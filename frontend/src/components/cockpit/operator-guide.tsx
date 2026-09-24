import {
  Activity,
  AlertTriangle,
  Bot,
  BookOpenText,
  CircleDollarSign,
  Database,
  Gauge,
  Layers3,
  Play,
  RefreshCw,
  Settings2,
  ShieldCheck,
  WalletCards,
  Waves,
} from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type GuideSection = {
  id: string;
  label: string;
};

const GUIDE_SECTIONS: GuideSection[] = [
  { id: "demarrage", label: "Démarrage rapide" },
  { id: "architecture", label: "Architecture mentale" },
  { id: "strategie", label: "Strategies & revisions" },
  { id: "campaign", label: "Campaign & configuration" },
  { id: "marches", label: "SPOT & PERPETUAL" },
  { id: "activation", label: "Activation & moteur" },
  { id: "reprise", label: "Reprise après redémarrage" },
  { id: "lecture", label: "Décisions, Risk & performance" },
  { id: "erreurs", label: "Erreurs fréquentes" },
  { id: "glossaire", label: "Glossaire" },
];

const QUICK_START = [
  "Créer ou choisir une Strategy.",
  "Créer une StrategyRevision contenant le texte opérateur souhaité.",
  "Créer une Campaign à partir de cette révision.",
  "Choisir les marchés SPOT ou PERPETUAL à tester.",
  "Vérifier capital PAPER, modèle, coûts et paramètres Risk.",
  "Activer fraîchement la Campaign si elle n’a jamais été exécutée.",
  "Lancer un run-cycle pour un test isolé, ou Start pour la boucle backend.",
  "Observer la proposition Agent, le résultat Risk puis l’éventuel résultat PAPER.",
  "Utiliser Stop pour arrêter explicitement une boucle RUNNING.",
];

function GuideCard({
  icon,
  title,
  description,
  children,
}: {
  icon: ReactNode;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Card className="shadow-none">
      <CardHeader>
        <div className="flex items-start gap-3">
          <div className="rounded-xl border bg-muted/45 p-2.5 text-muted-foreground">{icon}</div>
          <div className="space-y-1">
            <CardTitle>{title}</CardTitle>
            {description ? <CardDescription>{description}</CardDescription> : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="text-sm leading-6 text-muted-foreground">{children}</CardContent>
    </Card>
  );
}

function Definition({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border p-4">
      <dt className="font-semibold text-foreground">{term}</dt>
      <dd className="mt-1 text-sm leading-6 text-muted-foreground">{children}</dd>
    </div>
  );
}

export function OperatorGuide() {
  return (
    <div className="mx-auto flex w-full max-w-[1580px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_280px]">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Aide intégrée
          </p>
          <h2 className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <BookOpenText className="size-5" /> Guide opérateur
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            Ce guide explique le cockpit du point de vue opérateur. Il décrit quoi configurer, quelle
            action déclenche quoi, et comment lire les décisions sans reproduire la logique du backend.
          </p>
        </div>

        <Card className="gap-3 py-4 shadow-none">
          <CardHeader className="px-4">
            <CardTitle className="text-sm">Périmètre actuel</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 px-4 text-xs text-muted-foreground">
            <div className="flex flex-wrap gap-2">
              <Badge tone="info">PAPER uniquement</Badge>
              <Badge>SPOT</Badge>
              <Badge tone="warning">PERPETUAL</Badge>
            </div>
            <p>LIVE n’est pas disponible dans ce périmètre et reste un projet séparé et ultérieur.</p>
          </CardContent>
        </Card>
      </div>

      <nav className="flex gap-2 overflow-x-auto rounded-xl border bg-background p-2" aria-label="Sections du guide">
        {GUIDE_SECTIONS.map((section) => (
          <a
            key={section.id}
            href={`#${section.id}`}
            className="min-w-max rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
          >
            {section.label}
          </a>
        ))}
      </nav>

      <section id="demarrage" className="scroll-mt-36">
        <Card className="border-foreground/15 shadow-none">
          <CardHeader>
            <CardTitle>Démarrage rapide — premier test PAPER</CardTitle>
            <CardDescription>
              Pour un premier essai, commence par un run-cycle isolé avant d’utiliser la boucle autonome.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {QUICK_START.map((step, index) => (
                <li key={step} className="flex gap-3 rounded-xl border bg-muted/15 p-4 text-sm leading-6">
                  <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-foreground text-xs font-bold text-background">
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </section>

      <section id="architecture" className="scroll-mt-36 space-y-4">
        <GuideCard
          icon={<Layers3 className="size-5" />}
          title="Architecture mentale"
          description="Le frontend contrôle et observe ; le backend exécute le moteur de trading."
        >
          <div className="grid gap-3 lg:grid-cols-7 lg:items-stretch">
            {[
              ["Marché / contexte", Waves],
              ["Agent IA", Bot],
              ["BUY / SELL / HOLD", Activity],
              ["Risk Engine", ShieldCheck],
              ["ALLOW / MODIFY / REJECT", Gauge],
              ["Broker PAPER", WalletCards],
              ["Ledger / audit / performance", Database],
            ].map(([label, Icon], index) => {
              const PipelineIcon = Icon as typeof Waves;
              return (
                <div key={String(label)} className="relative rounded-xl border bg-muted/20 p-3 text-center">
                  <PipelineIcon className="mx-auto size-4 text-foreground" />
                  <p className="mt-2 text-xs font-semibold text-foreground">{String(label)}</p>
                  {index < 6 ? (
                    <span className="mt-2 block text-[11px] text-muted-foreground lg:absolute lg:-right-3 lg:top-1/2 lg:mt-0 lg:-translate-y-1/2">
                      ↓
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
          <div className="mt-4 rounded-xl border border-foreground/15 bg-muted/30 p-4 text-foreground">
            <p className="font-semibold">L’IA propose. Le Risk Engine autorise, modifie ou refuse.</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Une sortie LLM ne devient jamais directement un ordre. Seul le chemin backend canonique
              peut produire un ExecutionIntent puis un fill PAPER.
            </p>
          </div>
        </GuideCard>
      </section>

      <section id="strategie" className="scroll-mt-36 grid gap-4 lg:grid-cols-2">
        <GuideCard
          icon={<Settings2 className="size-5" />}
          title="Strategy"
          description="L’identité durable que tu nommes et que tu peux archiver."
        >
          <p>
            La Strategy sert de conteneur logique. Son nom peut évoluer, mais le texte réellement utilisé
            par l’Agent n’est pas stocké directement sur cette identité.
          </p>
        </GuideCard>
        <GuideCard
          icon={<BookOpenText className="size-5" />}
          title="StrategyRevision"
          description="Une version immuable du texte opérateur."
        >
          <p>
            Chaque modification du prompt opérateur crée une nouvelle révision. Une Campaign référence
            une révision précise : elle ne change donc pas silencieusement si tu écris une nouvelle version.
          </p>
        </GuideCard>
      </section>

      <section id="campaign" className="scroll-mt-36 grid gap-4 xl:grid-cols-3">
        <GuideCard icon={<Database className="size-5" />} title="Campaign">
          <p>
            Une Campaign fige la StrategyRevision et la configuration structurelle du test : modèle,
            agressivité, cadence, capital, univers de marchés, coûts, paramètres Risk et délais.
          </p>
          <p className="mt-3">
            Pour changer un paramètre structurel, crée une nouvelle Campaign plutôt que d’éditer
            l’historique d’une expérience existante.
          </p>
        </GuideCard>
        <GuideCard icon={<Bot className="size-5" />} title="Configuration Agent">
          <p>
            Luna ou Sol sont sélectionnés dans la Campaign. L’agressivité guide le contexte stratégique,
            mais ne contourne jamais Risk. Le prompt opérateur provient de la StrategyRevision choisie.
          </p>
        </GuideCard>
        <GuideCard icon={<ShieldCheck className="size-5" />} title="Configuration Risk">
          <p>
            Les limites exposées dans le cockpit configurent le Risk Engine backend. Le frontend ne
            recalcule pas la validation : une Campaign invalide est refusée par l’API.
          </p>
        </GuideCard>
      </section>

      <section id="marches" className="scroll-mt-36 grid gap-4 lg:grid-cols-2">
        <GuideCard icon={<CircleDollarSign className="size-5" />} title="SPOT">
          <p>
            Achat et vente d’actifs détenus dans le portefeuille PAPER. Pas de short, pas de marge et
            pas de levier. Une vente d’un actif non détenu reste impossible.
          </p>
        </GuideCard>
        <GuideCard icon={<Gauge className="size-5" />} title="PERPETUAL linéaire">
          <p>
            Le test PAPER peut ouvrir une exposition dérivée selon les contraintes backend. La marge
            est <strong className="text-foreground">ISOLATED</strong> et le levier PAPER est une
            configuration déterministe, jamais une décision libre du LLM.
          </p>
          <p className="mt-3">
            Le Risk Engine contrôle notamment les plafonds de levier, de position et d’exposition totale.
          </p>
        </GuideCard>
      </section>

      <section id="activation" className="scroll-mt-36 grid gap-4 xl:grid-cols-3">
        <GuideCard icon={<Play className="size-5" />} title="Activation fraîche">
          <p>
            À utiliser pour démarrer une Campaign qui n’a pas encore de run à reprendre. L’activation
            crée un nouveau contexte d’exécution PAPER explicite.
          </p>
        </GuideCard>
        <GuideCard icon={<Activity className="size-5" />} title="run-cycle">
          <p>
            Exécute un seul cycle, puis le moteur reste STOPPED. C’est le choix conseillé pour valider
            une nouvelle configuration étape par étape.
          </p>
        </GuideCard>
        <GuideCard icon={<Play className="size-5" />} title="Start / Stop">
          <p>
            Start lance la boucle autonome côté backend à la cadence de la Campaign. Stop envoie l’arrêt
            explicite. Fermer ou recharger le frontend n’arrête pas le moteur.
          </p>
        </GuideCard>
      </section>

      <section id="reprise" className="scroll-mt-36">
        <GuideCard
          icon={<RefreshCw className="size-5" />}
          title="Reprise après redémarrage backend"
          description="La reprise n’est jamais silencieuse."
        >
          <p>
            Après un redémarrage backend, le cockpit peut afficher un moteur UNAVAILABLE tant qu’aucune
            Campaign n’a été activée ou reprise. Pour continuer une expérience existante, sélectionne la
            Campaign et un paper run compatible, puis utilise la commande de reprise explicite.
          </p>
          <p className="mt-3">
            La reprise crée un nouveau <code className="rounded bg-muted px-1.5 py-0.5 text-xs">paper_run_id</code>
            lié au précédent et restaure le ledger durable selon le mécanisme de recovery canonique.
          </p>
        </GuideCard>
      </section>

      <section id="lecture" className="scroll-mt-36 grid gap-4 xl:grid-cols-3">
        <GuideCard icon={<Bot className="size-5" />} title="Décision Agent">
          <p>
            BUY et SELL sont des propositions stratégiques. HOLD signifie que l’Agent choisit de ne pas
            proposer de trade pour ce cycle ; c’est une issue normale et elle reste journalisée.
          </p>
        </GuideCard>
        <GuideCard icon={<ShieldCheck className="size-5" />} title="Résultat Risk">
          <p>
            <strong className="text-foreground">ALLOW</strong> conserve la proposition compatible,
            <strong className="text-foreground"> MODIFY</strong> l’ajuste pour respecter les limites,
            et <strong className="text-foreground">REJECT</strong> refuse l’exécution.
          </p>
        </GuideCard>
        <GuideCard icon={<WalletCards className="size-5" />} title="Positions & performance">
          <p>
            Les positions, le ledger et les analytics viennent du backend. Lis toujours le P&L net avec
            les frais, le spread et le slippage ; le P&L brut ne représente pas le résultat final du test.
          </p>
        </GuideCard>
      </section>

      <section id="erreurs" className="scroll-mt-36">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="size-4" /> Erreurs fréquentes
            </CardTitle>
            <CardDescription>Quelques situations normales à reconnaître avant de modifier la configuration.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <details className="group rounded-xl border p-4">
              <summary className="cursor-pointer font-medium">Le moteur affiche UNAVAILABLE</summary>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Après un restart backend, aucune Campaign n’est reprise automatiquement. Active une
                Campaign fraîche ou utilise la reprise explicite d’un run compatible.
              </p>
            </details>
            <details className="group rounded-xl border p-4">
              <summary className="cursor-pointer font-medium">run-cycle ou Start est désactivé</summary>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Vérifie qu’un runtime Campaign est configuré. run-cycle n’est pas disponible pendant
                RUNNING ; Start n’est pas relancé si la boucle est déjà active.
              </p>
            </details>
            <details className="group rounded-xl border p-4">
              <summary className="cursor-pointer font-medium">L’Agent a proposé BUY/SELL mais aucun fill n’apparaît</summary>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Regarde le résultat Risk. MODIFY peut changer la quantité et REJECT bloque l’exécution.
                Une erreur technique peut aussi interrompre le cycle avant le Broker PAPER.
              </p>
            </details>
            <details className="group rounded-xl border p-4">
              <summary className="cursor-pointer font-medium">Le P&L brut paraît meilleur que le P&L net</summary>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                C’est attendu : le P&L net prend en compte les coûts PAPER configurés, notamment frais,
                spread et slippage.
              </p>
            </details>
          </CardContent>
        </Card>
      </section>

      <section id="glossaire" className="scroll-mt-36">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Glossaire</CardTitle>
            <CardDescription>Les termes les plus importants du cockpit.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <Definition term="Strategy">Identité durable d’une stratégie opérateur.</Definition>
              <Definition term="StrategyRevision">Version immuable du texte opérateur.</Definition>
              <Definition term="Campaign">Snapshot immuable d’une expérience et de sa configuration.</Definition>
              <Definition term="paper run">Session d’exécution PAPER d’une Campaign, avec son propre identifiant.</Definition>
              <Definition term="HOLD">Décision Agent de ne pas proposer de trade pour ce cycle.</Definition>
              <Definition term="ALLOW">Risk autorise la proposition compatible.</Definition>
              <Definition term="MODIFY">Risk ajuste la proposition avant exécution.</Definition>
              <Definition term="REJECT">Risk refuse l’exécution de la proposition.</Definition>
              <Definition term="STOPPED">Runtime disponible mais boucle autonome arrêtée.</Definition>
              <Definition term="RUNNING">Boucle backend autonome active.</Definition>
              <Definition term="UNAVAILABLE">Aucun runtime Campaign contrôlable n’est actuellement actif.</Definition>
              <Definition term="ISOLATED">Marge PERPETUAL isolée au niveau de la position dans le périmètre PAPER actuel.</Definition>
            </dl>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
