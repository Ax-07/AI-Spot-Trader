import assert from "node:assert/strict";
import test from "node:test";
import { formatFailure, resolveCockpitFailurePresentation } from "./format.ts";

const historicalFailure = {
  cycle_id: "cycle-failed",
  paper_run_id: "run-1",
  recorded_at: "2026-09-28T12:16:02.248841Z",
  failure: { stage: "AGENT", error_type: "TimeoutError", timed_out: true },
};

const completedCycle = {
  cycle_id: "cycle-completed",
  status: "COMPLETED",
  recorded_at: "2026-09-28T14:22:57.386534Z",
  failure: null,
};

test("formatFailure distinguishes provider timeout from stage timeout", () => {
  assert.equal(formatFailure({ stage: "MARKET_SELECTION", error_type: "LLMRateLimitError", timed_out: false }), "MARKET_SELECTION · Limite temporaire du fournisseur IA");
  assert.equal(formatFailure({ stage: "MARKET_SELECTION", error_type: "LLMQuotaError", timed_out: false }), "MARKET_SELECTION · Quota / limite de dépenses du fournisseur IA");
  assert.equal(formatFailure({ stage: "MARKET_SELECTION", error_type: "LLMHTTPError", timed_out: false }), "MARKET_SELECTION · Autre erreur fournisseur IA");
  assert.equal(formatFailure({ stage: "MARKET_SELECTION", error_type: "LLMTimeoutError", timed_out: true }), "MARKET_SELECTION · Timeout du fournisseur IA");
  assert.equal(formatFailure({ stage: "AGENT", error_type: "TimeoutError", timed_out: true }), "AGENT · Délai maximal du stage dépassé");
});

test("completed cycle newer than latest error exposes history without an active alert", () => {
  assert.deepEqual(resolveCockpitFailurePresentation(completedCycle, historicalFailure), {
    activeCycleFailure: null,
    historicalError: historicalFailure,
  });
});

test("failed latest cycle keeps one active alert and does not duplicate latestError", () => {
  const failedCycle = {
    cycle_id: historicalFailure.cycle_id,
    status: "FAILED",
    recorded_at: historicalFailure.recorded_at,
    failure: historicalFailure.failure,
  };

  assert.deepEqual(resolveCockpitFailurePresentation(failedCycle, historicalFailure), {
    activeCycleFailure: historicalFailure.failure,
    historicalError: null,
  });
});

test("absence of persisted error produces no error presentation", () => {
  assert.deepEqual(resolveCockpitFailurePresentation(completedCycle, null), {
    activeCycleFailure: null,
    historicalError: null,
  });
});

test("an older error remains historical after later successful cycles", () => {
  const muchLaterCompletedCycle = {
    ...completedCycle,
    cycle_id: "cycle-completed-later",
    recorded_at: "2026-09-29T10:00:00Z",
  };

  assert.deepEqual(resolveCockpitFailurePresentation(muchLaterCompletedCycle, historicalFailure), {
    activeCycleFailure: null,
    historicalError: historicalFailure,
  });
});

test("an error newer than the loaded cycle is not misclassified as historical", () => {
  const olderCompletedCycle = {
    ...completedCycle,
    recorded_at: "2026-09-28T10:00:00Z",
  };

  assert.deepEqual(resolveCockpitFailurePresentation(olderCompletedCycle, historicalFailure), {
    activeCycleFailure: null,
    historicalError: null,
  });
});
