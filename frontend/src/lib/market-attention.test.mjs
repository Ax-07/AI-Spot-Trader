import assert from "node:assert/strict";
import test from "node:test";

import {
  attentionHorizon,
  citedPublicSources,
  formatSignedPercent,
  formatVolumeRatio,
  marketAttentionStatusMessage,
} from "./market-attention.ts";

const item = {
  market_activity: {
    market: { symbol: "QNT/USD", market_type: "PERPETUAL" },
    observed_at: "2026-09-28T12:00:00Z",
    status: "AVAILABLE",
    activity_state: "ACCELERATING",
    freshness_seconds: "20",
    horizons: [
      { timeframe: "5m", volume_ratio: "2.8", price_return: "0.01", complete: true },
      { timeframe: "15m", volume_ratio: "2.05", price_return: "0.031", complete: true },
    ],
    error_type: null,
  },
  public_attention: {
    asset: "QNT",
    observed_at: "2026-09-28T12:00:00Z",
    research_status: "AVAILABLE",
    attention_direction: "RISING",
    quantitative_metrics: [],
    qualitative_observations: [],
    possible_catalysts: [],
    confidence_context: "multiple public sources",
    error_type: null,
    sources: [
      { title: "Official", url: "https://example.com/a", source_domain: "example.com", observed_at: "2026-09-28T12:00:00Z", published_at: null },
      { title: "Duplicate", url: "https://example.com/a", source_domain: "example.com", observed_at: "2026-09-28T12:00:00Z", published_at: null },
      { title: "Invalid", url: "javascript:alert(1)", source_domain: "invalid", observed_at: "2026-09-28T12:00:00Z", published_at: null },
    ],
  },
  cross_state: "CONVERGING",
  attention_level: "HIGH",
};

const overview = (status, candidateCount = 0) => ({
  protocol_version: "market-attention-radar-v1",
  observed_at: "2026-09-28T12:00:00Z",
  status,
  informative_only: true,
  catalogue_market_count: 100,
  cached_activity_market_count: 80,
  scanned_market_count: 20,
  candidate_market_count: candidateCount,
  web_search_count: 0,
  activity_status_counts: { AVAILABLE: 80, PARTIAL: 0, STALE: 0, ERROR: 0 },
  activity_state_counts: { UNKNOWN: 10, NORMAL: 70, ELEVATED: 0, ACCELERATING: 0, VERY_HIGH: 0 },
  subthreshold_activity: [
    { market: { symbol: "SOL/USD", market_type: "SPOT" }, peak_volume_ratio: "1.31", peak_timeframe: "15m" },
  ],
  shortlist: [],
  error_type: null,
});

test("reads requested volume horizons without inventing missing ones", () => {
  assert.equal(attentionHorizon(item, "15m")?.volume_ratio, "2.05");
  assert.equal(attentionHorizon(item, "1h"), null);
});

test("keeps only unique clickable public HTTP sources", () => {
  assert.deepEqual(citedPublicSources(item).map((source) => source.url), ["https://example.com/a"]);
});

test("formats descriptive ratios and returns without trading semantics", () => {
  assert.equal(formatVolumeRatio("2.8"), "2.80×");
  assert.equal(formatSignedPercent("0.031"), "+3.10 %");
  assert.equal(formatVolumeRatio(null), "—");
});

test("maps an operational empty shortlist to an explicit healthy message", () => {
  assert.equal(
    marketAttentionStatusMessage(overview("AVAILABLE")),
    "Radar opérationnel — aucun événement inhabituel détecté.",
  );
});

test("keeps a genuinely partial empty shortlist distinguishable", () => {
  assert.match(marketAttentionStatusMessage(overview("PARTIAL")), /partiellement disponible/i);
});

test("preserves diagnostic counters and subthreshold payload mapping", () => {
  const value = overview("AVAILABLE");
  value.activity_status_counts.PARTIAL = 8;
  assert.equal(value.activity_status_counts.PARTIAL, 8);
  assert.equal(value.activity_state_counts.NORMAL, 70);
  assert.equal(value.subthreshold_activity[0].peak_volume_ratio, "1.31");
  assert.equal(value.subthreshold_activity[0].peak_timeframe, "15m");
});
