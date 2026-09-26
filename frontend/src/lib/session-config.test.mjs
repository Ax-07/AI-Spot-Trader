import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_MARKET_DISCOVERY_POLICY,
  TRADING_STYLE_MAPPING_VERSION,
  TRADING_STYLE_UI_METADATA,
  buildSessionCampaignConfiguration,
  inferSessionRiskProfile,
  initialSessionStyleValues,
  parseSessionMarkets,
  sessionStatusLabel,
  tradingStyleRecommendations,
} from "./session-config.ts";

const base = {
  marketType: "SPOT",
  marketSelectionMode: "AUTOMATIC_AI",
  pairs: "btc/usd",
  capital: "1000",
  model: "gpt-5.6-luna",
  aggressiveness: 5,
  tradingStyle: "SCALP",
  riskProfile: "balanced",
  cadence: "60",
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
  discovery: {
    ...DEFAULT_MARKET_DISCOVERY_POLICY,
    watchlist_refresh_seconds: 300,
  },
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

test("SCALP is persisted with the canonical mapping version", () => {
  const configuration = buildSessionCampaignConfiguration(base);
  assert.equal(configuration.trading_style, "SCALP");
  assert.equal(configuration.trading_style_mapping_version, TRADING_STYLE_MAPPING_VERSION);
  assert.equal(configuration.aggressiveness, 5);
  assert.equal(configuration.risk_max_order_notional, "100");
  assert.equal(configuration.market_discovery?.watchlist_refresh_seconds, 300);
});

test("SWING is persisted without changing aggressiveness, market mode or Risk", () => {
  const configuration = buildSessionCampaignConfiguration({
    ...base,
    tradingStyle: "SWING",
    aggressiveness: 9,
    riskProfile: "prudent",
    cadence: "900",
    discovery: {
      ...base.discovery,
      watchlist_refresh_seconds: 1800,
    },
  });
  assert.equal(configuration.trading_style, "SWING");
  assert.equal(configuration.trading_style_mapping_version, TRADING_STYLE_MAPPING_VERSION);
  assert.equal(configuration.aggressiveness, 9);
  assert.equal(configuration.risk_max_order_notional, "50");
  assert.equal(configuration.market_discovery?.protocol_version, "market-discovery-v1");
});

test("legacy Session keeps trading style absent when the user did not choose one", () => {
  const configuration = buildSessionCampaignConfiguration({
    ...base,
    tradingStyle: null,
    cadence: "120",
  });
  assert.equal("trading_style" in configuration, false);
  assert.equal("trading_style_mapping_version" in configuration, false);
  assert.equal(configuration.trading_cadence_seconds, 120);
});

test("changing style does not rewrite an explicitly customized cadence or watchlist refresh", () => {
  const scalp = buildSessionCampaignConfiguration({
    ...base,
    tradingStyle: "SCALP",
    cadence: "120",
    discovery: {
      ...base.discovery,
      watchlist_refresh_seconds: 720,
    },
  });
  const swing = buildSessionCampaignConfiguration({
    ...base,
    tradingStyle: "SWING",
    cadence: "120",
    discovery: {
      ...base.discovery,
      watchlist_refresh_seconds: 720,
    },
  });
  assert.equal(scalp.trading_cadence_seconds, 120);
  assert.equal(swing.trading_cadence_seconds, 120);
  assert.equal(scalp.market_discovery?.watchlist_refresh_seconds, 720);
  assert.equal(swing.market_discovery?.watchlist_refresh_seconds, 720);
  assert.equal(scalp.aggressiveness, swing.aggressiveness);
  assert.equal(scalp.risk_max_order_notional, swing.risk_max_order_notional);
});

test("style recommendations are explicit UX defaults only", () => {
  assert.deepEqual(tradingStyleRecommendations("SCALP"), {
    tradingCadenceSeconds: 60,
    watchlistRefreshSeconds: 300,
  });
  assert.deepEqual(tradingStyleRecommendations("SWING"), {
    tradingCadenceSeconds: 900,
    watchlistRefreshSeconds: 1800,
  });
  assert.deepEqual(TRADING_STYLE_UI_METADATA.SCALP.timeframes, ["1m", "5m", "15m", "30m"]);
  assert.deepEqual(TRADING_STYLE_UI_METADATA.SWING.timeframes, ["1h", "4h", "1d"]);
});

test("new Session starts with SCALP UX defaults", () => {
  assert.deepEqual(initialSessionStyleValues(null, false), {
    tradingStyle: "SCALP",
    tradingCadenceSeconds: 60,
    watchlistRefreshSeconds: 300,
  });
});

test("editing reconstructs persisted SCALP values instead of reapplying defaults", () => {
  const configuration = buildSessionCampaignConfiguration({
    ...base,
    cadence: "120",
    discovery: {
      ...base.discovery,
      watchlist_refresh_seconds: 720,
    },
  });
  assert.deepEqual(initialSessionStyleValues(configuration, true), {
    tradingStyle: "SCALP",
    tradingCadenceSeconds: 120,
    watchlistRefreshSeconds: 720,
  });
});

test("editing a legacy Session does not infer a style", () => {
  const configuration = buildSessionCampaignConfiguration({
    ...base,
    tradingStyle: null,
    cadence: "120",
    discovery: {
      ...base.discovery,
      watchlist_refresh_seconds: 720,
    },
  });
  assert.deepEqual(initialSessionStyleValues(configuration, true), {
    tradingStyle: null,
    tradingCadenceSeconds: 120,
    watchlistRefreshSeconds: 720,
  });
});

test("Risk profile inference recognizes prudent SPOT configuration", () => {
  const configuration = buildSessionCampaignConfiguration({ ...base, riskProfile: "prudent" });
  assert.equal(inferSessionRiskProfile(configuration), "prudent");
});

test("Risk profile inference recognizes balanced SPOT configuration", () => {
  const configuration = buildSessionCampaignConfiguration({ ...base, riskProfile: "balanced" });
  assert.equal(inferSessionRiskProfile(configuration), "balanced");
});

test("Risk profile inference recognizes aggressive SPOT configuration", () => {
  const configuration = buildSessionCampaignConfiguration({ ...base, riskProfile: "aggressive" });
  assert.equal(inferSessionRiskProfile(configuration), "aggressive");
});

test("Risk profile inference returns custom when a persisted cap differs", () => {
  const configuration = buildSessionCampaignConfiguration({ ...base, riskProfile: "balanced" });
  configuration.risk_max_order_notional = "101";
  assert.equal(inferSessionRiskProfile(configuration), "custom");
});

test("Risk profile inference compares Decimal string forms semantically", () => {
  const configuration = buildSessionCampaignConfiguration({ ...base, riskProfile: "balanced" });
  configuration.risk_max_order_notional = "100.0";
  configuration.paper_derivative_leverage = "1.0";
  configuration.risk_max_derivative_leverage = "1.00";
  configuration.risk_derivative_liquidation_buffer_ratio = "1.1500";
  assert.equal(inferSessionRiskProfile(configuration), "balanced");
});

test("Risk profile inference recognizes all PERPETUAL presets including derived caps", () => {
  for (const profile of ["prudent", "balanced", "aggressive"]) {
    const configuration = buildSessionCampaignConfiguration({
      ...base,
      marketType: "PERPETUAL",
      riskProfile: profile,
    });
    assert.equal(inferSessionRiskProfile(configuration), profile);
  }
});

test("Risk profile inference is independent from Agent aggressiveness", () => {
  const configuration = buildSessionCampaignConfiguration({
    ...base,
    riskProfile: "balanced",
    aggressiveness: 10,
  });
  assert.equal(inferSessionRiskProfile(configuration), "balanced");
});

test("Risk profile inference returns custom when a PERPETUAL derived cap differs", () => {
  const configuration = buildSessionCampaignConfiguration({
    ...base,
    marketType: "PERPETUAL",
    riskProfile: "prudent",
  });
  configuration.risk_max_total_derivative_exposure = "201";
  assert.equal(inferSessionRiskProfile(configuration), "custom");
});
