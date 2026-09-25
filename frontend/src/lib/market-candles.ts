import type {
  ExecutableMarketResponse,
  ExecutableMarketType,
  ExecutionResponse,
  ExplainabilityMarketResponse,
  PortfolioResponse,
} from "@/lib/api/types";

export type CandleTimeframe =
  | "1m"
  | "5m"
  | "15m"
  | "30m"
  | "1h"
  | "4h"
  | "12h"
  | "1d"
  | "1w"
  | "15d";

export type CandleKeyResponse = {
  symbol: string;
  market_type: ExecutableMarketType;
  timeframe: CandleTimeframe;
};

export type CandleResponse = {
  symbol: string;
  market_type: ExecutableMarketType;
  timeframe: CandleTimeframe;
  open_time: string;
  close_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  is_final: boolean;
  updated_at: string;
};

export type CandleStreamStatusResponse = {
  key: CandleKeyResponse;
  connected: boolean;
  stale: boolean;
  last_update_at: string | null;
  last_error: string | null;
};

export type CandleHistoryResponse = {
  key: CandleKeyResponse;
  candles: CandleResponse[];
  status: CandleStreamStatusResponse;
};

export type CandleSnapshotMessage = {
  type: "snapshot";
  key: CandleKeyResponse;
  candles: CandleResponse[];
  status: CandleStreamStatusResponse;
};

export type CandleUpdateMessage = {
  type: "candle";
  candle: CandleResponse;
  status: CandleStreamStatusResponse;
};

export type CandleErrorMessage = {
  type: "error";
  detail: string;
};

export type CandleStreamMessage = CandleSnapshotMessage | CandleUpdateMessage | CandleErrorMessage;

export type CockpitMarket = ExecutableMarketResponse & {
  hasPosition: boolean;
};

export type ChartCandlestick = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type ChartVolume = {
  time: number;
  value: number;
  direction: "up" | "down";
};

export type MarketFillMarker = {
  id: string;
  cycleId: string;
  executionId: string;
  fillId: string;
  action: "BUY" | "SELL";
  symbol: string;
  marketType: ExecutableMarketType;
  filledAt: string;
  quantity: string | null;
  price: string | null;
  fee: string | null;
  reduceOnly: boolean | null;
};

export const MARKET_TIMEFRAMES: Readonly<Record<ExecutableMarketType, readonly CandleTimeframe[]>> = {
  SPOT: ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "15d"],
  PERPETUAL: ["1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d", "1w"],
};

export function marketKey(market: Pick<ExecutableMarketResponse, "symbol" | "market_type">): string {
  return `${market.market_type}:${market.symbol}`;
}

function executableMarket(value: ExplainabilityMarketResponse): ExecutableMarketResponse | null {
  if (value.market_type !== "SPOT" && value.market_type !== "PERPETUAL") return null;
  const symbol = value.symbol.trim().toUpperCase();
  if (!symbol) return null;
  return { symbol, market_type: value.market_type };
}

function openPositionMarkets(portfolio: PortfolioResponse | null): ExecutableMarketResponse[] {
  if (!portfolio) return [];
  const result: ExecutableMarketResponse[] = [];
  const settlement = portfolio.settlement_asset?.trim().toUpperCase() ?? "";
  if (settlement) {
    for (const position of portfolio.positions) {
      const asset = position.asset.trim().toUpperCase();
      if (asset) result.push({ symbol: `${asset}/${settlement}`, market_type: "SPOT" });
    }
  }
  for (const position of portfolio.derivative_positions) {
    const symbol = position.symbol.trim().toUpperCase();
    if (symbol) result.push({ symbol, market_type: "PERPETUAL" });
  }
  return result;
}

export function buildCockpitMarkets({
  effectiveWatchlist,
  bootstrapMarkets,
  portfolio,
}: {
  effectiveWatchlist: ExplainabilityMarketResponse[] | null | undefined;
  bootstrapMarkets: ExecutableMarketResponse[] | null | undefined;
  portfolio: PortfolioResponse | null;
}): CockpitMarket[] {
  const watchlist = (effectiveWatchlist ?? [])
    .map(executableMarket)
    .filter((item): item is ExecutableMarketResponse => item !== null);
  const primary = watchlist.length > 0 ? watchlist : (bootstrapMarkets ?? []);
  const positions = openPositionMarkets(portfolio);
  const positionKeys = new Set(positions.map(marketKey));
  const result: CockpitMarket[] = [];
  const seen = new Set<string>();

  for (const market of [...primary, ...positions]) {
    if (market.market_type !== "SPOT" && market.market_type !== "PERPETUAL") continue;
    const normalized = {
      symbol: market.symbol.trim().toUpperCase(),
      market_type: market.market_type,
    } satisfies ExecutableMarketResponse;
    if (!normalized.symbol) continue;
    const key = marketKey(normalized);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({ ...normalized, hasPosition: positionKeys.has(key) });
  }
  return result;
}

export function mergeCandleSeries(
  current: readonly CandleResponse[],
  incoming: readonly CandleResponse[],
  limit = 1000,
): CandleResponse[] {
  const byOpenTime = new Map(current.map((item) => [item.open_time, item]));
  for (const candle of incoming) {
    const existing = byOpenTime.get(candle.open_time);
    if (existing?.is_final && !candle.is_final) continue;
    if (existing && Date.parse(candle.updated_at) < Date.parse(existing.updated_at)) continue;
    byOpenTime.set(candle.open_time, candle);
  }
  return [...byOpenTime.values()]
    .sort((left, right) => Date.parse(left.open_time) - Date.parse(right.open_time))
    .slice(-Math.max(1, limit));
}

function finiteNumber(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function epochSeconds(value: string): number | null {
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) return null;
  return Math.floor(milliseconds / 1000);
}

export function toCandlestickData(candles: readonly CandleResponse[]): ChartCandlestick[] {
  const result: ChartCandlestick[] = [];
  for (const candle of candles) {
    const time = epochSeconds(candle.open_time);
    const open = finiteNumber(candle.open);
    const high = finiteNumber(candle.high);
    const low = finiteNumber(candle.low);
    const close = finiteNumber(candle.close);
    if (time === null || open === null || high === null || low === null || close === null) continue;
    result.push({ time, open, high, low, close });
  }
  return result;
}

export function toVolumeData(candles: readonly CandleResponse[]): ChartVolume[] {
  const result: ChartVolume[] = [];
  for (const candle of candles) {
    const time = epochSeconds(candle.open_time);
    const value = finiteNumber(candle.volume);
    const open = finiteNumber(candle.open);
    const close = finiteNumber(candle.close);
    if (time === null || value === null || open === null || close === null) continue;
    result.push({ time, value, direction: close >= open ? "up" : "down" });
  }
  return result;
}

function payloadText(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function payloadBoolean(payload: Record<string, unknown>, key: string): boolean | null {
  const value = payload[key];
  return typeof value === "boolean" ? value : null;
}

export function buildMarketFillMarkers(
  executions: readonly ExecutionResponse[],
  market: Pick<ExecutableMarketResponse, "symbol" | "market_type">,
): MarketFillMarker[] {
  const result: MarketFillMarker[] = [];
  for (const execution of executions) {
    const executionPayload = execution.payload as Record<string, unknown>;
    for (const fill of execution.fills) {
      const fillPayload = fill.payload as Record<string, unknown>;
      const symbol = (payloadText(fillPayload, "symbol") ?? execution.symbol).toUpperCase();
      const marketType = payloadText(fillPayload, "market_type") ?? payloadText(executionPayload, "market_type");
      const action = payloadText(fillPayload, "action") ?? execution.action;
      if (symbol !== market.symbol || marketType !== market.market_type) continue;
      if (action !== "BUY" && action !== "SELL") continue;
      if (epochSeconds(fill.filled_at) === null) continue;
      result.push({
        id: fill.fill_id,
        cycleId: execution.cycle_id,
        executionId: execution.execution_id,
        fillId: fill.fill_id,
        action,
        symbol,
        marketType: market.market_type,
        filledAt: fill.filled_at,
        quantity: payloadText(fillPayload, "quantity"),
        price: payloadText(fillPayload, "price"),
        fee: payloadText(fillPayload, "fee"),
        reduceOnly: payloadBoolean(fillPayload, "reduce_only"),
      });
    }
  }
  return result.sort((left, right) => Date.parse(left.filledAt) - Date.parse(right.filledAt));
}

export function markerCandleTime(
  marker: Pick<MarketFillMarker, "filledAt">,
  candles: readonly CandleResponse[],
): number | null {
  const filledAt = Date.parse(marker.filledAt);
  if (!Number.isFinite(filledAt)) return null;
  for (const candle of candles) {
    const open = Date.parse(candle.open_time);
    const close = Date.parse(candle.close_time);
    if (!Number.isFinite(open) || !Number.isFinite(close)) continue;
    if (filledAt >= open && filledAt < close) return Math.floor(open / 1000);
  }
  return null;
}
