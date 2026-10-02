import assert from "node:assert/strict";
import test from "node:test";

import {
  activeMarketAttentionFilters,
  activityErrorEntries,
  attentionHorizon,
  formatBps,
  formatImbalance,
  formatSignedPercent,
  formatUsdCompact,
  formatVolumeRatio,
  marketAttentionStatusMessage,
  marketCapCategoryLabel,
  setMarketAttentionFilters,
  setMarketAttentionScope,
  slippageEstimate,
  trendDirectionLabel,
} from "./market-attention.ts";

const item = {
  market_activity: {
    market: { symbol: "QNT/USD", market_type: "SPOT" },
    observed_at: "2026-10-01T10:00:00Z",
    status: "AVAILABLE",
    activity_state: "ACCELERATING",
    trend_direction: "UP",
    liquidity_regime: "MEDIUM",
    liquidity_reference_usd: "500000",
    freshness_seconds: "20",
    characteristics: ["TRENDING", "VOLUME_ANOMALY"],
    interest_level: "HIGH",
    interest_reasons: ["Volume inhabituel"],
    horizons: [
      { timeframe: "5m", trend_direction: "UP", volume_ratio: "2.8", price_return: "0.01", complete: true },
      { timeframe: "15m", trend_direction: "UP", volume_ratio: "2.05", price_return: "0.031", complete: true },
    ],
    data_quality: "COMPLETE",
    error_type: null,
  },
  microstructure: {
    slippage: [
      { side: "BUY", notional_quote: "1000", slippage_bps: "4.2", insufficient_depth: false },
      { side: "SELL", notional_quote: "1000", slippage_bps: "5.1", insufficient_depth: false },
    ],
  },
  combined_characteristics: ["TRENDING", "TIGHT_SPREAD"],
  interest_level: "HIGH",
  interest_reasons: ["Volume inhabituel"],
  volume_24h_usd: "12500000",
  market_cap_usd: "8500000000",
  market_cap_category: "MID",
};

const emptyActivityErrors = () => ({
  KrakenConnectionError: 0,
  KrakenNetworkError: 0,
  KrakenTimeoutError: 0,
  KrakenHTTPError: 0,
  KrakenServerError: 0,
  KrakenRateLimitError: 0,
  KrakenAPIError: 0,
  KrakenPayloadError: 0,
  UnknownKrakenSymbolError: 0,
  CandleValidationError: 0,
  Other: 0,
});

const overview = (status, candidateCount = 0) => ({
  protocol_version: "market-attention-radar-v4",
  observed_at: "2026-10-01T10:00:00Z",
  status,
  informative_only: true,
  market_scope: "ALL",
  catalogue_market_count: 100,
  cached_activity_market_count: 80,
  scanned_market_count: 20,
  scanned_market_type_counts: { SPOT: 12, PERPETUAL: 8 },
  fresh_market_type_counts: { SPOT: 42, PERPETUAL: 38 },
  candidate_market_count: candidateCount,
  activity_status_counts: { AVAILABLE: 80, PARTIAL: 0, STALE: 0, ERROR: 0 },
  activity_state_counts: { UNKNOWN: 10, NORMAL: 70, ELEVATED: 0, ACCELERATING: 0, VERY_HIGH: 0 },
  activity_data_quality_counts: { COMPLETE: 70, NO_TRADE_GAPS: 10, INSUFFICIENT_HISTORY: 0, DISCONTINUOUS_HISTORY: 0, TECHNICAL_ERROR: 0 },
  activity_error_counts: emptyActivityErrors(),
  activity_payload_stage_counts: { ASSET_PAIRS_PAYLOAD: 0, ASSET_PAIRS_ENTRY: 0, ASSET_PAIRS_SYMBOL: 0, OHLC_RESULT: 0, OHLC_SERIES: 0, OHLC_PAIR_KEY: 0, OHLC_ROW: 0, OHLC_TIMESTAMP: 0, OHLC_NUMERIC: 0 },
  activity_market_type_status_counts: {
    SPOT: { AVAILABLE: 50, PARTIAL: 0, STALE: 0, ERROR: 0 },
    PERPETUAL: { AVAILABLE: 30, PARTIAL: 0, STALE: 0, ERROR: 0 },
  },
  liquidity_regime_counts: { UNKNOWN: 80, MICRO: 0, LOW: 0, MEDIUM: 0, HIGH: 0, VERY_HIGH: 0 },
  microstructure_scanned_market_count: 12,
  microstructure_cached_market_count: 30,
  microstructure_status_counts: { AVAILABLE: 25, PARTIAL: 5, STALE: 0, ERROR: 0, NOT_APPLICABLE: 38 },
  microstructure_quality_counts: { COMPLETE: 25, PARTIAL: 5, STALE: 0, TECHNICAL_ERROR: 0, NOT_APPLICABLE: 38 },
  microstructure_error_counts: {},
  subthreshold_activity: [],
  shortlist: [],
  error_type: null,
});

test("reads requested deterministic horizons without inventing missing ones", () => {
  assert.equal(attentionHorizon(item, "15m")?.volume_ratio, "2.05");
  assert.equal(attentionHorizon(item, "1h"), null);
});

test("formats descriptive ratios and microstructure metrics", () => {
  assert.equal(formatVolumeRatio("2.8"), "2.80×");
  assert.equal(formatSignedPercent("0.031"), "+3.10 %");
  assert.equal(formatBps("4.2"), "4.20 bps");
  assert.equal(formatImbalance("0.25"), "+25.0 %");
  assert.equal(formatVolumeRatio(null), "—");
});

test("formats Batch 43 volume and market-cap metadata", () => {
  assert.equal(formatUsdCompact(item.volume_24h_usd), "12.5 M$");
  assert.equal(formatUsdCompact(item.market_cap_usd), "8.5 B$");
  assert.equal(marketCapCategoryLabel(item.market_cap_category), "Mid (1 – 10 Md$)");
  assert.equal(marketCapCategoryLabel("UNKNOWN"), "Indéterminée");
});

test("renders deterministic trend directions as descriptive French labels", () => {
  assert.equal(trendDirectionLabel("UP"), "Haussière ↑");
  assert.equal(trendDirectionLabel("DOWN"), "Baissière ↓");
  assert.equal(trendDirectionLabel("NEUTRAL"), "Neutre →");
  assert.equal(trendDirectionLabel("MIXED"), "Mixte ↕");
  assert.equal(trendDirectionLabel("UNKNOWN"), "Indéterminée");
});

test("selects a theoretical slippage scenario without turning it into an order", () => {
  assert.equal(slippageEstimate(item, "BUY", 1000)?.slippage_bps, "4.2");
  assert.equal(slippageEstimate(item, "BUY", 500), null);
});

test("maps an operational empty shortlist to an explicit healthy message", () => {
  assert.equal(marketAttentionStatusMessage(overview("AVAILABLE")), "Radar opérationnel — aucun événement inhabituel détecté.");
});

test("keeps partial and stale Kraken states distinguishable", () => {
  assert.match(marketAttentionStatusMessage(overview("PARTIAL")), /partiellement disponible/i);
  assert.match(marketAttentionStatusMessage(overview("STALE")), /Kraken périmées/i);
});

test("returns only non-zero bounded Kraken error categories in deterministic order", () => {
  const counts = { ...emptyActivityErrors(), KrakenNetworkError: 8, KrakenRateLimitError: 3, Other: 1 };
  assert.deepEqual(activityErrorEntries(counts), [["KrakenNetworkError", 8], ["KrakenRateLimitError", 3], ["Other", 1]]);
});

test("falls back to the legacy scope when a pre-v6 snapshot has no filter object", () => {
  assert.deepEqual(activeMarketAttentionFilters({ ...overview("AVAILABLE"), market_scope: "SPOT" }), {
    market_scope: "SPOT",
    min_volume_24h_usd: null,
    market_cap_categories: [],
    min_market_cap_usd: null,
    max_market_cap_usd: null,
  });
});

test("sends a backend scope change before replacing the radar snapshot", async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "/backend/api/v1/market-attention/scope");
    assert.equal(init?.method, "PUT");
    assert.equal(init?.body, JSON.stringify({ market_scope: "SPOT" }));
    return {
      ok: true,
      status: 200,
      json: async () => ({ ...overview("AVAILABLE"), market_scope: "SPOT" }),
    };
  };
  try {
    const result = await setMarketAttentionScope("SPOT");
    assert.equal(result.market_scope, "SPOT");
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("sends volume and market-cap filters as backend runtime state", async () => {
  const previousFetch = globalThis.fetch;
  const filters = {
    market_scope: "SPOT",
    min_volume_24h_usd: "1000000",
    market_cap_categories: ["MID", "LARGE"],
    min_market_cap_usd: null,
    max_market_cap_usd: null,
  };
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "/backend/api/v1/market-attention/filters");
    assert.equal(init?.method, "PUT");
    assert.equal(init?.body, JSON.stringify(filters));
    return {
      ok: true,
      status: 200,
      json: async () => ({
        ...overview("AVAILABLE"),
        protocol_version: "market-attention-radar-v6",
        market_scope: "SPOT",
        filters,
      }),
    };
  };
  try {
    const result = await setMarketAttentionFilters(filters);
    assert.deepEqual(result.filters, filters);
  } finally {
    globalThis.fetch = previousFetch;
  }
});
