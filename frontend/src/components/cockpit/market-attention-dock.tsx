"use client";

import { Radar, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  activityErrorEntries,
  attentionHorizon,
  fetchMarketAttention,
  formatBps,
  formatImbalance,
  formatQuoteCompact,
  formatRate,
  formatSignedPercent,
  formatUsdCompact,
  formatVolumeRatio,
  marketAttentionStatusMessage,
  slippageEstimate,
  type LiquidityRegime,
  type MarketAttentionOverview,
  type MarketAttentionSnapshot,
  type MicrostructureCharacteristic,
  type RadarInterestLevel,
  type RadarStatus,
} from "@/lib/market-attention";

function statusTone(status: RadarStatus) {
  if (status === "AVAILABLE") return "success" as const;
  if (status === "PARTIAL" || status === "STALE") return "warning" as const;
  if (status === "ERROR") return "danger" as const;
  return "neutral" as const;
}

function interestTone(level: RadarInterestLevel) {
  if (level === "VERY_HIGH") return "danger" as const;
  if (level === "HIGH") return "warning" as const;
  if (level === "MEDIUM") return "info" as const;
  return "neutral" as const;
}

function liquidityTone(regime: LiquidityRegime) {
  if (regime === "VERY_HIGH" || regime === "HIGH") return "info" as const;
  if (regime === "MICRO" || regime === "LOW") return "warning" as const;
  return "neutral" as const;
}

function freshness(value: string | null) {
  if (value === null) return "—";
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

function shortTime(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
  }).format(parsed);
}

const MICRO_LABELS: Record<MicrostructureCharacteristic, string> = {
  TIGHT_SPREAD: "Spread serré",
  WIDE_SPREAD: "Spread large",
  DEEP_LIQUIDITY: "Profondeur confortable",
  THIN_LIQUIDITY: "Profondeur faible",
  ORDER_BOOK_IMBALANCE: "Carnet déséquilibré",
  TRADE_ACTIVITY_SURGE: "Trades en accélération",
  TRADE_ACTIVITY_FADE: "Trades en ralentissement",
  BUY_PRESSURE: "Pression côté acheteur",
  SELL_PRESSURE: "Pression côté vendeur",
  SLIPPAGE_RISK: "Risque de slippage",
};

function microLabel(value: string) {
  return MICRO_LABELS[value as MicrostructureCharacteristic] ?? value.replaceAll("_", " ");
}

function MarketRow({ item, expanded, onToggle }: { item: MarketAttentionSnapshot; expanded: boolean; onToggle: () => void }) {
  const activity = item.market_activity;
  const micro = item.microstructure;
  const h5 = attentionHorizon(item, "5m");
  const h15 = attentionHorizon(item, "15m");
  const h1 = attentionHorizon(item, "1h");
  const h4 = attentionHorizon(item, "4h");
  const priceMove = h15?.price_return ?? h5?.price_return ?? null;
  const acquisition1k = slippageEstimate(item, "BUY", 1000);
  const cession1k = slippageEstimate(item, "SELL", 1000);

  return (
    <div className="rounded-xl border bg-background/70">
      <button type="button" onClick={onToggle} className="grid w-full gap-3 p-3 text-left md:grid-cols-[minmax(190px,1.3fr)_repeat(7,minmax(74px,0.7fr))] md:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold">{activity.market.symbol}</span>
            <Badge tone="neutral">{activity.market.market_type}</Badge>
            <Badge tone={liquidityTone(activity.liquidity_regime)}>{activity.liquidity_regime}</Badge>
            <Badge tone={interestTone(item.interest_level)}>{item.interest_level}</Badge>
          </div>
          <p className="mt-1 truncate text-[11px] text-muted-foreground">
            {item.combined_characteristics.length ? item.combined_characteristics.map(microLabel).join(" · ") : "Aucune caractéristique forte"}
          </p>
        </div>
        <Fact label="Activité" value={activity.activity_state.replaceAll("_", " ")} />
        <Fact label="Vol. 5m" value={formatVolumeRatio(h5?.volume_ratio)} />
        <Fact label="Spread" value={formatBps(micro.spread_bps)} />
        <Fact label="Prof. L2" value={formatQuoteCompact(micro.total_depth_quote, micro.quote_asset)} />
        <Fact label="Déséquilibre" value={formatImbalance(micro.book_imbalance)} />
        <Fact label="Trades" value={formatRate(micro.trade_rate_per_minute)} />
        <Fact label="Prix" value={formatSignedPercent(priceMove)} />
      </button>

      {expanded ? (
        <div className="space-y-4 border-t px-3 py-4 text-xs">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
            <Fact label="Niveau d’intérêt" value={item.interest_level} />
            <Fact label="Qualité OHLCV" value={activity.data_quality} />
            <Fact label="Microstructure" value={`${micro.status} / ${micro.data_quality}`} />
            <Fact label="Fraîcheur OHLCV" value={freshness(activity.freshness_seconds)} />
            <Fact label="Fraîcheur micro" value={freshness(micro.freshness_seconds)} />
            <Fact label="Observation" value={shortTime(activity.observed_at)} />
          </div>

          <div className="rounded-lg border bg-muted/15 p-3">
            <p className="font-semibold">Pourquoi ce niveau d’intérêt ?</p>
            {item.interest_reasons.length ? (
              <ul className="mt-2 list-disc space-y-1 pl-4 text-muted-foreground">
                {item.interest_reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            ) : <p className="mt-1 text-muted-foreground">Aucune raison pondérée supplémentaire.</p>}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border bg-muted/10 p-3">
              <p className="font-semibold">Carnet L2</p>
              <div className="mt-2 space-y-1.5">
                <Fact label="Meilleur bid" value={micro.best_bid ?? "—"} />
                <Fact label="Meilleur ask" value={micro.best_ask ?? "—"} />
                <Fact label="Mid" value={micro.mid_price ?? "—"} />
                <Fact label="Spread" value={formatBps(micro.spread_bps)} />
                <Fact label="Profondeur bid" value={formatQuoteCompact(micro.bid_depth_quote, micro.quote_asset)} />
                <Fact label="Profondeur ask" value={formatQuoteCompact(micro.ask_depth_quote, micro.quote_asset)} />
                <Fact label="Déséquilibre" value={formatImbalance(micro.book_imbalance)} />
              </div>
            </div>

            <div className="rounded-lg border bg-muted/10 p-3">
              <p className="font-semibold">Trades récents</p>
              <div className="mt-2 space-y-1.5">
                <Fact label="Trades reçus" value={micro.trade_count === null ? "—" : String(micro.trade_count)} />
                <Fact label="Cadence récente" value={formatRate(micro.trade_rate_per_minute)} />
                <Fact label="Cadence de référence" value={formatRate(micro.baseline_trade_rate_per_minute)} />
                <Fact label="Ratio activité" value={formatVolumeRatio(micro.trade_activity_ratio)} />
                <Fact label="Couverture côté Kraken" value={formatSignedPercent(micro.provider_side_coverage)} />
                <Fact label="Pression transactionnelle" value={formatImbalance(micro.buy_sell_imbalance)} />
              </div>
            </div>

            <div className="rounded-lg border bg-muted/10 p-3">
              <p className="font-semibold">Slippage théorique · 1 000 {micro.quote_asset ?? "devise cotée"}</p>
              <div className="mt-2 space-y-1.5">
                <Fact label="Acquisition" value={acquisition1k?.insufficient_depth ? "Profondeur insuffisante" : formatBps(acquisition1k?.slippage_bps)} />
                <Fact label="Cession" value={cession1k?.insufficient_depth ? "Profondeur insuffisante" : formatBps(cession1k?.slippage_bps)} />
                <Fact label="VWAP acquisition" value={acquisition1k?.estimated_vwap ?? "—"} />
                <Fact label="VWAP cession" value={cession1k?.estimated_vwap ?? "—"} />
              </div>
              <p className="mt-2 text-[10px] text-muted-foreground">Calcul informatif par parcours du snapshot L2. Aucun ordre n’est construit ni envoyé.</p>
            </div>

            <div className="rounded-lg border bg-muted/10 p-3">
              <p className="font-semibold">Profondeur proche du mid</p>
              <div className="mt-2 space-y-1.5">
                {micro.depth_bands.length ? micro.depth_bands.map((band) => (
                  <Fact
                    key={band.band_bps}
                    label={`±${band.band_bps} bps`}
                    value={`${formatQuoteCompact(band.bid_depth_quote, micro.quote_asset)} / ${formatQuoteCompact(band.ask_depth_quote, micro.quote_asset)}`}
                  />
                )) : <p className="text-muted-foreground">—</p>}
              </div>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[h5, h15, h1, h4].map((horizon, index) => (
              <div key={horizon?.timeframe ?? index} className="rounded-lg border bg-muted/10 p-3">
                <p className="font-semibold">OHLCV · {horizon?.timeframe ?? "—"}</p>
                <div className="mt-2 space-y-1.5">
                  <Fact label="Volume relatif" value={formatVolumeRatio(horizon?.volume_ratio)} />
                  <Fact label="Variation prix" value={formatSignedPercent(horizon?.price_return)} />
                  <Fact label="Expansion range" value={formatVolumeRatio(horizon?.range_expansion_ratio)} />
                  <Fact label="Expansion volatilité" value={formatVolumeRatio(horizon?.volatility_expansion_ratio)} />
                  <Fact label="Distance breakout" value={formatSignedPercent(horizon?.breakout_distance)} />
                </div>
              </div>
            ))}
          </div>

          {micro.errors.length ? (
            <div className="rounded-lg border bg-muted/10 p-3">
              <p className="font-semibold">Diagnostic microstructure Kraken</p>
              <p className="mt-1 text-muted-foreground">{micro.errors.join(" · ")}</p>
            </div>
          ) : null}

          <p className="rounded-lg border bg-muted/10 p-3 text-muted-foreground">
            Radar déterministe Kraken uniquement. OHLCV, carnet L2 et trades récents décrivent l’activité observée ; ils ne constituent aucune instruction de trading.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[9px] font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 truncate font-mono text-[11px] font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function CountLine({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between gap-3 font-mono text-[11px] tabular-nums">
      <span className="text-muted-foreground">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function MarketAttentionDock() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<MarketAttentionOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const next = await fetchMarketAttention(signal);
      setData(next);
      setError(null);
    } catch (caught) {
      if (signal?.aborted) return;
      setError(caught instanceof Error ? caught.message : "Radar indisponible");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const interval = window.setInterval(() => void refresh(controller.signal), 60_000);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [open, refresh]);

  const displayed = useMemo(() => data?.shortlist.slice(0, 20) ?? [], [data]);

  function toggleOpen() {
    if (!open) void refresh();
    setOpen((value) => !value);
  }

  return (
    <>
      <Button type="button" onClick={toggleOpen} className="fixed bottom-5 right-5 z-50 shadow-xl" aria-expanded={open}>
        <Radar className="size-4" /> Radar marché
        {data ? <span className="ml-1"><Badge tone={statusTone(data.status)}>{data.status}</Badge></span> : null}
      </Button>

      {open ? <div className="fixed inset-0 z-40 bg-black/20" onClick={() => setOpen(false)} aria-hidden="true" /> : null}

      {open ? (
        <Card className="fixed bottom-20 right-3 z-50 max-h-[78vh] w-[min(96vw,1180px)] overflow-hidden shadow-2xl sm:right-5">
          <CardHeader className="border-b">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="flex items-center gap-2"><Radar className="size-4" /> Market Attention</CardTitle>
                  <span className="inline-flex"><Badge tone="info">INFORMATIF — N’INFLUENCE PAS LE TRADING</Badge></span>
                  {data ? <span className="inline-flex"><Badge tone={statusTone(data.status)}>État · {data.status}</Badge></span> : null}
                </div>
                <CardDescription className="mt-1">Données Kraken déterministes : OHLCV finalisé + snapshots SPOT de trades récents et carnet L2. Aucun appel IA, aucune recherche Web, aucune exécution.</CardDescription>
              </div>
              <div className="flex gap-1">
                <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading} aria-label="Actualiser le radar">
                  <RefreshCw className={loading ? "size-3.5 animate-spin" : "size-3.5"} />
                </Button>
                <Button variant="outline" size="sm" onClick={() => setOpen(false)} aria-label="Fermer le radar"><X className="size-3.5" /></Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="max-h-[calc(78vh-110px)] overflow-y-auto py-4">
            {error ? <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-xs text-destructive-subtle-foreground">{error}</div> : null}
            {data ? (
              <div className="space-y-4">
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
                  <Fact label="Catalogue" value={String(data.catalogue_market_count)} />
                  <Fact label="Marchés frais OHLCV" value={String(data.cached_activity_market_count)} />
                  <Fact label="Scannés OHLCV" value={String(data.scanned_market_count)} />
                  <Fact label="Scannés micro" value={String(data.microstructure_scanned_market_count)} />
                  <Fact label="Cache micro" value={String(data.microstructure_cached_market_count)} />
                  <Fact label="Candidats" value={String(data.candidate_market_count)} />
                </div>

                <div className="rounded-lg border bg-muted/10 px-3 py-2 text-xs font-medium">{marketAttentionStatusMessage(data)}</div>

                <div className="grid gap-3 lg:grid-cols-4">
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">OHLCV</p>
                    <div className="grid grid-cols-2 gap-x-5 gap-y-1.5">
                      <CountLine label="AVAILABLE" value={data.activity_status_counts.AVAILABLE} />
                      <CountLine label="PARTIAL" value={data.activity_status_counts.PARTIAL} />
                      <CountLine label="STALE" value={data.activity_status_counts.STALE} />
                      <CountLine label="ERROR" value={data.activity_status_counts.ERROR} />
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Microstructure SPOT</p>
                    <div className="grid grid-cols-2 gap-x-5 gap-y-1.5">
                      <CountLine label="AVAILABLE" value={data.microstructure_status_counts.AVAILABLE} />
                      <CountLine label="PARTIAL" value={data.microstructure_status_counts.PARTIAL} />
                      <CountLine label="STALE" value={data.microstructure_status_counts.STALE} />
                      <CountLine label="ERROR" value={data.microstructure_status_counts.ERROR} />
                      <CountLine label="N/A" value={data.microstructure_status_counts.NOT_APPLICABLE} />
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Activité OHLCV</p>
                    <div className="grid grid-cols-2 gap-x-5 gap-y-1.5">
                      <CountLine label="NORMAL" value={data.activity_state_counts.NORMAL} />
                      <CountLine label="ELEVATED" value={data.activity_state_counts.ELEVATED} />
                      <CountLine label="ACCELERATING" value={data.activity_state_counts.ACCELERATING} />
                      <CountLine label="VERY_HIGH" value={data.activity_state_counts.VERY_HIGH} />
                      <CountLine label="UNKNOWN" value={data.activity_state_counts.UNKNOWN} />
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Erreurs Kraken</p>
                    {activityErrorEntries(data.activity_error_counts).length ? (
                      <div className="space-y-1.5">{activityErrorEntries(data.activity_error_counts).map(([name, count]) => <CountLine key={name} label={name} value={count} />)}</div>
                    ) : Object.keys(data.microstructure_error_counts).length ? (
                      <div className="space-y-1.5">{Object.entries(data.microstructure_error_counts).map(([name, count]) => <CountLine key={name} label={name} value={count} />)}</div>
                    ) : <p className="text-[11px] text-muted-foreground">Aucune erreur technique dans les caches frais.</p>}
                  </div>
                </div>

                <div className="rounded-lg border p-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="text-xs font-semibold">Plus fortes activités OHLCV sous seuil</p>
                    <p className="text-[10px] text-muted-foreground">Diagnostic déterministe uniquement</p>
                  </div>
                  {data.subthreshold_activity.length ? (
                    <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                      {data.subthreshold_activity.map((item) => (
                        <div key={`${item.market.market_type}:${item.market.symbol}`} className="flex items-center justify-between gap-3 rounded-md bg-muted/15 px-2.5 py-2 text-xs">
                          <div className="min-w-0"><span className="truncate font-semibold">{item.market.symbol}</span><span className="ml-1.5 text-[10px] text-muted-foreground">{item.market.market_type}</span></div>
                          <span className="shrink-0 font-mono font-semibold tabular-nums">{formatVolumeRatio(item.peak_volume_ratio)} · {item.peak_timeframe}</span>
                        </div>
                      ))}
                    </div>
                  ) : <p className="mt-2 text-xs text-muted-foreground">Aucun marché `AVAILABLE / NORMAL` avec ratio exploitable dans le cache frais.</p>}
                </div>

                {displayed.length ? (
                  <div className="space-y-2">
                    {displayed.map((item) => {
                      const key = `${item.market_activity.market.market_type}:${item.market_activity.market.symbol}`;
                      return <MarketRow key={key} item={item} expanded={expandedKey === key} onToggle={() => setExpandedKey((value) => value === key ? null : key)} />;
                    })}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">
                    {loading ? "Construction du premier snapshot du radar…" : data.status === "NOT_CONFIGURED" ? "Radar non configuré." : "Aucun candidat d’attention disponible pour le moment."}
                  </div>
                )}
                <p className="text-[10px] text-muted-foreground">Snapshot {shortTime(data.observed_at)} · classement déterministe enrichi par la microstructure SPOT. Les montants L2 sont exprimés dans la devise cotée du marché ; aucun taux de change n’est inventé.</p>
              </div>
            ) : <p className="text-sm text-muted-foreground">{loading ? "Chargement du radar…" : "Aucun snapshot chargé."}</p>}
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
