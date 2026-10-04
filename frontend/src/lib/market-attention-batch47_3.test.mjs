import assert from "node:assert/strict";
import test from "node:test";

import {
  formatAdaptiveScore,
  formatKrakenRawNumber,
  formatSignedPercent,
  perpetualAnalyticsContext,
  perpetualAnalyticsCoverageMessage,
  perpetualAnalyticsSeriesCoverage,
} from "./market-attention.ts";

const analytics = {
  market: { symbol: "BTC/USD", market_type: "PERPETUAL" },
  status: "AVAILABLE",
  provider: "KRAKEN_FUTURES",
  observed_at: "2026-10-04T12:00:00Z",
  open_interest_status: "AVAILABLE",
  current_open_interest_observed_at: "2026-10-04T10:00:00Z",
  freshness_seconds: "3600",
  current_open_interest: "2137.5492",
  previous_open_interest: "2151.584",
  baseline_open_interest: "2145",
  baseline_open_interest_mad: "8",
  open_interest_change: "-14.0348",
  open_interest_change_ratio: "-0.006522",
  open_interest_anomaly_score: "-0.627",
  open_interest_anomaly_method: "ROBUST_MAD",
  baseline_period_count: 12,
  history_point_count: 24,
  funding: {
    status: "AVAILABLE",
    current_observed_at: "2026-10-04T10:00:00Z",
    freshness_seconds: "3600",
    current_rate: "5.25",
    previous_rate: "4.75",
    current_relative_rate: "0.000081",
    previous_relative_rate: "0.000073",
    baseline_relative_rate: "0.000050",
    baseline_relative_rate_mad: "0.000010",
    relative_rate_change: "0.000008",
    relative_rate_anomaly_score: "2.091",
    relative_rate_anomaly_method: "ROBUST_MAD",
    baseline_period_count: 12,
    history_point_count: 24,
    error_type: null,
  },
  liquidation_volume: {
    status: "AVAILABLE",
    current_observed_at: "2026-10-04T10:00:00Z",
    freshness_seconds: "3600",
    current_volume: "150000",
    previous_volume: "30000",
    baseline_volume: "25000",
    baseline_volume_mad: "5000",
    volume_change: "120000",
    volume_change_ratio: "4",
    volume_anomaly_score: "16.86",
    volume_anomaly_method: "ROBUST_MAD",
    baseline_period_count: 12,
    history_point_count: 24,
    error_type: null,
  },
  characteristics: ["FUNDING_POSITIVE_EXTREME", "LIQUIDATION_VOLUME_SPIKE"],
  error_type: null,
};

test("Batch 47.3 exposes funding and aggregate liquidation history additively", () => {
  const candidate = { perpetual_analytics: analytics };
  const value = perpetualAnalyticsContext(candidate);
  assert.equal(value?.funding?.current_rate, "5.25");
  assert.equal(formatSignedPercent(value?.funding?.current_relative_rate), "+0.01 %");
  assert.equal(formatAdaptiveScore(value?.funding?.relative_rate_anomaly_score), "+2.09 MADσ");
  assert.equal(value?.liquidation_volume?.current_volume, "150000");
  assert.equal(formatKrakenRawNumber(value?.liquidation_volume?.current_volume), "150.000 k");
  assert.equal("long_liquidations" in value.liquidation_volume, false);
  assert.equal("short_liquidations" in value.liquidation_volume, false);
});

test("Batch 47.3 keeps raw funding distinct from relative funding", () => {
  assert.equal(formatKrakenRawNumber(analytics.funding.current_rate), "5,25");
  assert.doesNotMatch(formatKrakenRawNumber(analytics.funding.current_rate), /%/);
  assert.equal(formatSignedPercent(analytics.funding.current_relative_rate), "+0.01 %");
});

test("Batch 47.3 exposes per-series coverage inside the shared Analytics rotation", () => {
  const coverage = {
    eligible_market_count: 20,
    fresh_market_count: 8,
    expired_market_count: 0,
    unseen_market_count: 12,
    scanned_market_count: 10,
    coverage_ratio: 0.4,
    effective_market_limit: 10,
    estimated_refreshes_per_full_rotation: 2,
    estimated_full_rotation_seconds: 600,
    cache_ttl_seconds: 3600,
    oldest_snapshot_age_seconds: 300,
    rotation_within_cache_ttl: true,
    requests_attempted: 30,
    requests_failed: 2,
    status: "ROTATING",
    series_coverage: [
      { series: "OPEN_INTEREST", available_market_count: 8, insufficient_history_market_count: 0, stale_market_count: 0, technical_error_market_count: 0, unavailable_market_count: 12 },
      { series: "FUNDING", available_market_count: 6, insufficient_history_market_count: 2, stale_market_count: 0, technical_error_market_count: 0, unavailable_market_count: 12 },
      { series: "LIQUIDATION_VOLUME", available_market_count: 7, insufficient_history_market_count: 0, stale_market_count: 0, technical_error_market_count: 1, unavailable_market_count: 12 },
    ],
  };
  assert.equal(perpetualAnalyticsSeriesCoverage(coverage, "FUNDING")?.available_market_count, 6);
  assert.equal(perpetualAnalyticsSeriesCoverage(coverage, "LIQUIDATION_VOLUME")?.technical_error_market_count, 1);
  assert.match(perpetualAnalyticsCoverageMessage(coverage), /rotation Analytics Futures en cours/i);
});

test("Batch 47.3 remains backward compatible when the new nested series are absent", () => {
  const legacy47_2 = {
    ...analytics,
    funding: undefined,
    liquidation_volume: undefined,
    open_interest_status: undefined,
    characteristics: ["OPEN_INTEREST_EXPANSION"],
  };
  assert.equal(perpetualAnalyticsContext({ perpetual_analytics: legacy47_2 })?.funding, undefined);
  assert.equal(perpetualAnalyticsSeriesCoverage({ series_coverage: [] }, "FUNDING"), null);
});
