"use client";

import {
  BarChart3,
  Database,
  Gauge,
  ReceiptText,
  RefreshCw,
  TrendingDown,
  WalletCards,
} from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAnalytics } from "@/hooks/use-analytics";
import { formatDecimal, formatTimestamp } from "@/lib/api/format";

function formatPercent(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return new Intl.NumberFormat("fr-FR", {
    style: "percent",
    maximumFractionDigits: 3,
  }).format(parsed);
}

function MetricCard({
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
    <Card className="gap-4 py-5">
      <CardHeader className="flex-row items-start justify-between gap-4 px-5">
        <div className="space-y-1">
          <CardDescription>{label}</CardDescription>
          <CardTitle className="text-2xl tracking-tight">{value}</CardTitle>
        </div>
        <div className="rounded-lg border bg-muted/50 p-2 text-muted-foreground">{icon}</div>
      </CardHeader>
      <CardContent className="px-5 text-xs text-muted-foreground">{detail}</CardContent>
    </Card>
  );
}

export function AnalyticsPanel() {
  const { state, refreshing, refresh } = useAnalytics();
  const report = state.kind === "ready" ? state.data : null;
  const summary = report?.summary ?? null;
  const hasValuation = Boolean(summary && summary.valued_cycle_count > 0);

  return (
    <section className="border-t bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold tracking-tight">Analytics PAPER</h2>
              <Badge tone="info">Batch 12</Badge>
              {report && <Badge>{report.timezone}</Badge>}
            </div>
            <p className="text-sm text-muted-foreground">
              Métriques calculées par le backend à partir des faits durables. Aucun calcul de trading
              n’est exécuté dans le navigateur.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={refreshing}>
            <RefreshCw className={refreshing ? "size-3.5 animate-spin" : "size-3.5"} />
            Actualiser les analytics
          </Button>
        </div>

        {state.kind === "loading" && (
          <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            Chargement des analytics…
          </p>
        )}
        {state.kind === "unavailable" && (
          <p className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            {state.message}
          </p>
        )}
        {state.kind === "error" && (
          <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            {state.message}
          </p>
        )}

        {summary && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="P&L net"
                value={hasValuation ? formatDecimal(summary.net_pnl) : "—"}
                detail={
                  hasValuation
                    ? `Equity ${formatDecimal(summary.ending_equity)} · rendement ${formatPercent(
                        report?.daily.at(-1)?.cumulative_return_fraction,
                      )}`
                    : "Aucun cycle valorisable"
                }
                icon={<WalletCards className="size-5" />}
              />
              <MetricCard
                label="P&L brut"
                value={hasValuation ? formatDecimal(summary.gross_pnl) : "—"}
                detail="P&L net + frais + spread + slippage cumulés"
                icon={<BarChart3 className="size-5" />}
              />
              <MetricCard
                label="Drawdown max"
                value={hasValuation ? formatPercent(summary.max_drawdown_fraction) : "—"}
                detail={`${formatDecimal(summary.max_drawdown_value)} en valeur · equity nette`}
                icon={<TrendingDown className="size-5" />}
              />
              <MetricCard
                label="Exposition courante"
                value={hasValuation ? formatPercent(summary.current_exposure_fraction) : "—"}
                detail={`${formatDecimal(summary.current_exposure_value)} valorisé au dernier prix durable`}
                icon={<Gauge className="size-5" />}
              />
            </div>

            <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
              <Card>
                <CardHeader>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <CardTitle>Coûts & activité</CardTitle>
                      <CardDescription>Valeurs issues directement des fills PAPER persistés.</CardDescription>
                    </div>
                    <ReceiptText className="size-5 text-muted-foreground" />
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <dl className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3">
                    <div className="rounded-lg border p-3">
                      <dt className="text-xs text-muted-foreground">Frais</dt>
                      <dd className="mt-1 font-mono text-sm">{formatDecimal(summary.fees)}</dd>
                    </div>
                    <div className="rounded-lg border p-3">
                      <dt className="text-xs text-muted-foreground">Spread</dt>
                      <dd className="mt-1 font-mono text-sm">{formatDecimal(summary.spread_cost)}</dd>
                    </div>
                    <div className="rounded-lg border p-3">
                      <dt className="text-xs text-muted-foreground">Slippage</dt>
                      <dd className="mt-1 font-mono text-sm">{formatDecimal(summary.slippage_cost)}</dd>
                    </div>
                  </dl>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-lg border bg-muted/30 p-4">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Trades fillés</p>
                      <p className="mt-1 text-xl font-semibold">{summary.trade_count}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {summary.buy_trade_count} BUY · {summary.sell_trade_count} SELL
                      </p>
                    </div>
                    <div className="rounded-lg border bg-muted/30 p-4">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">Issues sans trade</p>
                      <p className="mt-1 text-sm font-medium">
                        HOLD {summary.hold_count} · REJECT {summary.reject_count}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        MODIFY {summary.modify_count} · FAILED {summary.failed_cycle_count}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <CardTitle>Performance quotidienne</CardTitle>
                      <CardDescription>Clôtures de journée UTC, sans look-ahead.</CardDescription>
                    </div>
                    <Database className="size-5 text-muted-foreground" />
                  </div>
                </CardHeader>
                <CardContent>
                  {report && report.daily.length > 0 ? (
                    <div className="overflow-x-auto rounded-lg border">
                      <table className="min-w-[760px] w-full text-sm">
                        <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                          <tr>
                            <th className="px-3 py-2 font-medium">Jour UTC</th>
                            <th className="px-3 py-2 text-right font-medium">Equity</th>
                            <th className="px-3 py-2 text-right font-medium">P&L jour</th>
                            <th className="px-3 py-2 text-right font-medium">Perf. jour</th>
                            <th className="px-3 py-2 text-right font-medium">Perf. cumulée</th>
                            <th className="px-3 py-2 text-right font-medium">Trades</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {report.daily.slice(-14).map((item) => (
                            <tr key={item.day}>
                              <td className="px-3 py-2">
                                <div className="font-medium">{item.day}</div>
                                <div className="text-xs text-muted-foreground">
                                  {formatTimestamp(item.closing_at)}
                                </div>
                              </td>
                              <td className="px-3 py-2 text-right font-mono">
                                {formatDecimal(item.closing_equity)}
                              </td>
                              <td className="px-3 py-2 text-right font-mono">
                                {formatDecimal(item.daily_net_pnl)}
                              </td>
                              <td className="px-3 py-2 text-right">
                                {formatPercent(item.daily_return_fraction)}
                              </td>
                              <td className="px-3 py-2 text-right">
                                {formatPercent(item.cumulative_return_fraction)}
                              </td>
                              <td className="px-3 py-2 text-right">{item.trade_count}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                      Aucune série quotidienne valorisable.
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>

            {report && (
              <div className="flex flex-col gap-1 rounded-lg border bg-muted/20 p-3 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                <span>
                  Calcul {report.calculation_version} · {summary.valued_cycle_count} cycle(s) valorisé(s) / {summary.completed_cycle_count + summary.failed_cycle_count} journalisé(s)
                </span>
                <span className="font-mono" title={report.source_digest}>
                  source {report.source_digest.slice(0, 12)}…
                </span>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
