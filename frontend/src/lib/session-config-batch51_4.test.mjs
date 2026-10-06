import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_AGENT_TIMEOUT_SECONDS,
  DEFAULT_OLLAMA_TIMEOUT_SECONDS,
  compatibleOllamaAgentTimeoutSeconds,
  OLLAMA_AGENT_TIMEOUT_MULTIPLIER,
  recommendedOllamaAgentTimeoutSeconds,
} from "./session-config.ts";

test("Ollama Agent timeout recommendation is derived from the transport budget", () => {
  assert.equal(DEFAULT_OLLAMA_TIMEOUT_SECONDS, 60);
  assert.equal(DEFAULT_AGENT_TIMEOUT_SECONDS, 35);
  assert.equal(OLLAMA_AGENT_TIMEOUT_MULTIPLIER, 2);
  assert.equal(recommendedOllamaAgentTimeoutSeconds(DEFAULT_OLLAMA_TIMEOUT_SECONDS), 120);
  assert.equal(recommendedOllamaAgentTimeoutSeconds(120), 240);
  assert.equal(compatibleOllamaAgentTimeoutSeconds(35, 60), 120);
  assert.equal(compatibleOllamaAgentTimeoutSeconds(60, 60), 120);
  assert.equal(compatibleOllamaAgentTimeoutSeconds(300, 120), 300);
});

test("Ollama Agent timeout recommendation rejects invalid transport budgets", () => {
  assert.throws(() => recommendedOllamaAgentTimeoutSeconds(0), /strictement positif/i);
  assert.throws(() => recommendedOllamaAgentTimeoutSeconds(Number.NaN), /strictement positif/i);
});
