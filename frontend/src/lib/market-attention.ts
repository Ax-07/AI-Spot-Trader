export type RadarStatus = "AVAILABLE" | "PARTIAL" | "NOT_CONFIGURED" | "STALE" | "ERROR";
export type MarketActivityState = "UNKNOWN" | "NORMAL" | "ELEVATED" | "ACCELERATING" | "VERY_HIGH";
export type ActivityDataQuality = "COMPLETE" | "NO_TRADE_GAPS" | "INSUFFICIENT_HISTORY" | "DISCONTINUOUS_HISTORY" | "TECHNICAL_ERROR";
export type LiquidityRegime = "UNKNOWN" | "MICRO" | "LOW" | "MEDIUM" | "HIGH" | "VERY_HIGH";
export type MarketCharacteristic =
  | "TRENDING"
  | "VOLUME_ANOMALY"
  | "VOLATILITY_EXPANSION"
  | "BREAKOUT_WATCH"
  | "REVERSAL_WATCH"
  | "CONSOLIDATING"
  | "PRICE_VOLUME_DIVERGENCE";
export type RadarInterestLevel = "LOW" | "MEDIUM" | "HIGH" | "VERY_HIGH";
export type AttentionTimeframe = "5m" | "15m" | "1h" | "4h";

export type MicrostructureStatus = "AVAILABLE" | "PARTIAL" | "STALE" | "ERROR" | "NOT_APPLICABLE";
export type MicrostructureDataQuality = "COMPLETE" | "PARTIAL" | "STALE" | "TECHNICAL_ERROR" | "NOT_APPLICABLE";
export type MicrostructureCharacteristic =
  | "TIGHT_SPREAD"
  | "WIDE_SPREAD"
  | "DEEP_LIQUIDITY"
  | "THIN_LIQUIDITY"
  | "ORDER_BOOK_IMBALANCE"
  | "TRADE_ACTIVITY_SURGE"
  | "TRADE_ACTIVITY_FADE"
  | "BUY_PRESSURE"
  | "SELL_PRESSURE"
  | "SLIPPAGE_RISK";

export type AttentionMarket = {
  symbol: string;
  market_type: "SPOT" | "PERPETUAL";
};

export type ActivityHorizonSnapshot = {
  timeframe: AttentionTimeframe;
  current_volume: string | null;
  previous_comparable_volume: string | null;
  baseline_volume: string | null;
  volume_ratio: string | null;
  volume_change: string | null;
  volume_acceleration: string | null;
  current_notional_usd: string | null;
  baseline_notional_usd: string | null;
  notional_delta_usd: string | null;
  notional_method: string | null;
  price_return: string | null;
  previous_price_return: string | null;
  price_range: string | null;
  baseline_price_range: string | null;
  range_expansion_ratio: string | null;
  realized_volatility: string | null;
  baseline_realized_volatility: string | null;
  volatility_expansion_ratio: string | null;
  breakout_distance: string | null;
  observation_count: number;
  baseline_period_count: number;
  no_trade_interval_count: number;
  unexplained_gap_count: number;
  data_quality: ActivityDataQuality;
  complete: boolean;
};

export type MarketActivitySnapshot = {
  market: AttentionMarket;
  observed_at: string;
  status: RadarStatus;
  activity_state: MarketActivityState;
  liquidity_regime: LiquidityRegime;
  liquidity_reference_usd: string | null;
  freshness_seconds: string | null;
  horizons: ActivityHorizonSnapshot[];
  characteristics: MarketCharacteristic[];
  interest_level: RadarInterestLevel;
  interest_reasons: string[];
  data_quality: ActivityDataQuality;
  error_type: string | null;
};

export type DepthBandSnapshot = {
  band_bps: number;
  bid_depth_base: string;
  ask_depth_base: string;
  bid_depth_quote: string;
  ask_depth_quote: string;
};

export type SlippageEstimate = {
  side: "BUY" | "SELL";
  notional_quote: string;
  quote_asset: string;
  estimated_vwap: string | null;
  reference_price: string | null;
  slippage_absolute: string | null;
  slippage_bps: string | null;
  consumed_volume_base: string;
  available_notional_quote: string;
  insufficient_depth: boolean;
};

export type MarketMicrostructureSnapshot = {
  market: AttentionMarket;
  observed_at: string;
  status: MicrostructureStatus;
  data_quality: MicrostructureDataQuality;
  freshness_seconds: string | null;
  book_freshness_seconds: string | null;
  trade_freshness_seconds: string | null;
  quote_asset: string | null;
  best_bid: string | null;
  best_ask: string | null;
  mid_price: string | null;
  spread_absolute: string | null;
  spread_bps: string | null;
  bid_depth_base: string | null;
  ask_depth_base: string | null;
  bid_depth_quote: string | null;
  ask_depth_quote: string | null;
  total_depth_quote: string | null;
  book_imbalance: string | null;
  depth_bands: DepthBandSnapshot[];
  trade_count: number | null;
  trade_volume_base: string | null;
  trade_volume_quote: string | null;
  average_trade_size_base: string | null;
  median_trade_size_base: string | null;
  trade_rate_per_minute: string | null;
  baseline_trade_rate_per_minute: string | null;
  trade_activity_ratio: string | null;
  trade_activity_change_per_minute: string | null;
  provider_side_coverage: string | null;
  buy_volume_base: string | null;
  sell_volume_base: string | null;
  buy_sell_imbalance: string | null;
  slippage: SlippageEstimate[];
  characteristics: MicrostructureCharacteristic[];
  errors: string[];
  error_type: string | null;
};

export type ActivityStatusCounts = {
  AVAILABLE: number;
  PARTIAL: number;
  STALE: number;
  ERROR: number;
};
export type ActivityStateCounts = Record<MarketActivityState, number>;
export type ActivityDataQualityCounts = Record<ActivityDataQuality, number>;
export type ActivityErrorCounts = {
  KrakenConnectionError: number;
  KrakenNetworkError: number;
  KrakenTimeoutError: number;
  KrakenHTTPError: number;
  KrakenServerError: number;
  KrakenRateLimitError: number;
  KrakenAPIError: number;
  KrakenPayloadError: number;
  UnknownKrakenSymbolError: number;
  CandleValidationError: number;
  Other: number;
};
export type ActivityPayloadStageCounts = {
  ASSET_PAIRS_PAYLOAD: number;
  ASSET_PAIRS_ENTRY: number;
  ASSET_PAIRS_SYMBOL: number;
  OHLC_RESULT: number;
  OHLC_SERIES: number;
  OHLC_PAIR_KEY: number;
  OHLC_ROW: number;
  OHLC_TIMESTAMP: number;
  OHLC_NUMERIC: number;
};
export type ActivityMarketTypeStatusCounts = {
  SPOT: ActivityStatusCounts;
  PERPETUAL: ActivityStatusCounts;
};
export type MarketTypeCounts = { SPOT: number; PERPETUAL: number };
export type LiquidityRegimeCounts = Record<LiquidityRegime, number>;
export type MicrostructureStatusCounts = Record<MicrostructureStatus, number>;
export type MicrostructureQualityCounts = Record<MicrostructureDataQuality, number>;

export type SubthresholdActivitySnapshot = {
  market: AttentionMarket;
  peak_volume_ratio: string;
  peak_timeframe: AttentionTimeframe;
};

export type MarketAttentionSnapshot = {
  market_activity: MarketActivitySnapshot;
  microstructure: MarketMicrostructureSnapshot;
  combined_characteristics: string[];
  interest_level: RadarInterestLevel;
  interest_reasons: string[];
};

export type MarketAttentionOverview = {
  protocol_version: "market-attention-radar-v3";
  observed_at: string;
  status: RadarStatus;
  informative_only: true;
  catalogue_market_count: number;
  cached_activity_market_count: number;
  scanned_market_count: number;
  scanned_market_type_counts: MarketTypeCounts;
  fresh_market_type_counts: MarketTypeCounts;
  candidate_market_count: number;
  activity_status_counts: ActivityStatusCounts;
  activity_state_counts: ActivityStateCounts;
  activity_data_quality_counts: ActivityDataQualityCounts;
  activity_error_counts: ActivityErrorCounts;
  activity_payload_stage_counts: ActivityPayloadStageCounts;
  activity_market_type_status_counts: ActivityMarketTypeStatusCounts;
  liquidity_regime_counts: LiquidityRegimeCounts;
  microstructure_scanned_market_count: number;
  microstructure_cached_market_count: number;
  microstructure_status_counts: MicrostructureStatusCounts;
  microstructure_quality_counts: MicrostructureQualityCounts;
  microstructure_error_counts: Record<string, number>;
  subthreshold_activity: SubthresholdActivitySnapshot[];
  shortlist: MarketAttentionSnapshot[];
  error_type: string | null;
};

export function activityErrorEntries(
  counts: ActivityErrorCounts,
): Array<[keyof ActivityErrorCounts, number]> {
  const order: Array<keyof ActivityErrorCounts> = [
    "KrakenConnectionError",
    "KrakenNetworkError",
    "KrakenTimeoutError",
    "KrakenHTTPError",
    "KrakenServerError",
    "KrakenRateLimitError",
    "KrakenAPIError",
    "KrakenPayloadError",
    "UnknownKrakenSymbolError",
    "CandleValidationError",
    "Other",
  ];
  return order
    .map((name) => [name, counts[name]] as [keyof ActivityErrorCounts, number])
    .filter((entry) => entry[1] > 0);
}

export function attentionHorizon(
  item: MarketAttentionSnapshot,
  timeframe: AttentionTimeframe,
): ActivityHorizonSnapshot | null {
  return item.market_activity.horizons.find((entry) => entry.timeframe === timeframe) ?? null;
}

export function slippageEstimate(
  item: MarketAttentionSnapshot,
  side: "BUY" | "SELL",
  notionalQuote = 1000,
): SlippageEstimate | null {
  return item.microstructure.slippage.find(
    (entry) => entry.side === side && Number(entry.notional_quote) === notionalQuote,
  ) ?? null;
}

export function formatVolumeRatio(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  return `${parsed.toFixed(parsed >= 10 ? 1 : 2)}×`;
}

export function formatSignedPercent(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  const percent = parsed * 100;
  return `${percent > 0 ? "+" : ""}${percent.toFixed(2)} %`;
}

export function formatBps(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  return `${parsed.toFixed(parsed >= 100 ? 0 : parsed >= 10 ? 1 : 2)} bps`;
}

export function formatImbalance(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  const percent = parsed * 100;
  return `${percent > 0 ? "+" : ""}${percent.toFixed(1)} %`;
}

export function formatRate(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  return `${parsed.toFixed(parsed >= 10 ? 1 : 2)}/min`;
}

export function formatQuoteCompact(
  value: string | number | null | undefined,
  quoteAsset: string | null | undefined,
): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  const suffix = quoteAsset ? ` ${quoteAsset}` : "";
  const absolute = Math.abs(parsed);
  if (absolute >= 1_000_000_000) return `${(parsed / 1_000_000_000).toFixed(1)} B${suffix}`;
  if (absolute >= 1_000_000) return `${(parsed / 1_000_000).toFixed(1)} M${suffix}`;
  if (absolute >= 1_000) return `${(parsed / 1_000).toFixed(1)} k${suffix}`;
  if (absolute >= 10) return `${Math.round(parsed).toLocaleString("fr-FR")}${suffix}`;
  return `${parsed.toFixed(2)}${suffix}`;
}

export function formatUsdCompact(
  value: string | number | null | undefined,
  options: { signed?: boolean } = {},
): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  const sign = options.signed && parsed > 0 ? "+" : "";
  const absolute = Math.abs(parsed);
  if (absolute >= 1_000_000_000) return `${sign}${(parsed / 1_000_000_000).toFixed(1)} B$`;
  if (absolute >= 1_000_000) return `${sign}${(parsed / 1_000_000).toFixed(1)} M$`;
  if (absolute >= 1_000) return `${sign}${(parsed / 1_000).toFixed(1)} k$`;
  if (absolute >= 10) return `${sign}${Math.round(parsed).toLocaleString("fr-FR")} $`;
  return `${sign}${parsed.toFixed(2)} $`;
}

export function marketAttentionStatusMessage(overview: MarketAttentionOverview): string {
  if (overview.status === "NOT_CONFIGURED") return "Radar non configuré.";
  if (overview.status === "ERROR") return "Radar en erreur — consulter le diagnostic Kraken backend.";
  if (overview.status === "STALE") return "Radar opérationnel mais données Kraken périmées.";
  if (overview.status === "PARTIAL") {
    return overview.candidate_market_count > 0
      ? "Radar partiellement disponible — certains marchés Kraken sont dégradés."
      : "Radar partiellement disponible — aucune activité inhabituelle confirmée sur les données exploitables.";
  }
  if (overview.candidate_market_count === 0) {
    return "Radar opérationnel — aucun événement inhabituel détecté.";
  }
  return `Radar opérationnel — ${overview.candidate_market_count} candidat${overview.candidate_market_count > 1 ? "s" : ""} d’attention.`;
}

export async function fetchMarketAttention(signal?: AbortSignal): Promise<MarketAttentionOverview> {
  const response = await fetch("/backend/api/v1/market-attention", {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error(`Radar backend indisponible (${response.status})`);
  return (await response.json()) as MarketAttentionOverview;
}
