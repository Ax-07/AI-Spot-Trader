import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_MARKET_DISCOVERY_POLICY,
  DEFAULT_OLLAMA_MODEL,
  DEFAULT_OLLAMA_TIMEOUT_SECONDS,
  buildSessionCampaignConfiguration,
  initialSessionLlmValues,
} from "./session-config.ts";

const base = {
  marketType: "SPOT",
  marketSelectionMode: "AUTOMATIC_AI",
  pairs: "BTC/USD",
  capital: "1000",
  llmProvider: "OPENAI",
  model: "gpt-5.6-luna",
  ollamaModel: DEFAULT_OLLAMA_MODEL,
  ollamaTimeout: String(DEFAULT_OLLAMA_TIMEOUT_SECONDS),
  aggressiveness: 5,
  tradingStyle: "SCALP",
  strategicScheduleMode: "CANDLE_CLOSE",
  decisionTimeframe: "5m",
  riskProfile: "balanced",
  cadence: "60",
  maxDecisionsPerCycle: "6",
  feeRate: "0.001",
  spreadBps: "2",
  slippageBps: "2",
  customMaxOrder: "100",
  customLeverage: "1",
  customMaxLeverage: "1",
  customPositionNotional: "250",
  customTotalExposure: "500",
  customLiquidationBuffer: "1.10",
  customAllowedPairs: "",
  marketTimeout: "20",
  agentTimeout: "90",
  brokerTimeout: "5",
  discovery: {
    ...DEFAULT_MARKET_DISCOVERY_POLICY,
    watchlist_refresh_seconds: 300,
  },
};

test("new Session defaults expose an explicit OpenAI provider", () => {
  const values = initialSessionLlmValues(null, false);
  assert.equal(values.llmProvider, "OPENAI");
  assert.equal(values.model, "gpt-5.6-luna");
  assert.equal(values.ollamaModel, "qwen3.5:9b");
  assert.equal(values.ollamaTimeoutSeconds, 60);
});

test("legacy edit keeps provider absent instead of silently choosing OpenAI", () => {
  const values = initialSessionLlmValues({ llm_model: "gpt-5.6-sol" }, true);
  assert.equal(values.llmProvider, null);
  assert.equal(values.model, "gpt-5.6-sol");
});

test("OpenAI Session serializes only the explicit provider and OpenAI model", () => {
  const configuration = buildSessionCampaignConfiguration(base);
  assert.equal(configuration.llm_provider, "OPENAI");
  assert.equal(configuration.llm_model, "gpt-5.6-luna");
  assert.equal("ollama_model" in configuration, false);
  assert.equal("ollama_timeout_seconds" in configuration, false);
});

test("Ollama Session serializes local model and transport timeout", () => {
  const configuration = buildSessionCampaignConfiguration({
    ...base,
    llmProvider: "OLLAMA",
    ollamaModel: " qwen3.5:9b ",
    ollamaTimeout: "55",
  });
  assert.equal(configuration.llm_provider, "OLLAMA");
  assert.equal(configuration.ollama_model, "qwen3.5:9b");
  assert.equal(configuration.ollama_timeout_seconds, 55);
  assert.equal(configuration.llm_model, "gpt-5.6-luna");
});

test("legacy builder input keeps Batch 51.2 fields absent", () => {
  const configuration = buildSessionCampaignConfiguration({
    ...base,
    llmProvider: undefined,
    ollamaModel: undefined,
    ollamaTimeout: undefined,
  });
  assert.equal("llm_provider" in configuration, false);
  assert.equal("ollama_model" in configuration, false);
  assert.equal("ollama_timeout_seconds" in configuration, false);
});

test("Ollama local model cannot be empty", () => {
  assert.throws(
    () => buildSessionCampaignConfiguration({ ...base, llmProvider: "OLLAMA", ollamaModel: "  " }),
    /modèle local Ollama est obligatoire/i,
  );
});

test("Ollama timeout must be strictly positive", () => {
  assert.throws(
    () => buildSessionCampaignConfiguration({ ...base, llmProvider: "OLLAMA", ollamaTimeout: "0" }),
    /timeout transport Ollama.*strictement positif/i,
  );
});

test("Agent timeout must exceed Ollama transport timeout", () => {
  assert.throws(
    () => buildSessionCampaignConfiguration({
      ...base,
      llmProvider: "OLLAMA",
      ollamaTimeout: "60",
      agentTimeout: "60",
    }),
    /timeout Agent doit être strictement supérieur/i,
  );
});

test("persisted custom Ollama values round-trip into edit defaults", () => {
  const configuration = buildSessionCampaignConfiguration({
    ...base,
    llmProvider: "OLLAMA",
    ollamaModel: "custom-local:13b",
    ollamaTimeout: "42",
  });
  const values = initialSessionLlmValues(configuration, true);
  assert.equal(values.llmProvider, "OLLAMA");
  assert.equal(values.ollamaModel, "custom-local:13b");
  assert.equal(values.ollamaTimeoutSeconds, 42);
});
