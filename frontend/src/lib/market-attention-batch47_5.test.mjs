import assert from "node:assert/strict";
import test from "node:test";

import {
  formatAnalyticsRankChange,
  formatAnalyticsRankingScore,
  perpetualAnalyticsRankingComponentLabel,
  perpetualAnalyticsRankingContext,
} from "./market-attention.ts";

const ranking = {
  score: 4,
  max_score: 4,
  components: [
    {
      name: "OPEN_INTEREST",
      contribution: 1,
      evidence: ["OPEN_INTEREST_EXPANSION"],
      series: [{ series: "open-interest", status: "AVAILABLE", used: true }],
    },
    {
      name: "FUNDING",
      contribution: 1,
      evidence: ["FUNDING_NEGATIVE_EXTREME"],
      series: [{ series: "funding", status: "AVAILABLE", used: true }],
    },
    {
      name: "LIQUIDATION_VOLUME",
      contribution: 1,
      evidence: ["LIQUIDATION_VOLUME_SPIKE"],
      series: [{ series: "liquidation-volume", status: "AVAILABLE", used: true }],
    },
    {
      name: "ORDER_FLOW",
      contribution: 1,
      evidence: ["CVD_NEGATIVE_IMPULSE", "AGGRESSOR_SELL_DOMINANCE"],
      series: [
        { series: "cvd", status: "AVAILABLE", used: true },
        { series: "aggressor-differential", status: "AVAILABLE", used: true },
      ],
    },
  ],
  order_flow_deduplicated: true,
  order_flow_conflict: false,
  applied_to_ranking: true,
  rank_before_analytics: 7,
  rank_after_analytics: 4,
  rank_change: 3,
  ranking_policy: "INTEREST_STRUCTURE_ANALYTICS_V1",
};

test("Batch 47.5 exposes the bounded Analytics ranking diagnostics", () => {
  const item = { analytics_ranking: ranking };
  assert.equal(perpetualAnalyticsRankingContext(item), ranking);
  assert.equal(formatAnalyticsRankingScore(ranking), "4 / 4");
  assert.equal(formatAnalyticsRankChange(ranking), "+3");
  assert.equal(ranking.rank_before_analytics, 7);
  assert.equal(ranking.rank_after_analytics, 4);
  assert.equal(ranking.components.length, 4);
  assert.equal(ranking.components.at(-1).contribution, 1);
  assert.equal(ranking.components.at(-1).evidence.length, 2);
  assert.equal(ranking.order_flow_deduplicated, true);
});

test("Batch 47.5 stays compatible with payloads that predate analytics_ranking", () => {
  assert.equal(perpetualAnalyticsRankingContext({}), null);
  assert.equal(formatAnalyticsRankingScore(null), "—");
  assert.equal(formatAnalyticsRankChange(null), "—");
});

test("Batch 47.5 component labels remain explicit and economic-unit agnostic", () => {
  assert.equal(perpetualAnalyticsRankingComponentLabel("OPEN_INTEREST"), "Open Interest");
  assert.equal(perpetualAnalyticsRankingComponentLabel("FUNDING"), "Funding");
  assert.equal(perpetualAnalyticsRankingComponentLabel("LIQUIDATION_VOLUME"), "Liquidations");
  assert.equal(perpetualAnalyticsRankingComponentLabel("ORDER_FLOW"), "Order flow");
});

test("unavailable or stale series can be represented neutrally without negative contribution", () => {
  const neutral = {
    ...ranking,
    score: 0,
    components: ranking.components.map((component) => ({
      ...component,
      contribution: 0,
      evidence: [],
      series: component.series.map((series) => ({ ...series, status: "STALE", used: false })),
    })),
    order_flow_deduplicated: false,
  };
  assert.equal(formatAnalyticsRankingScore(neutral), "0 / 4");
  assert.equal(neutral.components.every((component) => component.contribution === 0), true);
  assert.equal(neutral.components.every((component) => component.series.every((series) => !series.used)), true);
});
