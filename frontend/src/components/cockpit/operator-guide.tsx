import {
  Activity,
  Bot,
  BookOpenText,
  History,
  Home,
  Play,
  RefreshCw,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  WalletCards,
} from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type GuideCardProps = {
  icon: ReactNode;
  title: string;
  description: string;
  children?: ReactNode;
};

function GuideCard({ icon, title, description, children }: GuideCardProps) {
  return (
    <Card className="shadow-none">
      <CardHeader>
        <div className="flex items-start gap-3">
          <div className="rounded-xl border bg-muted/45 p-2.5 text-muted-foreground">{icon}</div>
          <div className="space-y-1">
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      {children ? <CardContent className="text-sm leading-6 text-muted-foreground">{children}</CardContent> : null}
    </Card>
  );
}

export function OperatorGuide() {
  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Aide opérateur</p>
          <h2 className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <BookOpenText className="size-5" /> Utiliser AI Spot Trader
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            Le parcours normal ne demande plus de connaître Strategy, Revision, Campaign ou paper_run.
            Ces détails restent disponibles dans Réglages → Avancé pour l’audit et l’administration.
          </p>
        </div>
        <Card className="gap-3 py-4 shadow-none">
          <CardHeader className="px-4"><CardTitle className="text-sm">Périmètre actuel</CardTitle></CardHeader>
          <CardContent className="space-y-2 px-4 text-xs text-muted-foreground">
            <div className="flex flex-wrap gap-2"><Badge tone="info">PAPER uniquement</Badge><Badge>SPOT</Badge><Badge tone="warning">PERPETUAL</Badge></div>
            <p>LIVE reste indisponible. Fermer le frontend n’arrête pas le moteur backend.</p>
          </CardContent>
        </Card>
      </div>

      <Card className="border-foreground/15 shadow-none">
        <CardHeader>
          <CardTitle>Premier test en cinq étapes</CardTitle>
          <CardDescription>Le chemin recommandé pour commencer sans ouvrir le mode avancé.</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            {[
              "Ouvrir Configurer.",
              "Choisir marché, paires et capital.",
              "Choisir le modèle, l’agressivité et les instructions IA.",
              "Choisir un profil Risk simple.",
              "Vérifier puis Créer et démarrer.",
            ].map((step, index) => (
              <li key={step} className="flex gap-3 rounded-xl border bg-muted/15 p-4 text-sm leading-6">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-foreground text-xs font-bold text-background">{index + 1}</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <GuideCard icon={<Home className="size-5" />} title="Accueil" description="Statut et Action suivante.">
          <p>Utilise cette page pour savoir si le bot tourne, quelle configuration est active, quel est le P&L et quelle action est utile maintenant.</p>
        </GuideCard>
        <GuideCard icon={<SlidersHorizontal className="size-5" />} title="Configurer" description="Créer un test PAPER.">
          <p>L’assistant traduit tes choix en configuration canonique puis crée les objets techniques nécessaires via l’API backend.</p>
        </GuideCard>
        <GuideCard icon={<WalletCards className="size-5" />} title="Positions" description="Ce que le backend détient.">
          <p>Les positions et métriques viennent du backend. Le navigateur ne reconstruit pas un portefeuille parallèle.</p>
        </GuideCard>
        <GuideCard icon={<History className="size-5" />} title="Historique" description="Agent → Risk → PAPER.">
          <p>Chaque cycle regroupe la décision IA, le résultat Risk et l’éventuelle exécution PAPER.</p>
        </GuideCard>
        <GuideCard icon={<Settings2 className="size-5" />} title="Réglages" description="Aide, Assistant et Avancé.">
          <p>Les objets Strategy/Revision/Campaign, digests, recovery et contrôles détaillés y restent accessibles à la demande.</p>
        </GuideCard>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <GuideCard icon={<Bot className="size-5" />} title="1 · L’IA propose" description="BUY, SELL ou HOLD est une décision stratégique.">
          <p>HOLD est une décision normale et journalisée. L’agressivité influence le contexte stratégique mais ne relève jamais une limite Risk.</p>
        </GuideCard>
        <GuideCard icon={<ShieldCheck className="size-5" />} title="2 · Risk décide" description="ALLOW, MODIFY ou REJECT.">
          <p>Le Risk Engine déterministe garde l’autorité finale. Les profils Prudent, Équilibré et Agressif ne sont que des presets de configuration.</p>
        </GuideCard>
        <GuideCard icon={<Activity className="size-5" />} title="3 · PAPER exécute" description="Uniquement après autorisation Risk.">
          <p>Une sortie LLM ne déclenche jamais directement le Broker. Fills, ledger, positions et analytics restent gérés côté backend.</p>
        </GuideCard>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <GuideCard icon={<Play className="size-5" />} title="Démarrer" description="Lance la boucle autonome backend.">
          <p>Le moteur continue même si tu fermes ou recharges le frontend. Utilise Arrêter pour envoyer explicitement Stop.</p>
        </GuideCard>
        <GuideCard icon={<Activity className="size-5" />} title="Tester 1 cycle" description="Exécute run-cycle puis reste Arrêté.">
          <p>Pratique pour observer une nouvelle configuration sans laisser tourner la boucle autonome.</p>
        </GuideCard>
        <GuideCard icon={<RefreshCw className="size-5" />} title="Reprendre" description="Toujours explicite après restart backend.">
          <p>Le backend restaure le ledger selon le recovery canonique et refuse une session incompatible. Aucune reprise silencieuse n’est effectuée.</p>
        </GuideCard>
      </section>

      <Card className="shadow-none">
        <CardHeader><CardTitle>SPOT et PERPETUAL</CardTitle><CardDescription>Deux marchés, avec des contraintes différentes.</CardDescription></CardHeader>
        <CardContent className="grid gap-4 text-sm text-muted-foreground lg:grid-cols-2">
          <div className="rounded-xl border p-4"><p className="font-semibold text-foreground">SPOT</p><p className="mt-2 leading-6">Pas de short, pas de levier, pas de marge. SELL ne peut réduire qu’un actif détenu et disponible.</p><p className="mt-2 text-xs">Le contrat portefeuille actuel n’expose pas de coût moyen/P&L par position SPOT ; le cockpit n’invente pas ces valeurs.</p></div>
          <div className="rounded-xl border p-4"><p className="font-semibold text-foreground">PERPETUAL linéaire</p><p className="mt-2 leading-6">LONG/SHORT, marge ISOLATED et levier configuré. Risk contrôle les plafonds de levier, position et exposition.</p><p className="mt-2 text-xs">CROSS, contrats inverses et futures datés restent hors périmètre exécutable actuel.</p></div>
        </CardContent>
      </Card>

      <Card className="border-foreground/15 bg-muted/20 shadow-none">
        <CardContent className="py-5">
          <p className="font-semibold">À retenir</p>
          <p className="mt-1 text-sm text-muted-foreground">L’IA propose. Le Risk Engine autorise, modifie ou refuse. Le frontend contrôle et visualise uniquement.</p>
        </CardContent>
      </Card>
    </div>
  );
}
