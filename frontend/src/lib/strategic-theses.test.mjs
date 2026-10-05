import assert from "node:assert/strict";
import test from "node:test";

import {
  revisionsForStrategicPosition,
  strategicThesisPositionKey,
} from "./strategic-theses.ts";

const base = {
  paper_run_id: "00000000-0000-0000-0000-000000000001",
  lineage_paper_run_ids: ["00000000-0000-0000-0000-000000000001"],
  calculation_version: "strategic-thesis-observability-v1",
  timezone: "UTC",
  as_of: "2026-10-05T20:00:00Z",
  positions: [],
  revisions: [],
  total_revision_count: 0,
  history_limit: 100,
};

test("Batch 50.2 keeps SPOT/PERP and LONG/SHORT identities distinct", () => {
  assert.notEqual(
    strategicThesisPositionKey({ symbol: "BTC/USD", market_type: "SPOT", side: "LONG" }),
    strategicThesisPositionKey({ symbol: "BTC/USD", market_type: "PERPETUAL", side: "LONG" }),
  );
  assert.notEqual(
    strategicThesisPositionKey({ symbol: "BTC/USD", market_type: "PERPETUAL", side: "LONG" }),
    strategicThesisPositionKey({ symbol: "BTC/USD", market_type: "PERPETUAL", side: "SHORT" }),
  );
});

test("Batch 50.2 binds displayed revisions to the durable thesis id only", () => {
  const report = {
    ...base,
    revisions: [
      { thesis_id: "thesis-a", status: "NEW" },
      { thesis_id: "thesis-b", status: "INVALIDATED" },
      { thesis_id: "thesis-a", status: "CONFIRMED" },
    ],
  };
  assert.deepEqual(
    revisionsForStrategicPosition(report, { thesis_id: "thesis-a" }).map((item) => item.status),
    ["NEW", "CONFIRMED"],
  );
});

test("Batch 50.2 never fabricates history for UNAVAILABLE_LEGACY", () => {
  const report = {
    ...base,
    revisions: [{ thesis_id: null, status: "WEAKENING" }],
  };
  assert.deepEqual(revisionsForStrategicPosition(report, { thesis_id: null }), []);
});
