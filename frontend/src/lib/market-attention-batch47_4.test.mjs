import assert from "node:assert/strict";
import test from "node:test";

import {
  formatAdaptiveScore,
  formatKrakenRawNumber,
  formatKrakenSignedRawNumber,
  perpetualAnalyticsContext,
  perpetualAnalyticsSeriesCoverage,
  perpetualAnalyticsStatusLabel,
} from "./market-attention.ts";

const analytics47_4 = {
  market: { symbol: "BTC/USD", market_type: "PERPETUAL" },
  status: "AVAILABLE",
  provider: "KRAKEN_FUTURES",
  observed_at: "2026-10-05T00:00:00Z",
  open_interest_status: "AVAILABLE",
  current_open_interest_observed_at: "2026-10-04T22:00:00Z",
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
  funding: null,
  liquidation_volume: null,
  cvd: {
    status: "AVAILABLE",
    observed_at: "2026-10-05T00:00:00Z",
    current_observed_at: "2026-10-04T22:00:00Z",
    freshness_seconds: "3600",
    current_cvd: "1250.5",
    previous_cvd: "1100.25",
    current_cvd_change: "150.25",
    previous_cvd_change: "12.5",
    baseline_cvd_change: "5.5",
    baseline_cvd_change_mad: "8",
    cvd_change_anomaly_score: "12.20",
    cvd_change_anomaly_method: "ROBUST_MAD",
    buy_volume: "250.5",
    sell_volume: "100.25",
    baseline_period_count: 12,
    history_point_count: 24,
    error_type: null,
  },
  aggressor_differential: {
    status: "AVAILABLE",
    observed_at: "2026-10-05T00:00:00Z",
    current_observed_at: "2026-10-04T22:00:00Z",
    freshness_seconds: "3600",
    current_value: "85.5",
    previous_value: "-4.5",
    baseline_value: "1",
    baseline_value_mad: "5",
    value_change: "90",
    anomaly_score: "11.40",
    anomaly_method: "ROBUST_MAD",
    baseline_period_count: 12,
    history_point_count: 24,
    error_type: null,
  },
  characteristics: ["CVD_POSITIVE_IMPULSE", "AGGRESSOR_BUY_DOMINANCE"],
  error_type: null,
};

test("Batch 47.4 exposes CVD change without inventing economic units", () => {
  const value = perpetualAnalyticsContext({ perpetual_analytics: analytics47_4 });
  assert.equal(value?.cvd?.current_cvd, "1250.5");
  assert.equal(formatKrakenSignedRawNumber(value?.cvd?.current_cvd_change), "+150,25");
  assert.equal(formatAdaptiveScore(value?.cvd?.cvd_change_anomaly_score), "+12.20 MADσ");
  assert.equal(formatKrakenRawNumber(value?.cvd?.buy_volume), "250,5");
  assert.doesNotMatch(formatKrakenRawNumber(value?.cvd?.buy_volume), /\$|USD|%|contracts/i);
});

test("Batch 47.4 exposes signed Aggressor Differential descriptively", () => {
  const value = perpetualAnalyticsContext({ perpetual_analytics: analytics47_4 });
  assert.equal(formatKrakenSignedRawNumber(value?.aggressor_differential?.current_value), "+85,5");
  assert.equal(formatAdaptiveScore(value?.aggressor_differential?.anomaly_score), "+11.40 MADσ");
  assert.equal(value?.characteristics.includes("AGGRESSOR_BUY_DOMINANCE"), true);
});

test("Batch 47.4 coverage contains five shared Analytics series", () => {
  const coverage = {
    series_coverage: [
      { series: "open-interest", available_market_count: 2 },
      { series: "funding", available_market_count: 2 },
      { series: "liquidation-volume", available_market_count: 2 },
      { series: "cvd", available_market_count: 1, technical_error_market_count: 1 },
      { series: "aggressor-differential", available_market_count: 2 },
    ],
  };
  assert.equal(perpetualAnalyticsSeriesCoverage(coverage, "cvd")?.technical_error_market_count, 1);
  assert.equal(perpetualAnalyticsSeriesCoverage(coverage, "aggressor-differential")?.available_market_count, 2);
});

test("Batch 47.4 remains compatible with a Batch 47.3 payload", () => {
  const legacy47_3 = { ...analytics47_4 };
  delete legacy47_3.cvd;
  delete legacy47_3.aggressor_differential;
  const value = perpetualAnalyticsContext({ perpetual_analytics: legacy47_3 });
  assert.equal(value?.cvd, undefined);
  assert.equal(value?.aggressor_differential, undefined);
});


test("Batch 47.4 keeps negative scores symmetric and descriptive", () => {
  assert.equal(formatKrakenSignedRawNumber("-85.5"), "-85,5");
  assert.equal(formatAdaptiveScore("-11.40"), "-11.40 MADσ");
});

test("Batch 47.4 preserves unavailable and error-oriented status semantics", () => {
  assert.equal(perpetualAnalyticsStatusLabel("INSUFFICIENT_HISTORY"), "Historique insuffisant");
  assert.equal(perpetualAnalyticsStatusLabel("TECHNICAL_ERROR"), "Erreur technique");
  assert.equal(perpetualAnalyticsStatusLabel(undefined), "Indisponible");
});
