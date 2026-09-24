"use client";

import {
  Activity,
  AlertTriangle,
  Bot,
  CircleDollarSign,
  Gauge,
  History,
  Home,
  Play,
  RefreshCw,
  Server,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Square,
  WalletCards,
} from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

import { HistoryPanel } from "@/components/cockpit/history-panel";
import { PositionsPanel } from "@/components/cockpit/positions-panel";
import { SettingsPanel } from "@/components/cockpit/settings-panel";
import { SimpleConfigurator } from "@/components/cockpit/simple-configurator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAnalytics } from "@/hooks/use-analytics";
import { useCockpit } from "@/hooks/use-cockpit";
import { useControlPlane, type ControlPlaneController } from "@/hooks/use-control-plane";
import { formatDecimal, formatFailure, formatTimestamp } from "@/lib/api/format";
import { cn } from "@/lib/utils";

type ViewId = "home" | "configure" | "positions" | "history" | "settings";

type NavItem = {
  id: ViewId;
  label: string;
  description: string;
  icon: typeof Home;
};

const NAV_ITEMS: NavItem[] = [
  { id: "home", label: "Accueil", description: "État et action suivante", icon: Home },
  { id: "configure", label: "Configurer", description: "Créer un test PAPER", icon: SlidersHorizontal },
  { id: "positions", label: "Positions", description: "Portefeuille et P&L", icon: WalletCards },
  { id: "history", label: "Historique", description: "Agent → Risk → PAPER", icon: History },
  { id: "settings", label: "Réglages", description: "Aide et mode avancé", icon: Settings2 },
];

const percentFormatter = new Intl.NumberFormat("fr-FR", {
  style: "percent",
  maximumFractionDigits: 2,
});

function formatPercent(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return String(value);
  return percentFormatter.format(parsed);
}

function engineLabel(status: string | null | undefined) {
  if (status === "RUNNING") return "En cours";
  if (status === "STOPPED") return "Arrêté";
  return "Aucune session active";
}

function engineTone(status: string | null | undefined) {
  if (status === "RUNNING") return "success" as const;
  if (status === "STOPPED") return "neutral" as const;
  return "warning" as const;
}

function KpiCard({ label, value, detail, icon }: { label: string; value: string; detail: string; icon: ReactNode }) {
  return (
    <Card className="gap-3 py-5 shadow-none">
      <CardHeader className="flex-row items-start justify-between gap-4 px-5">
        <div className="min-w-0 space-y-1.5"><CardDescription className="text-xs font-semibold uppercase tracking-[0.12em]">{label}</CardDescription><CardTitle className="truncate text-2xl tracking-tight">{value}</CardTitle></div>
        <div className="rounded-xl border bg-muted/45 p-2.5 text-muted-foreground">{icon}</div>
      </CardHeader>
      <CardContent className="px-5 text-xs leading-relaxed text-muted-foreground">{detail}</CardContent>
    </Card>
  );
}

function HomePanel({ control, onNavigate }: { control: ControlPlaneController; onNavigate: (view: ViewId) => void }) {
  const cockpit = useCockpit();
  const analytics = useAnalytics();
  const [refreshingAll, setRefreshingAll] = useState(false);

  const health = cockpit.resources.health.kind === "ready" ? cockpit.resources.health.data : null;
  const portfolio = cockpit.resources.portfolio.kind === "ready" ? cockpit.resources.portfolio.data : null;
  const latestCycle = cockpit.resources.latestCycle.kind === "ready" ? cockpit.resources.latestCycle.data : null;
  const latestError = cockpit.resources.latestError.kind === "ready" ? cockpit.resources.latestError.data : null;
  const decisions = cockpit.resources.decisions.kind === "ready" ? cockpit.resources.decisions.data.items : [];
  const risks = cockpit.resources.riskAssessments.kind === "ready" ? cockpit.resources.riskAssessments.data.items : [];
  const summary = analytics.state.kind === "ready" ? analytics.state.data.summary : null;
  const activeCampaign = control.activeCampaign?.campaign ?? null;
  const engine = control.engine;
  const activeStrategy = activeCampaign ? control.strategies.find((item) => item.strategy_id === activeCampaign.strategy_id) ?? null : null;
  const latestCampaign = useMemo(
    () => [...control.campaigns].sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null,
    [control.campaigns],
  );
  const latestRun = useMemo(
    () => [...control.paperRuns.items].sort((a, b) => b.started_at.localeCompare(a.started_at)).find((item) => item.campaign_id) ?? null,
    [control.paperRuns.items],
  );
  const latestCampaignRun = latestCampaign
    ? control.paperRuns.items.find((run) => run.campaign_id === latestCampaign.campaign_id) ?? null
    : null;
  const recoverableCampaign = !activeCampaign && latestRun?.campaign_id
    ? control.campaigns.find((item) => item.campaign_id === latestRun.campaign_id) ?? null
    : null;
  const latestDecision = decisions[0] ?? null;
  const latestRisk = latestDecision ? risks.find((item) => item.decision_id === latestDecision.decision_id) ?? null : null;
  const openPositions = portfolio ? portfolio.positions.length + portfolio.derivative_positions.length : 0;
  const busy = control.busyAction !== null;

  async function refreshAll() {
    if (refreshingAll) return;
    setRefreshingAll(true);
    try {
      await Promise.all([cockpit.refresh(), analytics.refresh(), control.refresh()]);
    } finally {
      setRefreshingAll(false);
    }
  }

  let actionTitle = "Créer votre premier test";
  let actionDetail = "Choisissez le marché, le capital, l’IA et un profil Risk simple.";
  let actionLabel = "Créer mon premier test";
  let action: () => void = () => onNavigate("configure");
  let secondary: ReactNode = null;

  if (activeCampaign && engine?.status === "RUNNING") {
    actionTitle = "Le bot est en cours";
    actionDetail = "La boucle autonome tourne côté backend. Vous pouvez fermer le frontend sans arrêter le moteur.";
    actionLabel = "Surveiller les positions";
    action = () => onNavigate("positions");
    secondary = <Button variant="destructive" onClick={() => void control.stopEngine()} disabled={busy}><Square className="size-4" /> Arrêter</Button>;
  } else if (activeCampaign && engine?.configured && engine.status === "STOPPED") {
    actionTitle = "La session est prête";
    actionDetail = "La configuration est chargée. Démarrez la boucle ou testez un seul cycle avant de laisser tourner.";
    actionLabel = "Démarrer";
    action = () => { void control.startEngine(); };
    secondary = <Button variant="outline" onClick={() => void control.runCycle()} disabled={busy}><Activity className="size-4" /> Tester 1 cycle</Button>;
  } else if (!activeCampaign && latestCampaign && !latestCampaignRun) {
    actionTitle = "Une configuration est prête";
    actionDetail = "Elle n’a encore aucune session. Une activation fraîche créera son premier run PAPER avant démarrage.";
    actionLabel = "Démarrer cette configuration";
    action = () => { void control.startCampaign(latestCampaign.campaign_id); };
    secondary = <Button variant="outline" onClick={() => onNavigate("configure")}>Créer un autre test</Button>;
  } else if (!activeCampaign && recoverableCampaign) {
    actionTitle = "Une session précédente peut être reprise";
    actionDetail = "Le backend n’a rien repris silencieusement. La reprise tente explicitement de restaurer le ledger durable ; le backend refuse toute session incompatible.";
    actionLabel = "Reprendre la dernière session";
    action = () => { void control.resumeAndStartCampaign(recoverableCampaign.campaign_id); };
  } else if (!activeCampaign && latestCampaign) {
    actionTitle = "Choisir comment continuer";
    actionDetail = "Cette configuration possède déjà un historique. Ouvrez le mode avancé pour choisir explicitement une activation fraîche ou la reprise d’une session compatible.";
    actionLabel = "Ouvrir les réglages";
    action = () => onNavigate("settings");
    secondary = <Button variant="outline" onClick={() => onNavigate("configure")}>Créer un nouveau test</Button>;
  }

  const config = activeCampaign?.configuration ?? latestCampaign?.configuration ?? null;
  const configStrategy = activeCampaign
    ? activeStrategy
    : latestCampaign
      ? control.strategies.find((item) => item.strategy_id === latestCampaign.strategy_id) ?? null
      : null;

  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Cockpit PAPER</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight">Accueil</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">Statut, configuration, capital, P&L et prochaine action utile. Les détails techniques restent en mode avancé.</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refreshAll()} disabled={refreshingAll}><RefreshCw className={refreshingAll ? "size-3.5 animate-spin" : "size-3.5"} /> Actualiser</Button>
      </div>

      <Card className="border-foreground/20 bg-foreground text-background shadow-none">
        <CardContent className="grid gap-5 py-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-background/60"><Play className="size-3.5" /> Action suivante</div>
            <h3 className="mt-2 text-2xl font-semibold tracking-tight">{actionTitle}</h3>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-background/70">{actionDetail}</p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row lg:justify-end">
            {secondary}
            <Button onClick={action} disabled={busy || control.loading}><Play className="size-4" /> {actionLabel}</Button>
          </div>
        </CardContent>
      </Card>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Bot" value={engineLabel(engine?.status)} detail={health ? "Backend accessible" : "Backend inaccessible ou en chargement"} icon={<Bot className="size-5" />} />
        <KpiCard label="Capital PAPER" value={config ? formatDecimal(config.paper_initial_capital) : "—"} detail={config ? `${config.paper_settlement_asset} · ${config.paper_executable_markets.map((item) => item.market_type).filter((value, index, all) => all.indexOf(value) === index).join(" + ")}` : "Aucune configuration"} icon={<CircleDollarSign className="size-5" />} />
        <KpiCard label="P&L net" value={summary?.ending_equity ? formatDecimal(summary.net_pnl) : "—"} detail={summary?.ending_equity ? `Equity ${formatDecimal(summary.ending_equity)} · backend analytics` : "Pas encore de cycle valorisable"} icon={<Gauge className="size-5" />} />
        <KpiCard label="Positions" value={portfolio ? String(openPositions) : "—"} detail={portfolio ? `${portfolio.positions.length} SPOT · ${portfolio.derivative_positions.length} PERPETUAL` : "Portefeuille non disponible"} icon={<WalletCards className="size-5" />} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card className="shadow-none">
          <CardHeader><CardTitle>Configuration utilisée</CardTitle><CardDescription>Résumé opérateur ; les UUID, digests et versions techniques restent dans Réglages → Avancé.</CardDescription></CardHeader>
          <CardContent>
            {config ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Nom</p><p className="mt-1 font-semibold">{configStrategy?.strategy_name ?? "Configuration PAPER"}</p></div>
                <div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Modèle</p><p className="mt-1 font-semibold">{config.llm_model.replace("gpt-5.6-", "")}</p><p className="mt-1 text-xs text-muted-foreground">Agressivité {config.aggressiveness}/10</p></div>
                <div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Actifs</p><p className="mt-1 font-semibold">{config.paper_executable_markets.map((item) => item.symbol).join(", ")}</p><p className="mt-1 text-xs text-muted-foreground">{config.paper_executable_markets.map((item) => item.market_type).filter((value, index, all) => all.indexOf(value) === index).join(" + ")}</p></div>
              </div>
            ) : <p className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">Aucune configuration PAPER créée.</p>}
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader><CardTitle>Dernière décision</CardTitle><CardDescription>Lecture rapide sans entrer dans l’audit détaillé.</CardDescription></CardHeader>
          <CardContent>
            {latestDecision ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2"><Badge tone={latestDecision.action === "BUY" ? "success" : latestDecision.action === "SELL" ? "danger" : "neutral"}>{latestDecision.action}</Badge><span className="font-semibold">{latestDecision.symbol}</span>{latestRisk ? <Badge tone={latestRisk.status === "ALLOW" ? "success" : latestRisk.status === "MODIFY" ? "warning" : latestRisk.status === "REJECT" ? "danger" : "neutral"}>Risk {latestRisk.status}</Badge> : null}</div>
                <p className="text-xs text-muted-foreground">{formatTimestamp(latestDecision.created_at)}</p>
                <Button variant="outline" size="sm" onClick={() => onNavigate("history")}>Voir le parcours complet</Button>
              </div>
            ) : <p className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">Aucune décision IA journalisée.</p>}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card className="shadow-none">
          <CardHeader><CardTitle>Performance & exposition</CardTitle><CardDescription>Valeurs calculées par le backend à partir des faits durables.</CardDescription></CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Drawdown max</p><p className="mt-1 text-lg font-semibold">{formatPercent(summary?.max_drawdown_fraction)}</p></div>
            <div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Exposition</p><p className="mt-1 text-lg font-semibold">{formatPercent(summary?.current_exposure_fraction)}</p></div>
            <div className="rounded-xl border p-4"><p className="text-xs text-muted-foreground">Trades fillés</p><p className="mt-1 text-lg font-semibold">{summary?.trade_count ?? "—"}</p></div>
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader><CardTitle className="flex items-center gap-2"><AlertTriangle className="size-4" /> À surveiller</CardTitle><CardDescription>Les erreurs backend restent visibles et ne sont jamais contournées.</CardDescription></CardHeader>
          <CardContent>
            {latestCycle?.failure || latestError || control.feedback?.tone === "error" ? (
              <div className="space-y-2">
                {latestCycle?.failure ? <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">Dernier cycle : {formatFailure(latestCycle.failure)}</div> : null}
                {latestError ? <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">Erreur persistée : {formatFailure(latestError.failure)}</div> : null}
                {control.feedback?.tone === "error" ? <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">{control.feedback.message}</div> : null}
              </div>
            ) : <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900"><div className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-4" /> Aucun signal à traiter</div><p className="mt-1 text-xs text-emerald-800">Aucun échec de cycle récent ni refus technique visible.</p></div>}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function ViewContent({ view, control, onNavigate }: { view: ViewId; control: ControlPlaneController; onNavigate: (view: ViewId) => void }) {
  if (view === "home") return <HomePanel control={control} onNavigate={onNavigate} />;
  if (view === "configure") return <SimpleConfigurator control={control} onCreated={() => onNavigate("home")} />;
  if (view === "positions") return <PositionsPanel />;
  if (view === "history") return <HistoryPanel />;
  return <SettingsPanel />;
}

export function CockpitShell() {
  const [view, setView] = useState<ViewId>("home");
  const control = useControlPlane();
  const currentNav = NAV_ITEMS.find((item) => item.id === view) ?? NAV_ITEMS[0];
  const activeCampaign = control.activeCampaign?.campaign ?? null;
  const activeStrategy = activeCampaign ? control.strategies.find((item) => item.strategy_id === activeCampaign.strategy_id) ?? null : null;
  const engine = control.engine;
  const busy = control.busyAction !== null;

  return (
    <div className="min-h-svh bg-muted/20 lg:grid lg:grid-cols-[230px_minmax(0,1fr)]">
      <aside className="border-b bg-foreground text-background lg:sticky lg:top-0 lg:h-svh lg:border-b-0 lg:border-r">
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between gap-3 px-4 py-4 lg:block lg:px-5 lg:py-6">
            <div className="flex items-center gap-2"><div className="flex size-8 items-center justify-center rounded-lg bg-background/10"><Bot className="size-4" /></div><div><p className="text-sm font-semibold tracking-tight">AI Spot Trader</p><p className="text-[11px] text-background/60">Cockpit PAPER</p></div></div>
            <span className="rounded-full border border-background/20 bg-background/10 px-2 py-1 text-[10px] font-bold tracking-[0.16em] lg:mt-5 lg:inline-flex">PAPER ONLY</span>
          </div>

          <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-col lg:overflow-visible lg:px-3 lg:pb-0">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const active = item.id === view;
              return <button key={item.id} type="button" onClick={() => setView(item.id)} aria-current={active ? "page" : undefined} className={cn("group flex min-w-max items-center gap-3 rounded-lg px-3 py-2.5 text-left transition lg:min-w-0", active ? "bg-background text-foreground" : "text-background/70 hover:bg-background/10 hover:text-background")}><Icon className="size-4 shrink-0" /><span className="min-w-0"><span className="block text-sm font-medium">{item.label}</span><span className={cn("hidden truncate text-[11px] lg:block", active ? "text-muted-foreground" : "text-background/45")}>{item.description}</span></span></button>;
            })}
          </nav>

          <div className="mt-auto hidden px-5 pb-5 lg:block"><div className="rounded-xl border border-background/15 bg-background/5 p-3 text-xs text-background/65"><p className="font-semibold text-background/90">Principe central</p><p className="mt-1 leading-relaxed">L’IA propose. Le Risk Engine autorise, modifie ou refuse.</p></div></div>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/85">
          <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-3 px-4 py-3 sm:px-6 xl:px-8">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2"><h1 className="text-lg font-semibold tracking-tight">{currentNav.label}</h1><Badge tone="info">PAPER</Badge><Badge tone={engineTone(engine?.status)}>{engineLabel(engine?.status)}</Badge></div>
                <p className="mt-1 truncate text-xs text-muted-foreground">{activeCampaign ? `${activeStrategy?.strategy_name ?? "Configuration active"} · ${activeCampaign.configuration.paper_initial_capital} ${activeCampaign.configuration.paper_settlement_asset} · ${activeCampaign.configuration.llm_model.replace("gpt-5.6-", "")}` : "Aucune configuration active"}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {engine?.configured && engine.status === "STOPPED" ? <Button size="sm" onClick={() => void control.startEngine()} disabled={busy}><Play className="size-3.5" /> Démarrer</Button> : null}
                {engine?.status === "RUNNING" ? <Button variant="destructive" size="sm" onClick={() => void control.stopEngine()} disabled={busy}><Square className="size-3.5" /> Arrêter</Button> : null}
              </div>
            </div>
            {control.feedback ? <div className={cn("flex flex-col gap-2 rounded-lg border px-3 py-2 text-xs sm:flex-row sm:items-center sm:justify-between", control.feedback.tone === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-emerald-200 bg-emerald-50 text-emerald-800")}><span>{control.feedback.message}</span><button type="button" className="font-semibold underline underline-offset-2" onClick={() => control.setFeedback(null)}>Masquer</button></div> : null}
          </div>
        </header>

        <main className="min-w-0"><ViewContent view={view} control={control} onNavigate={setView} /></main>

        <footer className="mx-auto flex w-full max-w-[1500px] flex-col gap-1 border-t px-4 py-4 text-[11px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6 xl:px-8"><span>Backend = moteur de trading · Frontend = contrôle et visualisation uniquement.</span><span className="flex items-center gap-1.5"><Server className="size-3" /> état Control Plane {formatTimestamp(control.lastUpdatedAt)}</span></footer>
      </div>
    </div>
  );
}
