import assert from "node:assert/strict";
import test from "node:test";

import {
  marketStructure,
  structureEventLabel,
  structureStateLabel,
  structureTimeframe,
  timeframeStructureLabel,
  swingSequenceLabel,
} from "./market-structure.ts";

const structure = {
  observed_at: "2026-10-01T10:00:00Z",
  global_state: "MIXED",
  timeframes: [
    {
      timeframe: "4h",
      state: "TRANSITION",
      event: "CHOCH_DOWN",
      history_count: 100,
      latest_final_close: "2026-10-01T08:00:00Z",
      confirmed_swing_highs: [],
      confirmed_swing_lows: [],
      swings: [],
      sequence: ["HH", "HL", "LH", "LL"],
      error_type: null,
    },
  ],
};

const item = { market_structure: structure };

test("reads the market structure extension without changing Batch 41 snapshots", () => {
  assert.equal(marketStructure(item)?.global_state, "MIXED");
  assert.equal(marketStructure({}), null);
});

test("renders French descriptive structure labels", () => {
  assert.equal(structureStateLabel("BULLISH"), "Haussière");
  assert.equal(structureStateLabel("BEARISH"), "Baissière");
  assert.equal(structureStateLabel("TRANSITION"), "Transition");
  assert.equal(structureStateLabel("MIXED"), "Mixte");
  assert.equal(structureEventLabel("CHOCH_DOWN"), "Rupture de structure haussière");
  assert.equal(timeframeStructureLabel(structure.timeframes[0]), "Transition baissière");
});

test("renders a confirmed swing sequence for one native timeframe", () => {
  const h4 = structureTimeframe(structure, "4h");
  assert.equal(swingSequenceLabel(h4), "HH → HL → LH → LL");
  assert.equal(structureTimeframe(structure, "1h"), null);
});
