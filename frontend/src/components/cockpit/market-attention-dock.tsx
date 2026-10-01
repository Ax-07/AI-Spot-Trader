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
  formatSignedPercent,
  formatUsdCompact,
  formatVolumeRatio,
  marketAttentionStatusMessage,
  type LiquidityRegime,
  type MarketAttentionOverview,
  type MarketAttentionSnapshot,
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

function MarketRow({ item, expanded, onToggle }: { item: MarketAttentionSnapshot; expanded: boolean; onToggle: () => void }) {
  const activity = item.market_activity;
  const h5 = attentionHorizon(item, "5m");
  const h15 = attentionHorizon(item, "15m");
  const h1 = attentionHorizon(item, "1h");
  const h4 = attentionHorizon(item, "4h");
  const priceMove = h15?.price_return ?? h5?.price_return ?? null;

  return (
    <div className="rounded-xl border bg-background/70">
      <button type="button" onClick={onToggle} className="grid w-full gap-3 p-3 text-left md:grid-cols-[minmax(190px,1.3fr)_repeat(7,minmax(74px,0.7fr))] md:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold">{activity.market.symbol}</span>
            <Badge tone="neutral">{activity.market.market_type}</Badge>
            <Badge tone={liquidityTone(activity.liquidity_regime)}>{activity.liquidity_regime}</Badge>
            <Badge tone={interestTone(activity.interest_level)}>{activity.interest_level}</Badge>
          </div>
          <p className="mt-1 truncate text-[11px] text-muted-foreground">
            {activity.characteristics.length ? activity.characteristics.join(" · ") : "Aucune caractéristique forte"}
          </p>
        </div>
        <Fact label="Activité" value={activity.activity_state.replaceAll("_", " ")} />
        <Fact label="Vol. 5m" value={formatVolumeRatio(h5?.volume_ratio)} />
        <Fact label="USD 5m" value={formatUsdCompact(h5?.current_notional_usd)} />
        <Fact label="Δ USD 5m" value={formatUsdCompact(h5?.notional_delta_usd, { signed: true })} />
        <Fact label="Vol. 15m" value={formatVolumeRatio(h15?.volume_ratio)} />
        <Fact label="Prix" value={formatSignedPercent(priceMove)} />
        <Fact label="Fraîcheur" value={freshness(activity.freshness_seconds)} />
      </button>

      {expanded ? (
        <div className="space-y-4 border-t px-3 py-4 text-xs">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Fact label="Niveau d’intérêt" value={activity.interest_level} />
            <Fact label="Qualité données" value={activity.data_quality} />
            <Fact label="Fraîcheur Kraken" value={freshness(activity.freshness_seconds)} />
            <Fact label="Référence liquidité" value={formatUsdCompact(activity.liquidity_reference_usd)} />
            <Fact label="Observation" value={shortTime(activity.observed_at)} />
          </div>

          <div className="rounded-lg border bg-muted/15 p-3">
            <p className="font-semibold">Pourquoi ce niveau d’intérêt ?</p>
            {activity.interest_reasons.length ? (
              <ul className="mt-2 list-disc space-y-1 pl-4 text-muted-foreground">
                {activity.interest_reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            ) : <p className="mt-1 text-muted-foreground">Aucune raison pondérée supplémentaire.</p>}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[h5, h15, h1, h4].map((horizon, index) => (
              <div key={horizon?.timeframe ?? index} className="rounded-lg border bg-muted/10 p-3">
                <p className="font-semibold">{horizon?.timeframe ?? "—"}</p>
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

          <p className="rounded-lg border bg-muted/10 p-3 text-muted-foreground">
            Radar déterministe Kraken uniquement. Ces éléments décrivent l’activité observée et ne constituent ni BUY, ni SELL, ni HOLD.
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
        <Card className="fixed bottom-20 right-3 z-50 max-h-[78vh] w-[min(96vw,1120px)] overflow-hidden shadow-2xl sm:right-5">
          <CardHeader className="border-b">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="flex items-center gap-2"><Radar className="size-4" /> Market Attention</CardTitle>
                  <span className="inline-flex"><Badge tone="info">INFORMATIF — N’INFLUENCE PAS LE TRADING</Badge></span>
                  {data ? <span className="inline-flex"><Badge tone={statusTone(data.status)}>État · {data.status}</Badge></span> : null}
                </div>
                <CardDescription className="mt-1">Données Kraken + calculs déterministes sur bougies finalisées 5m, analysées en 5m / 15m / 1h / 4h. Aucun appel IA, aucune recherche Web, aucun BUY/SELL/HOLD.</CardDescription>
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
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  <Fact label="Catalogue" value={String(data.catalogue_market_count)} />
                  <Fact label="Marchés frais" value={String(data.cached_activity_market_count)} />
                  <Fact label="Scannés refresh" value={String(data.scanned_market_count)} />
                  <Fact label="Candidats" value={String(data.candidate_market_count)} />
                </div>

                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded-lg border bg-muted/10 px-3 py-2">
                    <p className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Scan du refresh</p>
                    <p className="mt-1 font-mono text-xs font-semibold tabular-nums">SPOT {data.scanned_market_type_counts.SPOT} · PERPETUAL {data.scanned_market_type_counts.PERPETUAL}</p>
                  </div>
                  <div className="rounded-lg border bg-muted/10 px-3 py-2">
                    <p className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Couverture fraîche</p>
                    <p className="mt-1 font-mono text-xs font-semibold tabular-nums">SPOT {data.fresh_market_type_counts.SPOT} · PERPETUAL {data.fresh_market_type_counts.PERPETUAL}</p>
                  </div>
                </div>

                <div className="rounded-lg border bg-muted/10 px-3 py-2 text-xs font-medium">{marketAttentionStatusMessage(data)}</div>

                <div className="grid gap-3 lg:grid-cols-3">
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Données</p>
                    <div className="grid grid-cols-2 gap-x-5 gap-y-1.5">
                      <CountLine label="AVAILABLE" value={data.activity_status_counts.AVAILABLE} />
                      <CountLine label="PARTIAL" value={data.activity_status_counts.PARTIAL} />
                      <CountLine label="STALE" value={data.activity_status_counts.STALE} />
                      <CountLine label="ERROR" value={data.activity_status_counts.ERROR} />
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Activité</p>
                    <div className="grid grid-cols-2 gap-x-5 gap-y-1.5">
                      <CountLine label="NORMAL" value={data.activity_state_counts.NORMAL} />
                      <CountLine label="ELEVATED" value={data.activity_state_counts.ELEVATED} />
                      <CountLine label="ACCELERATING" value={data.activity_state_counts.ACCELERATING} />
                      <CountLine label="VERY_HIGH" value={data.activity_state_counts.VERY_HIGH} />
                      <CountLine label="UNKNOWN" value={data.activity_state_counts.UNKNOWN} />
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Liquidité USD</p>
                    <div className="grid grid-cols-2 gap-x-5 gap-y-1.5">
                      <CountLine label="MICRO" value={data.liquidity_regime_counts.MICRO} />
                      <CountLine label="LOW" value={data.liquidity_regime_counts.LOW} />
                      <CountLine label="MEDIUM" value={data.liquidity_regime_counts.MEDIUM} />
                      <CountLine label="HIGH" value={data.liquidity_regime_counts.HIGH} />
                      <CountLine label="VERY_HIGH" value={data.liquidity_regime_counts.VERY_HIGH} />
                      <CountLine label="UNKNOWN" value={data.liquidity_regime_counts.UNKNOWN} />
                    </div>
                  </div>
                </div>

                <div className="grid gap-3 lg:grid-cols-3">
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Qualité structurelle</p>
                    <div className="grid grid-cols-2 gap-x-5 gap-y-1.5">
                      <CountLine label="COMPLETE" value={data.activity_data_quality_counts.COMPLETE} />
                      <CountLine label="NO_TRADE_GAPS" value={data.activity_data_quality_counts.NO_TRADE_GAPS} />
                      <CountLine label="INSUFFICIENT" value={data.activity_data_quality_counts.INSUFFICIENT_HISTORY} />
                      <CountLine label="DISCONTINUOUS" value={data.activity_data_quality_counts.DISCONTINUOUS_HISTORY} />
                      <CountLine label="TECHNICAL_ERROR" value={data.activity_data_quality_counts.TECHNICAL_ERROR} />
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Par marché</p>
                    <div className="space-y-2 font-mono text-[11px] tabular-nums">
                      <div><span className="font-semibold">SPOT</span><p className="mt-0.5 text-muted-foreground">A {data.activity_market_type_status_counts.SPOT.AVAILABLE} · P {data.activity_market_type_status_counts.SPOT.PARTIAL} · S {data.activity_market_type_status_counts.SPOT.STALE} · E {data.activity_market_type_status_counts.SPOT.ERROR}</p></div>
                      <div><span className="font-semibold">PERPETUAL</span><p className="mt-0.5 text-muted-foreground">A {data.activity_market_type_status_counts.PERPETUAL.AVAILABLE} · P {data.activity_market_type_status_counts.PERPETUAL.PARTIAL} · S {data.activity_market_type_status_counts.PERPETUAL.STALE} · E {data.activity_market_type_status_counts.PERPETUAL.ERROR}</p></div>
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Erreurs Kraken</p>
                    {activityErrorEntries(data.activity_error_counts).length ? (
                      <div className="space-y-1.5">{activityErrorEntries(data.activity_error_counts).map(([name, count]) => <CountLine key={name} label={name} value={count} />)}</div>
                    ) : <p className="text-[11px] text-muted-foreground">Aucune erreur technique dans le cache frais.</p>}
                  </div>
                </div>

                <div className="rounded-lg border p-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="text-xs font-semibold">Plus fortes activités sous seuil</p>
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
                <p className="text-[10px] text-muted-foreground">Snapshot {shortTime(data.observed_at)} · classement déterministe avec diversification descriptive par régime de liquidité. Les montants USD sont affichés uniquement lorsqu’une normalisation fiable est disponible ; sinon « — ».</p>
              </div>
            ) : <p className="text-sm text-muted-foreground">{loading ? "Chargement du radar…" : "Aucun snapshot chargé."}</p>}
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
