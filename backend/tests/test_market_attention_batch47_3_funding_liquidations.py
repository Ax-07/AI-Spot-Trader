from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import ActivityAnomalyMethod
from ai_spot_trader.market.perpetual_analytics import (
    PerpetualAnalyticsCharacteristic,
    PerpetualAnalyticsPoint,
    PerpetualAnalyticsPolicy,
    PerpetualAnalyticsScanner,
    PerpetualAnalyticsStatus,
    PerpetualFundingPoint,
    analyze_funding_history,
    analyze_liquidation_volume_history,
)

NOW = datetime(2026, 10, 4, 18, 0, tzinfo=UTC)
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


def _funding(values: list[str]) -> tuple[PerpetualFundingPoint, ...]:
    return tuple(
        PerpetualFundingPoint(
            observed_at=at,
            rate=Decimal(relative) * Decimal("50000"),
            relative_rate=Decimal(relative),
        )
        for at, relative in zip(_times(len(values)), values, strict=True)
    )


def _liquidations(values: list[str]) -> tuple[PerpetualAnalyticsPoint, ...]:
    return tuple(
        PerpetualAnalyticsPoint(observed_at=at, value=Decimal(value))
        for at, value in zip(_times(len(values)), values, strict=True)
    )


def test_funding_statistics_use_relative_rate_and_keep_raw_rate_separate() -> None:
    snapshot, characteristics = analyze_funding_history(
        points=_funding([
            "-0.00002",
            "-0.00001",
            "0",
            "0.00001",
            "0.00002",
            "0.00001",
            "0.00001",
            "0.00020",
        ]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.status is PerpetualAnalyticsStatus.AVAILABLE
    assert snapshot.current_relative_rate == Decimal("0.00020")
    assert snapshot.current_rate == Decimal("10.00000")
    assert snapshot.baseline_relative_rate is not None
    assert snapshot.relative_rate_anomaly_method is ActivityAnomalyMethod.ROBUST_MAD
    assert snapshot.relative_rate_anomaly_score is not None
    assert snapshot.relative_rate_anomaly_score > Decimal("2.5")
    assert characteristics == (PerpetualAnalyticsCharacteristic.FUNDING_POSITIVE_EXTREME,)


def test_negative_funding_extreme_is_directionally_symmetric() -> None:
    snapshot, characteristics = analyze_funding_history(
        points=_funding([
            "-0.00002",
            "-0.00001",
            "0",
            "0.00001",
            "0.00002",
            "0.00001",
            "0.00001",
            "-0.00020",
        ]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.current_relative_rate == Decimal("-0.00020")
    assert snapshot.relative_rate_anomaly_score is not None
    assert snapshot.relative_rate_anomaly_score < Decimal("-2.5")
    assert characteristics == (PerpetualAnalyticsCharacteristic.FUNDING_NEGATIVE_EXTREME,)


def test_zero_mad_funding_does_not_invent_ratio_semantics_for_signed_rates() -> None:
    snapshot, characteristics = analyze_funding_history(
        points=_funding(["0.00001"] * 7 + ["0.00020"]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.baseline_relative_rate_mad == Decimal("0")
    assert snapshot.relative_rate_anomaly_method is ActivityAnomalyMethod.UNAVAILABLE
    assert snapshot.relative_rate_anomaly_score is None
    assert characteristics == ()


def test_liquidation_volume_spike_is_aggregate_and_non_directional() -> None:
    snapshot, characteristics = analyze_liquidation_volume_history(
        points=_liquidations(["90", "95", "100", "100", "105", "110", "100", "500"]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.status is PerpetualAnalyticsStatus.AVAILABLE
    assert snapshot.current_volume == Decimal("500")
    assert snapshot.previous_volume == Decimal("100")
    assert snapshot.baseline_volume == Decimal("100")
    assert snapshot.volume_anomaly_score is not None
    assert characteristics == (PerpetualAnalyticsCharacteristic.LIQUIDATION_VOLUME_SPIKE,)


def test_future_buckets_are_excluded_for_funding_and_liquidations() -> None:
    funding = (*_funding(["0.00001"] * 8), PerpetualFundingPoint(
        observed_at=NOW,
        rate=Decimal("999"),
        relative_rate=Decimal("999"),
    ))
    liquidation = (*_liquidations(["100"] * 8), PerpetualAnalyticsPoint(
        observed_at=NOW,
        value=Decimal("999999"),
    ))
    f_snapshot, _ = analyze_funding_history(points=funding, as_of=NOW, policy=_policy())
    l_snapshot, _ = analyze_liquidation_volume_history(
        points=liquidation, as_of=NOW, policy=_policy()
    )
    assert f_snapshot.current_relative_rate != Decimal("999")
    assert l_snapshot.current_volume != Decimal("999999")


class Provider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.active = 0
        self.max_active = 0

    async def _pause(self, series: str, market) -> None:
        self.calls.append((series, market.symbol))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.005)
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


def _market(index: int) -> ExecutableMarket:
    return ExecutableMarket(symbol=f"M{index:02d}/USD", market_type=MarketType.PERPETUAL)


def test_scanner_reuses_one_rotation_and_bounds_total_http_concurrency() -> None:
    async def scenario() -> None:
        provider = Provider()
        scanner = PerpetualAnalyticsScanner(
            provider,
            policy=_policy(market_limit_per_refresh=2, fetch_concurrency=2),
        )
        markets = tuple(_market(index) for index in range(4))
        await scanner.scan(markets, as_of=NOW)
        assert len(provider.calls) == 6  # 2 selected markets × 3 series
        assert provider.max_active <= 2
        coverage = scanner.coverage(markets, as_of=NOW)
        assert coverage.scanned_market_count == 2
        assert coverage.requests_attempted == 6
        assert coverage.requests_failed == 0
        assert [item.series for item in coverage.series_coverage] == [
            "open-interest",
            "funding",
            "liquidation-volume",
        ]
        assert coverage.series_coverage[0].available_market_count == 2
        assert coverage.series_coverage[1].available_market_count == 2
        assert coverage.series_coverage[2].available_market_count == 2
        assert coverage.series_coverage[0].unavailable_market_count == 2

    asyncio.run(scenario())


def test_scanner_combines_descriptive_characteristics_without_ranking_authority() -> None:
    async def scenario() -> None:
        scanner = PerpetualAnalyticsScanner(Provider(), policy=_policy(market_limit_per_refresh=1))
        await scanner.scan((PERP,), as_of=NOW)
        snapshot = scanner.snapshot_for(PERP, as_of=NOW)
        assert snapshot.status is PerpetualAnalyticsStatus.AVAILABLE
        assert PerpetualAnalyticsCharacteristic.OPEN_INTEREST_EXPANSION in snapshot.characteristics
        assert PerpetualAnalyticsCharacteristic.FUNDING_POSITIVE_EXTREME in snapshot.characteristics
        assert PerpetualAnalyticsCharacteristic.LIQUIDATION_VOLUME_SPIKE in snapshot.characteristics
        assert snapshot.funding is not None
        assert snapshot.liquidation_volume is not None

    asyncio.run(scenario())
