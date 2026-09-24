"use client";

import { CircleDollarSign, Gauge, RefreshCw, TrendingUp, WalletCards } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAnalytics } from "@/hooks/use-analytics";
import { useCockpit } from "@/hooks/use-cockpit";
import { formatDecimal, formatTimestamp } from "@/lib/api/format";
import { cn } from "@/lib/utils";

function formatPercent(value: string | null | undefined) {
  if (value === null || value === undefined) return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return new Intl.NumberFormat("fr-FR", { style: "percent", maximumFractionDigits: 2 }).format(parsed);
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

function pnlClass(value: string | number | null | undefined) {
  const parsed = typeof value === "number" ? value : Number(value ?? 0);
  if (!Number.isFinite(parsed) || parsed === 0) return "text-foreground";
  return parsed > 0 ? "text-success-foreground" : "text-destructive-subtle-foreground";
}

export function PositionsPanel() {
  const cockpit = useCockpit();
  const analytics = useAnalytics();
  const portfolio = cockpit.resources.portfolio.kind === "ready" ? cockpit.resources.portfolio.data : null;
  const market = cockpit.resources.market.kind === "ready" ? cockpit.resources.market.data : null;
  const summary = analytics.state.kind === "ready" ? analytics.state.data.summary : null;
  const refreshing = cockpit.refreshing || analytics.refreshing;
  const spotPositions = portfolio?.positions ?? [];
  const derivativePositions = portfolio?.derivative_positions ?? [];

  async function refresh() {
    await Promise.all([cockpit.refresh(), analytics.refresh()]);
  }

  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Portefeuille PAPER</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight">Positions</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">Ce que le backend canonique détient actuellement, sans reconstruction de portefeuille dans le navigateur.</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={refreshing}>
          <RefreshCw className={refreshing ? "size-3.5 animate-spin" : "size-3.5"} /> Actualiser
        </Button>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card><CardHeader><CardDescription>Positions ouvertes</CardDescription><CardTitle className="text-2xl">{portfolio ? spotPositions.length + derivativePositions.length : "—"}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground"><WalletCards className="mb-2 size-4" />{spotPositions.length} SPOT · {derivativePositions.length} PERPETUAL</CardContent></Card>
        <Card><CardHeader><CardDescription>P&L net session</CardDescription><CardTitle className={cn("text-2xl", summary?.ending_equity ? pnlClass(summary.net_pnl) : undefined)}>{summary?.ending_equity ? signedDecimal(summary.net_pnl) : "—"}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground"><CircleDollarSign className="mb-2 size-4" />Signe +/− et calcul backend analytics</CardContent></Card>
        <Card><CardHeader><CardDescription>Exposition courante</CardDescription><CardTitle className="text-2xl">{formatPercent(summary?.current_exposure_fraction)}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground"><Gauge className="mb-2 size-4" />{summary ? formatDecimal(summary.current_exposure_value) : "—"} en valeur</CardContent></Card>
        <Card><CardHeader><CardDescription>Dernier marché</CardDescription><CardTitle className="text-2xl">{market?.symbol ?? "—"}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground"><TrendingUp className="mb-2 size-4" />{market ? `${formatDecimal(market.last_price)} · ${formatTimestamp(market.as_of)}` : "Aucun prix durable"}</CardContent></Card>
      </section>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><CardTitle>SPOT</CardTitle><CardDescription>Inventaire et comptabilité canonique du ledger PAPER backend.</CardDescription></div>
            <Badge tone="info">{spotPositions.length} position(s)</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {spotPositions.length ? (
            <div className="overflow-x-auto rounded-xl border border-border/80">
              <table className="w-full min-w-[1050px] text-sm">
                <thead className="bg-muted/60 text-left text-xs text-muted-foreground"><tr><th className="px-4 py-3 font-semibold">Actif</th><th className="px-4 py-3 text-right font-semibold">Quantité</th><th className="px-4 py-3 text-right font-semibold">Disponible</th><th className="px-4 py-3 text-right font-semibold">Coût moyen</th><th className="px-4 py-3 text-right font-semibold">Coût restant</th><th className="px-4 py-3 text-right font-semibold">Prix actuel</th><th className="px-4 py-3 text-right font-semibold">P&L réalisé</th><th className="px-4 py-3 text-right font-semibold">P&L latent</th></tr></thead>
                <tbody className="divide-y divide-border/80">
                  {spotPositions.map((position) => {
                    const currentPrice = market?.symbol.startsWith(`${position.asset}/`) ? market.last_price : null;
                    const accountingAvailable = position.accounting_complete;
                    return <tr key={position.asset} className="transition-colors hover:bg-muted/30"><td className="px-4 py-3 font-semibold">{position.asset}</td><td className="px-4 py-3 text-right font-mono tabular-nums">{formatDecimal(position.quantity)}</td><td className="px-4 py-3 text-right font-mono tabular-nums">{formatDecimal(position.available)}</td><td className="px-4 py-3 text-right font-mono tabular-nums">{accountingAvailable && position.average_entry_price ? formatDecimal(position.average_entry_price) : "—"}</td><td className="px-4 py-3 text-right font-mono tabular-nums">{accountingAvailable && position.remaining_cost_basis ? formatDecimal(position.remaining_cost_basis) : "—"}</td><td className="px-4 py-3 text-right font-mono tabular-nums">{currentPrice ? formatDecimal(currentPrice) : "—"}</td><td className={cn("px-4 py-3 text-right font-mono font-semibold tabular-nums", accountingAvailable ? pnlClass(position.realized_pnl) : "text-muted-foreground")}>{accountingAvailable ? signedDecimal(position.realized_pnl) : "—"}</td><td className="px-4 py-3 text-right text-muted-foreground">—</td></tr>;
                  })}
                </tbody>
              </table>
            </div>
          ) : <p className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">Aucune position SPOT ouverte.</p>}
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">Le coût moyen, le coût restant et le P&L réalisé proviennent directement du backend. Les anciennes positions récupérées sans historique comptable restent marquées indisponibles. Le P&L latent attend le mark-to-market canonique du Batch 19.2.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><CardTitle>PERPETUAL</CardTitle><CardDescription>Positions dérivées linéaires exposées directement par le backend PAPER.</CardDescription></div>
            <Badge tone="warning">{derivativePositions.length} position(s)</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {derivativePositions.length ? (
            <div className="overflow-x-auto rounded-xl border border-border/80">
              <table className="w-full min-w-[1100px] text-sm">
                <thead className="bg-muted/60 text-left text-xs text-muted-foreground"><tr><th className="px-3 py-3 font-semibold">Marché</th><th className="px-3 py-3 font-semibold">Sens</th><th className="px-3 py-3 text-right font-semibold">Quantité</th><th className="px-3 py-3 text-right font-semibold">Entrée</th><th className="px-3 py-3 text-right font-semibold">Mark</th><th className="px-3 py-3 text-right font-semibold">P&L latent</th><th className="px-3 py-3 text-right font-semibold">Notional</th><th className="px-3 py-3 text-right font-semibold">Levier</th><th className="px-3 py-3 text-right font-semibold">Marge</th><th className="px-3 py-3 text-right font-semibold">Liquidation</th></tr></thead>
                <tbody className="divide-y divide-border/80">
                  {derivativePositions.map((position) => <tr key={`${position.symbol}-${position.side}`} className="transition-colors hover:bg-muted/30"><td className="px-3 py-3 font-semibold">{position.symbol}</td><td className="px-3 py-3"><Badge tone={position.side === "LONG" ? "success" : "warning"}>{position.side}</Badge></td><td className="px-3 py-3 text-right font-mono tabular-nums">{formatDecimal(position.quantity)}</td><td className="px-3 py-3 text-right font-mono tabular-nums">{formatDecimal(position.average_entry_price)}</td><td className="px-3 py-3 text-right font-mono tabular-nums">{formatDecimal(position.mark_price)}</td><td className={cn("px-3 py-3 text-right font-mono font-semibold tabular-nums", pnlClass(position.unrealized_pnl))}>{signedDecimal(position.unrealized_pnl)}</td><td className="px-3 py-3 text-right font-mono tabular-nums">{formatDecimal(position.notional)}</td><td className="px-3 py-3 text-right">{formatDecimal(position.leverage)}×</td><td className="px-3 py-3 text-right font-mono tabular-nums">{formatDecimal(position.margin_used)}</td><td className="px-3 py-3 text-right font-mono tabular-nums">{position.liquidation_price ? formatDecimal(position.liquidation_price) : "—"}</td></tr>)}
                </tbody>
              </table>
            </div>
          ) : <p className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">Aucune position PERPETUAL ouverte.</p>}
        </CardContent>
      </Card>

      {portfolio ? <p className="text-xs text-muted-foreground">État portefeuille backend : {formatTimestamp(portfolio.as_of)} · mode {portfolio.mode}</p> : null}
    </div>
  );
}
