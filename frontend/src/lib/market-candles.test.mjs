import assert from "node:assert/strict";
import test from "node:test";

import {
  MARKET_TIMEFRAMES,
  buildCockpitMarkets,
  buildMarketFillMarkers,
  markerCandleTime,
  mergeCandleSeries,
  toCandlestickData,
} from "./market-candles.ts";

const baseCandle = {
  symbol: "BTC/EUR",
  market_type: "SPOT",
  timeframe: "5m",
  open_time: "2026-09-25T10:00:00Z",
  close_time: "2026-09-25T10:05:00Z",
  open: "100",
  high: "110",
  low: "95",
  close: "105",
  volume: "2.5",
  is_final: false,
  updated_at: "2026-09-25T10:03:00Z",
};

test("maps canonical candles without inventing missing points", () => {
  assert.deepEqual(toCandlestickData([baseCandle]), [
    { time: 1790330400, open: 100, high: 110, low: 95, close: 105 },
  ]);
  assert.equal(toCandlestickData([{ ...baseCandle, open: "not-a-number" }]).length, 0);
});

test("updates the current candle, creates the next candle and avoids duplicates", () => {
  const updated = { ...baseCandle, close: "107", updated_at: "2026-09-25T10:04:00Z" };
  const next = {
    ...baseCandle,
    open_time: "2026-09-25T10:05:00Z",
    close_time: "2026-09-25T10:10:00Z",
    updated_at: "2026-09-25T10:06:00Z",
  };
  const merged = mergeCandleSeries([baseCandle], [updated, updated, next]);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].close, "107");
  assert.equal(merged[1].open_time, next.open_time);
});

test("does not regress a final candle to a non-final candle", () => {
  const final = { ...baseCandle, is_final: true, updated_at: "2026-09-25T10:05:00Z" };
  const regression = { ...baseCandle, is_final: false, updated_at: "2026-09-25T10:06:00Z" };
  assert.deepEqual(mergeCandleSeries([final], [regression]), [final]);
});

test("uses only backend-supported timeframes for each market type", () => {
  assert.equal(MARKET_TIMEFRAMES.SPOT.includes("12h"), false);
  assert.equal(MARKET_TIMEFRAMES.PERPETUAL.includes("15d"), false);
  assert.equal(MARKET_TIMEFRAMES.SPOT.includes("15d"), true);
  assert.equal(MARKET_TIMEFRAMES.PERPETUAL.includes("12h"), true);
});

test("prioritizes the effective watchlist and always appends open positions", () => {
  const markets = buildCockpitMarkets({
    effectiveWatchlist: [{ symbol: "ETH/EUR", market_type: "SPOT" }],
    bootstrapMarkets: [{ symbol: "BTC/EUR", market_type: "SPOT" }],
    portfolio: {
      portfolio_state_id: "p",
      as_of: "2026-09-25T10:00:00Z",
      mode: "PAPER",
      settlement_asset: "EUR",
      balances: [],
      positions: [{
        asset: "BTC",
        quantity: "1",
        available: "1",
        average_entry_price: "100",
        remaining_cost_basis: "100",
        realized_pnl: "0",
        accounting_complete: true,
        mark_price: "101",
        mark_observed_at: null,
        mark_source: "LAST_PRICE",
        market_value: "101",
        unrealized_pnl: "1",
        valuation_complete: true,
      }],
      derivative_positions: [],
      cash_available: "1000",
      spot_remaining_cost_basis_total: "100",
      spot_market_value_total: "101",
      spot_realized_pnl_total: "0",
      spot_unrealized_pnl_total: "1",
      equity: "1101",
      exposure_value: "101",
      exposure_fraction: "0.0917",
      valuation_complete: true,
    },
  });
  assert.deepEqual(markets.map((item) => `${item.market_type}:${item.symbol}`), ["SPOT:ETH/EUR", "SPOT:BTC/EUR"]);
  assert.equal(markets[1].hasPosition, true);
});

test("builds BUY/SELL markers from persisted fills only and keeps partial facts partial", () => {
  const executions = [{
    execution_id: "execution-1",
    cycle_id: "cycle-1",
    decision_id: "decision-1",
    risk_assessment_id: "risk-1",
    created_at: "2026-09-25T10:01:00Z",
    action: "BUY",
    symbol: "BTC/EUR",
    payload: { market_type: "SPOT" },
    fills: [{
      fill_id: "fill-1",
      execution_id: "execution-1",
      market_state_id: "market-1",
      filled_at: "2026-09-25T10:02:30Z",
      payload: { action: "BUY", symbol: "BTC/EUR", market_type: "SPOT", quantity: "0.1", price: "102", reduce_only: false },
    }],
  }];
  const markers = buildMarketFillMarkers(executions, { symbol: "BTC/EUR", market_type: "SPOT" });
  assert.equal(markers.length, 1);
  assert.equal(markers[0].action, "BUY");
  assert.equal(markers[0].price, "102");
  assert.equal(markers[0].reduceOnly, false);
  assert.equal(markerCandleTime(markers[0], [baseCandle]), 1790330400);
  assert.equal(buildMarketFillMarkers([{ ...executions[0], fills: [] }], { symbol: "BTC/EUR", market_type: "SPOT" }).length, 0);
});
