"use client";

import { CircleDollarSign, Gauge, RefreshCw, TrendingUp, WalletCards } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAnalytics } from "@/hooks/use-analytics";
import { useCockpit } from "@/hooks/use-cockpit";
import { formatDecimal, formatTimestamp } from "@/lib/api/format";

function formatPercent(value: string | null | undefined) {
  if (value === null || value === undefined) return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return new Intl.NumberFormat("fr-FR", { style: "percent", maximumFractionDigits: 2 }).format(parsed);
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
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Portefeuille PAPER</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight">Positions</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">Ce que le backend canonique détient actuellement, sans reconstruction de portefeuille dans le navigateur.</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={refreshing}>
          <RefreshCw className={refreshing ? "size-3.5 animate-spin" : "size-3.5"} /> Actualiser
        </Button>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="shadow-none"><CardHeader><CardDescription>Positions ouvertes</CardDescription><CardTitle className="text-2xl">{portfolio ? spotPositions.length + derivativePositions.length : "—"}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground"><WalletCards className="mb-2 size-4" />{spotPositions.length} SPOT · {derivativePositions.length} PERPETUAL</CardContent></Card>
        <Card className="shadow-none"><CardHeader><CardDescription>P&L net session</CardDescription><CardTitle className="text-2xl">{summary?.ending_equity ? formatDecimal(summary.net_pnl) : "—"}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground"><CircleDollarSign className="mb-2 size-4" />Calcul backend analytics</CardContent></Card>
        <Card className="shadow-none"><CardHeader><CardDescription>Exposition courante</CardDescription><CardTitle className="text-2xl">{formatPercent(summary?.current_exposure_fraction)}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground"><Gauge className="mb-2 size-4" />{summary ? formatDecimal(summary.current_exposure_value) : "—"} en valeur</CardContent></Card>
        <Card className="shadow-none"><CardHeader><CardDescription>Dernier marché</CardDescription><CardTitle className="text-2xl">{market?.symbol ?? "—"}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground"><TrendingUp className="mb-2 size-4" />{market ? `${formatDecimal(market.last_price)} · ${formatTimestamp(market.as_of)}` : "Aucun prix durable"}</CardContent></Card>
      </section>

      <Card className="shadow-none">
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><CardTitle>SPOT</CardTitle><CardDescription>Actifs effectivement détenus par le ledger PAPER backend.</CardDescription></div>
            <Badge tone="info">{spotPositions.length} position(s)</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {spotPositions.length ? (
            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full min-w-[760px] text-sm">
                <thead className="bg-muted/50 text-left text-xs text-muted-foreground"><tr><th className="px-4 py-3 font-medium">Actif</th><th className="px-4 py-3 text-right font-medium">Quantité</th><th className="px-4 py-3 text-right font-medium">Disponible</th><th className="px-4 py-3 text-right font-medium">Prix d’entrée</th><th className="px-4 py-3 text-right font-medium">Prix actuel</th><th className="px-4 py-3 text-right font-medium">P&L position</th></tr></thead>
                <tbody className="divide-y">
                  {spotPositions.map((position) => {
                    const currentPrice = market?.symbol.startsWith(`${position.asset}/`) ? market.last_price : null;
                    return <tr key={position.asset}><td className="px-4 py-3 font-semibold">{position.asset}</td><td className="px-4 py-3 text-right font-mono">{formatDecimal(position.quantity)}</td><td className="px-4 py-3 text-right font-mono">{formatDecimal(position.available)}</td><td className="px-4 py-3 text-right text-muted-foreground">—</td><td className="px-4 py-3 text-right font-mono">{currentPrice ? formatDecimal(currentPrice) : "—"}</td><td className="px-4 py-3 text-right text-muted-foreground">—</td></tr>;
                  })}
                </tbody>
              </table>
            </div>
          ) : <p className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">Aucune position SPOT ouverte.</p>}
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">Le contrat portefeuille SPOT canonique expose actuellement quantité et disponibilité, mais pas de coût moyen ni de P&L par position. Le cockpit n’invente donc pas ces valeurs : le P&L et l’exposition globaux restent ceux des analytics backend.</p>
        </CardContent>
      </Card>

      <Card className="shadow-none">
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><CardTitle>PERPETUAL</CardTitle><CardDescription>Positions dérivées linéaires exposées directement par le backend PAPER.</CardDescription></div>
            <Badge tone="warning">{derivativePositions.length} position(s)</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {derivativePositions.length ? (
            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full min-w-[1100px] text-sm">
                <thead className="bg-muted/50 text-left text-xs text-muted-foreground"><tr><th className="px-3 py-3 font-medium">Marché</th><th className="px-3 py-3 font-medium">Sens</th><th className="px-3 py-3 text-right font-medium">Quantité</th><th className="px-3 py-3 text-right font-medium">Entrée</th><th className="px-3 py-3 text-right font-medium">Mark</th><th className="px-3 py-3 text-right font-medium">P&L latent</th><th className="px-3 py-3 text-right font-medium">Notional</th><th className="px-3 py-3 text-right font-medium">Levier</th><th className="px-3 py-3 text-right font-medium">Marge</th><th className="px-3 py-3 text-right font-medium">Liquidation</th></tr></thead>
                <tbody className="divide-y">
                  {derivativePositions.map((position) => <tr key={`${position.symbol}-${position.side}`}><td className="px-3 py-3 font-semibold">{position.symbol}</td><td className="px-3 py-3"><Badge tone={position.side === "LONG" ? "success" : "warning"}>{position.side}</Badge></td><td className="px-3 py-3 text-right font-mono">{formatDecimal(position.quantity)}</td><td className="px-3 py-3 text-right font-mono">{formatDecimal(position.average_entry_price)}</td><td className="px-3 py-3 text-right font-mono">{formatDecimal(position.mark_price)}</td><td className="px-3 py-3 text-right font-mono">{formatDecimal(position.unrealized_pnl)}</td><td className="px-3 py-3 text-right font-mono">{formatDecimal(position.notional)}</td><td className="px-3 py-3 text-right">{formatDecimal(position.leverage)}×</td><td className="px-3 py-3 text-right font-mono">{formatDecimal(position.margin_used)}</td><td className="px-3 py-3 text-right font-mono">{position.liquidation_price ? formatDecimal(position.liquidation_price) : "—"}</td></tr>)}
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
