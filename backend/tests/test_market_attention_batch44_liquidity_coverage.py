from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    ActivityHorizonSnapshot,
    LiquidityRegime,
    MarketActivitySnapshot,
    MarketActivityState,
    MarketAttentionPolicy,
    RadarInterestLevel,
    RadarStatus,
)
from ai_spot_trader.market.attention_filters import (
    FilteredStructuredMarketAttentionRadar,
    MarketAttentionCoverageStatus,
    MarketAttentionFilters,
    Volume24hMeasurement,
    Volume24hStatus,
    _classify_perpetual_liquidity,
    _coverage_diagnostics,
)
from ai_spot_trader.market.attention_scope_trend import MarketScope
from ai_spot_trader.market.candles import CandleTimeframe

NOW = datetime(2026, 10, 3, 10, 0, tzinfo=UTC)


def _market(symbol: str, market_type: MarketType) -> ExecutableMarket:
    return ExecutableMarket(symbol=symbol, market_type=market_type)


def _activity(
    market: ExecutableMarket,
    *,
    observed_at: datetime = NOW,
    state: MarketActivityState = MarketActivityState.NORMAL,
    regime: LiquidityRegime = LiquidityRegime.UNKNOWN,
    reference: Decimal | None = None,
    interest: RadarInterestLevel = RadarInterestLevel.LOW,
) -> MarketActivitySnapshot:
    return MarketActivitySnapshot(
        market=market,
        observed_at=observed_at,
        status=RadarStatus.AVAILABLE,
        activity_state=state,
        liquidity_regime=regime,
        liquidity_reference_usd=reference,
        horizons=(
            ActivityHorizonSnapshot(
                timeframe=CandleTimeframe.M5,
                observation_count=1,
                baseline_period_count=0,
                complete=False,
            ),
        ),
        interest_level=interest,
    )


def test_spot_liquidity_classification_is_left_untouched_by_batch44() -> None:
    spot = _activity(
        _market("BTC/USD", MarketType.SPOT),
        regime=LiquidityRegime.HIGH,
        reference=Decimal("123456"),
        interest=RadarInterestLevel.MEDIUM,
    )
    perp = _activity(_market("ETH/USD", MarketType.PERPETUAL))

    result = _classify_perpetual_liquidity(
        (spot, perp),
        {
            perp.market: Volume24hMeasurement(
                status=Volume24hStatus.AVAILABLE,
                value_usd=Decimal("1000000"),
            )
        },
    )

    assert result[0] is spot
    assert result[0].liquidity_reference_usd == Decimal("123456")
    assert result[0].liquidity_regime is LiquidityRegime.HIGH
    assert result[0].interest_level is RadarInterestLevel.MEDIUM


def test_perpetual_usd_volume_quote_builds_exploitable_family_percentiles() -> None:
    perps = tuple(
        _activity(
            _market(f"P{index}/USD", MarketType.PERPETUAL),
            state=MarketActivityState.ACCELERATING,
        )
        for index in range(5)
    )
    measurements = {
        snapshot.market: Volume24hMeasurement(
            status=Volume24hStatus.AVAILABLE,
            value_usd=Decimal(str((index + 1) * 100000)),
        )
        for index, snapshot in enumerate(perps)
    }

    result = _classify_perpetual_liquidity(perps, measurements)

    assert tuple(item.liquidity_regime for item in result) == (
        LiquidityRegime.MICRO,
        LiquidityRegime.LOW,
        LiquidityRegime.MEDIUM,
        LiquidityRegime.HIGH,
        LiquidityRegime.VERY_HIGH,
    )
    assert result[-1].liquidity_reference_usd == Decimal("500000")
    assert result[-1].interest_level is RadarInterestLevel.MEDIUM
    assert "Liquidité relative élevée" in result[-1].interest_reasons


def test_perpetual_without_reliable_volume_quote_stays_unknown() -> None:
    known = _activity(_market("BTC/USD", MarketType.PERPETUAL))
    missing = _activity(_market("DOGE/USD", MarketType.PERPETUAL))
    result = _classify_perpetual_liquidity(
        (known, missing),
        {
            known.market: Volume24hMeasurement(
                status=Volume24hStatus.AVAILABLE,
                value_usd=Decimal("250000"),
            ),
            missing.market: Volume24hMeasurement(
                status=Volume24hStatus.UNKNOWN_MISSING_QUOTE_VOLUME
            ),
        },
    )

    assert result[0].liquidity_regime is LiquidityRegime.MEDIUM
    assert result[1].liquidity_reference_usd is None
    assert result[1].liquidity_regime is LiquidityRegime.UNKNOWN


def test_spot_values_cannot_contaminate_perpetual_percentile_population() -> None:
    spot = _activity(
        _market("BTC/USD", MarketType.SPOT),
        regime=LiquidityRegime.VERY_HIGH,
        reference=Decimal("999999999999"),
    )
    low = _activity(_market("AAA/USD", MarketType.PERPETUAL))
    high = _activity(_market("BBB/USD", MarketType.PERPETUAL))
    result = _classify_perpetual_liquidity(
        (spot, low, high),
        {
            low.market: Volume24hMeasurement(
                status=Volume24hStatus.AVAILABLE,
                value_usd=Decimal("100"),
            ),
            high.market: Volume24hMeasurement(
                status=Volume24hStatus.AVAILABLE,
                value_usd=Decimal("200"),
            ),
        },
    )

    assert result[0] is spot
    assert result[1].liquidity_regime is LiquidityRegime.MICRO
    assert result[2].liquidity_regime is LiquidityRegime.VERY_HIGH


def test_coverage_small_universe_reports_full_coverage() -> None:
    markets = tuple(_market(f"S{index}/USD", MarketType.SPOT) for index in range(4))
    cache = {market: _activity(market) for market in markets}
    diagnostics = _coverage_diagnostics(
        eligible_markets=markets,
        activity_cache=cache,
        now=NOW,
        policy=MarketAttentionPolicy(
            scan_limit=120,
            refresh_seconds=300,
            activity_ttl_seconds=900,
        ),
    )

    assert diagnostics.status is MarketAttentionCoverageStatus.COVERED
    assert diagnostics.eligible_market_count == 4
    assert diagnostics.fresh_market_count == 4
    assert diagnostics.expired_market_count == 0
    assert diagnostics.unseen_market_count == 0
    assert diagnostics.coverage_ratio == 1.0
    assert diagnostics.effective_scan_limit == 4
    assert diagnostics.estimated_refreshes_per_full_rotation == 1
    assert diagnostics.estimated_full_rotation_seconds == 300
    assert diagnostics.rotation_within_activity_ttl is True


def test_coverage_large_mixed_universe_detects_rotation_slower_than_ttl() -> None:
    spots = tuple(_market(f"S{index}/USD", MarketType.SPOT) for index in range(200))
    perps = tuple(_market(f"P{index}/USD", MarketType.PERPETUAL) for index in range(200))
    diagnostics = _coverage_diagnostics(
        eligible_markets=spots + perps,
        activity_cache={},
        now=NOW,
        policy=MarketAttentionPolicy(
            scan_limit=120,
            refresh_seconds=300,
            activity_ttl_seconds=900,
        ),
    )

    assert diagnostics.status is MarketAttentionCoverageStatus.CONFIGURATION_TOO_SLOW
    assert diagnostics.eligible_market_count == 400
    assert diagnostics.fresh_market_count == 0
    assert diagnostics.unseen_market_count == 400
    assert diagnostics.coverage_ratio == 0.0
    assert diagnostics.effective_scan_limit == 120
    assert diagnostics.estimated_refreshes_per_full_rotation == 4
    assert diagnostics.estimated_full_rotation_seconds == 1200
    assert diagnostics.rotation_within_activity_ttl is False


def test_coverage_distinguishes_rotation_in_progress_from_ttl_expiration() -> None:
    markets = tuple(_market(f"S{index}/USD", MarketType.SPOT) for index in range(12))
    policy = MarketAttentionPolicy(
        scan_limit=10,
        refresh_seconds=300,
        activity_ttl_seconds=900,
    )

    rotating = _coverage_diagnostics(
        eligible_markets=markets,
        activity_cache={markets[0]: _activity(markets[0])},
        now=NOW,
        policy=policy,
    )
    assert rotating.status is MarketAttentionCoverageStatus.ROTATING
    assert rotating.fresh_market_count == 1
    assert rotating.unseen_market_count == 11
    assert rotating.rotation_within_activity_ttl is True

    expired = _coverage_diagnostics(
        eligible_markets=markets,
        activity_cache={
            markets[0]: _activity(markets[0]),
            markets[1]: _activity(markets[1], observed_at=NOW - timedelta(seconds=901)),
        },
        now=NOW,
        policy=policy,
    )
    assert expired.status is MarketAttentionCoverageStatus.TTL_EXPIRED
    assert expired.fresh_market_count == 1
    assert expired.expired_market_count == 1
    assert expired.unseen_market_count == 10
    assert expired.oldest_activity_age_seconds == 901


def test_coverage_scope_uses_only_selected_market_family() -> None:
    spot = _market("BTC/USD", MarketType.SPOT)
    perp = _market("BTC/USD", MarketType.PERPETUAL)
    radar = FilteredStructuredMarketAttentionRadar.__new__(FilteredStructuredMarketAttentionRadar)
    radar._catalogue = (spot, perp)  # type: ignore[attr-defined]
    radar._market_scope = MarketScope.SPOT  # type: ignore[attr-defined]
    radar._filters = MarketAttentionFilters(market_scope=MarketScope.SPOT)  # type: ignore[attr-defined]
    radar._metadata_by_symbol = {}  # type: ignore[attr-defined]

    assert radar._eligible_coverage_markets() == (spot,)

    radar._market_scope = MarketScope.PERPETUAL  # type: ignore[attr-defined]
    radar._filters = MarketAttentionFilters(market_scope=MarketScope.PERPETUAL)  # type: ignore[attr-defined]
    assert radar._eligible_coverage_markets() == (perp,)


def test_scan_rotation_remains_deterministic_with_family_cursors() -> None:
    markets = tuple(
        [_market(f"S{index}/USD", MarketType.SPOT) for index in range(20)]
        + [_market(f"P{index}/USD", MarketType.PERPETUAL) for index in range(20)]
    )
    radar = FilteredStructuredMarketAttentionRadar.__new__(FilteredStructuredMarketAttentionRadar)
    radar._policy = MarketAttentionPolicy(scan_limit=10)  # type: ignore[attr-defined]
    radar._scan_cursors = {MarketType.SPOT: 0, MarketType.PERPETUAL: 0}  # type: ignore[attr-defined]

    first = radar._next_scan_batch(markets)
    second = radar._next_scan_batch(markets)
    radar._scan_cursors = {MarketType.SPOT: 0, MarketType.PERPETUAL: 0}  # type: ignore[attr-defined]

    assert first == radar._next_scan_batch(markets)
    assert second == radar._next_scan_batch(markets)
    assert set(first).isdisjoint(second)
