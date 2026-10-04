import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_MARKET_ATTENTION_FILTERS,
  activeMarketAttentionFilters,
  activityErrorEntries,
  anomalyMethodLabel,
  attentionHorizon,
  formatAdaptiveScore,
  formatBps,
  formatCoverageRatio,
  formatDurationSeconds,
  formatImbalance,
  formatKrakenRawNumber,
  formatSignedPercent,
  formatUsdCompact,
  formatVolumeRatio,
  hasActiveStructureFilter,
  marketAttentionCoverageMessage,
  marketAttentionStatusMessage,
  marketCapCategoryLabel,
  marketStructureCoverageMessage,
  perpetualTickerContext,
  perpetualTickerStatusLabel,
  setMarketAttentionFilters,
  setMarketAttentionScope,
  slippageEstimate,
  structureEventFilterLabel,
  structureStateFilterLabel,
  trendDirectionLabel,
} from "./market-attention.ts";

const item = {
  market_activity: {
    market: { symbol: "QNT/USD", market_type: "SPOT" },
    observed_at: "2026-10-01T10:00:00Z",
    status: "AVAILABLE",
    activity_state: "ACCELERATING",
    trend_direction: "UP",
    liquidity_regime: "MEDIUM",
    liquidity_reference_usd: "500000",
    freshness_seconds: "20",
    characteristics: ["TRENDING", "VOLUME_ANOMALY"],
    interest_level: "HIGH",
    interest_reasons: ["Volume inhabituel"],
    horizons: [
      { timeframe: "5m", trend_direction: "UP", volume_ratio: "2.8", price_return: "0.01", complete: true },
      { timeframe: "15m", trend_direction: "UP", volume_ratio: "2.05", price_return: "0.031", complete: true },
    ],
    data_quality: "COMPLETE",
    error_type: null,
  },
  microstructure: {
    slippage: [
      { side: "BUY", notional_quote: "1000", slippage_bps: "4.2", insufficient_depth: false },
      { side: "SELL", notional_quote: "1000", slippage_bps: "5.1", insufficient_depth: false },
    ],
  },
  combined_characteristics: ["TRENDING", "TIGHT_SPREAD"],
  interest_level: "HIGH",
  interest_reasons: ["Volume inhabituel"],
  volume_24h_usd: "12500000",
  market_cap_usd: "8500000000",
  market_cap_category: "MID",
};

const emptyActivityErrors = () => ({
  KrakenConnectionError: 0,
  KrakenNetworkError: 0,
  KrakenTimeoutError: 0,
  KrakenHTTPError: 0,
  KrakenServerError: 0,
  KrakenRateLimitError: 0,
  KrakenAPIError: 0,
  KrakenPayloadError: 0,
  UnknownKrakenSymbolError: 0,
  CandleValidationError: 0,
  Other: 0,
});

const overview = (status, candidateCount = 0) => ({
  protocol_version: "market-attention-radar-v6",
  observed_at: "2026-10-01T10:00:00Z",
  status,
  informative_only: true,
  market_scope: "ALL",
  filters: { ...DEFAULT_MARKET_ATTENTION_FILTERS },
  catalogue_market_count: 100,
  cached_activity_market_count: 80,
  scanned_market_count: 20,
  scanned_market_type_counts: { SPOT: 12, PERPETUAL: 8 },
  fresh_market_type_counts: { SPOT: 42, PERPETUAL: 38 },
  candidate_market_count: candidateCount,
  activity_status_counts: { AVAILABLE: 80, PARTIAL: 0, STALE: 0, ERROR: 0 },
  activity_state_counts: { UNKNOWN: 10, NORMAL: 70, ELEVATED: 0, ACCELERATING: 0, VERY_HIGH: 0 },
  activity_data_quality_counts: { COMPLETE: 70, NO_TRADE_GAPS: 10, INSUFFICIENT_HISTORY: 0, DISCONTINUOUS_HISTORY: 0, TECHNICAL_ERROR: 0 },
  activity_error_counts: emptyActivityErrors(),
  activity_payload_stage_counts: { ASSET_PAIRS_PAYLOAD: 0, ASSET_PAIRS_ENTRY: 0, ASSET_PAIRS_SYMBOL: 0, OHLC_RESULT: 0, OHLC_SERIES: 0, OHLC_PAIR_KEY: 0, OHLC_ROW: 0, OHLC_TIMESTAMP: 0, OHLC_NUMERIC: 0 },
  activity_market_type_status_counts: {
    SPOT: { AVAILABLE: 50, PARTIAL: 0, STALE: 0, ERROR: 0 },
    PERPETUAL: { AVAILABLE: 30, PARTIAL: 0, STALE: 0, ERROR: 0 },
  },
  liquidity_regime_counts: { UNKNOWN: 80, MICRO: 0, LOW: 0, MEDIUM: 0, HIGH: 0, VERY_HIGH: 0 },
  microstructure_scanned_market_count: 12,
  microstructure_cached_market_count: 30,
  microstructure_status_counts: { AVAILABLE: 25, PARTIAL: 5, STALE: 0, ERROR: 0, NOT_APPLICABLE: 38 },
  microstructure_quality_counts: { COMPLETE: 25, PARTIAL: 5, STALE: 0, TECHNICAL_ERROR: 0, NOT_APPLICABLE: 38 },
  microstructure_error_counts: {},
  subthreshold_activity: [],
  shortlist: [],
  error_type: null,
});

test("reads requested deterministic horizons without inventing missing ones", () => {
  assert.equal(attentionHorizon(item, "15m")?.volume_ratio, "2.05");
  assert.equal(attentionHorizon(item, "1h"), null);
});

test("formats descriptive ratios and microstructure metrics", () => {
  assert.equal(formatVolumeRatio("2.8"), "2.80×");
  assert.equal(formatSignedPercent("0.031"), "+3.10 %");
  assert.equal(formatBps("4.2"), "4.20 bps");
  assert.equal(formatImbalance("0.25"), "+25.0 %");
  assert.equal(formatVolumeRatio(null), "—");
});

test("formats Batch 43 volume and market-cap metadata", () => {
  assert.equal(formatUsdCompact(item.volume_24h_usd), "12.5 M$");
  assert.equal(formatUsdCompact(item.market_cap_usd), "8.5 B$");
  assert.equal(marketCapCategoryLabel(item.market_cap_category), "Mid (1 – 10 Md$)");
  assert.equal(marketCapCategoryLabel("UNKNOWN"), "Indéterminée");
});

test("formats Batch 44 coverage diagnostics", () => {
  assert.equal(formatCoverageRatio(0.625), "62.5 %");
  assert.equal(formatDurationSeconds(1200), "20 min");
  assert.match(
    marketAttentionCoverageMessage({
      eligible_market_count: 400,
      fresh_market_count: 120,
      expired_market_count: 0,
      unseen_market_count: 280,
      coverage_ratio: 0.3,
      effective_scan_limit: 120,
      estimated_refreshes_per_full_rotation: 4,
      estimated_full_rotation_seconds: 1200,
      activity_ttl_seconds: 900,
      oldest_activity_age_seconds: 300,
      rotation_within_activity_ttl: false,
      status: "CONFIGURATION_TOO_SLOW",
    }),
    /ne peut pas maintenir toute la population fraîche/i,
  );
});

test("formats Batch 45 structure coverage diagnostics", () => {
  const rotating = {
    eligible_market_count: 40,
    fresh_market_count: 20,
    expired_market_count: 0,
    unseen_market_count: 20,
    scanned_market_count: 10,
    coverage_ratio: 0.5,
    effective_market_limit: 20,
    estimated_refreshes_per_full_rotation: 2,
    estimated_full_rotation_seconds: 600,
    cache_ttl_seconds: 3600,
    oldest_structure_age_seconds: 300,
    rotation_within_cache_ttl: true,
    status: "ROTATING",
  };
  assert.match(marketStructureCoverageMessage(rotating), /rotation Structure en cours/i);
  assert.match(
    marketStructureCoverageMessage({
      ...rotating,
      status: "CONFIGURATION_TOO_SLOW",
      estimated_full_rotation_seconds: 7200,
      rotation_within_cache_ttl: false,
    }),
    /trop lente/i,
  );
  assert.match(
    marketStructureCoverageMessage({
      ...rotating,
      fresh_market_count: 40,
      unseen_market_count: 0,
      coverage_ratio: 1,
      status: "COVERED",
    }),
    /complète/i,
  );
});

test("keeps rotation, expired TTL and full OHLCV coverage distinguishable", () => {
  const base = {
    eligible_market_count: 10,
    fresh_market_count: 5,
    expired_market_count: 0,
    unseen_market_count: 5,
    coverage_ratio: 0.5,
    effective_scan_limit: 10,
    estimated_refreshes_per_full_rotation: 1,
    estimated_full_rotation_seconds: 300,
    activity_ttl_seconds: 900,
    oldest_activity_age_seconds: 200,
    rotation_within_activity_ttl: true,
  };
  assert.match(marketAttentionCoverageMessage({ ...base, status: "ROTATING" }), /rotation en cours/i);
  assert.match(
    marketAttentionCoverageMessage({
      ...base,
      fresh_market_count: 8,
      expired_market_count: 1,
      unseen_market_count: 1,
      status: "TTL_EXPIRED",
    }),
    /sorti du TTL/i,
  );
  assert.match(
    marketAttentionCoverageMessage({
      ...base,
      fresh_market_count: 10,
      unseen_market_count: 0,
      coverage_ratio: 1,
      status: "COVERED",
    }),
    /univers couvert/i,
  );
});

test("renders deterministic trend and structure labels", () => {
  assert.equal(trendDirectionLabel("UP"), "Haussière ↑");
  assert.equal(trendDirectionLabel("DOWN"), "Baissière ↓");
  assert.equal(trendDirectionLabel("NEUTRAL"), "Neutre →");
  assert.equal(trendDirectionLabel("MIXED"), "Mixte ↕");
  assert.equal(trendDirectionLabel("UNKNOWN"), "Indéterminée");
  assert.equal(structureStateFilterLabel("TRANSITION"), "Transition");
  assert.equal(structureStateFilterLabel("MIXED"), "Mixte");
  assert.equal(structureEventFilterLabel("BOS_UP"), "BOS ↑");
  assert.equal(structureEventFilterLabel("CHOCH_DOWN"), "CHOCH ↓");
});

test("selects a theoretical slippage scenario without turning it into an order", () => {
  assert.equal(slippageEstimate(item, "BUY", 1000)?.slippage_bps, "4.2");
  assert.equal(slippageEstimate(item, "BUY", 500), null);
});

test("maps an operational empty shortlist to an explicit healthy message", () => {
  assert.equal(marketAttentionStatusMessage(overview("AVAILABLE")), "Radar opérationnel — aucun événement inhabituel détecté.");
});

test("distinguishes incomplete structure rotation from no matching structure", () => {
  const filters = {
    ...DEFAULT_MARKET_ATTENTION_FILTERS,
    structure_4h: { states: ["TRANSITION"], events: ["CHOCH_DOWN"] },
  };
  const incomplete = {
    ...overview("AVAILABLE"),
    filters,
    structure_coverage: {
      eligible_market_count: 30,
      fresh_market_count: 10,
      expired_market_count: 0,
      unseen_market_count: 20,
      scanned_market_count: 10,
      coverage_ratio: 1 / 3,
      effective_market_limit: 20,
      estimated_refreshes_per_full_rotation: 2,
      estimated_full_rotation_seconds: 600,
      cache_ttl_seconds: 3600,
      oldest_structure_age_seconds: 120,
      rotation_within_cache_ttl: true,
      status: "ROTATING",
    },
  };
  assert.match(marketAttentionStatusMessage(incomplete), /couverture encore incomplète/i);

  const complete = {
    ...incomplete,
    structure_coverage: {
      ...incomplete.structure_coverage,
      fresh_market_count: 30,
      unseen_market_count: 0,
      coverage_ratio: 1,
      status: "COVERED",
    },
  };
  assert.match(marketAttentionStatusMessage(complete), /aucun marché couvert ne correspond/i);
});

test("detects active structure filters across global states and timeframe criteria", () => {
  assert.equal(hasActiveStructureFilter(DEFAULT_MARKET_ATTENTION_FILTERS), false);
  assert.equal(
    hasActiveStructureFilter({
      ...DEFAULT_MARKET_ATTENTION_FILTERS,
      structure_global_states: ["MIXED"],
    }),
    true,
  );
  assert.equal(
    hasActiveStructureFilter({
      ...DEFAULT_MARKET_ATTENTION_FILTERS,
      structure_1h: { states: [], events: ["BOS_DOWN"] },
    }),
    true,
  );
});

test("keeps partial and stale Kraken states distinguishable", () => {
  assert.match(marketAttentionStatusMessage(overview("PARTIAL")), /partiellement disponible/i);
  assert.match(marketAttentionStatusMessage(overview("STALE")), /Kraken périmées/i);
});

test("returns only non-zero bounded Kraken error categories in deterministic order", () => {
  const counts = { ...emptyActivityErrors(), KrakenNetworkError: 8, KrakenRateLimitError: 3, Other: 1 };
  assert.deepEqual(activityErrorEntries(counts), [["KrakenNetworkError", 8], ["KrakenRateLimitError", 3], ["Other", 1]]);
});

test("falls back to legacy scope with all Batch 45 filters disabled", () => {
  const legacy = { ...overview("AVAILABLE"), market_scope: "SPOT" };
  delete legacy.filters;
  assert.deepEqual(activeMarketAttentionFilters(legacy), {
    ...DEFAULT_MARKET_ATTENTION_FILTERS,
    market_scope: "SPOT",
  });
});


test("formats Batch 46 adaptive anomaly diagnostics without hiding the historical ratio", () => {
  assert.equal(formatVolumeRatio("1.30"), "1.30×");
  assert.equal(formatAdaptiveScore("2.345"), "+2.35 MADσ");
  assert.equal(formatAdaptiveScore("-2.1"), "-2.10 MADσ");
  assert.equal(formatAdaptiveScore(null), "—");
  assert.equal(anomalyMethodLabel("ROBUST_MAD"), "MAD robuste");
  assert.equal(anomalyMethodLabel("LEGACY_RATIO_FALLBACK"), "Fallback ratio");
  assert.equal(anomalyMethodLabel("UNAVAILABLE"), "Indisponible");
  assert.equal(anomalyMethodLabel(undefined), "Indisponible");
});

test("keeps legacy v6 horizon payloads readable when Batch 46 additive fields are absent", () => {
  const horizon = attentionHorizon(item, "5m");
  assert.equal(horizon?.volume_ratio, "2.8");
  assert.equal(horizon?.volume_anomaly_score, undefined);
  assert.equal(horizon?.volume_anomaly_method, undefined);
  assert.equal(anomalyMethodLabel(horizon?.volume_anomaly_method), "Indisponible");
});

test("exposes adaptive subthreshold diagnostics additively", () => {
  const adaptive = {
    market: { symbol: "AAA/USD", market_type: "SPOT" },
    peak_volume_ratio: "1.31",
    peak_timeframe: "15m",
    peak_anomaly_score: "2.8",
    anomaly_method: "ROBUST_MAD",
  };
  assert.equal(formatVolumeRatio(adaptive.peak_volume_ratio), "1.31×");
  assert.equal(formatAdaptiveScore(adaptive.peak_anomaly_score), "+2.80 MADσ");
  assert.equal(anomalyMethodLabel(adaptive.anomaly_method), "MAD robuste");
});

test("keeps legacy v6 candidate payloads readable when Futures context is absent", () => {
  assert.equal(perpetualTickerContext(item), null);
  assert.equal(perpetualTickerStatusLabel(undefined), "Indisponible");
});

test("exposes PERPETUAL Open Interest and raw funding fields without fake percent formatting", () => {
  const perpetual = {
    ...item,
    market_activity: {
      ...item.market_activity,
      market: { symbol: "BTC/USD", market_type: "PERPETUAL" },
    },
    perpetual_ticker: {
      status: "AVAILABLE",
      provider: "KRAKEN_FUTURES",
      venue_symbol: "PF_XBTUSD",
      observed_at: "2026-10-04T12:00:00Z",
      mark_price: "65000.5",
      index_price: "64998.1",
      volume_quote: "125000000",
      open_interest: "8123.5",
      open_interest_unit: null,
      funding_rate_raw: "6.5",
      funding_rate_relative: null,
      funding_rate_prediction_raw: "7.1",
      funding_rate_raw_unit: null,
      funding_rate_prediction_unit: null,
      suspended: false,
    },
  };
  const futures = perpetualTickerContext(perpetual);
  assert.equal(futures?.open_interest, "8123.5");
  assert.equal(futures?.funding_rate_raw, "6.5");
  assert.equal(futures?.funding_rate_prediction_raw, "7.1");
  assert.equal(perpetualTickerStatusLabel(futures?.status), "Disponible");
  assert.equal(formatKrakenRawNumber(futures?.open_interest), "8.123 k");
  assert.doesNotMatch(formatKrakenRawNumber(futures?.funding_rate_raw), /%/);
  assert.doesNotMatch(formatKrakenRawNumber(futures?.funding_rate_prediction_raw), /%/);
});

test("keeps Futures prediction distinct and tolerates partial or technical states", () => {
  const partial = {
    ...item,
    perpetual_ticker: {
      status: "PARTIAL",
      provider: "KRAKEN_FUTURES",
      venue_symbol: "PF_XBTUSD",
      observed_at: "2026-10-04T12:00:00Z",
      mark_price: "65000",
      index_price: null,
      volume_quote: "1000",
      open_interest: null,
      open_interest_unit: null,
      funding_rate_raw: "5.2",
      funding_rate_relative: null,
      funding_rate_prediction_raw: null,
      funding_rate_raw_unit: null,
      funding_rate_prediction_unit: null,
      suspended: false,
    },
  };
  assert.equal(perpetualTickerStatusLabel(perpetualTickerContext(partial)?.status), "Partiel");
  assert.equal(formatKrakenRawNumber(perpetualTickerContext(partial)?.funding_rate_prediction_raw), "—");
  assert.equal(perpetualTickerStatusLabel("TECHNICAL_ERROR"), "Erreur technique");
  assert.equal(perpetualTickerStatusLabel("NOT_APPLICABLE"), "N/A");
});

test("sends a backend scope change before replacing the radar snapshot", async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "/backend/api/v1/market-attention/scope");
    assert.equal(init?.method, "PUT");
    assert.equal(init?.body, JSON.stringify({ market_scope: "SPOT" }));
    return {
      ok: true,
      status: 200,
      json: async () => ({ ...overview("AVAILABLE"), market_scope: "SPOT" }),
    };
  };
  try {
    const result = await setMarketAttentionScope("SPOT");
    assert.equal(result.market_scope, "SPOT");
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("sends volume, cap, trend and structure filters as one backend runtime state", async () => {
  const previousFetch = globalThis.fetch;
  const filters = {
    ...DEFAULT_MARKET_ATTENTION_FILTERS,
    market_scope: "SPOT",
    min_volume_24h_usd: "1000000",
    market_cap_categories: ["MID", "LARGE"],
    trend_directions: ["DOWN", "MIXED"],
    structure_global_states: ["TRANSITION", "MIXED"],
    structure_1h: { states: ["BEARISH"], events: [] },
    structure_4h: { states: ["TRANSITION"], events: ["CHOCH_DOWN"] },
  };
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "/backend/api/v1/market-attention/filters");
    assert.equal(init?.method, "PUT");
    assert.equal(init?.body, JSON.stringify(filters));
    return {
      ok: true,
      status: 200,
      json: async () => ({
        ...overview("AVAILABLE"),
        market_scope: "SPOT",
        filters,
      }),
    };
  };
  try {
    const result = await setMarketAttentionFilters(filters);
    assert.deepEqual(result.filters, filters);
  } finally {
    globalThis.fetch = previousFetch;
  }
});
