import assert from "node:assert/strict";
import test from "node:test";

import {
  paperObservabilityBreakdown,
  paperObservabilityMarketKey,
} from "./economic-history.ts";

const baseReport = {
  paper_run_id: "00000000-0000-0000-0000-000000000001",
  lineage_paper_run_ids: ["00000000-0000-0000-0000-000000000001"],
  calculation_version: "paper-analytics-v3+economic-history-v1",
  timezone: "UTC",
  source_digest: "a".repeat(64),
  summary: {},
  operations: [],
  cycles: [],
  observability: {
    calculation_version: "paper-analytics-v3+economic-history-v1+paper-observability-v1",
    timezone: "UTC",
    source_digest: "a".repeat(64),
    breakdowns: [
      { scope: "TOTAL", net_pnl: "5" },
      { scope: "SPOT", net_pnl: null },
      { scope: "PERPETUAL", net_pnl: null },
    ],
    funnel: {},
    markets: [],
    unavailable_metrics: [],
  },
};

test("Batch 49.4 keeps unavailable SPOT/PERP P&L explicit instead of fabricating attribution", () => {
  assert.equal(paperObservabilityBreakdown(baseReport, "TOTAL")?.net_pnl, "5");
  assert.equal(paperObservabilityBreakdown(baseReport, "SPOT")?.net_pnl, null);
  assert.equal(paperObservabilityBreakdown(baseReport, "PERPETUAL")?.net_pnl, null);
});

test("Batch 49.4 keeps identical symbols distinct by market type", () => {
  assert.notEqual(
    paperObservabilityMarketKey({ symbol: "BTC/USD", market_type: "SPOT" }),
    paperObservabilityMarketKey({ symbol: "BTC/USD", market_type: "PERPETUAL" }),
  );
  assert.equal(
    paperObservabilityMarketKey({ symbol: "BTC/USD", market_type: "SPOT" }),
    "BTC/USD::SPOT",
  );
});

test("Batch 49.4 remains compatible with economic-history payloads without observability", () => {
  assert.equal(paperObservabilityBreakdown({ ...baseReport, observability: null }, "TOTAL"), null);
});
