"use client";

import { CircleDollarSign, Gauge, RefreshCw, TrendingUp, WalletCards } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
  const portfolio = cockpit.resources.portfolio.kind === "ready" ? cockpit.resources.portfolio.data : null;
  const refreshing = cockpit.refreshing;
  const spotPositions = portfolio?.positions ?? [];
  const derivativePositions = portfolio?.derivative_positions ?? [];

  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Portefeuille PAPER</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight">Positions</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            Valorisation canonique calculée par le backend. Le navigateur affiche les montants sans reconstruire le P&amp;L.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void cockpit.refresh()} disabled={refreshing}>
          <RefreshCw className={refreshing ? "size-3.5 animate-spin" : "size-3.5"} /> Actualiser
        </Button>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        <Card>
          <CardHeader><CardDescription>Positions ouvertes</CardDescription><CardTitle className="text-2xl">{portfolio ? spotPositions.length + derivativePositions.length : "—"}</CardTitle></CardHeader>
          <CardContent className="text-xs text-muted-foreground"><WalletCards className="mb-2 size-4" />{spotPositions.length} SPOT · {derivativePositions.length} PERPETUAL</CardContent>
        </Card>
        <Card>
          <CardHeader><CardDescription>Cash disponible</CardDescription><CardTitle className="text-2xl">{portfolio?.cash_available !== null && portfolio?.cash_available !== undefined ? formatDecimal(portfolio.cash_available) : "—"}</CardTitle></CardHeader>
          <CardContent className="text-xs text-muted-foreground"><CircleDollarSign className="mb-2 size-4" />{portfolio?.settlement_asset ?? "Actif de règlement indisponible"}</CardContent>
        </Card>
        <Card>
          <CardHeader><CardDescription>Valeur SPOT</CardDescription><CardTitle className="text-2xl">{portfolio?.spot_market_value_total !== null && portfolio?.spot_market_value_total !== undefined ? formatDecimal(portfolio.spot_market_value_total) : "—"}</CardTitle></CardHeader>
          <CardContent className="text-xs text-muted-foreground"><TrendingUp className="mb-2 size-4" />Somme des marks frais backend</CardContent>
        </Card>
        <Card>
          <CardHeader><CardDescription>P&amp;L latent SPOT</CardDescription><CardTitle className={cn("text-2xl", pnlClass(portfolio?.spot_unrealized_pnl_total))}>{signedDecimal(portfolio?.spot_unrealized_pnl_total)}</CardTitle></CardHeader>
          <CardContent className="text-xs text-muted-foreground"><CircleDollarSign className="mb-2 size-4" />Valeur de marché − coût restant</CardContent>
        </Card>
        <Card>
          <CardHeader><CardDescription>Equity</CardDescription><CardTitle className="text-2xl">{portfolio?.equity !== null && portfolio?.equity !== undefined ? formatDecimal(portfolio.equity) : "—"}</CardTitle></CardHeader>
          <CardContent className="text-xs text-muted-foreground"><WalletCards className="mb-2 size-4" />{portfolio?.valuation_complete ? "Valorisation complète" : "Valorisation incomplète"}</CardContent>
        </Card>
        <Card>
          <CardHeader><CardDescription>Exposition courante</CardDescription><CardTitle className="text-2xl">{formatPercent(portfolio?.exposure_fraction)}</CardTitle></CardHeader>
          <CardContent className="text-xs text-muted-foreground"><Gauge className="mb-2 size-4" />{portfolio?.exposure_value !== null && portfolio?.exposure_value !== undefined ? `${formatDecimal(portfolio.exposure_value)} en valeur` : "—"}</CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><CardTitle>SPOT</CardTitle><CardDescription>Inventaire, coût et mark-to-market produits par le ledger PAPER backend.</CardDescription></div>
            <Badge tone="info">{spotPositions.length} position(s)</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {spotPositions.length ? (
            <div className="overflow-x-auto rounded-xl border border-border/80">
              <table className="w-full min-w-[1320px] text-sm">
                <thead className="bg-muted/60 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Actif</th>
                    <th className="px-4 py-3 text-right font-semibold">Quantité</th>
                    <th className="px-4 py-3 text-right font-semibold">Disponible</th>
                    <th className="px-4 py-3 text-right font-semibold">Prix d&apos;entrée</th>
                    <th className="px-4 py-3 text-right font-semibold">Prix courant</th>
                    <th className="px-4 py-3 text-right font-semibold">Valeur position</th>
                    <th className="px-4 py-3 text-right font-semibold">Coût restant</th>
                    <th className="px-4 py-3 text-right font-semibold">P&amp;L réalisé</th>
                    <th className="px-4 py-3 text-right font-semibold">P&amp;L latent</th>
                    <th className="px-4 py-3 text-right font-semibold">Valorisation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/80">
                  {spotPositions.map((position) => {
                    const accountingAvailable = position.accounting_complete;
                    return (
                      <tr key={position.asset} className="transition-colors hover:bg-muted/30">
                        <td className="px-4 py-3 font-semibold">{position.asset}</td>
                        <td className="px-4 py-3 text-right font-mono tabular-nums">{formatDecimal(position.quantity)}</td>
                        <td className="px-4 py-3 text-right font-mono tabular-nums">{formatDecimal(position.available)}</td>
                        <td className="px-4 py-3 text-right font-mono tabular-nums">{accountingAvailable && position.average_entry_price ? formatDecimal(position.average_entry_price) : "—"}</td>
                        <td className="px-4 py-3 text-right font-mono tabular-nums">
                          {position.mark_price ? formatDecimal(position.mark_price) : "—"}
                          {position.mark_observed_at ? <span className="mt-1 block font-sans text-[10px] text-muted-foreground">{formatTimestamp(position.mark_observed_at)}</span> : null}
                        </td>
                        <td className="px-4 py-3 text-right font-mono tabular-nums">{position.market_value !== null ? formatDecimal(position.market_value) : "—"}</td>
                        <td className="px-4 py-3 text-right font-mono tabular-nums">{accountingAvailable && position.remaining_cost_basis ? formatDecimal(position.remaining_cost_basis) : "—"}</td>
                        <td className={cn("px-4 py-3 text-right font-mono font-semibold tabular-nums", accountingAvailable ? pnlClass(position.realized_pnl) : "text-muted-foreground")}>{accountingAvailable ? signedDecimal(position.realized_pnl) : "—"}</td>
                        <td className={cn("px-4 py-3 text-right font-mono font-semibold tabular-nums", position.unrealized_pnl !== null ? pnlClass(position.unrealized_pnl) : "text-muted-foreground")}>{signedDecimal(position.unrealized_pnl)}</td>
                        <td className="px-4 py-3 text-right"><Badge tone={position.valuation_complete ? "success" : "warning"}>{position.valuation_complete ? "Complète" : "Indisponible"}</Badge></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : <p className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">Aucune position SPOT ouverte.</p>}
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
            Un mark absent ou trop ancien apparaît comme « — ». Une position legacy sans comptabilité complète peut afficher sa valeur de marché, mais jamais un P&amp;L latent inventé.
          </p>
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
                <thead className="bg-muted/60 text-left text-xs text-muted-foreground"><tr><th className="px-3 py-3 font-semibold">Marché</th><th className="px-3 py-3 font-semibold">Sens</th><th className="px-3 py-3 text-right font-semibold">Quantité</th><th className="px-3 py-3 text-right font-semibold">Entrée</th><th className="px-3 py-3 text-right font-semibold">Mark</th><th className="px-3 py-3 text-right font-semibold">P&amp;L latent</th><th className="px-3 py-3 text-right font-semibold">Notional</th><th className="px-3 py-3 text-right font-semibold">Levier</th><th className="px-3 py-3 text-right font-semibold">Marge</th><th className="px-3 py-3 text-right font-semibold">Liquidation</th></tr></thead>
                <tbody className="divide-y divide-border/80">
                  {derivativePositions.map((position) => <tr key={`${position.symbol}-${position.side}`} className="transition-colors hover:bg-muted/30"><td className="px-3 py-3 font-semibold">{position.symbol}</td><td className="px-3 py-3"><Badge tone={position.side === "LONG" ? "success" : "warning"}>{position.side}</Badge></td><td className="px-3 py-3 text-right font-mono tabular-nums">{formatDecimal(position.quantity)}</td><td className="px-3 py-3 text-right font-mono tabular-nums">{formatDecimal(position.average_entry_price)}</td><td className="px-3 py-3 text-right font-mono tabular-nums">{formatDecimal(position.mark_price)}{position.mark_observed_at ? <span className="mt-1 block font-sans text-[10px] text-muted-foreground">{formatTimestamp(position.mark_observed_at)}</span> : null}</td><td className={cn("px-3 py-3 text-right font-mono font-semibold tabular-nums", pnlClass(position.unrealized_pnl))}>{signedDecimal(position.unrealized_pnl)}</td><td className="px-3 py-3 text-right font-mono tabular-nums">{formatDecimal(position.notional)}</td><td className="px-3 py-3 text-right">{formatDecimal(position.leverage)}×</td><td className="px-3 py-3 text-right font-mono tabular-nums">{formatDecimal(position.margin_used)}</td><td className="px-3 py-3 text-right font-mono tabular-nums">{position.liquidation_price ? formatDecimal(position.liquidation_price) : "—"}</td></tr>)}
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
