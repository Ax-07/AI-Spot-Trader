"use client";

import {
  Activity,
  AlertTriangle,
  BarChart3,
  BookOpenText,
  Bot,
  ChartNoAxesCombined,
  CircleDollarSign,
  CircleHelp,
  Gauge,
  LayoutDashboard,
  MessageSquareText,
  Play,
  RefreshCw,
  Server,
  Settings2,
  ShieldCheck,
  Square,
  WalletCards,
  Waves,
} from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

import { AnalyticsPanel } from "@/components/cockpit/analytics-panel";
import { ChatPanel } from "@/components/cockpit/chat-panel";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";
import { ControlPlanePanel } from "@/components/cockpit/control-plane-panel";
import { OperatorGuide } from "@/components/cockpit/operator-guide";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAnalytics } from "@/hooks/use-analytics";
import { useCockpit } from "@/hooks/use-cockpit";
import { useControlPlane } from "@/hooks/use-control-plane";
import { formatDecimal, formatFailure, formatTimestamp, shortUuid } from "@/lib/api/format";
import { cn } from "@/lib/utils";

type ViewId = "overview" | "guide" | "control" | "activity" | "analytics" | "assistant";
type ControlPlaneController = ReturnType<typeof useControlPlane>;

type NavItem = {
  id: ViewId;
  label: string;
  description: string;
  icon: typeof LayoutDashboard;
};

const NAV_ITEMS: NavItem[] = [
  {
    id: "overview",
    label: "Vue d’ensemble",
    description: "Statut, activité et décisions",
    icon: LayoutDashboard,
  },
  {
    id: "guide",
    label: "Guide",
    description: "Démarrage et notions clés",
    icon: BookOpenText,
  },
  {
    id: "control",
    label: "Pilotage",
    description: "Strategies, Campaigns et moteur",
    icon: Settings2,
  },
  {
    id: "activity",
    label: "Activité",
    description: "Cycles, Risk et exécutions",
    icon: Activity,
  },
  {
    id: "analytics",
    label: "Performance",
    description: "P&L, coûts et drawdown",
    icon: ChartNoAxesCombined,
  },
  {
    id: "assistant",
    label: "Assistant",
    description: "Chat opérateur informatif",
    icon: MessageSquareText,
  },
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

function engineTone(status: string | null | undefined) {
  if (status === "RUNNING") return "success" as const;
  if (status === "STOPPED") return "neutral" as const;
  return "danger" as const;
}

function actionTone(action: string | null | undefined) {
  if (action === "BUY") return "success" as const;
  if (action === "SELL") return "danger" as const;
  if (action === "HOLD") return "neutral" as const;
  return "neutral" as const;
}

function riskTone(status: string | null | undefined) {
  if (status === "ALLOW") return "success" as const;
  if (status === "MODIFY") return "warning" as const;
  if (status === "REJECT") return "danger" as const;
  return "neutral" as const;
}

function KpiCard({
  label,
  value,
  detail,
  icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: ReactNode;
}) {
  return (
    <Card className="gap-3 py-5 shadow-none">
      <CardHeader className="flex-row items-start justify-between gap-4 px-5">
        <div className="min-w-0 space-y-1.5">
          <CardDescription className="text-xs font-semibold uppercase tracking-[0.12em]">
            {label}
          </CardDescription>
          <CardTitle className="truncate text-2xl tracking-tight">{value}</CardTitle>
        </div>
        <div className="rounded-xl border bg-muted/45 p-2.5 text-muted-foreground">{icon}</div>
      </CardHeader>
      <CardContent className="px-5 text-xs leading-relaxed text-muted-foreground">
        {detail}
      </CardContent>
    </Card>
  );
}

function EmptyLine({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed px-4 py-5 text-sm text-muted-foreground">
      {children}
    </div>
  );
}

function ContextHelp({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="group rounded-lg border bg-muted/15 px-3 py-2 text-xs text-muted-foreground">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-foreground marker:hidden">
        <CircleHelp className="size-3.5" />
        {summary}
      </summary>
      <div className="pt-2 leading-relaxed">{children}</div>
    </details>
  );
}

function Overview({
  control,
  onNavigate,
}: {
  control: ControlPlaneController;
  onNavigate: (view: ViewId) => void;
}) {
  const cockpit = useCockpit();
  const analytics = useAnalytics();
  const [refreshingAll, setRefreshingAll] = useState(false);

  const health = cockpit.resources.health.kind === "ready" ? cockpit.resources.health.data : null;
  const market = cockpit.resources.market.kind === "ready" ? cockpit.resources.market.data : null;
  const portfolio =
    cockpit.resources.portfolio.kind === "ready" ? cockpit.resources.portfolio.data : null;
  const latestCycle =
    cockpit.resources.latestCycle.kind === "ready" ? cockpit.resources.latestCycle.data : null;
  const latestError =
    cockpit.resources.latestError.kind === "ready" ? cockpit.resources.latestError.data : null;
  const decisions =
    cockpit.resources.decisions.kind === "ready" ? cockpit.resources.decisions.data.items : [];
  const analyticsReport = analytics.state.kind === "ready" ? analytics.state.data : null;
  const summary = analyticsReport?.summary ?? null;
  const activeCampaign = control.activeCampaign?.campaign ?? null;
  const activePaperRun = control.activeCampaign?.paper_run_id ?? null;
  const activeStrategy = activeCampaign
    ? control.strategies.find((item) => item.strategy_id === activeCampaign.strategy_id) ?? null
    : null;
  const engine = control.engine;
  const commandBusy = control.busyAction?.startsWith("engine-") ?? false;

  const riskByDecision = useMemo<Map<string, string | null | undefined>>(() => {
    const riskAssessments =
      cockpit.resources.riskAssessments.kind === "ready"
        ? cockpit.resources.riskAssessments.data.items
        : [];
    return new Map(riskAssessments.map((item) => [item.decision_id, item.status]));
  }, [cockpit.resources.riskAssessments]);

  const alertItems = useMemo(() => {
    const items: Array<{ key: string; tone: "warning" | "danger"; title: string; detail: string }> = [];
    if (!health && cockpit.resources.health.kind !== "loading") {
      items.push({
        key: "backend",
        tone: "danger",
        title: "Backend inaccessible",
        detail: "Le cockpit ne peut plus lire le moteur ni les états durables.",
      });
    }
    if (!engine?.configured && control.loading === false) {
      items.push({
        key: "engine",
        tone: "warning",
        title: "Aucun runtime Campaign actif",
        detail: "Active ou reprends explicitement une Campaign avant de lancer un cycle.",
      });
    }
    if (latestCycle?.failure) {
      items.push({
        key: "cycle-failure",
        tone: "danger",
        title: "Dernier cycle en échec",
        detail: formatFailure(latestCycle.failure),
      });
    }
    if (latestError) {
      items.push({
        key: `error-${latestError.cycle_id}`,
        tone: "danger",
        title: "Erreur technique persistée",
        detail: `${formatFailure(latestError.failure)} · cycle ${shortUuid(latestError.cycle_id)}`,
      });
    }
    if (control.feedback?.tone === "error") {
      items.push({
        key: "control-feedback",
        tone: "danger",
        title: "Refus ou erreur Control Plane",
        detail: control.feedback.message,
      });
    }
    return items;
  }, [cockpit.resources.health.kind, control.feedback, control.loading, engine, health, latestCycle, latestError]);

  async function refreshAll() {
    if (refreshingAll) return;
    setRefreshingAll(true);
    try {
      await Promise.all([cockpit.refresh(), analytics.refresh(), control.refresh()]);
    } finally {
      setRefreshingAll(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-[1580px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Cockpit opérateur
          </p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight">Vue d’ensemble</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Les informations utiles pour décider quoi faire maintenant, sans mélanger configuration,
            audit technique et pilotage du moteur.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refreshAll()} disabled={refreshingAll}>
          <RefreshCw className={refreshingAll ? "size-3.5 animate-spin" : "size-3.5"} />
          Actualiser la vue
        </Button>
      </div>

      <Card className="border-foreground/10 bg-background shadow-none">
        <CardContent className="grid gap-4 py-5 lg:grid-cols-[1fr_auto] lg:items-center">
          <div>
            <div className="flex items-center gap-2">
              <BookOpenText className="size-4" />
              <p className="font-semibold">Premier test PAPER</p>
            </div>
            <div className="mt-3 grid gap-3 text-xs text-muted-foreground sm:grid-cols-3">
              <div className="rounded-lg border bg-muted/20 p-3">
                <p className="font-semibold text-foreground">1 · Préparer</p>
                <p className="mt-1 leading-relaxed">Strategy → StrategyRevision → Campaign.</p>
              </div>
              <div className="rounded-lg border bg-muted/20 p-3">
                <p className="font-semibold text-foreground">2 · Vérifier</p>
                <p className="mt-1 leading-relaxed">Marchés, capital, modèle, coûts et paramètres Risk.</p>
              </div>
              <div className="rounded-lg border bg-muted/20 p-3">
                <p className="font-semibold text-foreground">3 · Exécuter & lire</p>
                <p className="mt-1 leading-relaxed">Activer, run-cycle ou Start, puis lire Agent → Risk → PAPER.</p>
              </div>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => onNavigate("guide")}>
            <BookOpenText className="size-3.5" /> Ouvrir le guide
          </Button>
        </CardContent>
      </Card>

      <section className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-4">
        <KpiCard
          label="P&L net PAPER"
          value={summary?.ending_equity !== null && summary?.ending_equity !== undefined ? formatDecimal(summary.net_pnl) : "—"}
          detail={
            summary?.ending_equity
              ? `Equity ${formatDecimal(summary.ending_equity)} · ${summary.trade_count} trade(s) fillé(s)`
              : "En attente de cycles valorisables par les analytics backend."
          }
          icon={<CircleDollarSign className="size-5" />}
        />
        <KpiCard
          label="Drawdown max"
          value={formatPercent(summary?.max_drawdown_fraction)}
          detail={
            summary
              ? `${formatDecimal(summary.max_drawdown_value)} en valeur · calcul backend`
              : "Aucune mesure disponible pour le PAPER run courant."
          }
          icon={<BarChart3 className="size-5" />}
        />
        <KpiCard
          label="Exposition courante"
          value={formatPercent(summary?.current_exposure_fraction)}
          detail={
            summary
              ? `${formatDecimal(summary.current_exposure_value)} valorisé au dernier prix durable`
              : "Aucune exposition valorisable disponible."
          }
          icon={<Gauge className="size-5" />}
        />
        <KpiCard
          label="Activité"
          value={summary ? `${summary.trade_count} trade${summary.trade_count > 1 ? "s" : ""}` : "—"}
          detail={
            summary
              ? `${summary.hold_count} HOLD · ${summary.modify_count} MODIFY · ${summary.failed_cycle_count} échec(s)`
              : "Les décisions restent consultables même sans exécution."
          }
          icon={<WalletCards className="size-5" />}
        />
      </section>

      <section className="grid gap-6 2xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.55fr)]">
        <Card className="shadow-none">
          <CardHeader className="gap-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Waves className="size-4" /> Marché & activité
                </CardTitle>
                <CardDescription>
                  Dernier état durable réellement utilisé par le backend et contexte du cycle courant.
                </CardDescription>
              </div>
              {market ? (
                <div className="flex flex-wrap gap-2">
                  <Badge tone={market.market_type === "PERPETUAL" ? "warning" : "info"}>
                    {market.market_type}
                  </Badge>
                  <Badge>{market.symbol}</Badge>
                </div>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            {market ? (
              <>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-xl border bg-muted/20 p-4">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Marché</p>
                    <p className="mt-1 text-lg font-semibold">{market.symbol}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{market.market_type}</p>
                  </div>
                  <div className="rounded-xl border bg-muted/20 p-4">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Dernier prix</p>
                    <p className="mt-1 text-lg font-semibold tabular-nums">
                      {formatDecimal(market.last_price)}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">{formatTimestamp(market.as_of)}</p>
                  </div>
                  <div className="rounded-xl border bg-muted/20 p-4">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Dernier cycle</p>
                    <p className="mt-1 text-lg font-semibold">{latestCycle?.status ?? "—"}</p>
                    <p className="mt-1 font-mono text-xs text-muted-foreground">
                      {shortUuid(latestCycle?.cycle_id)}
                    </p>
                  </div>
                  <div className="rounded-xl border bg-muted/20 p-4">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Portefeuille</p>
                    <p className="mt-1 text-lg font-semibold">
                      {portfolio ? portfolio.positions.length + portfolio.derivative_positions.length : "—"}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">position(s) ouverte(s)</p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 text-sm">
                  <div>
                    <p className="font-medium">
                      {latestCycle?.failure ? "Cycle à investiguer" : "Flux durable disponible"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {latestCycle
                        ? `${formatTimestamp(latestCycle.recorded_at)} · PAPER run ${shortUuid(latestCycle.paper_run_id)}`
                        : "Aucun cycle durable n’a encore été journalisé."}
                    </p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => onNavigate("activity")}>
                    Voir l’activité détaillée
                  </Button>
                </div>
              </>
            ) : (
              <EmptyLine>
                {cockpit.resources.market.kind === "loading"
                  ? "Chargement du dernier marché durable…"
                  : "Aucun marché durable disponible pour le moment."}
              </EmptyLine>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Play className="size-4" /> Actions rapides
            </CardTitle>
            <CardDescription>Commandes explicites. Le moteur reste entièrement côté backend.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button
              className="w-full justify-start"
              variant="outline"
              onClick={() => void control.runCycle()}
              disabled={!engine?.configured || engine.status === "RUNNING" || commandBusy}
            >
              <Activity className="size-4" /> Exécuter un cycle
            </Button>
            <Button
              className="w-full justify-start"
              onClick={() => void control.startEngine()}
              disabled={!engine?.configured || engine.status === "RUNNING" || commandBusy}
            >
              <Play className="size-4" /> Démarrer la boucle backend
            </Button>
            <Button
              className="w-full justify-start"
              variant="destructive"
              onClick={() => void control.stopEngine()}
              disabled={!engine?.configured || engine.status !== "RUNNING" || commandBusy}
            >
              <Square className="size-4" /> Arrêter explicitement
            </Button>
            <ContextHelp summary="run-cycle ou Start ?">
              <p>
                <strong className="text-foreground">run-cycle</strong> exécute un seul cycle puis laisse
                le moteur STOPPED. <strong className="text-foreground">Start</strong> lance la boucle
                autonome backend à la cadence de la Campaign jusqu’à Stop.
              </p>
            </ContextHelp>
            <div className="my-3 border-t" />
            <Button className="w-full justify-start" variant="ghost" onClick={() => onNavigate("control")}>
              <Settings2 className="size-4" /> Configurer Strategy / Campaign
            </Button>
            <Button className="w-full justify-start" variant="ghost" onClick={() => onNavigate("analytics")}>
              <ChartNoAxesCombined className="size-4" /> Ouvrir la performance
            </Button>
            <p className="pt-1 text-xs leading-relaxed text-muted-foreground">
              Fermer ou recharger le frontend n’arrête jamais le TradingEngine. Seul le bouton Stop
              envoie une commande d’arrêt au backend.
            </p>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="size-4" /> Dernières décisions de l’IA
            </CardTitle>
            <CardDescription>
              Décisions stratégiques journalisées ; le statut Risk est affiché séparément.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {decisions.length ? (
              <div className="overflow-hidden rounded-xl border">
                <div className="divide-y">
                  {decisions.slice(0, 6).map((decision) => {
                    const riskStatus = riskByDecision.get(decision.decision_id);
                    return (
                      <div
                        key={decision.decision_id}
                        className="grid gap-3 px-4 py-3 sm:grid-cols-[auto_minmax(120px,0.6fr)_minmax(140px,1fr)_auto] sm:items-center"
                      >
                        <Badge tone={actionTone(decision.action)}>{decision.action}</Badge>
                        <div>
                          <p className="text-sm font-semibold">{decision.symbol}</p>
                          <p className="font-mono text-[11px] text-muted-foreground">
                            {shortUuid(decision.cycle_id)}
                          </p>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {formatTimestamp(decision.created_at)}
                        </p>
                        <Badge tone={riskTone(riskStatus)}>Risk {riskStatus ?? "—"}</Badge>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <EmptyLine>Aucune décision IA journalisée pour le moment.</EmptyLine>
            )}
            <ContextHelp summary="HOLD et résultat Risk">
              <p>
                HOLD signifie que l’Agent ne propose aucun trade pour ce cycle : c’est une décision
                normale et journalisée. Pour BUY/SELL, Risk peut ALLOW, MODIFY la proposition ou REJECT
                l’exécution. L’IA ne déclenche jamais directement le Broker PAPER.
              </p>
            </ContextHelp>
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="size-4" /> Alertes système & backend
            </CardTitle>
            <CardDescription>Les refus backend restent visibles et ne sont jamais contournés par l’UI.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {alertItems.length ? (
              alertItems.slice(0, 5).map((item) => (
                <div
                  key={item.key}
                  className={cn(
                    "rounded-xl border p-3",
                    item.tone === "danger"
                      ? "border-red-200 bg-red-50 text-red-900"
                      : "border-amber-200 bg-amber-50 text-amber-900",
                  )}
                >
                  <p className="text-sm font-semibold">{item.title}</p>
                  <p className="mt-1 text-xs leading-relaxed opacity-80">{item.detail}</p>
                </div>
              ))
            ) : (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-900">
                <div className="flex items-center gap-2 font-semibold">
                  <ShieldCheck className="size-4" /> Aucun signal à traiter
                </div>
                <p className="mt-1 text-xs text-emerald-800">
                  Backend lisible, aucun échec de cycle récent et aucun refus Control Plane en attente.
                </p>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3 pt-1">
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Backend</p>
                <p className="mt-1 text-sm font-semibold">{health ? "ONLINE" : "OFFLINE"}</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Moteur</p>
                <p className="mt-1 text-sm font-semibold">{engine?.status ?? "UNAVAILABLE"}</p>
              </div>
            </div>
            <ContextHelp summary="Comprendre l’état moteur">
              <p>
                STOPPED = runtime disponible mais boucle arrêtée. RUNNING = boucle backend active.
                UNAVAILABLE = aucun runtime Campaign contrôlable, notamment après un redémarrage avant
                activation ou reprise explicite.
              </p>
            </ContextHelp>
          </CardContent>
        </Card>
      </section>

      <Card className="shadow-none">
        <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-semibold">Contexte actif</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {activeCampaign
                ? `${activeStrategy?.strategy_name ?? shortUuid(activeCampaign.strategy_id)} · r${activeCampaign.strategy_revision} · ${activeCampaign.configuration.llm_model} · PAPER run ${shortUuid(activePaperRun)}`
                : "Aucune Campaign active. Le cockpit reste en lecture et le moteur n’est pas repris silencieusement."}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => onNavigate("control")}>
            Ouvrir le pilotage
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function ViewContent({
  view,
  control,
  onNavigate,
}: {
  view: ViewId;
  control: ControlPlaneController;
  onNavigate: (view: ViewId) => void;
}) {
  if (view === "overview") return <Overview control={control} onNavigate={onNavigate} />;
  if (view === "guide") return <OperatorGuide />;
  if (view === "control") return <ControlPlanePanel />;
  if (view === "analytics") return <AnalyticsPanel />;
  if (view === "assistant") return <ChatPanel />;
  return (
    <div className="[&>main]:min-h-0 [&>main>header]:hidden [&>main>div]:pt-6">
      <CockpitDashboard />
    </div>
  );
}

export function CockpitShell() {
  const [view, setView] = useState<ViewId>("overview");
  const control = useControlPlane();
  const currentNav = NAV_ITEMS.find((item) => item.id === view) ?? NAV_ITEMS[0];
  const activeCampaign = control.activeCampaign?.campaign ?? null;
  const activeStrategy = activeCampaign
    ? control.strategies.find((item) => item.strategy_id === activeCampaign.strategy_id) ?? null
    : null;
  const engine = control.engine;
  const commandBusy = control.busyAction?.startsWith("engine-") ?? false;
  const marketTypes = activeCampaign
    ? Array.from(new Set(activeCampaign.configuration.paper_executable_markets.map((item) => item.market_type)))
    : [];

  return (
    <div className="min-h-svh bg-muted/20 lg:grid lg:grid-cols-[250px_minmax(0,1fr)]">
      <aside className="border-b bg-foreground text-background lg:sticky lg:top-0 lg:h-svh lg:border-b-0 lg:border-r">
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between gap-3 px-4 py-4 lg:block lg:px-5 lg:py-6">
            <div>
              <div className="flex items-center gap-2">
                <div className="flex size-8 items-center justify-center rounded-lg bg-background/10">
                  <Bot className="size-4" />
                </div>
                <div>
                  <p className="text-sm font-semibold tracking-tight">AI Spot Trader</p>
                  <p className="text-[11px] text-background/60">Cockpit opérateur</p>
                </div>
              </div>
            </div>
            <span className="rounded-full border border-background/20 bg-background/10 px-2 py-1 text-[10px] font-bold tracking-[0.16em] lg:mt-5 lg:inline-flex">
              PAPER
            </span>
          </div>

          <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-col lg:overflow-visible lg:px-3 lg:pb-0">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const active = item.id === view;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setView(item.id)}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "group flex min-w-max items-center gap-3 rounded-lg px-3 py-2.5 text-left transition lg:min-w-0",
                    active
                      ? "bg-background text-foreground"
                      : "text-background/70 hover:bg-background/10 hover:text-background",
                  )}
                >
                  <Icon className="size-4 shrink-0" />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{item.label}</span>
                    <span
                      className={cn(
                        "hidden truncate text-[11px] lg:block",
                        active ? "text-muted-foreground" : "text-background/45",
                      )}
                    >
                      {item.description}
                    </span>
                  </span>
                </button>
              );
            })}
          </nav>

          <div className="mt-auto hidden px-5 pb-5 lg:block">
            <div className="rounded-xl border border-background/15 bg-background/5 p-3 text-xs text-background/65">
              <p className="font-semibold text-background/90">Frontend = cockpit</p>
              <p className="mt-1 leading-relaxed">
                Aucune logique de trading ou de Risk n’est exécutée dans cette interface.
              </p>
            </div>
          </div>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/85">
          <div className="mx-auto flex w-full max-w-[1580px] flex-col gap-4 px-4 py-4 sm:px-6 xl:px-8">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-lg font-semibold tracking-tight">{currentNav.label}</h1>
                  <Badge tone="info">PAPER</Badge>
                  <Badge tone={engineTone(engine?.status)}>{engine?.status ?? "UNAVAILABLE"}</Badge>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span>
                    {activeCampaign
                      ? `Campaign ${shortUuid(activeCampaign.campaign_id)} · ${activeStrategy?.strategy_name ?? shortUuid(activeCampaign.strategy_id)} r${activeCampaign.strategy_revision}`
                      : "Aucune Campaign active"}
                  </span>
                  {activeCampaign ? <span>· {activeCampaign.configuration.llm_model}</span> : null}
                  {marketTypes.map((marketType) => (
                    <span key={marketType}>· {marketType}</span>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void control.runCycle()}
                  disabled={!engine?.configured || engine.status === "RUNNING" || commandBusy}
                >
                  <Activity className="size-3.5" /> Run cycle
                </Button>
                <Button
                  size="sm"
                  onClick={() => void control.startEngine()}
                  disabled={!engine?.configured || engine.status === "RUNNING" || commandBusy}
                >
                  <Play className="size-3.5" /> Start
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => void control.stopEngine()}
                  disabled={!engine?.configured || engine.status !== "RUNNING" || commandBusy}
                >
                  <Square className="size-3.5" /> Stop
                </Button>
              </div>
            </div>

            {control.feedback ? (
              <div
                className={cn(
                  "flex flex-col gap-2 rounded-lg border px-3 py-2 text-xs sm:flex-row sm:items-center sm:justify-between",
                  control.feedback.tone === "error"
                    ? "border-red-200 bg-red-50 text-red-800"
                    : "border-emerald-200 bg-emerald-50 text-emerald-800",
                )}
              >
                <span>{control.feedback.message}</span>
                <button
                  type="button"
                  className="font-semibold underline underline-offset-2"
                  onClick={() => control.setFeedback(null)}
                >
                  Masquer
                </button>
              </div>
            ) : null}
          </div>
        </header>

        <div className="min-w-0" role="main">
          <ViewContent view={view} control={control} onNavigate={setView} />
        </div>

        <footer className="mx-auto flex w-full max-w-[1580px] flex-col gap-1 border-t px-4 py-4 text-[11px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6 xl:px-8">
          <span>Backend = moteur de trading · Frontend = contrôle et visualisation uniquement.</span>
          <span className="flex items-center gap-1.5">
            <Server className="size-3" /> lecture Control Plane {formatTimestamp(control.lastUpdatedAt)}
          </span>
        </footer>
      </div>
    </div>
  );
}
