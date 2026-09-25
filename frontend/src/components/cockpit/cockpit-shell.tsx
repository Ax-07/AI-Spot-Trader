"use client";

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bot,
  CircleDollarSign,
  Gauge,
  History,
  Home,
  Layers3,
  Play,
  Plus,
  RefreshCw,
  Server,
  Settings2,
  ShieldCheck,
  Square,
  WalletCards,
} from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import { HistoryPanel } from "@/components/cockpit/history-panel";
import { MarketsPanel } from "@/components/cockpit/markets-panel";
import { PositionsPanel } from "@/components/cockpit/positions-panel";
import { SessionsPanel } from "@/components/cockpit/sessions-panel";
import { SettingsPanel } from "@/components/cockpit/settings-panel";
import { SimpleConfigurator } from "@/components/cockpit/simple-configurator";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAnalytics } from "@/hooks/use-analytics";
import { useCockpit } from "@/hooks/use-cockpit";
import { useControlPlane, type ControlPlaneController } from "@/hooks/use-control-plane";
import { formatDecimal, formatFailure, formatTimestamp } from "@/lib/api/format";
import type { SessionResponse } from "@/lib/api/types";
import { sessionStatusLabel } from "@/lib/session-config";
import { cn } from "@/lib/utils";

type ViewId = "home" | "sessions" | "configure" | "markets" | "positions" | "history" | "settings";

type NavItem = {
  id: Exclude<ViewId, "configure">;
  label: string;
  description: string;
  icon: typeof Home;
};

const NAV_ITEMS: NavItem[] = [
  { id: "home", label: "Accueil", description: "État et action suivante", icon: Home },
  { id: "sessions", label: "Sessions", description: "Créer et piloter les Sessions", icon: Layers3 },
  { id: "markets", label: "Marchés", description: "Charts, positions et fills PAPER", icon: Activity },
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
  if (status === "STOPPED") return "Prête";
  return "Aucune session active";
}

function engineTone(status: string | null | undefined) {
  if (status === "RUNNING") return "success" as const;
  if (status === "STOPPED") return "info" as const;
  return "neutral" as const;
}

function signedValueClass(value: string | number | null | undefined) {
  const parsed = typeof value === "number" ? value : Number(value ?? 0);
  if (!Number.isFinite(parsed) || parsed === 0) return "text-foreground";
  return parsed > 0 ? "text-success-foreground" : "text-destructive-subtle-foreground";
}

function signedDecimal(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return String(value);
  const formatted = formatDecimal(Math.abs(parsed));
  if (parsed > 0) return `+${formatted}`;
  if (parsed < 0) return `−${formatted}`;
  return formatted;
}

function codeLabel(value: string | null | undefined) {
  return value ? value.replaceAll("_", " ") : "—";
}

function KpiCard({
  label,
  value,
  detail,
  icon,
  valueClassName,
}: {
  label: string;
  value: string;
  detail: string;
  icon: ReactNode;
  valueClassName?: string;
}) {
  return (
    <Card className="gap-3 py-5">
      <CardHeader className="flex-row items-start justify-between gap-4 px-5">
        <div className="min-w-0 space-y-1.5">
          <CardDescription className="text-[11px] font-bold uppercase tracking-[0.14em]">{label}</CardDescription>
          <CardTitle className={cn("truncate text-2xl tracking-tight", valueClassName)}>{value}</CardTitle>
        </div>
        <div className="rounded-xl border border-border/80 bg-muted/60 p-2.5 text-muted-foreground">{icon}</div>
      </CardHeader>
      <CardContent className="px-5 text-xs leading-relaxed text-muted-foreground">{detail}</CardContent>
    </Card>
  );
}

function activeSession(control: ControlPlaneController): SessionResponse | null {
  const strategyId = control.activeCampaign?.campaign.strategy_id ?? null;
  if (!strategyId) return null;
  return control.sessions.find((item) => item.session_id === strategyId) ?? null;
}

function HomePanel({ control, onNavigate }: { control: ControlPlaneController; onNavigate: (view: ViewId) => void }) {
  const cockpit = useCockpit();
  const analytics = useAnalytics();
  const [refreshingAll, setRefreshingAll] = useState(false);

  const health = cockpit.resources.health.kind === "ready" ? cockpit.resources.health.data : null;
  const portfolio = cockpit.resources.portfolio.kind === "ready" ? cockpit.resources.portfolio.data : null;
  const latestCycle = cockpit.resources.latestCycle.kind === "ready" ? cockpit.resources.latestCycle.data : null;
  const latestError = cockpit.resources.latestError.kind === "ready" ? cockpit.resources.latestError.data : null;
  const summary = analytics.state.kind === "ready" ? analytics.state.data.summary : null;
  const latestExplanation = latestCycle?.explainability ?? null;
  const latestDecision = latestExplanation?.agent ?? null;
  const latestRisk = latestExplanation?.risk ?? null;
  const latestExecution = latestExplanation?.execution ?? null;
  const latestContext = latestExplanation?.context ?? null;
  const latestSelection = latestExplanation?.market_selection ?? null;
  const openPositions = portfolio ? portfolio.positions.length + portfolio.derivative_positions.length : 0;
  const currentSession = activeSession(control);
  const referenceSession = currentSession ?? control.sessions[0] ?? null;
  const config = referenceSession?.configuration ?? null;
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

  let actionTitle = "Créer votre première Session";
  let actionDetail = "Choisissez le capital PAPER, les marchés, l’IA, l’agressivité et un profil Risk simple.";
  let actionLabel = "Nouvelle session";
  let action: () => void = () => onNavigate("configure");
  let secondary: ReactNode = null;

  if (currentSession?.status === "RUNNING") {
    actionTitle = `${currentSession.name} est en cours`;
    actionDetail = "La boucle autonome tourne côté backend. Fermer le frontend n’arrête pas le moteur de trading.";
    actionLabel = "Surveiller les positions";
    action = () => onNavigate("positions");
    secondary = (
      <Button variant="destructive" onClick={() => void control.stopSession(currentSession.session_id)} disabled={busy}>
        <Square className="size-4" /> Arrêter
      </Button>
    );
  } else if (currentSession?.status === "READY") {
    actionTitle = `${currentSession.name} est prête`;
    actionDetail = "La Session est chargée côté backend. Démarrez la boucle ou testez exactement un cycle.";
    actionLabel = "Démarrer";
    action = () => void control.startSession(currentSession.session_id);
    secondary = (
      <Button variant="outline" onClick={() => void control.runSessionCycle(currentSession.session_id)} disabled={busy}>
        <Activity className="size-4" /> Tester 1 cycle
      </Button>
    );
  } else if (referenceSession?.status === "RESUMABLE") {
    actionTitle = `${referenceSession.name} peut être reprise`;
    actionDetail = "Aucune reprise n’est automatique après restart. La reprise restaure explicitement le ledger durable compatible.";
    actionLabel = "Reprendre";
    action = () => void control.resumeSession(referenceSession.session_id);
    secondary = <Button variant="outline" onClick={() => onNavigate("sessions")}>Voir les Sessions</Button>;
  } else if (referenceSession) {
    actionTitle = `${referenceSession.name} est ${sessionStatusLabel(referenceSession.status).toLowerCase()}`;
    actionDetail = referenceSession.current_campaign_has_history
      ? "Cette version possède déjà un historique : utilisez Reprendre pour continuer explicitement."
      : "Cette version peut être démarrée sans modifier les faits historiques précédents.";
    actionLabel = referenceSession.current_campaign_has_history ? "Reprendre" : "Démarrer";
    action = referenceSession.current_campaign_has_history
      ? () => void control.resumeSession(referenceSession.session_id)
      : () => void control.startSession(referenceSession.session_id);
    secondary = <Button variant="outline" onClick={() => onNavigate("sessions")}>Gérer les Sessions</Button>;
  }

  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Cockpit PAPER</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight">Accueil</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">Statut, capital, P&L et prochaine action utile. Le parcours normal parle de Sessions ; les objets techniques restent dans Réglages → Avancé.</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refreshAll()} disabled={refreshingAll}>
          <RefreshCw className={refreshingAll ? "size-3.5 animate-spin" : "size-3.5"} /> Actualiser
        </Button>
      </div>

      <Card className="relative overflow-hidden border-primary/35 bg-primary text-primary-foreground shadow-xl shadow-primary/10">
        <div className="pointer-events-none absolute -right-16 -top-24 size-64 rounded-full bg-white/10 blur-3xl" />
        <CardContent className="relative grid gap-5 py-7 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-primary-foreground/75"><Play className="size-3.5" /> Action suivante</div>
            <h3 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{actionTitle}</h3>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-primary-foreground/80">{actionDetail}</p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row lg:justify-end">
            {secondary}
            <Button onClick={action} disabled={busy || control.loading} className="border-primary-foreground/20 bg-primary-foreground text-primary hover:bg-primary-foreground/90">
              {actionLabel} <ArrowRight className="size-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Session" value={currentSession ? sessionStatusLabel(currentSession.status) : referenceSession ? sessionStatusLabel(referenceSession.status) : "Aucune"} detail={health ? "Backend accessible" : "Backend inaccessible ou en chargement"} icon={<Bot className="size-5" />} />
        <KpiCard label="Capital PAPER" value={config ? formatDecimal(config.paper_initial_capital) : "—"} detail={config ? `${config.paper_settlement_asset} · ${referenceSession?.market_mode === "AUTOMATIC_AI" ? "Auto IA" : "Manuel"}` : "Aucune Session"} icon={<CircleDollarSign className="size-5" />} />
        <KpiCard label="P&L net" value={summary?.ending_equity ? signedDecimal(summary.net_pnl) : "—"} valueClassName={summary?.ending_equity ? signedValueClass(summary.net_pnl) : undefined} detail={summary?.ending_equity ? `Equity ${formatDecimal(summary.ending_equity)} · backend analytics` : "Pas encore de cycle valorisable"} icon={<Gauge className="size-5" />} />
        <KpiCard label="Positions" value={portfolio ? String(openPositions) : "—"} detail={portfolio ? `${portfolio.positions.length} SPOT · ${portfolio.derivative_positions.length} PERPETUAL` : "Portefeuille non disponible"} icon={<WalletCards className="size-5" />} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader><CardTitle>Session utilisée</CardTitle><CardDescription>Résumé opérateur ; les identifiants, versions et détails techniques restent dans Réglages → Avancé.</CardDescription></CardHeader>
          <CardContent>
            {referenceSession ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <div className="rounded-xl border bg-muted/20 p-4"><p className="text-xs text-muted-foreground">Nom</p><p className="mt-1 font-semibold">{referenceSession.name}</p></div>
                <div className="rounded-xl border bg-muted/20 p-4"><p className="text-xs text-muted-foreground">Modèle</p><p className="mt-1 font-semibold">{referenceSession.configuration.llm_model.replace("gpt-5.6-", "")}</p><p className="mt-1 text-xs text-muted-foreground">Agressivité {referenceSession.configuration.aggressiveness}/10</p></div>
                <div className="rounded-xl border bg-muted/20 p-4"><p className="text-xs text-muted-foreground">Marchés</p><p className="mt-1 font-semibold">{referenceSession.market_mode === "AUTOMATIC_AI" ? "Automatique — IA" : "Manuel"}</p><p className="mt-1 text-xs text-muted-foreground">{referenceSession.configuration.paper_executable_markets.map((item) => item.symbol).join(", ")}</p></div>
              </div>
            ) : (
              <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed p-5 text-sm text-muted-foreground">
                <span>Aucune Session créée.</span>
                <Button size="sm" onClick={() => onNavigate("configure")}><Plus className="size-3.5" /> Nouvelle session</Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Dernière décision</CardTitle><CardDescription>Synthèse explicable de l’Agent, Risk et de l’exécution PAPER.</CardDescription></CardHeader>
          <CardContent>
            {latestDecision ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={latestDecision.action === "BUY" ? "success" : latestDecision.action === "SELL" ? "danger" : "neutral"}>{latestDecision.action}</Badge>
                  <span className="font-semibold">{latestDecision.symbol}</span>
                  {latestContext?.mode ? <Badge tone={latestContext.mode === "MANAGEMENT" ? "warning" : "info"}>{latestContext.mode}</Badge> : null}
                  {latestRisk ? <Badge tone={latestRisk.status === "ALLOW" ? "success" : latestRisk.status === "MODIFY" ? "warning" : latestRisk.status === "REJECT" ? "danger" : "neutral"}>Risk {latestRisk.status}</Badge> : null}
                </div>
                <div className="rounded-xl border bg-muted/20 p-3">
                  <p className="text-xs font-semibold">Pourquoi l’IA ?</p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{latestDecision.rationale ?? "Rationale non disponible pour cet historique"}</p>
                  {latestSelection?.rationale ? <p className="mt-2 border-t pt-2 text-[11px] leading-relaxed text-muted-foreground"><strong className="text-foreground">Pourquoi ce marché ?</strong> {latestSelection.rationale}</p> : null}
                </div>
                {latestRisk ? (
                  <div className="space-y-2 text-xs">
                    {latestRisk.reasons.length ? <div className="flex flex-wrap gap-1.5">{latestRisk.reasons.slice(0, 3).map((reason) => <Badge key={reason} tone={latestRisk.status === "REJECT" ? "danger" : "warning"}>{codeLabel(reason)}</Badge>)}</div> : <p className="text-muted-foreground">Aucune raison de modification/refus persistée.</p>}
                    {latestRisk.requested_quantity ? <p>Quantité IA <strong>{formatDecimal(latestRisk.requested_quantity)}</strong>{latestRisk.authorized_quantity ? <> · autorisée <strong>{formatDecimal(latestRisk.authorized_quantity)}</strong></> : null}</p> : latestDecision.action === "HOLD" && latestRisk.status === "ALLOW" ? <p className="text-muted-foreground">HOLD autorisé : aucune quantité ni exécution attendue.</p> : null}
                  </div>
                ) : null}
                <div className="rounded-lg border bg-background p-3 text-xs">
                  <span className="font-semibold">Exécution PAPER : </span>
                  {latestExecution?.outcome === "FILLED" ? `${latestExecution.fill_count} fill(s) réel(s)` : latestExecution?.outcome === "INTENT_CREATED_NO_FILL" ? "intent créé, aucun fill persisté" : latestExecution?.outcome === "NOT_CREATED_RISK_REJECT" ? "aucun intent après REJECT" : latestExecution?.outcome === "NOT_CREATED_HOLD" ? "aucune exécution attendue pour HOLD" : latestCycle?.failure ? `aucune exécution avant échec ${latestCycle.failure.stage}` : "aucune exécution persistée"}
                </div>
                <p className="text-xs text-muted-foreground">{formatTimestamp(latestCycle?.recorded_at ?? null)}</p>
                <Button variant="outline" size="sm" onClick={() => onNavigate("history")}>Voir le parcours complet</Button>
              </div>
            ) : latestCycle ? (
              <div className="space-y-3"><p className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">Ce dernier cycle ne contient aucune décision IA exploitable. Aucun rationale n’est inventé.</p><Button variant="outline" size="sm" onClick={() => onNavigate("history")}>Voir le cycle</Button></div>
            ) : <p className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">Aucune décision IA journalisée.</p>}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Performance & exposition</CardTitle><CardDescription>Valeurs calculées par le backend à partir des faits durables.</CardDescription></CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border bg-muted/20 p-4"><p className="text-xs text-muted-foreground">Drawdown max</p><p className="mt-1 text-lg font-semibold">{formatPercent(summary?.max_drawdown_fraction)}</p></div>
            <div className="rounded-xl border bg-muted/20 p-4"><p className="text-xs text-muted-foreground">Exposition</p><p className="mt-1 text-lg font-semibold">{formatPercent(summary?.current_exposure_fraction)}</p></div>
            <div className="rounded-xl border bg-muted/20 p-4"><p className="text-xs text-muted-foreground">Trades fillés</p><p className="mt-1 text-lg font-semibold">{summary?.trade_count ?? "—"}</p></div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><AlertTriangle className="size-4" /> À surveiller</CardTitle><CardDescription>Les erreurs backend restent visibles et ne sont jamais contournées.</CardDescription></CardHeader>
          <CardContent>
            {latestCycle?.failure || latestError || control.feedback?.tone === "error" ? (
              <div className="space-y-2">
                {latestCycle?.failure ? <div className="rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-xs text-destructive-subtle-foreground"><strong>Dernier cycle :</strong> {formatFailure(latestCycle.failure)}</div> : null}
                {latestError ? <div className="rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-xs text-destructive-subtle-foreground"><strong>Erreur persistée :</strong> {formatFailure(latestError.failure)}</div> : null}
                {control.feedback?.tone === "error" ? <div className="rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-xs text-destructive-subtle-foreground">{control.feedback.message}</div> : null}
              </div>
            ) : <div className="rounded-xl border border-success/30 bg-success-subtle p-4 text-sm text-success-foreground"><div className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-4" /> État normal</div><p className="mt-1 text-xs">Aucun échec de cycle récent ni refus technique visible.</p></div>}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function ViewContent({
  view,
  control,
  editingSession,
  onNavigate,
  onCreateSession,
  onEditSession,
}: {
  view: ViewId;
  control: ControlPlaneController;
  editingSession: SessionResponse | null;
  onNavigate: (view: ViewId) => void;
  onCreateSession: () => void;
  onEditSession: (session: SessionResponse) => void;
}) {
  if (view === "home") return <HomePanel control={control} onNavigate={onNavigate} />;
  if (view === "sessions") return <SessionsPanel control={control} onCreate={onCreateSession} onEdit={onEditSession} />;
  if (view === "configure") return <SimpleConfigurator key={editingSession?.session_id ?? "new"} control={control} session={editingSession} onSaved={() => onNavigate("sessions")} onCancel={() => onNavigate("sessions")} />;
  if (view === "markets") return <MarketsPanel control={control} />;
  if (view === "positions") return <PositionsPanel />;
  if (view === "history") return <HistoryPanel />;
  return <SettingsPanel />;
}

export function CockpitShell() {
  const [view, setView] = useState<ViewId>("home");
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const control = useControlPlane();
  const currentNav = NAV_ITEMS.find((item) => item.id === view) ?? NAV_ITEMS[0];
  const currentSession = activeSession(control);
  const editingSession = editingSessionId ? control.sessions.find((item) => item.session_id === editingSessionId) ?? null : null;
  const engine = control.engine;
  const busy = control.busyAction !== null;

  function createSession() {
    setEditingSessionId(null);
    setView("configure");
  }

  function editSession(session: SessionResponse) {
    setEditingSessionId(session.session_id);
    setView("configure");
  }

  function navigate(next: ViewId) {
    if (next !== "configure") setEditingSessionId(null);
    setView(next);
  }

  return (
    <div className="min-h-svh bg-background lg:grid lg:grid-cols-[240px_minmax(0,1fr)]">
      <aside className="border-b border-white/10 bg-sidebar text-sidebar-foreground lg:sticky lg:top-0 lg:h-svh lg:border-b-0 lg:border-r">
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between gap-3 px-4 py-4 lg:block lg:px-5 lg:py-6">
            <div className="flex items-center gap-2.5"><div className="flex size-9 items-center justify-center rounded-xl border border-white/10 bg-white/5"><Bot className="size-4" /></div><div><p className="text-sm font-semibold tracking-tight">AI Spot Trader</p><p className="text-[11px] text-sidebar-muted">Cockpit PAPER</p></div></div>
            <span className="rounded-full border border-white/15 bg-white/5 px-2 py-1 text-[10px] font-bold tracking-[0.16em] lg:mt-5 lg:inline-flex">PAPER ONLY</span>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-col lg:overflow-visible lg:px-3 lg:pb-0" aria-label="Navigation principale">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const active = item.id === view;
              return (
                <button key={item.id} type="button" onClick={() => navigate(item.id)} aria-current={active ? "page" : undefined} className={cn("group flex min-w-max items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors focus-visible:ring-offset-sidebar lg:min-w-0", active ? "bg-sidebar-active text-sidebar-active-foreground shadow-sm" : "text-sidebar-muted hover:bg-white/10 hover:text-sidebar-foreground")}>
                  <Icon className="size-4 shrink-0" />
                  <span className="min-w-0"><span className="block text-sm font-semibold">{item.label}</span><span className={cn("hidden truncate text-[11px] lg:block", active ? "text-muted-foreground" : "text-sidebar-muted")}>{item.description}</span></span>
                </button>
              );
            })}
          </nav>
          <div className="mt-auto hidden px-5 pb-5 lg:block"><div className="rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-sidebar-muted"><p className="font-semibold text-sidebar-foreground">Principe central</p><p className="mt-1 leading-relaxed">L’IA propose. Le Risk Engine autorise, modifie ou refuse.</p></div></div>
        </div>
      </aside>

      <div className="min-w-0 bg-[radial-gradient(circle_at_top_right,color-mix(in_oklab,var(--primary)_7%,transparent),transparent_30rem)]">
        <header className="sticky top-0 z-30 border-b border-border/80 bg-background/90 backdrop-blur-xl supports-[backdrop-filter]:bg-background/75">
          <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-3 px-4 py-3 sm:px-6 xl:px-8">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2"><h1 className="text-lg font-semibold tracking-tight">{view === "configure" ? editingSession ? "Modifier la Session" : "Nouvelle session" : currentNav.label}</h1><Badge tone="info">PAPER</Badge><Badge tone={engineTone(engine?.status)}>{engineLabel(engine?.status)}</Badge></div>
                <p className="mt-1 truncate text-xs text-muted-foreground">{currentSession ? `${currentSession.name} · ${currentSession.configuration.paper_initial_capital} ${currentSession.configuration.paper_settlement_asset} · ${currentSession.configuration.llm_model.replace("gpt-5.6-", "")}` : "Aucune Session active"}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <ThemeToggle compact />
                {currentSession && engine?.configured && engine.status === "STOPPED" ? <Button size="sm" onClick={() => void control.startSession(currentSession.session_id)} disabled={busy}><Play className="size-3.5" /> Démarrer</Button> : null}
                {currentSession?.status === "RUNNING" ? <Button variant="destructive" size="sm" onClick={() => void control.stopSession(currentSession.session_id)} disabled={busy}><Square className="size-3.5" /> Arrêter</Button> : null}
              </div>
            </div>
            {control.feedback ? <div className={cn("flex flex-col gap-2 rounded-lg border px-3 py-2 text-xs sm:flex-row sm:items-center sm:justify-between", control.feedback.tone === "error" ? "border-destructive/30 bg-destructive-subtle text-destructive-subtle-foreground" : "border-success/30 bg-success-subtle text-success-foreground")}><span>{control.feedback.message}</span><button type="button" className="font-semibold underline underline-offset-2" onClick={() => control.setFeedback(null)}>Masquer</button></div> : null}
          </div>
        </header>

        <main className="min-w-0"><ViewContent view={view} control={control} editingSession={editingSession} onNavigate={navigate} onCreateSession={createSession} onEditSession={editSession} /></main>

        <footer className="mx-auto flex w-full max-w-[1500px] flex-col gap-1 border-t border-border/80 px-4 py-4 text-[11px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6 xl:px-8">
          <span>Backend = moteur de trading · Frontend = contrôle et visualisation uniquement.</span>
          <span className="flex items-center gap-1.5"><Server className="size-3" /> état Control Plane {formatTimestamp(control.lastUpdatedAt)}</span>
        </footer>
      </div>
    </div>
  );
}
