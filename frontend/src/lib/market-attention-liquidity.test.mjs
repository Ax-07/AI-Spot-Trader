import assert from "node:assert/strict";
import test from "node:test";

import { formatUsdCompact } from "./market-attention.ts";

test("formats compact USD notionals without inventing missing values", () => {
  assert.equal(formatUsdCompact("850"), "850 $");
  assert.equal(formatUsdCompact("12400"), "12.4 k$");
  assert.equal(formatUsdCompact("3800000"), "3.8 M$");
  assert.equal(formatUsdCompact("1200000000"), "1.2 B$");
  assert.equal(formatUsdCompact(null), "—");
  assert.equal(formatUsdCompact("not-a-number"), "—");
});

test("formats signed notional deltas", () => {
  assert.equal(formatUsdCompact("5300000", { signed: true }), "+5.3 M$");
  assert.equal(formatUsdCompact("-69000", { signed: true }), "-69.0 k$");
  assert.equal(formatUsdCompact("0", { signed: true }), "0.00 $");
});
