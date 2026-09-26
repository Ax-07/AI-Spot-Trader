import assert from "node:assert/strict";
import test from "node:test";
import { formatFailure } from "./format.ts";

test("formatFailure distinguishes AI provider failures", () => {
  assert.equal(formatFailure({ stage: "MARKET_SELECTION", error_type: "LLMRateLimitError", timed_out: false }), "MARKET_SELECTION · Limite temporaire du fournisseur IA");
  assert.equal(formatFailure({ stage: "MARKET_SELECTION", error_type: "LLMQuotaError", timed_out: false }), "MARKET_SELECTION · Quota / limite de dépenses du fournisseur IA");
  assert.equal(formatFailure({ stage: "MARKET_SELECTION", error_type: "LLMHTTPError", timed_out: false }), "MARKET_SELECTION · Autre erreur fournisseur IA");
  assert.equal(formatFailure({ stage: "MARKET_SELECTION", error_type: "LLMTimeoutError", timed_out: true }), "MARKET_SELECTION · Timeout du fournisseur IA");
});
