import assert from "node:assert/strict";
import test from "node:test";

import {
  MARKET_TIMEFRAMES,
  buildCockpitMarkets,
  buildMarketFillMarkers,
  buildMarketPositionOverlays,
  markerCandleTime,
  mergeCandleSeries,
  replaceMarketPositionOverlayHandles,
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

function spotPosition(overrides = {}) {
  return {
    asset: "BTC",
    quantity: "1",
    available: "1",
    average_entry_price: "100",
    remaining_cost_basis: "100",
    realized_pnl: "0",
    accounting_complete: true,
    mark_price: "101",
    mark_observed_at: "2026-09-25T10:00:00Z",
    mark_source: "LAST_PRICE",
    market_value: "101",
    unrealized_pnl: "1",
    valuation_complete: true,
    ...overrides,
  };
}

function derivativePosition(overrides = {}) {
  return {
    symbol: "BTC/USD",
    side: "LONG",
    quantity: "0.5",
    average_entry_price: "62000",
    mark_price: "62500",
    mark_observed_at: "2026-09-25T10:00:00Z",
    contract_size: "1",
    notional: "31250",
    realized_pnl: "0",
    unrealized_pnl: "250",
    leverage: "2",
    margin_used: "15625",
    initial_margin_rate: "0.5",
    maintenance_margin_rate: "0.1",
    maintenance_margin: "3125",
    cumulative_funding: "0",
    liquidation_price: "50000",
    margin_mode: "ISOLATED",
    funding_updated_at: null,
    ...overrides,
  };
}

function portfolio(overrides = {}) {
  return {
    portfolio_state_id: "p",
    as_of: "2026-09-25T10:00:00Z",
    mode: "PAPER",
    settlement_asset: "EUR",
    balances: [],
    positions: [],
    derivative_positions: [],
    cash_available: "1000",
    spot_remaining_cost_basis_total: "0",
    spot_market_value_total: "0",
    spot_realized_pnl_total: "0",
    spot_unrealized_pnl_total: "0",
    equity: "1000",
    exposure_value: "0",
    exposure_fraction: "0",
    valuation_complete: true,
    ...overrides,
  };
}

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
    portfolio: portfolio({ positions: [spotPosition()] }),
  });
  assert.deepEqual(markets.map((item) => `${item.market_type}:${item.symbol}`), ["SPOT:ETH/EUR", "SPOT:BTC/EUR"]);
  assert.equal(markets[1].hasPosition, true);
});

test("builds SPOT average-entry and mark overlays only from the canonical position", () => {
  const overlays = buildMarketPositionOverlays(
    portfolio({ positions: [spotPosition()] }),
    { symbol: "BTC/EUR", market_type: "SPOT" },
  );
  assert.deepEqual(overlays, [
    { id: "SPOT:BTC/EUR:average-entry", kind: "average-entry", label: "Prix moyen", price: 100 },
    { id: "SPOT:BTC/EUR:mark", kind: "mark", label: "Mark backend", price: 101 },
  ]);
});

test("keeps distinct canonical overlays when average-entry and mark levels coincide", () => {
  const overlays = buildMarketPositionOverlays(
    portfolio({ positions: [spotPosition({ average_entry_price: "100", mark_price: "100" })] }),
    { symbol: "BTC/EUR", market_type: "SPOT" },
  );
  assert.deepEqual(overlays.map((item) => item.kind), ["average-entry", "mark"]);
  assert.deepEqual(overlays.map((item) => item.price), [100, 100]);
  assert.equal(new Set(overlays.map((item) => item.id)).size, 2);
});

test("builds no SPOT overlay when there is no matching position", () => {
  const overlays = buildMarketPositionOverlays(
    portfolio({ positions: [spotPosition({ asset: "ETH" })] }),
    { symbol: "BTC/EUR", market_type: "SPOT" },
  );
  assert.deepEqual(overlays, []);
});

test("does not invent missing SPOT overlay values", () => {
  const overlays = buildMarketPositionOverlays(
    portfolio({ positions: [spotPosition({ average_entry_price: null, mark_price: null })] }),
    { symbol: "BTC/EUR", market_type: "SPOT" },
  );
  assert.deepEqual(overlays, []);
});

test("does not project a SPOT position onto another quote currency", () => {
  const overlays = buildMarketPositionOverlays(
    portfolio({ positions: [spotPosition()] }),
    { symbol: "BTC/USD", market_type: "SPOT" },
  );
  assert.deepEqual(overlays, []);
});

test("builds PERPETUAL average-entry, mark and liquidation overlays", () => {
  const overlays = buildMarketPositionOverlays(
    portfolio({ derivative_positions: [derivativePosition()] }),
    { symbol: "BTC/USD", market_type: "PERPETUAL" },
  );
  assert.deepEqual(overlays, [
    { id: "PERPETUAL:BTC/USD:average-entry", kind: "average-entry", label: "Prix moyen", price: 62000 },
    { id: "PERPETUAL:BTC/USD:mark", kind: "mark", label: "Mark backend", price: 62500 },
    { id: "PERPETUAL:BTC/USD:liquidation", kind: "liquidation", label: "Liquidation", price: 50000 },
  ]);
});

test("omits the PERPETUAL liquidation overlay when liquidation_price is absent", () => {
  const overlays = buildMarketPositionOverlays(
    portfolio({ derivative_positions: [derivativePosition({ liquidation_price: null })] }),
    { symbol: "BTC/USD", market_type: "PERPETUAL" },
  );
  assert.deepEqual(overlays.map((item) => item.kind), ["average-entry", "mark"]);
});

test("keeps overlay identity scoped to the active market and updates values without duplication", () => {
  const first = buildMarketPositionOverlays(
    portfolio({ positions: [spotPosition()] }),
    { symbol: "BTC/EUR", market_type: "SPOT" },
  );
  const updated = buildMarketPositionOverlays(
    portfolio({ positions: [spotPosition({ average_entry_price: "102", mark_price: "104" })] }),
    { symbol: "BTC/EUR", market_type: "SPOT" },
  );
  const otherMarket = buildMarketPositionOverlays(
    portfolio({ positions: [spotPosition()] }),
    { symbol: "ETH/EUR", market_type: "SPOT" },
  );

  assert.deepEqual(first.map((item) => item.id), ["SPOT:BTC/EUR:average-entry", "SPOT:BTC/EUR:mark"]);
  assert.deepEqual(updated.map((item) => item.id), first.map((item) => item.id));
  assert.deepEqual(updated.map((item) => item.price), [102, 104]);
  assert.equal(new Set(updated.map((item) => item.id)).size, updated.length);
  assert.deepEqual(otherMarket, []);
});

test("replaces old overlay handles when the active market changes", () => {
  const removed = [];
  const created = [];
  const next = replaceMarketPositionOverlayHandles(
    [{ overlayId: "SPOT:BTC/EUR:mark", value: "old-btc-line" }],
    [{ id: "SPOT:ETH/EUR:mark", kind: "mark", label: "Mark backend", price: 201 }],
    (overlay) => { created.push(overlay.id); return `line:${overlay.id}`; },
    (value) => removed.push(value),
  );
  assert.deepEqual(removed, ["old-btc-line"]);
  assert.deepEqual(created, ["SPOT:ETH/EUR:mark"]);
  assert.deepEqual(next.map((item) => item.overlayId), ["SPOT:ETH/EUR:mark"]);
});

test("updates overlay handles without duplication when canonical position values change", () => {
  const overlays = buildMarketPositionOverlays(
    portfolio({ positions: [spotPosition({ average_entry_price: "102", mark_price: "104" })] }),
    { symbol: "BTC/EUR", market_type: "SPOT" },
  );
  const removed = [];
  const next = replaceMarketPositionOverlayHandles(
    [
      { overlayId: "SPOT:BTC/EUR:average-entry", value: "old-average" },
      { overlayId: "SPOT:BTC/EUR:mark", value: "old-mark" },
    ],
    overlays,
    (overlay) => `new:${overlay.id}:${overlay.price}`,
    (value) => removed.push(value),
  );
  assert.deepEqual(removed, ["old-average", "old-mark"]);
  assert.equal(next.length, 2);
  assert.equal(new Set(next.map((item) => item.overlayId)).size, 2);
});

test("removes every overlay handle when the active market has no canonical overlays", () => {
  const removed = [];
  const next = replaceMarketPositionOverlayHandles(
    [
      { overlayId: "PERPETUAL:BTC/USD:average-entry", value: "average" },
      { overlayId: "PERPETUAL:BTC/USD:mark", value: "mark" },
      { overlayId: "PERPETUAL:BTC/USD:liquidation", value: "liquidation" },
    ],
    [],
    () => "unreachable",
    (value) => removed.push(value),
  );
  assert.deepEqual(removed, ["average", "mark", "liquidation"]);
  assert.deepEqual(next, []);
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
