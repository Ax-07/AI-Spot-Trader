"use client";

import { Radar, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  activeMarketAttentionFilters,
  activityErrorEntries,
  attentionHorizon,
  fetchMarketAttention,
  formatBps,
  formatCoverageRatio,
  formatDurationSeconds,
  formatImbalance,
  formatQuoteCompact,
  formatRate,
  formatSignedPercent,
  formatUsdCompact,
  formatVolumeRatio,
  marketAttentionCoverageMessage,
  marketAttentionStatusMessage,
  marketCapCategoryLabel,
  marketStructureCoverageMessage,
  setMarketAttentionFilters,
  slippageEstimate,
  structureEventFilterLabel,
  structureStateFilterLabel,
  trendDirectionLabel,
  type AttentionTimeframe,
  type LiquidityRegime,
  type MarketAttentionCoverageStatus,
  type MarketAttentionFilters,
  type MarketAttentionOverview,
  type MarketAttentionSnapshot,
  type MarketCapCategory,
  type MarketScope,
  type MarketStructureState,
  type MicrostructureCharacteristic,
  type MultiTimeframeStructureState,
  type RadarInterestLevel,
  type RadarStatus,
  type StructureEvent,
  type TrendDirection,
} from "@/lib/market-attention";
import {
  marketStructure,
  structureEventLabel,
  structureStateLabel,
  structureTimeframe,
  swingSequenceLabel,
} from "@/lib/market-structure";

function statusTone(status: RadarStatus) {
  if (status === "AVAILABLE") return "success" as const;
  if (status === "PARTIAL" || status === "STALE") return "warning" as const;
  if (status === "ERROR") return "danger" as const;
  return "neutral" as const;
}

function coverageTone(status: MarketAttentionCoverageStatus) {
  if (status === "COVERED") return "success" as const;
  if (status === "ROTATING") return "info" as const;
  if (status === "TTL_EXPIRED" || status === "CONFIGURATION_TOO_SLOW") return "warning" as const;
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

const SCOPE_OPTIONS: Array<{ value: MarketScope; label: string }> = [
  { value: "SPOT", label: "SPOT" },
  { value: "PERPETUAL", label: "PERP" },
  { value: "ALL", label: "TOUS" },
];

const VOLUME_OPTIONS: Array<{ value: string | null; label: string }> = [
  { value: null, label: "Tous" },
  { value: "100000", label: "≥ 100 k$" },
  { value: "500000", label: "≥ 500 k$" },
  { value: "1000000", label: "≥ 1 M$" },
  { value: "5000000", label: "≥ 5 M$" },
  { value: "10000000", label: "≥ 10 M$" },
];

const MARKET_CAP_OPTIONS: Array<{ value: MarketCapCategory; label: string }> = [
  { value: "MICRO", label: "Micro" },
  { value: "SMALL", label: "Small" },
  { value: "MID", label: "Mid" },
  { value: "LARGE", label: "Large" },
];

const TREND_OPTIONS: TrendDirection[] = ["UP", "DOWN", "NEUTRAL", "MIXED"];
const GLOBAL_STRUCTURE_OPTIONS: MultiTimeframeStructureState[] = [
  "BULLISH",
  "BEARISH",
  "RANGE",
  "TRANSITION",
  "MIXED",
];
const TIMEFRAME_STRUCTURE_STATES: MarketStructureState[] = [
  "BULLISH",
  "BEARISH",
  "RANGE",
  "TRANSITION",
];
const STRUCTURE_EVENTS: StructureEvent[] = ["BOS_UP", "BOS_DOWN", "CHOCH_UP", "CHOCH_DOWN"];
const STRUCTURE_FILTER_KEYS = {
  "5m": "structure_5m",
  "15m": "structure_15m",
  "1h": "structure_1h",
  "4h": "structure_4h",
} as const;

type StructureFilterKey = (typeof STRUCTURE_FILTER_KEYS)[AttentionTimeframe];

function toggleValue<T extends string>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((entry) => entry !== value) : [...values, value];
}

function microLabel(value: string) {
  return MICRO_LABELS[value as MicrostructureCharacteristic] ?? value.replaceAll("_", " ");
}

function MarketRow({ item, expanded, onToggle }: { item: MarketAttentionSnapshot; expanded: boolean; onToggle: () => void }) {
  const activity = item.market_activity;
  const micro = item.microstructure;
  const structure = marketStructure(item);
  const h5 = attentionHorizon(item, "5m");
  const h15 = attentionHorizon(item, "15m");
  const h1 = attentionHorizon(item, "1h");
  const h4 = attentionHorizon(item, "4h");
  const priceMove = h15?.price_return ?? h5?.price_return ?? null;
  const acquisition1k = slippageEstimate(item, "BUY", 1000);
  const cession1k = slippageEstimate(item, "SELL", 1000);

  return (
    <div className="rounded-xl border bg-background/70">
      <button type="button" onClick={onToggle} className="grid w-full gap-3 p-3 text-left md:grid-cols-[minmax(190px,1.3fr)_repeat(11,minmax(68px,0.7fr))] md:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold">{activity.market.symbol}</span>
            <Badge tone="neutral">{activity.market.market_type}</Badge>
            <Badge tone="neutral">{trendDirectionLabel(activity.trend_direction)}</Badge>
            <Badge tone="neutral">Structure · {structureStateLabel(structure?.global_state)}</Badge>
            <Badge tone={liquidityTone(activity.liquidity_regime)}>{activity.liquidity_regime}</Badge>
            <Badge tone={interestTone(item.interest_level)}>{item.interest_level}</Badge>
          </div>
          <p className="mt-1 truncate text-[11px] text-muted-foreground">
            {item.combined_characteristics.length ? item.combined_characteristics.map(microLabel).join(" · ") : "Aucune caractéristique forte"}
          </p>
        </div>
        <Fact label="Activité" value={activity.activity_state.replaceAll("_", " ")} />
        <Fact label="Tendance" value={trendDirectionLabel(activity.trend_direction)} />
        <Fact label="Structure" value={structureStateLabel(structure?.global_state)} />
        <Fact label="Vol. 24h" value={formatUsdCompact(item.volume_24h_usd)} />
        <Fact label="Capitalisation" value={formatUsdCompact(item.market_cap_usd)} />
        <Fact label="Vol. 5m" value={formatVolumeRatio(h5?.volume_ratio)} />
        <Fact label="Spread" value={formatBps(micro.spread_bps)} />
        <Fact label="Prof. L2" value={formatQuoteCompact(micro.total_depth_quote, micro.quote_asset)} />
        <Fact label="Déséquilibre" value={formatImbalance(micro.book_imbalance)} />
        <Fact label="Trades" value={formatRate(micro.trade_rate_per_minute)} />
        <Fact label="Prix" value={formatSignedPercent(priceMove)} />
      </button>

      {expanded ? (
        <div className="space-y-4 border-t px-3 py-4 text-xs">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-10">
            <Fact label="Niveau d’intérêt" value={item.interest_level} />
            <Fact label="Tendance globale" value={trendDirectionLabel(activity.trend_direction)} />
            <Fact label="Structure globale" value={structureStateLabel(structure?.global_state)} />
            <Fact label="Volume 24h" value={formatUsdCompact(item.volume_24h_usd)} />
            <Fact label="Capitalisation" value={formatUsdCompact(item.market_cap_usd)} />
            <Fact label="Catégorie cap." value={marketCapCategoryLabel(item.market_cap_category)} />
            <Fact label="Rang cap." value={item.market_cap_rank ? `#${item.market_cap_rank}` : "—"} />
            <Fact label="Qualité OHLCV" value={activity.data_quality} />
            <Fact label="Microstructure" value={`${micro.status} / ${micro.data_quality}`} />
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
              <p className="font-semibold">Métadonnées de taille</p>
              <div className="mt-2 space-y-1.5">
                <Fact label="Capitalisation" value={formatUsdCompact(item.market_cap_usd)} />
                <Fact label="Catégorie" value={marketCapCategoryLabel(item.market_cap_category)} />
                <Fact label="Rang" value={item.market_cap_rank ? `#${item.market_cap_rank}` : "—"} />
                <Fact label="Provider" value={item.market_cap_provider ?? "—"} />
                <Fact label="Mise à jour" value={shortTime(item.market_cap_observed_at)} />
              </div>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[h5, h15, h1, h4].map((horizon, index) => (
              <div key={horizon?.timeframe ?? index} className="rounded-lg border bg-muted/10 p-3">
                <p className="font-semibold">OHLCV · {horizon?.timeframe ?? "—"}</p>
                <div className="mt-2 space-y-1.5">
                  <Fact label="Tendance récente" value={trendDirectionLabel(horizon?.trend_direction)} />
                  <Fact label="Volume relatif" value={formatVolumeRatio(horizon?.volume_ratio)} />
                  <Fact label="Variation prix" value={formatSignedPercent(horizon?.price_return)} />
                  <Fact label="Expansion range" value={formatVolumeRatio(horizon?.range_expansion_ratio)} />
                  <Fact label="Expansion volatilité" value={formatVolumeRatio(horizon?.volatility_expansion_ratio)} />
                  <Fact label="Distance breakout" value={formatSignedPercent(horizon?.breakout_distance)} />
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-lg border bg-muted/10 p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="font-semibold">Structure de marché multi-timeframe</p>
              <p className="text-[10px] text-muted-foreground">Pivots confirmés sur candles Kraken natives finalisées · ~100 bougies / timeframe</p>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {(["5m", "15m", "1h", "4h"] as const).map((timeframe) => {
                const frame = structureTimeframe(structure, timeframe);
                const eventLabel = structureEventLabel(frame?.event);
                return (
                  <div key={timeframe} className="rounded-lg border bg-background/50 p-3">
                    <p className="font-semibold">Structure {timeframe}</p>
                    <div className="mt-2 space-y-1.5">
                      <Fact label="État" value={structureStateLabel(frame?.state)} />
                      <Fact label="Swings" value={swingSequenceLabel(frame)} />
                      <Fact label="Bougies finalisées" value={frame ? String(frame.history_count) : "—"} />
                      <Fact label="Dernière clôture" value={shortTime(frame?.latest_final_close)} />
                    </div>
                    {eventLabel ? <p className="mt-2 text-[10px] font-medium text-muted-foreground">{eventLabel}</p> : null}
                    {frame?.error_type ? <p className="mt-2 text-[10px] text-destructive-subtle-foreground">{frame.error_type}</p> : null}
                  </div>
                );
              })}
            </div>
            <p className="mt-3 text-[10px] text-muted-foreground">
              La tendance récente décrit le mouvement de prix observé. La structure décrit la géométrie des swings confirmés. Elles restent indépendantes et ne constituent ni BUY, ni SELL, ni HOLD.
            </p>
          </div>

          {micro.errors.length ? (
            <div className="rounded-lg border bg-muted/10 p-3">
              <p className="font-semibold">Diagnostic microstructure Kraken</p>
              <p className="mt-1 text-muted-foreground">{micro.errors.join(" · ")}</p>
            </div>
          ) : null}

          <p className="rounded-lg border bg-muted/10 p-3 text-muted-foreground">
            Prix, OHLCV, structure de marché, carnet L2 et trades récents proviennent de Kraken. La capitalisation est une métadonnée externe read-only ; elle n’autorise aucune décision ni aucun ordre.
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

  const changeFilters = useCallback(async (update: Partial<MarketAttentionFilters>) => {
    if (!data) return;
    setLoading(true);
    try {
      const current = activeMarketAttentionFilters(data);
      const next = await setMarketAttentionFilters({ ...current, ...update });
      setData(next);
      setExpandedKey(null);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Changement de filtres impossible");
    } finally {
      setLoading(false);
    }
  }, [data]);

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
  const filters = useMemo(() => data ? activeMarketAttentionFilters(data) : null, [data]);

  function toggleOpen() {
    if (!open) void refresh();
    setOpen((value) => !value);
  }

  function toggleMarketCapCategory(category: MarketCapCategory) {
    if (!filters) return;
    void changeFilters({ market_cap_categories: toggleValue(filters.market_cap_categories, category) });
  }

  function toggleTrend(direction: TrendDirection) {
    if (!filters) return;
    void changeFilters({ trend_directions: toggleValue(filters.trend_directions, direction) });
  }

  function toggleGlobalStructure(state: MultiTimeframeStructureState) {
    if (!filters) return;
    void changeFilters({
      structure_global_states: toggleValue(filters.structure_global_states, state),
    });
  }

  function updateTimeframeStructure(
    timeframe: AttentionTimeframe,
    field: "states" | "events",
    value: MarketStructureState | StructureEvent,
  ) {
    if (!filters) return;
    const key: StructureFilterKey = STRUCTURE_FILTER_KEYS[timeframe];
    const criterion = filters[key];
    const next = field === "states"
      ? { ...criterion, states: toggleValue(criterion.states, value as MarketStructureState) }
      : { ...criterion, events: toggleValue(criterion.events, value as StructureEvent) };
    void changeFilters({ [key]: next } as Partial<MarketAttentionFilters>);
  }

  function clearStructureFilters() {
    void changeFilters({
      structure_global_states: [],
      structure_5m: { states: [], events: [] },
      structure_15m: { states: [], events: [] },
      structure_1h: { states: [], events: [] },
      structure_4h: { states: [], events: [] },
    });
  }

  return (
    <>
      <Button type="button" onClick={toggleOpen} className="fixed bottom-5 right-5 z-50 shadow-xl" aria-expanded={open}>
        <Radar className="size-4" /> Radar marché
        {data ? <span className="ml-1"><Badge tone={statusTone(data.status)}>{data.status}</Badge></span> : null}
      </Button>

      {open ? <div className="fixed inset-0 z-40 bg-black/20" onClick={() => setOpen(false)} aria-hidden="true" /> : null}

      {open ? (
        <Card className="fixed bottom-20 right-3 z-50 max-h-[78vh] w-[min(96vw,1240px)] overflow-hidden shadow-2xl sm:right-5">
          <CardHeader className="border-b">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="flex items-center gap-2"><Radar className="size-4" /> Market Attention</CardTitle>
                  <span className="inline-flex"><Badge tone="info">INFORMATIF — N’INFLUENCE PAS LE TRADING</Badge></span>
                  {data ? <span className="inline-flex"><Badge tone={statusTone(data.status)}>État · {data.status}</Badge></span> : null}
                  {data ? <span className="inline-flex"><Badge tone="neutral">Marché · {data.market_scope === "ALL" ? "TOUS" : data.market_scope === "PERPETUAL" ? "PERP" : "SPOT"}</Badge></span> : null}
                </div>
                <CardDescription className="mt-1">Données de marché Kraken déterministes, avec capitalisation descriptive via provider externe read-only. Aucun appel IA, aucune exécution et aucun signal BUY / SELL / HOLD.</CardDescription>
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
            {data && filters ? (
              <div className="space-y-4">
                <div className="grid gap-3 rounded-lg border p-3 lg:grid-cols-3">
                  <div>
                    <p className="text-xs font-semibold">Marché</p>
                    <p className="text-[10px] text-muted-foreground">Appliqué avant le scan OHLCV.</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {SCOPE_OPTIONS.map((option) => (
                        <Button
                          key={option.value}
                          type="button"
                          size="sm"
                          variant={filters.market_scope === option.value ? "default" : "outline"}
                          disabled={loading}
                          aria-pressed={filters.market_scope === option.value}
                          onClick={() => void changeFilters({ market_scope: option.value })}
                        >
                          {option.label}
                        </Button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold">Volume 24h</p>
                    <p className="text-[10px] text-muted-foreground">SPOT/USD : candles Kraken causales. PERP linear/USD : `volumeQuote` Kraken Futures. UNKNOWN est exclu lorsqu’un seuil est actif.</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {VOLUME_OPTIONS.map((option) => (
                        <Button
                          key={option.value ?? "ALL"}
                          type="button"
                          size="sm"
                          variant={filters.min_volume_24h_usd === option.value ? "default" : "outline"}
                          disabled={loading}
                          aria-pressed={filters.min_volume_24h_usd === option.value}
                          onClick={() => void changeFilters({ min_volume_24h_usd: option.value })}
                        >
                          {option.label}
                        </Button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold">Capitalisation</p>
                    <p className="text-[10px] text-muted-foreground">Catégories applicatives : &lt;100 M$, 100 M$–1 Md$, 1–10 Md$, ≥10 Md$.</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Button
                        type="button"
                        size="sm"
                        variant={filters.market_cap_categories.length === 0 ? "default" : "outline"}
                        disabled={loading}
                        aria-pressed={filters.market_cap_categories.length === 0}
                        onClick={() => void changeFilters({ market_cap_categories: [] })}
                      >
                        Toutes
                      </Button>
                      {MARKET_CAP_OPTIONS.map((option) => (
                        <Button
                          key={option.value}
                          type="button"
                          size="sm"
                          variant={filters.market_cap_categories.includes(option.value) ? "default" : "outline"}
                          disabled={loading}
                          aria-pressed={filters.market_cap_categories.includes(option.value)}
                          onClick={() => toggleMarketCapCategory(option.value)}
                        >
                          {option.label}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>

                <details className="rounded-lg border p-3">
                  <summary className="cursor-pointer text-xs font-semibold">Filtres Tendance & Market Structure</summary>
                  <p className="mt-1 text-[10px] text-muted-foreground">OR dans un même champ ; AND entre familles et timeframes configurées. UNKNOWN est fail-closed lorsqu’un filtre est actif.</p>

                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    <div className="rounded-lg border bg-muted/10 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-semibold">Tendance récente</p>
                        <Button size="sm" variant="outline" disabled={loading || filters.trend_directions.length === 0} onClick={() => void changeFilters({ trend_directions: [] })}>Toutes</Button>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {TREND_OPTIONS.map((direction) => (
                          <Button
                            key={direction}
                            size="sm"
                            variant={filters.trend_directions.includes(direction) ? "default" : "outline"}
                            disabled={loading}
                            aria-pressed={filters.trend_directions.includes(direction)}
                            onClick={() => toggleTrend(direction)}
                          >
                            {trendDirectionLabel(direction)}
                          </Button>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-lg border bg-muted/10 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-semibold">Structure globale</p>
                        <Button size="sm" variant="outline" disabled={loading || filters.structure_global_states.length === 0} onClick={clearStructureFilters}>Effacer Structure</Button>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {GLOBAL_STRUCTURE_OPTIONS.map((state) => (
                          <Button
                            key={state}
                            size="sm"
                            variant={filters.structure_global_states.includes(state) ? "default" : "outline"}
                            disabled={loading}
                            aria-pressed={filters.structure_global_states.includes(state)}
                            onClick={() => toggleGlobalStructure(state)}
                          >
                            {structureStateFilterLabel(state)}
                          </Button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    {(["5m", "15m", "1h", "4h"] as const).map((timeframe) => {
                      const key: StructureFilterKey = STRUCTURE_FILTER_KEYS[timeframe];
                      const criterion = filters[key];
                      return (
                        <div key={timeframe} className="rounded-lg border bg-muted/10 p-3">
                          <p className="text-xs font-semibold">Structure {timeframe}</p>
                          <p className="mt-2 text-[9px] font-bold uppercase tracking-wide text-muted-foreground">États</p>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {TIMEFRAME_STRUCTURE_STATES.map((state) => (
                              <Button
                                key={state}
                                size="sm"
                                variant={criterion.states.includes(state) ? "default" : "outline"}
                                disabled={loading}
                                aria-pressed={criterion.states.includes(state)}
                                onClick={() => updateTimeframeStructure(timeframe, "states", state)}
                              >
                                {structureStateFilterLabel(state)}
                              </Button>
                            ))}
                          </div>
                          <p className="mt-3 text-[9px] font-bold uppercase tracking-wide text-muted-foreground">Événements</p>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {STRUCTURE_EVENTS.map((event) => (
                              <Button
                                key={event}
                                size="sm"
                                variant={criterion.events.includes(event) ? "default" : "outline"}
                                disabled={loading}
                                aria-pressed={criterion.events.includes(event)}
                                onClick={() => updateTimeframeStructure(timeframe, "events", event)}
                              >
                                {structureEventFilterLabel(event)}
                              </Button>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </details>

                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-8">
                  <Fact label="Catalogue filtré" value={String(data.catalogue_market_count)} />
                  <Fact label="Marchés frais OHLCV" value={String(data.cached_activity_market_count)} />
                  <Fact label="Scannés OHLCV" value={String(data.scanned_market_count)} />
                  <Fact label="Scannés micro" value={String(data.microstructure_scanned_market_count)} />
                  <Fact label="Cache micro" value={String(data.microstructure_cached_market_count)} />
                  <Fact label="Scannés Structure" value={String(data.structure_coverage?.scanned_market_count ?? 0)} />
                  <Fact label="Candidats" value={String(data.candidate_market_count)} />
                  <Fact label="Metadata cap." value={data.market_cap_metadata_status ?? "—"} />
                </div>

                <div className="rounded-lg border bg-muted/10 px-3 py-2 text-xs font-medium">{marketAttentionStatusMessage(data)}</div>

                {data.coverage ? (
                  <div className="rounded-lg border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-xs font-semibold">Couverture et rotation OHLCV</p>
                        <p className="text-[10px] text-muted-foreground">Univers de scan après scope et filtre de capitalisation, avant filtre volume post-OHLCV.</p>
                      </div>
                      <Badge tone={coverageTone(data.coverage.status)}>{data.coverage.status}</Badge>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
                      <Fact label="Éligibles" value={String(data.coverage.eligible_market_count)} />
                      <Fact label="Frais" value={String(data.coverage.fresh_market_count)} />
                      <Fact label="Expirés TTL" value={String(data.coverage.expired_market_count)} />
                      <Fact label="Jamais vus" value={String(data.coverage.unseen_market_count)} />
                      <Fact label="Couverture" value={formatCoverageRatio(data.coverage.coverage_ratio)} />
                      <Fact label="Scan effectif" value={String(data.coverage.effective_scan_limit)} />
                      <Fact label="Cycles / rotation" value={String(data.coverage.estimated_refreshes_per_full_rotation)} />
                      <Fact label="Rotation estimée" value={formatDurationSeconds(data.coverage.estimated_full_rotation_seconds)} />
                      <Fact label="TTL activité" value={formatDurationSeconds(data.coverage.activity_ttl_seconds)} />
                      <Fact label="Plus vieille activité" value={formatDurationSeconds(data.coverage.oldest_activity_age_seconds)} />
                      <Fact label="Rotation ≤ TTL" value={data.coverage.rotation_within_activity_ttl ? "OUI" : "NON"} />
                    </div>
                    <p className="mt-3 text-[11px] text-muted-foreground">{marketAttentionCoverageMessage(data.coverage)}</p>
                  </div>
                ) : null}

                {data.structure_coverage ? (
                  <div className="rounded-lg border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-xs font-semibold">Couverture et rotation Market Structure</p>
                        <p className="text-[10px] text-muted-foreground">Pool après scope, capitalisation, OHLCV exploitable et filtre volume ; cache Structure séparé du cache activité.</p>
                      </div>
                      <Badge tone={coverageTone(data.structure_coverage.status)}>{data.structure_coverage.status}</Badge>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
                      <Fact label="Éligibles Structure" value={String(data.structure_coverage.eligible_market_count)} />
                      <Fact label="Structures fraîches" value={String(data.structure_coverage.fresh_market_count)} />
                      <Fact label="Structures expirées" value={String(data.structure_coverage.expired_market_count)} />
                      <Fact label="Jamais analysés" value={String(data.structure_coverage.unseen_market_count)} />
                      <Fact label="Scannés ce cycle" value={String(data.structure_coverage.scanned_market_count)} />
                      <Fact label="Couverture" value={formatCoverageRatio(data.structure_coverage.coverage_ratio)} />
                      <Fact label="Limite / refresh" value={String(data.structure_coverage.effective_market_limit)} />
                      <Fact label="Cycles / rotation" value={String(data.structure_coverage.estimated_refreshes_per_full_rotation)} />
                      <Fact label="Rotation estimée" value={formatDurationSeconds(data.structure_coverage.estimated_full_rotation_seconds)} />
                      <Fact label="TTL Structure" value={formatDurationSeconds(data.structure_coverage.cache_ttl_seconds)} />
                      <Fact label="Plus vieille Structure" value={formatDurationSeconds(data.structure_coverage.oldest_structure_age_seconds)} />
                      <Fact label="Rotation ≤ TTL" value={data.structure_coverage.rotation_within_cache_ttl ? "OUI" : "NON"} />
                    </div>
                    <p className="mt-3 text-[11px] text-muted-foreground">{marketStructureCoverageMessage(data.structure_coverage)}</p>
                  </div>
                ) : null}

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
                    {loading ? "Construction du snapshot du radar…" : data.status === "NOT_CONFIGURED" ? "Radar non configuré." : marketAttentionStatusMessage(data)}
                  </div>
                )}
                <p className="text-[10px] text-muted-foreground">Snapshot {shortTime(data.observed_at)} · filtres pilotés par le backend · classement déterministe. Volume 24h SPOT = candles Kraken causales ; volume 24h PERP linear/USD = `volumeQuote` Kraken Futures uniquement lorsqu’il est validé ; capitalisation = {data.market_cap_metadata_provider ?? "provider externe indisponible"}. La Market Structure utilise uniquement des candles finalisées et des pivots confirmés ; UNKNOWN est fail-closed lorsqu’un filtre correspondant est actif.</p>
              </div>
            ) : <p className="text-sm text-muted-foreground">{loading ? "Chargement du radar…" : "Aucun snapshot chargé."}</p>}
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
