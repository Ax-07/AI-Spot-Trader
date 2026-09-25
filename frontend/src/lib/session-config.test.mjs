import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_MARKET_DISCOVERY_POLICY,
  buildSessionCampaignConfiguration,
  parseSessionMarkets,
  sessionStatusLabel,
} from "./session-config.ts";

const base = {
  marketType: "SPOT",
  marketSelectionMode: "AUTOMATIC_AI",
  pairs: "btc/usd",
  capital: "1000",
  model: "gpt-5.6-luna",
  aggressiveness: 5,
  riskProfile: "balanced",
  cadence: "30",
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
  agentTimeout: "35",
  brokerTimeout: "5",
  discovery: { ...DEFAULT_MARKET_DISCOVERY_POLICY },
};

test("automatic mode keeps dynamic discovery and no forced Risk whitelist", () => {
  const configuration = buildSessionCampaignConfiguration(base);
  assert.equal(configuration.market_discovery?.protocol_version, "market-discovery-v1");
  assert.deepEqual(configuration.market_discovery?.market_types, ["SPOT"]);
  assert.equal(configuration.risk_allowed_pairs, null);
  assert.deepEqual(configuration.paper_executable_markets, [{ symbol: "BTC/USD", market_type: "SPOT" }]);
});

test("manual mode disables discovery and constrains Risk to the explicit universe", () => {
  const configuration = buildSessionCampaignConfiguration({
    ...base,
    marketSelectionMode: "MANUAL",
    pairs: "btc/usd, eth/usd, BTC/USD",
  });
  assert.equal(configuration.market_discovery, null);
  assert.deepEqual(configuration.risk_allowed_pairs, ["BTC/USD", "ETH/USD"]);
  assert.equal(configuration.paper_executable_markets.length, 2);
});

test("market parser rejects mixed settlement assets", () => {
  assert.throws(() => parseSessionMarkets("BTC/USD, ETH/EUR", "SPOT"), /même actif de règlement/);
});

test("Session status vocabulary is user-facing", () => {
  assert.equal(sessionStatusLabel("DRAFT"), "Brouillon");
  assert.equal(sessionStatusLabel("RESUMABLE"), "À reprendre");
});
