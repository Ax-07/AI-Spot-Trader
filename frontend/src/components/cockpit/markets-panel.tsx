"use client";

import { Activity, Bot, CircleDollarSign, History, RefreshCw, ShieldCheck, Wifi, WifiOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { MarketChart } from "@/components/cockpit/market-chart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCockpit } from "@/hooks/use-cockpit";
import { useMarketCandles } from "@/hooks/use-market-candles";
import type { ControlPlaneController } from "@/hooks/use-control-plane";
import { api, ApiError } from "@/lib/api/client";
import { formatDecimal, formatTimestamp, shortUuid } from "@/lib/api/format";
import type { CycleDetailResponse, ExecutionResponse } from "@/lib/api/types";
import {
  MARKET_TIMEFRAMES,
  buildCockpitMarkets,
  buildMarketFillMarkers,
  buildMarketPositionOverlays,
  marketKey,
  type CandleTimeframe,
  type CockpitMarket,
  type MarketFillMarker,
} from "@/lib/market-candles";
import { cn } from "@/lib/utils";

type ExecutionState =
  | { kind: "loading" }
  | { kind: "ready"; items: ExecutionResponse[] }
  | { kind: "error"; message: string };

type ExecutionResult = {
  requestKey: string;
  state: Exclude<ExecutionState, { kind: "loading" }>;
};

type DetailState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; detail: CycleDetailResponse }
  | { kind: "error"; message: string };

type DetailResult = {
  cycleId: string;
  state: Exclude<DetailState, { kind: "idle" } | { kind: "loading" }>;
};


const percentFormatter = new Intl.NumberFormat("fr-FR", {
  style: "percent",
  maximumFractionDigits: 2,
});

function formatPercent(value: string | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? percentFormatter.format(parsed) : value;
}

function actionTone(action: string) {
  return action === "BUY" ? "success" as const : "danger" as const;
}

function riskTone(status: string | null | undefined) {
  if (status === "ALLOW") return "success" as const;
  if (status === "MODIFY") return "warning" as const;
  if (status === "REJECT") return "danger" as const;
  return "neutral" as const;
}

function signedDecimal(value: string | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  const formatted = formatDecimal(Math.abs(parsed));
  return parsed > 0 ? `+${formatted}` : parsed < 0 ? `−${formatted}` : formatted;
}

function pnlClass(value: string | null | undefined) {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed) || parsed === 0) return "text-foreground";
  return parsed > 0 ? "text-success-foreground" : "text-destructive-subtle-foreground";
}

function codeLabel(value: string) {
  return value.replaceAll("_", " ");
}

function PositionContext({ market, cockpit }: { market: CockpitMarket; cockpit: ReturnType<typeof useCockpit> }) {
  const portfolio = cockpit.resources.portfolio.kind === "ready" ? cockpit.resources.portfolio.data : null;
  if (!portfolio) {
    return <p className="text-sm text-muted-foreground">Portefeuille backend indisponible.</p>;
  }

  if (market.market_type === "SPOT") {
    const baseAsset = market.symbol.split("/")[0];
    const position = portfolio.positions.find((item) => item.asset === baseAsset) ?? null;
    if (!position) return <p className="text-sm text-muted-foreground">Aucune position SPOT ouverte sur ce marché.</p>;
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-7">
        <Fact label="Quantité" value={formatDecimal(position.quantity)} />
        <Fact label="Prix moyen" value={position.average_entry_price ? formatDecimal(position.average_entry_price) : "—"} />
        <Fact label="Cost basis" value={position.remaining_cost_basis ? formatDecimal(position.remaining_cost_basis) : "—"} />
        <Fact label="Mark backend" value={position.mark_price ? formatDecimal(position.mark_price) : "—"} detail={formatTimestamp(position.mark_observed_at)} />
        <Fact label="Valeur position" value={position.market_value ? formatDecimal(position.market_value) : "—"} />
        <Fact label="P&L latent" value={signedDecimal(position.unrealized_pnl)} valueClassName={pnlClass(position.unrealized_pnl)} />
        <Fact label="Exposition portefeuille" value={formatPercent(portfolio.exposure_fraction)} detail={portfolio.exposure_value ? `Valeur ${formatDecimal(portfolio.exposure_value)}` : undefined} />
      </div>
    );
  }

  const position = portfolio.derivative_positions.find((item) => item.symbol === market.symbol) ?? null;
  if (!position) return <p className="text-sm text-muted-foreground">Aucune position PERPETUAL ouverte sur ce marché.</p>;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5">
      <Fact label="Quantité" value={formatDecimal(position.quantity)} />
      <Fact label="Prix moyen" value={formatDecimal(position.average_entry_price)} />
      <Fact label="Mark backend" value={formatDecimal(position.mark_price)} detail={formatTimestamp(position.mark_observed_at)} />
      <Fact label="P&L latent" value={signedDecimal(position.unrealized_pnl)} valueClassName={pnlClass(position.unrealized_pnl)} />
      <Fact label="Notional" value={formatDecimal(position.notional)} />
      <Fact label="Levier" value={`${formatDecimal(position.leverage)}×`} />
      <Fact label="Marge" value={formatDecimal(position.margin_used)} />
      <Fact label="Liquidation" value={position.liquidation_price ? formatDecimal(position.liquidation_price) : "—"} />
      <Fact label="Funding cumulé" value={signedDecimal(position.cumulative_funding)} valueClassName={pnlClass(position.cumulative_funding)} />
      <Fact label="Exposition portefeuille" value={formatPercent(portfolio.exposure_fraction)} detail={portfolio.exposure_value ? `Valeur ${formatDecimal(portfolio.exposure_value)}` : undefined} />
    </div>
  );
}

function Fact({ label, value, detail, valueClassName }: { label: string; value: string; detail?: string; valueClassName?: string }) {
  return (
    <div className="rounded-xl border bg-muted/15 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn("mt-1 font-mono text-sm font-semibold tabular-nums", valueClassName)}>{value}</p>
      {detail && detail !== "—" ? <p className="mt-1 text-[10px] text-muted-foreground">{detail}</p> : null}
    </div>
  );
}

function MarkerDetail({ marker, state }: { marker: MarketFillMarker; state: DetailState }) {
  const detail = state.kind === "ready" ? state.detail : null;
  const explanation = detail?.explainability ?? null;
  const agent = explanation?.agent ?? null;
  const risk = explanation?.risk ?? null;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Badge tone={actionTone(marker.action)}>{marker.action}</Badge>
              {marker.reduceOnly ? <Badge tone="warning">réduction</Badge> : null}
              Fill PAPER sélectionné
            </CardTitle>
            <CardDescription>{formatTimestamp(marker.filledAt)} · {marker.symbol} · {marker.marketType}</CardDescription>
          </div>
          <span className="font-mono text-[10px] text-muted-foreground">fill {shortUuid(marker.fillId)}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid gap-3 sm:grid-cols-3">
          <Fact label="Action" value={marker.action} />
          <Fact label="Quantité fill" value={marker.quantity ? formatDecimal(marker.quantity) : "—"} />
          <Fact label="Prix fill" value={marker.price ? formatDecimal(marker.price) : "—"} />
        </div>

        {state.kind === "loading" ? <p className="text-xs text-muted-foreground">Chargement des faits corrélés du cycle…</p> : null}
        {state.kind === "error" ? (
          <p className="rounded-lg border border-warning/30 bg-warning-subtle p-3 text-xs text-warning-foreground">
            {state.message}. Le fill reste réel, mais aucune causalité supplémentaire n’est inventée.
          </p>
        ) : null}
        {detail && !explanation ? (
          <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
            Ce cycle ne possède pas de projection d’explicabilité 19.5 exploitable. Aucun rationale n’est reconstruit côté frontend.
          </p>
        ) : null}

        {explanation ? (
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="rounded-xl border bg-muted/15 p-4">
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-muted-foreground"><Bot className="size-3.5" /> Agent IA</div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{agent?.rationale ?? "Rationale non disponible pour ce cycle."}</p>
            </div>
            <div className="rounded-xl border bg-muted/15 p-4">
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-muted-foreground"><ShieldCheck className="size-3.5" /> Risk Engine</div>
              {risk ? (
                <>
                  <div className="mt-2"><Badge tone={riskTone(risk.status)}>Risk {risk.status}</Badge></div>
                  {risk.reasons.length ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">{risk.reasons.map((reason) => <Badge key={reason} tone={risk.status === "REJECT" ? "danger" : "warning"}>{codeLabel(reason)}</Badge>)}</div>
                  ) : <p className="mt-2 text-xs text-muted-foreground">Aucune raison Risk persistée.</p>}
                </>
              ) : <p className="mt-2 text-xs text-muted-foreground">Résultat Risk non disponible.</p>}
            </div>
          </div>
        ) : null}

        <details className="rounded-lg border bg-muted/10 px-3 py-2 text-xs">
          <summary className="cursor-pointer font-semibold">IDs techniques</summary>
          <div className="mt-2 space-y-1 font-mono text-[10px] text-muted-foreground">
            <p>cycle {marker.cycleId}</p><p>execution {marker.executionId}</p><p>fill {marker.fillId}</p>
          </div>
        </details>
      </CardContent>
    </Card>
  );
}

export function MarketsPanel({ control }: { control: ControlPlaneController }) {
  const cockpit = useCockpit();
  const portfolio = cockpit.resources.portfolio.kind === "ready" ? cockpit.resources.portfolio.data : null;
  const latestCycle = cockpit.resources.latestCycle.kind === "ready" ? cockpit.resources.latestCycle.data : null;
  const discovery = latestCycle?.explainability?.discovery ?? null;
  const bootstrapMarkets = control.activeCampaign?.campaign.configuration.paper_executable_markets;
  const markets = useMemo(() => buildCockpitMarkets({
    effectiveWatchlist: discovery?.effective_watchlist,
    bootstrapMarkets,
    portfolio,
  }), [bootstrapMarkets, discovery?.effective_watchlist, portfolio]);

  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<CandleTimeframe>("5m");
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null);
  const [selectedMarker, setSelectedMarker] = useState<MarketFillMarker | null>(null);
  const [detailResult, setDetailResult] = useState<DetailResult | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);

  const resolvedActiveKey = activeKey && markets.some((item) => marketKey(item) === activeKey)
    ? activeKey
    : markets[0]
      ? marketKey(markets[0])
      : null;
  const activeMarket = markets.find((item) => marketKey(item) === resolvedActiveKey) ?? null;
  const activeSymbol = activeMarket?.symbol ?? null;
  const activeMarketType = activeMarket?.market_type ?? null;
  const timeframes = activeMarketType ? MARKET_TIMEFRAMES[activeMarketType] : MARKET_TIMEFRAMES.SPOT;
  const resolvedTimeframe = activeMarketType && MARKET_TIMEFRAMES[activeMarketType].includes(timeframe)
    ? timeframe
    : "5m";

  const stream = useMarketCandles(activeMarket, resolvedTimeframe, 500);
  const executionRequestKey = activeMarket
    ? `${marketKey(activeMarket)}:${refreshNonce}`
    : null;
  const executionState = useMemo<ExecutionState>(() => {
    if (!executionRequestKey) return { kind: "ready", items: [] };
    if (executionResult?.requestKey === executionRequestKey) return executionResult.state;
    return { kind: "loading" };
  }, [executionRequestKey, executionResult]);

  useEffect(() => {
    if (!activeSymbol || !activeMarketType || !executionRequestKey) return;
    let active = true;
    void api.executions(100, { symbol: activeSymbol })
      .then((page) => {
        if (active) {
          setExecutionResult({
            requestKey: executionRequestKey,
            state: { kind: "ready", items: page.items },
          });
        }
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setExecutionResult({
          requestKey: executionRequestKey,
          state: {
            kind: "error",
            message: cause instanceof ApiError ? cause.message : "Fills indisponibles",
          },
        });
      });
    return () => { active = false; };
  }, [activeMarketType, activeSymbol, executionRequestKey]);

  const markers = useMemo(
    () => activeMarket && executionState.kind === "ready"
      ? buildMarketFillMarkers(executionState.items, activeMarket)
      : [],
    [activeMarket, executionState],
  );
  const positionOverlays = useMemo(
    () => buildMarketPositionOverlays(portfolio, activeMarket),
    [activeMarket, portfolio],
  );
  const activeSelectedMarker = selectedMarker
    && activeMarket
    && selectedMarker.symbol === activeMarket.symbol
    && selectedMarker.marketType === activeMarket.market_type
    && markers.some((marker) => marker.id === selectedMarker.id)
      ? selectedMarker
      : null;
  const selectedCycleId = activeSelectedMarker?.cycleId ?? null;
  const detailState: DetailState = !selectedCycleId
    ? { kind: "idle" }
    : detailResult?.cycleId === selectedCycleId
      ? detailResult.state
      : { kind: "loading" };

  useEffect(() => {
    if (!selectedCycleId) return;
    let active = true;
    void api.cycle(selectedCycleId)
      .then((detail) => {
        if (active) {
          setDetailResult({
            cycleId: selectedCycleId,
            state: { kind: "ready", detail },
          });
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setDetailResult({
            cycleId: selectedCycleId,
            state: {
              kind: "error",
              message: cause instanceof ApiError ? cause.message : "Cycle indisponible",
            },
          });
        }
      });
    return () => { active = false; };
  }, [selectedCycleId]);

  async function refresh() {
    await cockpit.refresh();
    setRefreshNonce((value) => value + 1);
  }

  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">Streaming backend 19.6A</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight">Marchés</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            Watchlist stratégique, positions ouvertes, chandeliers Kraken normalisés par le backend et fills PAPER persistés. Aucun calcul Risk/P&amp;L n’est reconstruit ici.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={cockpit.refreshing}>
          <RefreshCw className={cockpit.refreshing ? "size-3.5 animate-spin" : "size-3.5"} /> Actualiser
        </Button>
      </div>

      {markets.length ? (
        <>
          <div className="overflow-x-auto pb-1">
            <div className="flex min-w-max gap-2">
              {markets.map((market) => {
                const key = marketKey(market);
                const active = key === marketKey(activeMarket!);
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setActiveKey(key)}
                    className={cn(
                      "max-w-[240px] rounded-xl border px-3 py-2 text-left transition-colors",
                      active ? "border-primary bg-primary/10" : "border-border bg-card hover:bg-muted/40",
                    )}
                  >
                    <span className="block truncate text-sm font-semibold">{market.symbol}</span>
                    <span className="mt-0.5 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                      {market.market_type}{market.hasPosition ? <Badge tone="success">position</Badge> : null}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <Card>
            <CardHeader className="gap-3">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <CardTitle>{activeMarket!.symbol}</CardTitle>
                    <Badge tone={activeMarket!.market_type === "PERPETUAL" ? "warning" : "info"}>{activeMarket!.market_type}</Badge>
                    {stream.status?.connected ? <Badge tone="success"><Wifi className="mr-1 size-3" /> connecté</Badge> : <Badge tone="neutral"><WifiOff className="mr-1 size-3" /> déconnecté</Badge>}
                    {stream.status?.stale ? <Badge tone="warning">stale</Badge> : null}
                    {stream.reconnecting ? <Badge tone="warning">reconnexion…</Badge> : null}
                  </div>
                  <CardDescription className="mt-1">
                    {stream.status?.last_update_at ? `Dernière donnée backend ${formatTimestamp(stream.status.last_update_at)}` : "En attente d’une donnée backend."}
                  </CardDescription>
                </div>
                <div className="max-w-full overflow-x-auto">
                  <div className="flex min-w-max gap-1 rounded-xl border bg-muted/20 p-1">
                    {timeframes.map((item) => (
                      <button key={item} type="button" onClick={() => setTimeframe(item)} className={cn("rounded-lg px-2.5 py-1.5 text-xs font-semibold", resolvedTimeframe === item ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground")}>{item}</button>
                    ))}
                  </div>
                </div>
              </div>
              {stream.error ? <div className="rounded-lg border border-warning/30 bg-warning-subtle px-3 py-2 text-xs text-warning-foreground">{stream.error}</div> : null}
            </CardHeader>
            <CardContent>
              {stream.state === "loading" && !stream.candles.length ? (
                <div className="flex h-[360px] items-center justify-center rounded-xl border border-dashed text-sm text-muted-foreground sm:h-[480px]">Chargement de l’historique candles…</div>
              ) : stream.state === "error" && !stream.candles.length ? (
                <div className="flex h-[360px] items-center justify-center rounded-xl border border-destructive/30 bg-destructive-subtle p-6 text-center text-sm text-destructive-subtle-foreground sm:h-[480px]">Historique indisponible. Aucune candle de remplacement n’est inventée.</div>
              ) : (
                <MarketChart key={marketKey(activeMarket!)} candles={stream.candles} markers={markers} overlays={positionOverlays} onMarkerSelect={setSelectedMarker} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Position & contexte marché</CardTitle><CardDescription>Faits exposés directement par le portefeuille backend, jamais recalculés depuis les candles.</CardDescription></CardHeader>
            <CardContent><PositionContext market={activeMarket!} cockpit={cockpit} /></CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div><CardTitle className="flex items-center gap-2"><History className="size-4" /> Fills PAPER sur ce marché</CardTitle><CardDescription>Markers issus uniquement des fills persistés et suffisamment typés. Une exécution sans fill ne crée aucun marker.</CardDescription></div>
                <Badge tone="neutral">{markers.length} marker(s)</Badge>
              </div>
            </CardHeader>
            <CardContent>
              {executionState.kind === "loading" ? <p className="text-sm text-muted-foreground">Chargement des fills…</p> : null}
              {executionState.kind === "error" ? <p className="rounded-lg border border-warning/30 bg-warning-subtle p-3 text-xs text-warning-foreground">{executionState.message}. Aucun marker n’est inventé.</p> : null}
              {executionState.kind === "ready" && !markers.length ? <p className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">Aucun fill PAPER canonique affichable pour ce marché dans la fenêtre d’audit chargée.</p> : null}
              {markers.length ? (
                <div className="flex gap-2 overflow-x-auto pb-1">
                  {markers.slice(-24).reverse().map((marker) => (
                    <button key={marker.id} type="button" onClick={() => setSelectedMarker(marker)} className={cn("min-w-[190px] rounded-xl border p-3 text-left transition-colors", activeSelectedMarker?.id === marker.id ? "border-primary bg-primary/10" : "hover:bg-muted/30")}>
                      <div className="flex items-center justify-between gap-2"><span className="flex items-center gap-1"><Badge tone={actionTone(marker.action)}>{marker.action}</Badge>{marker.reduceOnly ? <Badge tone="warning">réduction</Badge> : null}</span><span className="text-[10px] text-muted-foreground">{formatTimestamp(marker.filledAt)}</span></div>
                      <p className="mt-2 font-mono text-xs">{marker.quantity ? formatDecimal(marker.quantity) : "quantité —"}{marker.price ? ` @ ${formatDecimal(marker.price)}` : ""}</p>
                    </button>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>

          {activeSelectedMarker ? <MarkerDetail marker={activeSelectedMarker} state={detailState} /> : null}
        </>
      ) : (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center text-muted-foreground">
            <Activity className="size-6" />
            <p className="text-sm font-medium text-foreground">Aucun marché à afficher</p>
            <p className="max-w-lg text-xs">Le cockpit attend une watchlist effective, un bootstrap de Campaign active ou une position ouverte. Il ne fabrique pas sa propre sélection de marchés.</p>
          </CardContent>
        </Card>
      )}

      <p className="flex items-center gap-2 text-[11px] text-muted-foreground"><CircleDollarSign className="size-3" /> Les prix du chart viennent du pipeline candles 19.6A ; les valeurs de position et P&amp;L viennent du portefeuille backend.</p>
    </div>
  );
}
