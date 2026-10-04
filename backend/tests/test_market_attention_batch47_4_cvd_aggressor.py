from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import ActivityAnomalyMethod
from ai_spot_trader.market.perpetual_analytics import (
    PerpetualAggressorDifferentialPoint,
    PerpetualAnalyticsCharacteristic,
    PerpetualAnalyticsPoint,
    PerpetualAnalyticsPolicy,
    PerpetualAnalyticsScanner,
    PerpetualAnalyticsStatus,
    PerpetualCvdPoint,
    PerpetualFundingPoint,
    analyze_aggressor_differential_history,
    analyze_cvd_history,
)

NOW = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)
PERP = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)


def _policy(**updates) -> PerpetualAnalyticsPolicy:
    return PerpetualAnalyticsPolicy(
        market_limit_per_refresh=updates.pop("market_limit_per_refresh", 2),
        cache_ttl_seconds=updates.pop("cache_ttl_seconds", 3600),
        history_interval_seconds=updates.pop("history_interval_seconds", 3600),
        history_lookback_seconds=updates.pop("history_lookback_seconds", 72_000),
        fetch_concurrency=updates.pop("fetch_concurrency", 2),
        baseline_periods=updates.pop("baseline_periods", 6),
        data_stale_after_seconds=updates.pop("data_stale_after_seconds", 7200),
        **updates,
    )


def _times(count: int, *, end: datetime = NOW) -> list[datetime]:
    start = end - timedelta(hours=count)
    return [start + timedelta(hours=index) for index in range(count)]


def _cvd(values: list[str]) -> tuple[PerpetualCvdPoint, ...]:
    return tuple(
        PerpetualCvdPoint(
            observed_at=at,
            buy_volume=Decimal("100"),
            sell_volume=Decimal("90"),
            cvd=Decimal(value),
        )
        for at, value in zip(_times(len(values)), values, strict=True)
    )


def _aggressor(values: list[str]) -> tuple[PerpetualAggressorDifferentialPoint, ...]:
    return tuple(
        PerpetualAggressorDifferentialPoint(observed_at=at, value=Decimal(value))
        for at, value in zip(_times(len(values)), values, strict=True)
    )


def test_cvd_anomaly_uses_change_not_cumulative_level() -> None:
    snapshot, characteristics = analyze_cvd_history(
        points=_cvd(["1000", "1001", "1000", "1002", "1001", "1003", "1002", "1003", "1050"]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.status is PerpetualAnalyticsStatus.AVAILABLE
    assert snapshot.current_cvd == Decimal("1050")
    assert snapshot.previous_cvd == Decimal("1003")
    assert snapshot.current_cvd_change == Decimal("47")
    assert snapshot.previous_cvd_change == Decimal("1")
    assert snapshot.baseline_cvd_change is not None
    assert snapshot.cvd_change_anomaly_score is not None
    assert snapshot.cvd_change_anomaly_score > Decimal("2.5")
    assert characteristics == (PerpetualAnalyticsCharacteristic.CVD_POSITIVE_IMPULSE,)


def test_cvd_negative_impulse_is_symmetric() -> None:
    snapshot, characteristics = analyze_cvd_history(
        points=_cvd(["1000", "999", "1000", "998", "999", "997", "998", "997", "950"]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.current_cvd_change == Decimal("-47")
    assert snapshot.cvd_change_anomaly_score is not None
    assert snapshot.cvd_change_anomaly_score < Decimal("-2.5")
    assert characteristics == (PerpetualAnalyticsCharacteristic.CVD_NEGATIVE_IMPULSE,)


def test_zero_mad_cvd_has_no_signed_ratio_fallback() -> None:
    snapshot, characteristics = analyze_cvd_history(
        points=_cvd(["0", "1", "2", "3", "4", "5", "6", "7", "20"]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.baseline_cvd_change_mad == Decimal("0")
    assert snapshot.cvd_change_anomaly_method is ActivityAnomalyMethod.UNAVAILABLE
    assert snapshot.cvd_change_anomaly_score is None
    assert characteristics == ()


def test_aggressor_buy_and_sell_dominance_are_symmetric() -> None:
    positive, positive_chars = analyze_aggressor_differential_history(
        points=_aggressor(["-2", "-1", "0", "1", "2", "1", "1", "25"]),
        as_of=NOW,
        policy=_policy(),
    )
    negative, negative_chars = analyze_aggressor_differential_history(
        points=_aggressor(["2", "1", "0", "-1", "-2", "-1", "-1", "-25"]),
        as_of=NOW,
        policy=_policy(),
    )
    assert positive.anomaly_score is not None and positive.anomaly_score > Decimal("2.5")
    assert negative.anomaly_score is not None and negative.anomaly_score < Decimal("-2.5")
    assert positive_chars == (PerpetualAnalyticsCharacteristic.AGGRESSOR_BUY_DOMINANCE,)
    assert negative_chars == (PerpetualAnalyticsCharacteristic.AGGRESSOR_SELL_DOMINANCE,)
    assert positive.anomaly_score == -negative.anomaly_score


def test_zero_mad_aggressor_has_no_signed_ratio_fallback() -> None:
    snapshot, characteristics = analyze_aggressor_differential_history(
        points=_aggressor(["1"] * 7 + ["25"]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.baseline_value_mad == Decimal("0")
    assert snapshot.anomaly_method is ActivityAnomalyMethod.UNAVAILABLE
    assert snapshot.anomaly_score is None
    assert characteristics == ()




def test_cvd_baseline_excludes_current_and_remains_robust_to_historical_outlier() -> None:
    snapshot, _ = analyze_cvd_history(
        points=_cvd(["0", "1", "3", "4", "6", "106", "107", "127"]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.current_cvd_change == Decimal("20")
    assert snapshot.baseline_cvd_change == Decimal("1.5")
    assert snapshot.baseline_cvd_change_mad == Decimal("0.5")
    assert snapshot.cvd_change_anomaly_score is not None
    assert snapshot.cvd_change_anomaly_score > Decimal("2.5")


def test_aggressor_baseline_mad_and_reproducibility_are_deterministic() -> None:
    points = _aggressor(["-2", "-1", "0", "1", "2", "100", "-25"]),
    first, first_chars = analyze_aggressor_differential_history(
        points=points[0],
        as_of=NOW,
        policy=_policy(),
    )
    second, second_chars = analyze_aggressor_differential_history(
        points=points[0],
        as_of=NOW,
        policy=_policy(),
    )
    assert first.baseline_value == Decimal("0.5")
    assert first.baseline_value_mad == Decimal("1.5")
    assert first.anomaly_score == second.anomaly_score
    assert first_chars == second_chars


def test_aggressor_insufficient_history_is_explicit() -> None:
    snapshot, characteristics = analyze_aggressor_differential_history(
        points=_aggressor(["-1", "0", "1"]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.status is PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY
    assert snapshot.anomaly_score is None
    assert characteristics == ()


def test_future_points_are_excluded_for_cvd_and_aggressor() -> None:
    cvd = (*_cvd(["0", "1", "0", "1", "0", "1", "0", "1", "2"]), PerpetualCvdPoint(
        observed_at=NOW,
        buy_volume=Decimal("999"),
        sell_volume=Decimal("0"),
        cvd=Decimal("999999"),
    ))
    aggressor = (*_aggressor(["0", "1", "0", "1", "0", "1", "0", "1"]), PerpetualAggressorDifferentialPoint(
        observed_at=NOW,
        value=Decimal("999999"),
    ))
    cvd_snapshot, _ = analyze_cvd_history(points=cvd, as_of=NOW, policy=_policy())
    aggressor_snapshot, _ = analyze_aggressor_differential_history(
        points=aggressor, as_of=NOW, policy=_policy()
    )
    assert cvd_snapshot.current_cvd != Decimal("999999")
    assert aggressor_snapshot.current_value != Decimal("999999")


class Provider:
    def __init__(self, *, broken: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.active = 0
        self.max_active = 0
        self.broken = broken or set()

    async def _pause(self, series: str, market) -> None:
        self.calls.append((series, market.symbol))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.005)
            if series in self.broken:
                raise RuntimeError(series)
        finally:
            self.active -= 1

    async def open_interest_history(self, market, *, since, until, interval_seconds):
        await self._pause("open-interest", market)
        return tuple(
            PerpetualAnalyticsPoint(observed_at=at, value=Decimal(value))
            for at, value in zip(_times(8, end=until), ["98", "99", "100", "100", "101", "102", "100", "110"], strict=True)
        )

    async def funding_history(self, market, *, since, until, interval_seconds):
        await self._pause("funding", market)
        return tuple(
            PerpetualFundingPoint(observed_at=at, rate=Decimal("1"), relative_rate=Decimal(value))
            for at, value in zip(_times(8, end=until), ["-0.00002", "-0.00001", "0", "0.00001", "0.00002", "0.00001", "0.00001", "0.0002"], strict=True)
        )

    async def liquidation_volume_history(self, market, *, since, until, interval_seconds):
        await self._pause("liquidation-volume", market)
        return tuple(
            PerpetualAnalyticsPoint(observed_at=at, value=Decimal(value))
            for at, value in zip(_times(8, end=until), ["90", "95", "100", "100", "105", "110", "100", "500"], strict=True)
        )

    async def cvd_history(self, market, *, since, until, interval_seconds):
        await self._pause("cvd", market)
        return tuple(
            PerpetualCvdPoint(observed_at=at, buy_volume=Decimal("100"), sell_volume=Decimal("90"), cvd=Decimal(value))
            for at, value in zip(_times(9, end=until), ["0", "1", "0", "2", "1", "3", "2", "3", "50"], strict=True)
        )

    async def aggressor_differential_history(self, market, *, since, until, interval_seconds):
        await self._pause("aggressor-differential", market)
        return tuple(
            PerpetualAggressorDifferentialPoint(observed_at=at, value=Decimal(value))
            for at, value in zip(_times(8, end=until), ["-2", "-1", "0", "1", "2", "1", "1", "25"], strict=True)
        )


def _market(index: int) -> ExecutableMarket:
    return ExecutableMarket(symbol=f"M{index:02d}/USD", market_type=MarketType.PERPETUAL)


def test_scanner_uses_one_rotation_cache_and_global_concurrency_for_five_series() -> None:
    async def scenario() -> None:
        provider = Provider()
        scanner = PerpetualAnalyticsScanner(
            provider,
            policy=_policy(market_limit_per_refresh=2, fetch_concurrency=2),
        )
        markets = tuple(_market(index) for index in range(4))
        await scanner.scan(markets, as_of=NOW)
        assert len(provider.calls) == 10  # 2 selected markets × 5 series
        assert provider.max_active <= 2
        assert len(scanner.cache) == 2
        coverage = scanner.coverage(markets, as_of=NOW)
        assert coverage.scanned_market_count == 2
        assert coverage.requests_attempted == 10
        assert coverage.requests_failed == 0
        assert [item.series for item in coverage.series_coverage] == [
            "open-interest",
            "funding",
            "liquidation-volume",
            "cvd",
            "aggressor-differential",
        ]

    asyncio.run(scenario())


@pytest.mark.parametrize("broken", ["cvd", "aggressor-differential"])
def test_one_new_series_failure_does_not_hide_other_series(broken: str) -> None:
    async def scenario() -> None:
        scanner = PerpetualAnalyticsScanner(
            Provider(broken={broken}),
            policy=_policy(market_limit_per_refresh=1),
        )
        await scanner.scan((PERP,), as_of=NOW)
        snapshot = scanner.snapshot_for(PERP, as_of=NOW)
        assert snapshot.status is PerpetualAnalyticsStatus.PARTIAL
        assert snapshot.funding is not None
        assert snapshot.liquidation_volume is not None
        assert snapshot.cvd is not None
        assert snapshot.aggressor_differential is not None
        failed_snapshot = (
            snapshot.cvd if broken == "cvd" else snapshot.aggressor_differential
        )
        assert failed_snapshot.status is PerpetualAnalyticsStatus.TECHNICAL_ERROR
        coverage = scanner.coverage((PERP,), as_of=NOW)
        assert coverage.requests_attempted == 5
        assert coverage.requests_failed == 1

    asyncio.run(scenario())


def test_legacy_three_series_provider_remains_compatible() -> None:
    class LegacyProvider(Provider):
        cvd_history = None
        aggressor_differential_history = None

    async def scenario() -> None:
        scanner = PerpetualAnalyticsScanner(LegacyProvider(), policy=_policy(market_limit_per_refresh=1))
        await scanner.scan((PERP,), as_of=NOW)
        snapshot = scanner.snapshot_for(PERP, as_of=NOW)
        assert snapshot.cvd is None
        assert snapshot.aggressor_differential is None
        coverage = scanner.coverage((PERP,), as_of=NOW)
        assert coverage.requests_attempted == 3
        assert coverage.series_coverage[3].unavailable_market_count == 1
        assert coverage.series_coverage[4].unavailable_market_count == 1

    asyncio.run(scenario())


def test_default_policy_keeps_network_limits_and_no_parallel_series_state() -> None:
    policy = PerpetualAnalyticsPolicy()
    scanner = PerpetualAnalyticsScanner(Provider(), policy=policy)
    assert policy.market_limit_per_refresh == 10
    assert policy.fetch_concurrency == 4
    assert hasattr(scanner, "_perpetual_analytics_cursor")
    assert hasattr(scanner, "_cache")
    assert not hasattr(scanner, "_cvd_cursor")
    assert not hasattr(scanner, "_aggressor_cursor")
    assert not hasattr(scanner, "_cvd_cache")
    assert not hasattr(scanner, "_aggressor_cache")


def test_fresh_cache_is_reused_then_expired_cache_is_refreshed() -> None:
    async def scenario() -> None:
        provider = Provider()
        scanner = PerpetualAnalyticsScanner(
            provider,
            policy=_policy(market_limit_per_refresh=1, cache_ttl_seconds=3600),
        )
        await scanner.scan((PERP,), as_of=NOW)
        assert len(provider.calls) == 5
        await scanner.scan((PERP,), as_of=NOW + timedelta(minutes=5))
        assert len(provider.calls) == 5
        fresh_snapshot = scanner.snapshot_for(
            PERP,
            as_of=NOW + timedelta(minutes=5),
        )
        assert fresh_snapshot.cvd is not None
        assert fresh_snapshot.aggressor_differential is not None
        assert fresh_snapshot.cvd.freshness_seconds == Decimal("300.0")
        assert fresh_snapshot.aggressor_differential.freshness_seconds == Decimal("300.0")
        fresh_coverage = scanner.coverage((PERP,), as_of=NOW + timedelta(minutes=5))
        assert fresh_coverage.scanned_market_count == 0
        assert fresh_coverage.requests_attempted == 0
        await scanner.scan((PERP,), as_of=NOW + timedelta(hours=2))
        assert len(provider.calls) == 10
        expired_coverage = scanner.coverage((PERP,), as_of=NOW + timedelta(hours=2))
        assert expired_coverage.scanned_market_count == 1
        assert expired_coverage.requests_attempted == 5

    asyncio.run(scenario())


def test_future_cache_snapshot_is_not_reused() -> None:
    async def scenario() -> None:
        provider = Provider()
        scanner = PerpetualAnalyticsScanner(provider, policy=_policy(market_limit_per_refresh=1))
        await scanner.scan((PERP,), as_of=NOW)
        snapshot = scanner.cache[PERP]
        scanner._cache[PERP] = snapshot.model_copy(  # noqa: SLF001 - invariant regression test
            update={"observed_at": NOW + timedelta(hours=1)}
        )
        visible = scanner.snapshot_for(PERP, as_of=NOW)
        assert visible.status is PerpetualAnalyticsStatus.PARTIAL
        await scanner.scan((PERP,), as_of=NOW)
        assert len(provider.calls) == 10

    asyncio.run(scenario())
