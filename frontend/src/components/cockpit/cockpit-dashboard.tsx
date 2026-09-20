"use client";

import {
  Activity,
  AlertTriangle,
  Bot,
  CircleDollarSign,
  Database,
  Play,
  RefreshCw,
  Server,
  ShieldCheck,
  Square,
  Waves,
} from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { contextEntries, formatDecimal, formatFailure, formatTimestamp, shortUuid } from "@/lib/api/format";
import type { CycleFailure } from "@/lib/api/types";
import { type ResourceState, useCockpit } from "@/hooks/use-cockpit";

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

function engineTone(status: string | null | undefined) {
  if (status === "RUNNING") return "success" as const;
  if (status === "STOPPED") return "neutral" as const;
  return "danger" as const;
}

function ResourceFallback({ state }: { state: ResourceState<unknown> }) {
  if (state.kind === "loading") {
    return <p className="text-sm text-muted-foreground">Chargement…</p>;
  }
  if (state.kind === "empty") {
    return <p className="text-sm text-muted-foreground">{state.message}</p>;
  }
  if (state.kind === "unavailable") {
    return <p className="text-sm text-amber-700">{state.message}</p>;
  }
  if (state.kind === "error") {
    return <p className="text-sm text-red-700">{state.message}</p>;
  }
  return null;
}

function SummaryCard({
  label,
  value,
  detail,
  icon,
  badge,
}: {
  label: string;
  value: string;
  detail: string;
  icon: ReactNode;
  badge?: ReactNode;
}) {
  return (
    <Card className="gap-4 py-5">
      <CardHeader className="flex-row items-start justify-between gap-4 px-5">
        <div className="space-y-1">
          <CardDescription>{label}</CardDescription>
          <CardTitle className="text-2xl tracking-tight">{value}</CardTitle>
        </div>
        <div className="rounded-lg border bg-muted/50 p-2 text-muted-foreground">{icon}</div>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-3 px-5 text-xs text-muted-foreground">
        <span className="truncate">{detail}</span>
        {badge}
      </CardContent>
    </Card>
  );
}

function FailureLine({ failure }: { failure: CycleFailure | null | undefined }) {
  if (!failure) return <span className="text-muted-foreground">Aucune erreur technique</span>;
  return <span className="text-red-700">{formatFailure(failure)}</span>;
}

function AuditStatus({ state }: { state: ResourceState<unknown> }) {
  if (state.kind === "ready" || state.kind === "empty") {
    return <Badge tone="success">disponible</Badge>;
  }
  if (state.kind === "loading") return <Badge>vérification</Badge>;
  if (state.kind === "unavailable") return <Badge tone="warning">non configuré</Badge>;
  return <Badge tone="danger">erreur</Badge>;
}

export function CockpitDashboard() {
  const {
    resources,
    refreshing,
    lastUpdatedAt,
    controlPending,
    controlError,
    refresh,
    startEngine,
    stopEngine,
  } = useCockpit();

  const engine = resources.engine.kind === "ready" ? resources.engine.data : null;
  const health = resources.health.kind === "ready" ? resources.health.data : null;
  const latestCycle = resources.latestCycle.kind === "ready" ? resources.latestCycle.data : null;
  const market = resources.market.kind === "ready" ? resources.market.data : null;
  const portfolio = resources.portfolio.kind === "ready" ? resources.portfolio.data : null;
  const latestError = resources.latestError.kind === "ready" ? resources.latestError.data : null;
  const cycles = resources.cycles.kind === "ready" ? resources.cycles.data : null;
  const decisions = resources.decisions.kind === "ready" ? resources.decisions.data : null;
  const riskAssessments =
    resources.riskAssessments.kind === "ready" ? resources.riskAssessments.data : null;
  const executions = resources.executions.kind === "ready" ? resources.executions.data : null;

  const backendAvailable = resources.health.kind === "ready";
  const startDisabled =
    !engine || !engine.configured || engine.status === "RUNNING" || !backendAvailable || controlPending !== null;
  const stopDisabled =
    !engine || !engine.configured || engine.status !== "RUNNING" || !backendAvailable || controlPending !== null;

  return (
    <main className="min-h-svh bg-background text-foreground">
      <header className="border-b bg-card/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-4 px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">AI Spot Trader</h1>
              <Badge tone="info">PAPER</Badge>
              <Badge>Cockpit Batch 11</Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              Observation et contrôle du backend canonique. Aucune logique de trading n’est exécutée ici.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <span>Actualisation auto · 10 s · onglet actif</span>
            <span className="hidden sm:inline">•</span>
            <span>Dernière lecture : {formatTimestamp(lastUpdatedAt)}</span>
            <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={refreshing}>
              <RefreshCw className={refreshing ? "size-3.5 animate-spin" : "size-3.5"} />
              Actualiser
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryCard
            label="Backend"
            value={health ? "ONLINE" : resources.health.kind === "loading" ? "…" : "OFFLINE"}
            detail={health ? `${health.service} · ${health.environment}` : "FastAPI non joignable"}
            icon={<Server className="size-5" />}
            badge={<Badge tone={health ? "success" : "danger"}>{health ? "ok" : "indisponible"}</Badge>}
          />
          <SummaryCard
            label="Moteur"
            value={engine?.status ?? "UNAVAILABLE"}
            detail={engine?.configured ? "TradingEngine injecté" : "Moteur non configuré"}
            icon={<Bot className="size-5" />}
            badge={<Badge tone={engineTone(engine?.status)}>{engine?.configured ? "configuré" : "non configuré"}</Badge>}
          />
          <SummaryCard
            label="Dernier cycle"
            value={latestCycle?.status ?? (resources.latestCycle.kind === "loading" ? "…" : "AUCUN")}
            detail={latestCycle ? `${shortUuid(latestCycle.cycle_id)} · ${formatTimestamp(latestCycle.recorded_at)}` : "Pas encore de cycle durable"}
            icon={<Activity className="size-5" />}
            badge={latestCycle?.failure ? <Badge tone="danger">échec</Badge> : <Badge>journal</Badge>}
          />
          <SummaryCard
            label="Marché durable"
            value={market?.symbol ?? (resources.market.kind === "loading" ? "…" : "AUCUN")}
            detail={market ? `${formatDecimal(market.last_price)} · ${formatTimestamp(market.as_of)}` : "Aucun snapshot marché persistant"}
            icon={<Waves className="size-5" />}
            badge={<AuditStatus state={resources.cycles} />}
          />
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-1.5">
                  <CardTitle>Contrôle moteur</CardTitle>
                  <CardDescription>
                    Start/Stop appellent exclusivement les endpoints lifecycle du Batch 10.
                  </CardDescription>
                </div>
                {engine && <Badge tone={engineTone(engine.status)}>{engine.status}</Badge>}
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              {resources.engine.kind === "ready" ? (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-lg border bg-muted/30 p-4">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Configuration</p>
                      <p className="mt-1 font-medium">{engine?.configured ? "Disponible" : "Non configurée"}</p>
                    </div>
                    <div className="rounded-lg border bg-muted/30 p-4">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Dernier cycle moteur</p>
                      <p className="mt-1 font-medium">{engine?.last_cycle_status ?? "—"}</p>
                      <p className="mt-1 font-mono text-xs text-muted-foreground">{shortUuid(engine?.last_cycle_id)}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <Button onClick={() => void startEngine()} disabled={startDisabled}>
                      <Play className="size-4" />
                      {controlPending === "start" ? "Démarrage…" : "Start"}
                    </Button>
                    <Button variant="destructive" onClick={() => void stopEngine()} disabled={stopDisabled}>
                      <Square className="size-4" />
                      {controlPending === "stop" ? "Arrêt…" : "Stop"}
                    </Button>
                  </div>
                  {!engine?.configured && (
                    <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                      Le backend répond, mais aucun TradingEngine contrôlable n’est injecté dans ce runtime.
                    </p>
                  )}
                  {controlError && (
                    <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{controlError}</p>
                  )}
                  <div className="border-t pt-4 text-sm">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Dernière anomalie moteur</p>
                    <p className="mt-1">
                      {engine?.last_unexpected_error_type ?? formatFailure(engine?.last_cycle_failure)}
                    </p>
                  </div>
                </>
              ) : (
                <ResourceFallback state={resources.engine} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardTitle>Disponibilité & dernière erreur</CardTitle>
                  <CardDescription>État du backend et du journal durable, sans stack trace.</CardDescription>
                </div>
                <Database className="size-5 text-muted-foreground" />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between rounded-lg border p-3">
                <div>
                  <p className="text-sm font-medium">FastAPI</p>
                  <p className="text-xs text-muted-foreground">GET /health</p>
                </div>
                <Badge tone={backendAvailable ? "success" : "danger"}>{backendAvailable ? "disponible" : "hors ligne"}</Badge>
              </div>
              <div className="flex items-center justify-between rounded-lg border p-3">
                <div>
                  <p className="text-sm font-medium">Audit store</p>
                  <p className="text-xs text-muted-foreground">Lecture cycles / décisions / Risk / exécutions</p>
                </div>
                <AuditStatus state={resources.cycles} />
              </div>
              <div className="rounded-lg border p-3">
                <div className="mb-2 flex items-center gap-2">
                  <AlertTriangle className="size-4 text-muted-foreground" />
                  <p className="text-sm font-medium">Dernière erreur technique persistée</p>
                </div>
                {latestError ? (
                  <div className="space-y-1 text-sm">
                    <p className="text-red-700">{formatFailure(latestError.failure)}</p>
                    <p className="font-mono text-xs text-muted-foreground">cycle {shortUuid(latestError.cycle_id)}</p>
                    <p className="text-xs text-muted-foreground">{formatTimestamp(latestError.recorded_at)}</p>
                  </div>
                ) : (
                  <ResourceFallback state={resources.latestError} />
                )}
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardTitle>Portefeuille PAPER</CardTitle>
                  <CardDescription>Snapshot courant fourni par le backend, sans calcul P&amp;L frontend.</CardDescription>
                </div>
                <CircleDollarSign className="size-5 text-muted-foreground" />
              </div>
            </CardHeader>
            <CardContent>
              {portfolio ? (
                <div className="space-y-5">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span>Snapshot {shortUuid(portfolio.portfolio_state_id)}</span>
                    <span>{formatTimestamp(portfolio.as_of)}</span>
                  </div>
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Balances</p>
                    {portfolio.balances.length ? (
                      <div className="overflow-hidden rounded-lg border">
                        <table className="w-full text-sm">
                          <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                            <tr><th className="px-3 py-2 font-medium">Actif</th><th className="px-3 py-2 text-right font-medium">Disponible</th></tr>
                          </thead>
                          <tbody className="divide-y">
                            {portfolio.balances.map((balance) => (
                              <tr key={balance.asset}><td className="px-3 py-2 font-medium">{balance.asset}</td><td className="px-3 py-2 text-right font-mono">{formatDecimal(balance.available)}</td></tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">Aucune balance.</p>}
                  </div>
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Positions</p>
                    {portfolio.positions.length ? (
                      <div className="overflow-hidden rounded-lg border">
                        <table className="w-full text-sm">
                          <thead className="bg-muted/50 text-left text-xs text-muted-foreground"><tr><th className="px-3 py-2 font-medium">Actif</th><th className="px-3 py-2 text-right font-medium">Quantité</th><th className="px-3 py-2 text-right font-medium">Vendable</th></tr></thead>
                          <tbody className="divide-y">
                            {portfolio.positions.map((position) => (
                              <tr key={position.asset}><td className="px-3 py-2 font-medium">{position.asset}</td><td className="px-3 py-2 text-right font-mono">{formatDecimal(position.quantity)}</td><td className="px-3 py-2 text-right font-mono">{formatDecimal(position.available)}</td></tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">Aucune position détenue.</p>}
                  </div>
                </div>
              ) : <ResourceFallback state={resources.portfolio} />}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardTitle>Dernier marché durable</CardTitle>
                  <CardDescription>Snapshot déjà utilisé par un cycle ; aucun appel Kraken depuis le navigateur.</CardDescription>
                </div>
                <Waves className="size-5 text-muted-foreground" />
              </div>
            </CardHeader>
            <CardContent>
              {market ? (
                <div className="space-y-5">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-lg border bg-muted/30 p-4"><p className="text-xs uppercase tracking-wide text-muted-foreground">Symbole</p><p className="mt-1 text-xl font-semibold">{market.symbol}</p></div>
                    <div className="rounded-lg border bg-muted/30 p-4"><p className="text-xs uppercase tracking-wide text-muted-foreground">Dernier prix</p><p className="mt-1 text-xl font-semibold tabular-nums">{formatDecimal(market.last_price)}</p></div>
                  </div>
                  <div className="text-sm"><p className="text-xs uppercase tracking-wide text-muted-foreground">Timestamp</p><p className="mt-1">{formatTimestamp(market.as_of)}</p><p className="mt-1 font-mono text-xs text-muted-foreground">{shortUuid(market.market_state_id)}</p></div>
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Contexte disponible</p>
                    {contextEntries(market.context).length ? (
                      <dl className="grid gap-2 sm:grid-cols-2">
                        {contextEntries(market.context).map(([key, value]) => (
                          <div key={key} className="rounded-md border p-3"><dt className="truncate text-xs text-muted-foreground">{key}</dt><dd className="mt-1 truncate text-sm font-medium" title={value}>{value}</dd></div>
                        ))}
                      </dl>
                    ) : <p className="text-sm text-muted-foreground">Aucun contexte additionnel exposé.</p>}
                  </div>
                </div>
              ) : <ResourceFallback state={resources.market} />}
            </CardContent>
          </Card>
        </section>

        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle>Cycles récents</CardTitle>
                <CardDescription>Lecture corrélée du journal durable. HOLD et REJECT restent des issues métier normales.</CardDescription>
              </div>
              <Activity className="size-5 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent>
            {cycles ? (
              cycles.items.length ? (
                <div className="overflow-x-auto rounded-lg border">
                  <table className="min-w-[850px] w-full text-sm">
                    <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                      <tr><th className="px-3 py-2 font-medium">Cycle</th><th className="px-3 py-2 font-medium">Statut</th><th className="px-3 py-2 font-medium">Décision</th><th className="px-3 py-2 font-medium">Risk</th><th className="px-3 py-2 font-medium">Exécution</th><th className="px-3 py-2 font-medium">Erreur</th><th className="px-3 py-2 font-medium">Journalisé</th></tr>
                    </thead>
                    <tbody className="divide-y">
                      {cycles.items.map((cycle) => (
                        <tr key={cycle.cycle_id} className="align-top">
                          <td className="px-3 py-3"><div className="font-mono text-xs">{shortUuid(cycle.cycle_id)}</div><div className="mt-1 text-xs text-muted-foreground">{cycle.symbol ?? "—"}</div></td>
                          <td className="px-3 py-3"><Badge tone={cycle.status === "FAILED" ? "danger" : "neutral"}>{cycle.status}</Badge></td>
                          <td className="px-3 py-3">{cycle.decision_action ? <Badge tone={actionTone(cycle.decision_action)}>{cycle.decision_action}</Badge> : "—"}</td>
                          <td className="px-3 py-3">{cycle.risk_status ? <Badge tone={riskTone(cycle.risk_status)}>{cycle.risk_status}</Badge> : "—"}</td>
                          <td className="px-3 py-3"><div>{cycle.execution_id ? shortUuid(cycle.execution_id) : "Aucun intent"}</div><div className="mt-1 text-xs text-muted-foreground">{cycle.fill_count} fill(s)</div></td>
                          <td className="px-3 py-3 text-xs"><FailureLine failure={cycle.failure} /></td>
                          <td className="px-3 py-3 whitespace-nowrap text-xs text-muted-foreground">{formatTimestamp(cycle.recorded_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">Aucun cycle journalisé.</p>
            ) : <ResourceFallback state={resources.cycles} />}
          </CardContent>
        </Card>

        <section className="grid gap-6 xl:grid-cols-3">
          <Card>
            <CardHeader><div className="flex items-start justify-between gap-4"><div><CardTitle>Décisions Agent</CardTitle><CardDescription>BUY / SELL / HOLD récents.</CardDescription></div><Bot className="size-5 text-muted-foreground" /></div></CardHeader>
            <CardContent>
              {decisions ? decisions.items.length ? <div className="divide-y rounded-lg border">{decisions.items.map((item) => <div key={item.decision_id} className="flex items-center justify-between gap-3 p-3"><div className="min-w-0"><div className="flex items-center gap-2"><Badge tone={actionTone(item.action)}>{item.action}</Badge><span className="font-medium">{item.symbol}</span></div><p className="mt-1 font-mono text-xs text-muted-foreground">{shortUuid(item.cycle_id)}</p></div><span className="whitespace-nowrap text-xs text-muted-foreground">{formatTimestamp(item.created_at)}</span></div>)}</div> : <p className="text-sm text-muted-foreground">Aucune décision.</p> : <ResourceFallback state={resources.decisions} />}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><div className="flex items-start justify-between gap-4"><div><CardTitle>Résultats Risk</CardTitle><CardDescription>ALLOW / MODIFY / REJECT récents.</CardDescription></div><ShieldCheck className="size-5 text-muted-foreground" /></div></CardHeader>
            <CardContent>
              {riskAssessments ? riskAssessments.items.length ? <div className="divide-y rounded-lg border">{riskAssessments.items.map((item) => <div key={item.risk_assessment_id} className="flex items-center justify-between gap-3 p-3"><div className="min-w-0"><Badge tone={riskTone(item.status)}>{item.status}</Badge><p className="mt-1 font-mono text-xs text-muted-foreground">{shortUuid(item.cycle_id)}</p></div><span className="whitespace-nowrap text-xs text-muted-foreground">{formatTimestamp(item.assessed_at)}</span></div>)}</div> : <p className="text-sm text-muted-foreground">Aucun résultat Risk.</p> : <ResourceFallback state={resources.riskAssessments} />}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><div className="flex items-start justify-between gap-4"><div><CardTitle>Exécutions & fills</CardTitle><CardDescription>Intents produits par Risk et fills PAPER.</CardDescription></div><Database className="size-5 text-muted-foreground" /></div></CardHeader>
            <CardContent>
              {executions ? executions.items.length ? <div className="divide-y rounded-lg border">{executions.items.map((item) => <div key={item.execution_id} className="p-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="flex items-center gap-2"><Badge tone={actionTone(item.action)}>{item.action}</Badge><span className="font-medium">{item.symbol}</span></div><p className="mt-1 text-xs text-muted-foreground">{item.fills.length} fill(s) · <span className="font-mono">{shortUuid(item.execution_id)}</span></p></div><span className="whitespace-nowrap text-xs text-muted-foreground">{formatTimestamp(item.created_at)}</span></div>{item.fills.length > 0 && <div className="mt-2 space-y-1 border-t pt-2">{item.fills.map((fill) => <div key={fill.fill_id} className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground"><span className="font-mono">fill {shortUuid(fill.fill_id)}</span><span>{formatTimestamp(fill.filled_at)}</span></div>)}</div>}</div>)}</div> : <p className="text-sm text-muted-foreground">Aucune exécution.</p> : <ResourceFallback state={resources.executions} />}
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
