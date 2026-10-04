from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import ActivityAnomalyMethod
from ai_spot_trader.market.perpetual_analytics import (
    PerpetualAnalyticsCharacteristic,
    PerpetualAnalyticsCoverageStatus,
    PerpetualAnalyticsPoint,
    PerpetualAnalyticsPolicy,
    PerpetualAnalyticsScanner,
    PerpetualAnalyticsStatus,
    analyze_open_interest_history,
)

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
PERP = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.PERPETUAL)
SPOT = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)


def _policy(**updates) -> PerpetualAnalyticsPolicy:
    return PerpetualAnalyticsPolicy(
        market_limit_per_refresh=updates.pop("market_limit_per_refresh", 2),
        cache_ttl_seconds=updates.pop("cache_ttl_seconds", 3600),
        history_interval_seconds=updates.pop("history_interval_seconds", 3600),
        history_lookback_seconds=updates.pop("history_lookback_seconds", 72_000),
        fetch_concurrency=updates.pop("fetch_concurrency", 2),
        baseline_periods=updates.pop("baseline_periods", 6),
        data_stale_after_seconds=updates.pop("data_stale_after_seconds", 7200),
        anomaly_score_threshold=updates.pop("anomaly_score_threshold", Decimal("2.5")),
        fallback_expansion_ratio=updates.pop("fallback_expansion_ratio", Decimal("1.10")),
        fallback_contraction_ratio=updates.pop("fallback_contraction_ratio", Decimal("0.90")),
        **updates,
    )


def _points(values: list[str], *, end: datetime = NOW) -> tuple[PerpetualAnalyticsPoint, ...]:
    # Batch 47.2 applies a conservative one-interval finalization lag to Kraken timestamps.
    start = end - timedelta(hours=len(values))
    return tuple(
        PerpetualAnalyticsPoint(
            observed_at=start + timedelta(hours=index),
            value=Decimal(value),
        )
        for index, value in enumerate(values)
    )


def test_spot_is_explicitly_not_applicable() -> None:
    snapshot = analyze_open_interest_history(
        market=SPOT,
        points=(),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.status is PerpetualAnalyticsStatus.NOT_APPLICABLE


def test_robust_baseline_mad_score_and_current_exclusion_are_deterministic() -> None:
    values = ["98", "99", "100", "100", "101", "102", "100", "130"]
    snapshot = analyze_open_interest_history(
        market=PERP,
        points=_points(values),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.current_open_interest == Decimal("130")
    assert snapshot.previous_open_interest == Decimal("100")
    # Six prior points only; current=130 is excluded from the baseline.
    assert snapshot.baseline_open_interest == Decimal("100")
    assert snapshot.baseline_open_interest_mad == Decimal("0.5")
    assert snapshot.open_interest_anomaly_method is ActivityAnomalyMethod.ROBUST_MAD
    assert snapshot.open_interest_anomaly_score is not None
    assert snapshot.open_interest_anomaly_score > Decimal("2.5")
    assert snapshot.open_interest_change == Decimal("30")
    assert snapshot.open_interest_change_ratio == Decimal("0.3")
    assert snapshot.characteristics == (
        PerpetualAnalyticsCharacteristic.OPEN_INTEREST_EXPANSION,
    )


def test_robust_contraction_is_symmetric_with_expansion_threshold() -> None:
    policy = _policy()
    high = analyze_open_interest_history(
        market=PERP,
        points=_points(["98", "99", "100", "100", "101", "102", "100", "130"]),
        as_of=NOW,
        policy=policy,
    )
    low = analyze_open_interest_history(
        market=PERP,
        points=_points(["98", "99", "100", "100", "101", "102", "100", "70"]),
        as_of=NOW,
        policy=policy,
    )
    assert high.open_interest_anomaly_score is not None
    assert low.open_interest_anomaly_score is not None
    assert high.open_interest_anomaly_score == -low.open_interest_anomaly_score
    assert low.characteristics == (
        PerpetualAnalyticsCharacteristic.OPEN_INTEREST_CONTRACTION,
    )


def test_zero_mad_uses_explicit_ratio_fallback() -> None:
    snapshot = analyze_open_interest_history(
        market=PERP,
        points=_points(["100", "100", "100", "100", "100", "100", "100", "120"]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.baseline_open_interest_mad == Decimal("0")
    assert snapshot.open_interest_anomaly_score is None
    assert snapshot.open_interest_anomaly_method is ActivityAnomalyMethod.LEGACY_RATIO_FALLBACK
    assert snapshot.characteristics == (
        PerpetualAnalyticsCharacteristic.OPEN_INTEREST_EXPANSION,
    )


def test_insufficient_history_and_future_bucket_are_not_used() -> None:
    points = _points(["100", "101", "102", "103"])
    future = PerpetualAnalyticsPoint(observed_at=NOW, value=Decimal("999999"))
    snapshot = analyze_open_interest_history(
        market=PERP,
        points=(*points, future),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.status is PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY
    assert snapshot.current_open_interest == Decimal("103")
    assert snapshot.current_open_interest != Decimal("999999")


def test_historical_outlier_does_not_move_the_median_baseline_materially() -> None:
    snapshot = analyze_open_interest_history(
        market=PERP,
        points=_points(["99", "100", "100", "101", "100", "10000", "100", "101"]),
        as_of=NOW,
        policy=_policy(),
    )
    assert snapshot.baseline_open_interest == Decimal("100")


class Provider:
    def __init__(self, *, broken: set[str] | None = None, delay: float = 0.0) -> None:
        self.broken = broken or set()
        self.delay = delay
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0

    async def open_interest_history(self, market, *, since, until, interval_seconds):
        assert market.market_type is MarketType.PERPETUAL
        assert since < until
        assert until == NOW or until > NOW - timedelta(days=30)
        assert interval_seconds == 3600
        self.calls.append(market.symbol)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if market.symbol in self.broken:
                raise RuntimeError("analytics failed")
            return _points(["98", "99", "100", "100", "101", "102", "100", "110"], end=until)
        finally:
            self.active -= 1


def _market(index: int) -> ExecutableMarket:
    return ExecutableMarket(symbol=f"M{index:02d}/USD", market_type=MarketType.PERPETUAL)


def test_rotation_is_deterministic_and_respects_market_limit() -> None:
    scanner = PerpetualAnalyticsScanner(Provider(), policy=_policy(market_limit_per_refresh=2))
    markets = tuple(_market(index) for index in range(5))
    assert [m.symbol for m in scanner.next_batch(markets)] == ["M00/USD", "M01/USD"]
    assert [m.symbol for m in scanner.next_batch(markets)] == ["M02/USD", "M03/USD"]
    assert [m.symbol for m in scanner.next_batch(markets)] == ["M04/USD", "M00/USD"]


def test_scan_enforces_concurrency_and_reuses_fresh_cache() -> None:
    async def scenario() -> None:
        provider = Provider(delay=0.01)
        scanner = PerpetualAnalyticsScanner(
            provider,
            policy=_policy(market_limit_per_refresh=4, fetch_concurrency=2),
        )
        markets = tuple(_market(index) for index in range(4))
        await scanner.scan(markets, as_of=NOW)
        assert len(provider.calls) == 4
        assert provider.max_active <= 2
        first_coverage = scanner.coverage(markets, as_of=NOW)
        assert first_coverage.requests_attempted == 4
        assert first_coverage.requests_failed == 0
        await scanner.scan(markets, as_of=NOW + timedelta(minutes=5))
        assert len(provider.calls) == 4
        second = scanner.coverage(markets, as_of=NOW + timedelta(minutes=5))
        assert second.requests_attempted == 0
        assert second.scanned_market_count == 0

    asyncio.run(scenario())


def test_expired_cache_refreshes_and_future_cache_is_never_reused() -> None:
    async def scenario() -> None:
        provider = Provider()
        scanner = PerpetualAnalyticsScanner(
            provider,
            policy=_policy(market_limit_per_refresh=1, cache_ttl_seconds=3600),
        )
        await scanner.scan((PERP,), as_of=NOW)
        assert len(provider.calls) == 1
        await scanner.scan((PERP,), as_of=NOW + timedelta(hours=2))
        assert len(provider.calls) == 2
        # A scan at an earlier as_of must not treat the newer cache entry as reusable.
        await scanner.scan((PERP,), as_of=NOW + timedelta(hours=1))
        assert len(provider.calls) == 3

    asyncio.run(scenario())


def test_one_market_failure_is_fail_soft_for_other_markets_and_counted() -> None:
    async def scenario() -> None:
        markets = (_market(0), _market(1), _market(2))
        provider = Provider(broken={"M01/USD"})
        scanner = PerpetualAnalyticsScanner(
            provider,
            policy=_policy(market_limit_per_refresh=3),
        )
        await scanner.scan(markets, as_of=NOW)
        coverage = scanner.coverage(markets, as_of=NOW)
        assert coverage.requests_attempted == 3
        assert coverage.requests_failed == 1
        assert (
            scanner.snapshot_for(markets[0], as_of=NOW).status
            is PerpetualAnalyticsStatus.AVAILABLE
        )
        assert (
            scanner.snapshot_for(markets[1], as_of=NOW).status
            is PerpetualAnalyticsStatus.TECHNICAL_ERROR
        )
        assert (
            scanner.snapshot_for(markets[2], as_of=NOW).status
            is PerpetualAnalyticsStatus.AVAILABLE
        )

    asyncio.run(scenario())


def test_coverage_distinguishes_small_large_and_configuration_too_slow_populations() -> None:
    async def scenario() -> None:
        small = tuple(_market(index) for index in range(2))
        scanner = PerpetualAnalyticsScanner(
            Provider(),
            policy=_policy(market_limit_per_refresh=2, cache_ttl_seconds=3600),
            refresh_seconds=300,
        )
        await scanner.scan(small, as_of=NOW)
        covered = scanner.coverage(small, as_of=NOW)
        assert covered.status is PerpetualAnalyticsCoverageStatus.COVERED
        assert covered.coverage_ratio == 1

        large = tuple(_market(index) for index in range(20))
        too_slow = PerpetualAnalyticsScanner(
            Provider(),
            policy=_policy(market_limit_per_refresh=2, cache_ttl_seconds=600),
            refresh_seconds=300,
        )
        rotating = too_slow.coverage(large, as_of=NOW)
        assert rotating.estimated_refreshes_per_full_rotation == 10
        assert rotating.estimated_full_rotation_seconds == 3000
        assert rotating.rotation_within_cache_ttl is False
        assert rotating.status is PerpetualAnalyticsCoverageStatus.CONFIGURATION_TOO_SLOW

    asyncio.run(scenario())


def test_identical_history_is_reproducible() -> None:
    points = _points(["98", "99", "100", "100", "101", "102", "100", "115"])
    first = analyze_open_interest_history(
        market=PERP,
        points=points,
        as_of=NOW,
        policy=_policy(),
    )
    second = analyze_open_interest_history(
        market=PERP,
        points=points,
        as_of=NOW,
        policy=_policy(),
    )
    assert first == second


def test_sufficient_but_old_history_is_stale() -> None:
    snapshot = analyze_open_interest_history(
        market=PERP,
        points=_points(
            ["98", "99", "100", "100", "101", "102", "100", "110"],
            end=NOW - timedelta(hours=4),
        ),
        as_of=NOW,
        policy=_policy(data_stale_after_seconds=3600),
    )
    assert snapshot.status is PerpetualAnalyticsStatus.STALE
    assert snapshot.freshness_seconds is not None
    assert snapshot.freshness_seconds > Decimal("3600")


def test_coverage_reports_ttl_expiration_without_auto_tuning() -> None:
    async def scenario() -> None:
        markets = (_market(0), _market(1))
        scanner = PerpetualAnalyticsScanner(
            Provider(),
            policy=_policy(market_limit_per_refresh=2, cache_ttl_seconds=3600),
            refresh_seconds=300,
        )
        await scanner.scan(markets, as_of=NOW)
        expired = scanner.coverage(markets, as_of=NOW + timedelta(hours=2))
        assert expired.expired_market_count == 2
        assert expired.fresh_market_count == 0
        assert expired.status is PerpetualAnalyticsCoverageStatus.TTL_EXPIRED
        assert expired.effective_market_limit == 2

    asyncio.run(scenario())
