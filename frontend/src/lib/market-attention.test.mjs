import assert from "node:assert/strict";
import test from "node:test";

import {
  activityErrorEntries,
  attentionHorizon,
  formatSignedPercent,
  formatVolumeRatio,
  marketAttentionStatusMessage,
} from "./market-attention.ts";

const item = {
  market_activity: {
    market: { symbol: "QNT/USD", market_type: "SPOT" },
    observed_at: "2026-10-01T10:00:00Z",
    status: "AVAILABLE",
    activity_state: "ACCELERATING",
    liquidity_regime: "MEDIUM",
    liquidity_reference_usd: "500000",
    freshness_seconds: "20",
    characteristics: ["TRENDING", "VOLUME_ANOMALY"],
    interest_level: "HIGH",
    interest_reasons: ["Volume inhabituel"],
    horizons: [
      { timeframe: "5m", volume_ratio: "2.8", price_return: "0.01", complete: true },
      { timeframe: "15m", volume_ratio: "2.05", price_return: "0.031", complete: true },
    ],
    data_quality: "COMPLETE",
    error_type: null,
  },
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
  protocol_version: "market-attention-radar-v2",
  observed_at: "2026-10-01T10:00:00Z",
  status,
  informative_only: true,
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
  subthreshold_activity: [],
  shortlist: [],
  error_type: null,
});

test("reads requested deterministic horizons without inventing missing ones", () => {
  assert.equal(attentionHorizon(item, "15m")?.volume_ratio, "2.05");
  assert.equal(attentionHorizon(item, "1h"), null);
});

test("formats descriptive ratios without trading semantics", () => {
  assert.equal(formatVolumeRatio("2.8"), "2.80×");
  assert.equal(formatSignedPercent("0.031"), "+3.10 %");
  assert.equal(formatVolumeRatio(null), "—");
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
