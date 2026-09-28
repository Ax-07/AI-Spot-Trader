import assert from "node:assert/strict";
import test from "node:test";

import {
  attentionHorizon,
  citedPublicSources,
  formatSignedPercent,
  formatVolumeRatio,
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
