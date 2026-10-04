from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from math import ceil
from statistics import median
from typing import Protocol

from pydantic import Field, model_validator

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.attention import (
    ActivityAnomalyMethod,
    AttentionModel,
    _median_absolute_deviation,
    _robust_anomaly,
)


class PerpetualAnalyticsStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    STALE = "STALE"
    TECHNICAL_ERROR = "TECHNICAL_ERROR"


class PerpetualAnalyticsCharacteristic(StrEnum):
    OPEN_INTEREST_EXPANSION = "OPEN_INTEREST_EXPANSION"
    OPEN_INTEREST_CONTRACTION = "OPEN_INTEREST_CONTRACTION"
    FUNDING_POSITIVE_EXTREME = "FUNDING_POSITIVE_EXTREME"
    FUNDING_NEGATIVE_EXTREME = "FUNDING_NEGATIVE_EXTREME"
    LIQUIDATION_VOLUME_SPIKE = "LIQUIDATION_VOLUME_SPIKE"


class PerpetualAnalyticsCoverageStatus(StrEnum):
    NO_MARKETS = "NO_MARKETS"
    COVERED = "COVERED"
    ROTATING = "ROTATING"
    TTL_EXPIRED = "TTL_EXPIRED"
    CONFIGURATION_TOO_SLOW = "CONFIGURATION_TOO_SLOW"


class PerpetualAnalyticsPoint(AttentionModel):
    """Provider-neutral non-negative historical analytics point (OI or liquidation volume)."""

    observed_at: datetime
    value: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_point(self) -> "PerpetualAnalyticsPoint":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("perpetual analytics point observed_at must be timezone-aware")
        return self


class PerpetualFundingPoint(AttentionModel):
    """Provider-neutral funding point keeping absolute/raw and relative rates separate."""

    observed_at: datetime
    rate: Decimal
    relative_rate: Decimal

    @model_validator(mode="after")
    def validate_point(self) -> "PerpetualFundingPoint":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("perpetual funding point observed_at must be timezone-aware")
        return self


class PerpetualAnalyticsPolicy(AttentionModel):
    """Bounded historical Futures analytics policy shared by OI, funding and liquidations."""

    market_limit_per_refresh: int = Field(default=10, ge=1, le=100)
    cache_ttl_seconds: float = Field(default=3600.0, ge=60.0, le=86_400.0)
    history_interval_seconds: int = Field(default=3600)
    history_lookback_seconds: int = Field(default=172_800, ge=3600, le=2_592_000)
    fetch_concurrency: int = Field(default=4, ge=1, le=16)
    baseline_periods: int = Field(default=12, ge=3, le=48)
    data_stale_after_seconds: float = Field(default=7200.0, ge=60.0, le=86_400.0)
    anomaly_score_threshold: Decimal = Field(default=Decimal("2.5"), gt=0)
    fallback_expansion_ratio: Decimal = Field(default=Decimal("1.10"), gt=1)
    fallback_contraction_ratio: Decimal = Field(default=Decimal("0.90"), gt=0, lt=1)
    funding_anomaly_score_threshold: Decimal = Field(default=Decimal("2.5"), gt=0)
    liquidation_anomaly_score_threshold: Decimal = Field(default=Decimal("3.0"), gt=0)
    liquidation_fallback_spike_ratio: Decimal = Field(default=Decimal("2.0"), gt=1)

    @model_validator(mode="after")
    def validate_policy(self) -> "PerpetualAnalyticsPolicy":
        supported = {60, 300, 900, 1800, 3600, 14400, 43200, 86400, 604800}
        if self.history_interval_seconds not in supported:
            raise ValueError("unsupported Kraken Futures analytics interval")
        minimum_lookback = self.history_interval_seconds * (self.baseline_periods + 2)
        if self.history_lookback_seconds < minimum_lookback:
            raise ValueError("history_lookback_seconds is too short for the configured baseline")
        return self


class PerpetualFundingAnalyticsSnapshot(AttentionModel):
    status: PerpetualAnalyticsStatus
    observed_at: datetime
    current_observed_at: datetime | None = None
    freshness_seconds: Decimal | None = Field(default=None, ge=0)
    current_rate: Decimal | None = None
    previous_rate: Decimal | None = None
    baseline_rate: Decimal | None = None
    current_relative_rate: Decimal | None = None
    previous_relative_rate: Decimal | None = None
    baseline_relative_rate: Decimal | None = None
    baseline_relative_rate_mad: Decimal | None = Field(default=None, ge=0)
    relative_rate_change: Decimal | None = None
    relative_rate_anomaly_score: Decimal | None = None
    relative_rate_anomaly_method: ActivityAnomalyMethod = ActivityAnomalyMethod.UNAVAILABLE
    baseline_period_count: int = Field(default=0, ge=0)
    history_point_count: int = Field(default=0, ge=0)
    error_type: str | None = None


class PerpetualLiquidationVolumeAnalyticsSnapshot(AttentionModel):
    status: PerpetualAnalyticsStatus
    observed_at: datetime
    current_observed_at: datetime | None = None
    freshness_seconds: Decimal | None = Field(default=None, ge=0)
    current_volume: Decimal | None = Field(default=None, ge=0)
    previous_volume: Decimal | None = Field(default=None, ge=0)
    baseline_volume: Decimal | None = Field(default=None, ge=0)
    baseline_volume_mad: Decimal | None = Field(default=None, ge=0)
    volume_change: Decimal | None = None
    volume_change_ratio: Decimal | None = None
    volume_anomaly_score: Decimal | None = None
    volume_anomaly_method: ActivityAnomalyMethod = ActivityAnomalyMethod.UNAVAILABLE
    baseline_period_count: int = Field(default=0, ge=0)
    history_point_count: int = Field(default=0, ge=0)
    error_type: str | None = None


class PerpetualAnalyticsSnapshot(AttentionModel):
    market: ExecutableMarket
    status: PerpetualAnalyticsStatus
    provider: str = "KRAKEN_FUTURES"
    observed_at: datetime
    open_interest_status: PerpetualAnalyticsStatus = PerpetualAnalyticsStatus.PARTIAL
    current_open_interest_observed_at: datetime | None = None
    freshness_seconds: Decimal | None = Field(default=None, ge=0)
    current_open_interest: Decimal | None = Field(default=None, ge=0)
    previous_open_interest: Decimal | None = Field(default=None, ge=0)
    baseline_open_interest: Decimal | None = Field(default=None, ge=0)
    baseline_open_interest_mad: Decimal | None = Field(default=None, ge=0)
    open_interest_change: Decimal | None = None
    open_interest_change_ratio: Decimal | None = None
    open_interest_anomaly_score: Decimal | None = None
    open_interest_anomaly_method: ActivityAnomalyMethod = ActivityAnomalyMethod.UNAVAILABLE
    baseline_period_count: int = Field(default=0, ge=0)
    history_point_count: int = Field(default=0, ge=0)
    funding: PerpetualFundingAnalyticsSnapshot | None = None
    liquidation_volume: PerpetualLiquidationVolumeAnalyticsSnapshot | None = None
    characteristics: tuple[PerpetualAnalyticsCharacteristic, ...] = ()
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_snapshot(self) -> "PerpetualAnalyticsSnapshot":
        for label, value in (
            ("perpetual analytics observed_at", self.observed_at),
            ("current open interest observed_at", self.current_open_interest_observed_at),
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{label} must be timezone-aware")
        if self.market.market_type is MarketType.SPOT:
            if self.status is not PerpetualAnalyticsStatus.NOT_APPLICABLE:
                raise ValueError("SPOT perpetual analytics must be NOT_APPLICABLE")
        return self


class PerpetualAnalyticsSeriesCoverageDiagnostics(AttentionModel):
    series: str
    available_market_count: int = Field(default=0, ge=0)
    insufficient_history_market_count: int = Field(default=0, ge=0)
    stale_market_count: int = Field(default=0, ge=0)
    technical_error_market_count: int = Field(default=0, ge=0)
    unavailable_market_count: int = Field(default=0, ge=0)

    @property
    def covered_market_count(self) -> int:
        return (
            self.available_market_count
            + self.insufficient_history_market_count
            + self.stale_market_count
            + self.technical_error_market_count
        )


class PerpetualAnalyticsCoverageDiagnostics(AttentionModel):
    eligible_market_count: int = Field(default=0, ge=0)
    fresh_market_count: int = Field(default=0, ge=0)
    expired_market_count: int = Field(default=0, ge=0)
    unseen_market_count: int = Field(default=0, ge=0)
    scanned_market_count: int = Field(default=0, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    effective_market_limit: int = Field(default=0, ge=0)
    estimated_refreshes_per_full_rotation: int = Field(default=0, ge=0)
    estimated_full_rotation_seconds: float = Field(default=0.0, ge=0)
    cache_ttl_seconds: float = Field(default=0.0, ge=0)
    oldest_snapshot_age_seconds: float | None = Field(default=None, ge=0)
    rotation_within_cache_ttl: bool = True
    requests_attempted: int = Field(default=0, ge=0)
    requests_failed: int = Field(default=0, ge=0)
    series_coverage: tuple[PerpetualAnalyticsSeriesCoverageDiagnostics, ...] = ()
    status: PerpetualAnalyticsCoverageStatus = PerpetualAnalyticsCoverageStatus.NO_MARKETS

    @model_validator(mode="after")
    def validate_partition(self) -> "PerpetualAnalyticsCoverageDiagnostics":
        if (
            self.fresh_market_count
            + self.expired_market_count
            + self.unseen_market_count
            != self.eligible_market_count
        ):
            raise ValueError("analytics coverage counts must partition eligible markets")
        if self.requests_failed > self.requests_attempted:
            raise ValueError("analytics failed requests cannot exceed attempted requests")
        for item in self.series_coverage:
            if item.covered_market_count + item.unavailable_market_count != self.eligible_market_count:
                raise ValueError("series coverage counts must partition eligible markets")
        return self


class PerpetualAnalyticsProvider(Protocol):
    async def open_interest_history(
        self,
        market: ExecutableMarket,
        *,
        since: datetime,
        until: datetime,
        interval_seconds: int,
    ) -> tuple[PerpetualAnalyticsPoint, ...]: ...

    async def funding_history(
        self,
        market: ExecutableMarket,
        *,
        since: datetime,
        until: datetime,
        interval_seconds: int,
    ) -> tuple[PerpetualFundingPoint, ...]: ...

    async def liquidation_volume_history(
        self,
        market: ExecutableMarket,
        *,
        since: datetime,
        until: datetime,
        interval_seconds: int,
    ) -> tuple[PerpetualAnalyticsPoint, ...]: ...


def analyze_open_interest_history(
    *,
    market: ExecutableMarket,
    points: tuple[PerpetualAnalyticsPoint, ...],
    as_of: datetime,
    policy: PerpetualAnalyticsPolicy,
) -> PerpetualAnalyticsSnapshot:
    """Build one causal Open Interest snapshot using the Batch 46 robust primitives."""

    if market.market_type is not MarketType.PERPETUAL:
        return PerpetualAnalyticsSnapshot(
            market=market,
            status=PerpetualAnalyticsStatus.NOT_APPLICABLE,
            open_interest_status=PerpetualAnalyticsStatus.NOT_APPLICABLE,
            observed_at=_utc(as_of),
        )
    as_of = _utc(as_of)
    _validate_chronology(points)
    finalized = _finalized(points, as_of=as_of, policy=policy)
    current = finalized[-1] if finalized else None
    if current is None:
        return PerpetualAnalyticsSnapshot(
            market=market,
            status=PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY,
            open_interest_status=PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY,
            observed_at=as_of,
            history_point_count=0,
        )

    current_at, freshness, is_stale = _freshness(current.observed_at, as_of=as_of, policy=policy)
    previous = finalized[-2] if len(finalized) >= 2 else None
    historical = finalized[:-1]
    baseline_points = historical[-policy.baseline_periods :]
    if len(baseline_points) < policy.baseline_periods:
        status = PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY
        return PerpetualAnalyticsSnapshot(
            market=market,
            status=status,
            open_interest_status=status,
            observed_at=as_of,
            current_open_interest_observed_at=current_at,
            freshness_seconds=freshness,
            current_open_interest=current.value,
            previous_open_interest=(previous.value if previous is not None else None),
            open_interest_change=(current.value - previous.value if previous is not None else None),
            open_interest_change_ratio=(
                _change_ratio(current.value, previous.value) if previous is not None else None
            ),
            baseline_period_count=len(baseline_points),
            history_point_count=len(finalized),
        )

    baseline_values = tuple(point.value for point in baseline_points)
    baseline = Decimal(median(baseline_values))
    mad = _median_absolute_deviation(baseline_values, center=baseline)
    fallback_ratio = _safe_ratio(current.value, baseline)
    score, method = _robust_anomaly(
        current.value,
        baseline=baseline,
        mad=mad,
        fallback_ratio=fallback_ratio,
    )
    characteristics: list[PerpetualAnalyticsCharacteristic] = []
    if method is ActivityAnomalyMethod.ROBUST_MAD and score is not None:
        if score >= policy.anomaly_score_threshold:
            characteristics.append(PerpetualAnalyticsCharacteristic.OPEN_INTEREST_EXPANSION)
        elif score <= -policy.anomaly_score_threshold:
            characteristics.append(PerpetualAnalyticsCharacteristic.OPEN_INTEREST_CONTRACTION)
    elif method is ActivityAnomalyMethod.LEGACY_RATIO_FALLBACK and fallback_ratio is not None:
        if fallback_ratio >= policy.fallback_expansion_ratio:
            characteristics.append(PerpetualAnalyticsCharacteristic.OPEN_INTEREST_EXPANSION)
        elif fallback_ratio <= policy.fallback_contraction_ratio:
            characteristics.append(PerpetualAnalyticsCharacteristic.OPEN_INTEREST_CONTRACTION)

    status = PerpetualAnalyticsStatus.STALE if is_stale else PerpetualAnalyticsStatus.AVAILABLE
    return PerpetualAnalyticsSnapshot(
        market=market,
        status=status,
        open_interest_status=status,
        observed_at=as_of,
        current_open_interest_observed_at=current_at,
        freshness_seconds=freshness,
        current_open_interest=current.value,
        previous_open_interest=(previous.value if previous is not None else None),
        baseline_open_interest=baseline,
        baseline_open_interest_mad=mad,
        open_interest_change=(current.value - previous.value if previous is not None else None),
        open_interest_change_ratio=(
            _change_ratio(current.value, previous.value) if previous is not None else None
        ),
        open_interest_anomaly_score=score,
        open_interest_anomaly_method=method,
        baseline_period_count=len(baseline_points),
        history_point_count=len(finalized),
        characteristics=tuple(characteristics),
    )


def analyze_funding_history(
    *,
    points: tuple[PerpetualFundingPoint, ...],
    as_of: datetime,
    policy: PerpetualAnalyticsPolicy,
) -> tuple[PerpetualFundingAnalyticsSnapshot, tuple[PerpetualAnalyticsCharacteristic, ...]]:
    """Analyze signed historical funding, using relativeRate for normalized anomaly statistics."""

    as_of = _utc(as_of)
    _validate_chronology(points)
    finalized = _finalized(points, as_of=as_of, policy=policy)
    current = finalized[-1] if finalized else None
    if current is None:
        return (
            PerpetualFundingAnalyticsSnapshot(
                status=PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY,
                observed_at=as_of,
            ),
            (),
        )
    current_at, freshness, is_stale = _freshness(current.observed_at, as_of=as_of, policy=policy)
    previous = finalized[-2] if len(finalized) >= 2 else None
    baseline_points = finalized[:-1][-policy.baseline_periods :]
    if len(baseline_points) < policy.baseline_periods:
        return (
            PerpetualFundingAnalyticsSnapshot(
                status=PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY,
                observed_at=as_of,
                current_observed_at=current_at,
                freshness_seconds=freshness,
                current_rate=current.rate,
                previous_rate=(previous.rate if previous is not None else None),
                current_relative_rate=current.relative_rate,
                previous_relative_rate=(previous.relative_rate if previous is not None else None),
                relative_rate_change=(
                    current.relative_rate - previous.relative_rate if previous is not None else None
                ),
                baseline_period_count=len(baseline_points),
                history_point_count=len(finalized),
            ),
            (),
        )

    raw_values = tuple(point.rate for point in baseline_points)
    relative_values = tuple(point.relative_rate for point in baseline_points)
    baseline_rate = Decimal(median(raw_values))
    baseline_relative = Decimal(median(relative_values))
    mad = _median_absolute_deviation(relative_values, center=baseline_relative)
    score, method = _robust_anomaly(
        current.relative_rate,
        baseline=baseline_relative,
        mad=mad,
        fallback_ratio=None,
    )
    characteristics: list[PerpetualAnalyticsCharacteristic] = []
    if score is not None and method is ActivityAnomalyMethod.ROBUST_MAD:
        if current.relative_rate > 0 and score >= policy.funding_anomaly_score_threshold:
            characteristics.append(PerpetualAnalyticsCharacteristic.FUNDING_POSITIVE_EXTREME)
        elif current.relative_rate < 0 and score <= -policy.funding_anomaly_score_threshold:
            characteristics.append(PerpetualAnalyticsCharacteristic.FUNDING_NEGATIVE_EXTREME)

    status = PerpetualAnalyticsStatus.STALE if is_stale else PerpetualAnalyticsStatus.AVAILABLE
    return (
        PerpetualFundingAnalyticsSnapshot(
            status=status,
            observed_at=as_of,
            current_observed_at=current_at,
            freshness_seconds=freshness,
            current_rate=current.rate,
            previous_rate=(previous.rate if previous is not None else None),
            baseline_rate=baseline_rate,
            current_relative_rate=current.relative_rate,
            previous_relative_rate=(previous.relative_rate if previous is not None else None),
            baseline_relative_rate=baseline_relative,
            baseline_relative_rate_mad=mad,
            relative_rate_change=(
                current.relative_rate - previous.relative_rate if previous is not None else None
            ),
            relative_rate_anomaly_score=score,
            relative_rate_anomaly_method=method,
            baseline_period_count=len(baseline_points),
            history_point_count=len(finalized),
        ),
        tuple(characteristics),
    )


def analyze_liquidation_volume_history(
    *,
    points: tuple[PerpetualAnalyticsPoint, ...],
    as_of: datetime,
    policy: PerpetualAnalyticsPolicy,
) -> tuple[
    PerpetualLiquidationVolumeAnalyticsSnapshot,
    tuple[PerpetualAnalyticsCharacteristic, ...],
]:
    """Analyze aggregate liquidation volume as a non-directional market-stress series."""

    as_of = _utc(as_of)
    _validate_chronology(points)
    finalized = _finalized(points, as_of=as_of, policy=policy)
    current = finalized[-1] if finalized else None
    if current is None:
        return (
            PerpetualLiquidationVolumeAnalyticsSnapshot(
                status=PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY,
                observed_at=as_of,
            ),
            (),
        )
    current_at, freshness, is_stale = _freshness(current.observed_at, as_of=as_of, policy=policy)
    previous = finalized[-2] if len(finalized) >= 2 else None
    baseline_points = finalized[:-1][-policy.baseline_periods :]
    if len(baseline_points) < policy.baseline_periods:
        return (
            PerpetualLiquidationVolumeAnalyticsSnapshot(
                status=PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY,
                observed_at=as_of,
                current_observed_at=current_at,
                freshness_seconds=freshness,
                current_volume=current.value,
                previous_volume=(previous.value if previous is not None else None),
                volume_change=(current.value - previous.value if previous is not None else None),
                volume_change_ratio=(
                    _change_ratio(current.value, previous.value) if previous is not None else None
                ),
                baseline_period_count=len(baseline_points),
                history_point_count=len(finalized),
            ),
            (),
        )

    values = tuple(point.value for point in baseline_points)
    baseline = Decimal(median(values))
    mad = _median_absolute_deviation(values, center=baseline)
    fallback_ratio = _safe_ratio(current.value, baseline)
    score, method = _robust_anomaly(
        current.value,
        baseline=baseline,
        mad=mad,
        fallback_ratio=fallback_ratio,
    )
    characteristics: list[PerpetualAnalyticsCharacteristic] = []
    if (
        method is ActivityAnomalyMethod.ROBUST_MAD
        and score is not None
        and score >= policy.liquidation_anomaly_score_threshold
    ):
        characteristics.append(PerpetualAnalyticsCharacteristic.LIQUIDATION_VOLUME_SPIKE)
    elif (
        method is ActivityAnomalyMethod.LEGACY_RATIO_FALLBACK
        and fallback_ratio is not None
        and fallback_ratio >= policy.liquidation_fallback_spike_ratio
    ):
        characteristics.append(PerpetualAnalyticsCharacteristic.LIQUIDATION_VOLUME_SPIKE)

    status = PerpetualAnalyticsStatus.STALE if is_stale else PerpetualAnalyticsStatus.AVAILABLE
    return (
        PerpetualLiquidationVolumeAnalyticsSnapshot(
            status=status,
            observed_at=as_of,
            current_observed_at=current_at,
            freshness_seconds=freshness,
            current_volume=current.value,
            previous_volume=(previous.value if previous is not None else None),
            baseline_volume=baseline,
            baseline_volume_mad=mad,
            volume_change=(current.value - previous.value if previous is not None else None),
            volume_change_ratio=(
                _change_ratio(current.value, previous.value) if previous is not None else None
            ),
            volume_anomaly_score=score,
            volume_anomaly_method=method,
            baseline_period_count=len(baseline_points),
            history_point_count=len(finalized),
        ),
        tuple(characteristics),
    )


class PerpetualAnalyticsScanner:
    """Single deterministic rotation/cache shared by all historical Futures analytics series."""

    def __init__(
        self,
        provider: PerpetualAnalyticsProvider,
        *,
        policy: PerpetualAnalyticsPolicy | None = None,
        refresh_seconds: float = 300.0,
    ) -> None:
        if refresh_seconds <= 0:
            raise ValueError("analytics refresh_seconds must be positive")
        self._provider = provider
        self._policy = policy or PerpetualAnalyticsPolicy()
        self._refresh_seconds = float(refresh_seconds)
        self._cache: dict[ExecutableMarket, PerpetualAnalyticsSnapshot] = {}
        self._perpetual_analytics_cursor = 0
        self._latest_requests_attempted = 0
        self._latest_requests_failed = 0
        self._latest_scanned_market_count = 0

    @property
    def policy(self) -> PerpetualAnalyticsPolicy:
        return self._policy

    @property
    def cache(self) -> dict[ExecutableMarket, PerpetualAnalyticsSnapshot]:
        return dict(self._cache)

    def next_batch(
        self,
        markets: tuple[ExecutableMarket, ...],
    ) -> tuple[ExecutableMarket, ...]:
        eligible = tuple(
            sorted(
                {
                    market
                    for market in markets
                    if market.market_type is MarketType.PERPETUAL
                },
                key=lambda item: item.symbol,
            )
        )
        if not eligible:
            self._perpetual_analytics_cursor = 0
            return ()
        limit = min(self._policy.market_limit_per_refresh, len(eligible))
        start = self._perpetual_analytics_cursor % len(eligible)
        selected = tuple(eligible[(start + offset) % len(eligible)] for offset in range(limit))
        self._perpetual_analytics_cursor = (start + limit) % len(eligible)
        return selected

    async def scan(
        self,
        markets: tuple[ExecutableMarket, ...],
        *,
        as_of: datetime,
    ) -> None:
        as_of = _utc(as_of)
        selected = self.next_batch(markets)
        semaphore = asyncio.Semaphore(self._policy.fetch_concurrency)
        counters_lock = asyncio.Lock()
        attempted = 0
        failed = 0
        scanned = 0

        async def call(method_name: str, market: ExecutableMarket):
            nonlocal attempted, failed
            method = getattr(self._provider, method_name, None)
            if not callable(method):
                return None, False
            async with counters_lock:
                attempted += 1
            try:
                async with semaphore:
                    value = await method(
                        market,
                        since=as_of - timedelta(seconds=self._policy.history_lookback_seconds),
                        until=as_of,
                        interval_seconds=self._policy.history_interval_seconds,
                    )
                return value, True
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                async with counters_lock:
                    failed += 1
                return exc, True

        async def one(market: ExecutableMarket) -> None:
            nonlocal scanned
            cached = self._cache.get(market)
            if self._is_fresh(cached, as_of=as_of):
                return
            async with counters_lock:
                scanned += 1

            oi_result, oi_expected = await call("open_interest_history", market)
            if not oi_expected:
                oi_snapshot = PerpetualAnalyticsSnapshot(
                    market=market,
                    status=PerpetualAnalyticsStatus.TECHNICAL_ERROR,
                    open_interest_status=PerpetualAnalyticsStatus.TECHNICAL_ERROR,
                    observed_at=as_of,
                    error_type="MissingOpenInterestProvider",
                )
            elif isinstance(oi_result, Exception):
                oi_snapshot = PerpetualAnalyticsSnapshot(
                    market=market,
                    status=PerpetualAnalyticsStatus.TECHNICAL_ERROR,
                    open_interest_status=PerpetualAnalyticsStatus.TECHNICAL_ERROR,
                    observed_at=as_of,
                    error_type=type(oi_result).__name__,
                )
            else:
                oi_snapshot = analyze_open_interest_history(
                    market=market,
                    points=oi_result,
                    as_of=as_of,
                    policy=self._policy,
                )

            funding_result, funding_expected = await call("funding_history", market)
            funding_snapshot: PerpetualFundingAnalyticsSnapshot | None = None
            funding_characteristics: tuple[PerpetualAnalyticsCharacteristic, ...] = ()
            if funding_expected:
                if isinstance(funding_result, Exception):
                    funding_snapshot = PerpetualFundingAnalyticsSnapshot(
                        status=PerpetualAnalyticsStatus.TECHNICAL_ERROR,
                        observed_at=as_of,
                        error_type=type(funding_result).__name__,
                    )
                else:
                    funding_snapshot, funding_characteristics = analyze_funding_history(
                        points=funding_result,
                        as_of=as_of,
                        policy=self._policy,
                    )

            liquidation_result, liquidation_expected = await call(
                "liquidation_volume_history", market
            )
            liquidation_snapshot: PerpetualLiquidationVolumeAnalyticsSnapshot | None = None
            liquidation_characteristics: tuple[PerpetualAnalyticsCharacteristic, ...] = ()
            if liquidation_expected:
                if isinstance(liquidation_result, Exception):
                    liquidation_snapshot = PerpetualLiquidationVolumeAnalyticsSnapshot(
                        status=PerpetualAnalyticsStatus.TECHNICAL_ERROR,
                        observed_at=as_of,
                        error_type=type(liquidation_result).__name__,
                    )
                else:
                    (
                        liquidation_snapshot,
                        liquidation_characteristics,
                    ) = analyze_liquidation_volume_history(
                        points=liquidation_result,
                        as_of=as_of,
                        policy=self._policy,
                    )

            statuses = [oi_snapshot.open_interest_status]
            if funding_expected and funding_snapshot is not None:
                statuses.append(funding_snapshot.status)
            if liquidation_expected and liquidation_snapshot is not None:
                statuses.append(liquidation_snapshot.status)
            combined_status = _combine_statuses(tuple(statuses))
            combined_characteristics = tuple(
                dict.fromkeys(
                    (*oi_snapshot.characteristics, *funding_characteristics, *liquidation_characteristics)
                )
            )
            self._cache[market] = oi_snapshot.model_copy(
                update={
                    "status": combined_status,
                    "funding": funding_snapshot,
                    "liquidation_volume": liquidation_snapshot,
                    "characteristics": combined_characteristics,
                }
            )

        if selected:
            await asyncio.gather(*(one(market) for market in selected))
        self._latest_requests_attempted = attempted
        self._latest_requests_failed = failed
        self._latest_scanned_market_count = scanned

    def snapshot_for(
        self,
        market: ExecutableMarket,
        *,
        as_of: datetime,
    ) -> PerpetualAnalyticsSnapshot:
        as_of = _utc(as_of)
        if market.market_type is not MarketType.PERPETUAL:
            return PerpetualAnalyticsSnapshot(
                market=market,
                status=PerpetualAnalyticsStatus.NOT_APPLICABLE,
                open_interest_status=PerpetualAnalyticsStatus.NOT_APPLICABLE,
                observed_at=as_of,
            )
        snapshot = self._cache.get(market)
        if snapshot is None or snapshot.observed_at.astimezone(UTC) > as_of:
            return PerpetualAnalyticsSnapshot(
                market=market,
                status=PerpetualAnalyticsStatus.PARTIAL,
                open_interest_status=PerpetualAnalyticsStatus.PARTIAL,
                observed_at=as_of,
            )
        age = (as_of - snapshot.observed_at.astimezone(UTC)).total_seconds()
        updates: dict[str, object] = {}
        point_at = snapshot.current_open_interest_observed_at
        if point_at is not None:
            _, freshness, _ = _freshness(point_at, as_of=as_of, policy=self._policy)
            updates["freshness_seconds"] = freshness
        if age > self._policy.cache_ttl_seconds and snapshot.status not in (
            PerpetualAnalyticsStatus.NOT_APPLICABLE,
            PerpetualAnalyticsStatus.TECHNICAL_ERROR,
        ):
            updates["status"] = PerpetualAnalyticsStatus.STALE
        return snapshot.model_copy(update=updates) if updates else snapshot

    def coverage(
        self,
        markets: tuple[ExecutableMarket, ...],
        *,
        as_of: datetime,
    ) -> PerpetualAnalyticsCoverageDiagnostics:
        as_of = _utc(as_of)
        eligible = tuple(
            sorted(
                {
                    market
                    for market in markets
                    if market.market_type is MarketType.PERPETUAL
                },
                key=lambda item: item.symbol,
            )
        )
        fresh = 0
        expired = 0
        unseen = 0
        ages: list[float] = []
        for market in eligible:
            snapshot = self._cache.get(market)
            if snapshot is None:
                unseen += 1
                continue
            snapshot_at = snapshot.observed_at.astimezone(UTC)
            if snapshot_at > as_of:
                unseen += 1
                continue
            age = (as_of - snapshot_at).total_seconds()
            ages.append(age)
            if age <= self._policy.cache_ttl_seconds:
                fresh += 1
            else:
                expired += 1

        count = len(eligible)
        effective_limit = min(self._policy.market_limit_per_refresh, count)
        refreshes = ceil(count / effective_limit) if effective_limit else 0
        estimated_seconds = refreshes * self._refresh_seconds
        within_ttl = refreshes == 0 or estimated_seconds <= self._policy.cache_ttl_seconds
        ratio = fresh / count if count else None
        if count == 0:
            status = PerpetualAnalyticsCoverageStatus.NO_MARKETS
        elif not within_ttl:
            status = PerpetualAnalyticsCoverageStatus.CONFIGURATION_TOO_SLOW
        elif expired:
            status = PerpetualAnalyticsCoverageStatus.TTL_EXPIRED
        elif fresh == count:
            status = PerpetualAnalyticsCoverageStatus.COVERED
        else:
            status = PerpetualAnalyticsCoverageStatus.ROTATING

        series_coverage = tuple(
            self._series_coverage(eligible, series)
            for series in ("open-interest", "funding", "liquidation-volume")
        )
        return PerpetualAnalyticsCoverageDiagnostics(
            eligible_market_count=count,
            fresh_market_count=fresh,
            expired_market_count=expired,
            unseen_market_count=unseen,
            scanned_market_count=self._latest_scanned_market_count,
            coverage_ratio=ratio,
            effective_market_limit=effective_limit,
            estimated_refreshes_per_full_rotation=refreshes,
            estimated_full_rotation_seconds=estimated_seconds,
            cache_ttl_seconds=float(self._policy.cache_ttl_seconds),
            oldest_snapshot_age_seconds=max(ages) if ages else None,
            rotation_within_cache_ttl=within_ttl,
            requests_attempted=self._latest_requests_attempted,
            requests_failed=self._latest_requests_failed,
            series_coverage=series_coverage,
            status=status,
        )

    def _series_coverage(
        self,
        markets: tuple[ExecutableMarket, ...],
        series: str,
    ) -> PerpetualAnalyticsSeriesCoverageDiagnostics:
        counts = {
            PerpetualAnalyticsStatus.AVAILABLE: 0,
            PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY: 0,
            PerpetualAnalyticsStatus.STALE: 0,
            PerpetualAnalyticsStatus.TECHNICAL_ERROR: 0,
        }
        unavailable = 0
        for market in markets:
            snapshot = self._cache.get(market)
            status: PerpetualAnalyticsStatus | None = None
            if snapshot is not None:
                if series == "open-interest":
                    status = snapshot.open_interest_status
                elif series == "funding" and snapshot.funding is not None:
                    status = snapshot.funding.status
                elif series == "liquidation-volume" and snapshot.liquidation_volume is not None:
                    status = snapshot.liquidation_volume.status
            if status in counts:
                counts[status] += 1
            else:
                unavailable += 1
        return PerpetualAnalyticsSeriesCoverageDiagnostics(
            series=series,
            available_market_count=counts[PerpetualAnalyticsStatus.AVAILABLE],
            insufficient_history_market_count=counts[
                PerpetualAnalyticsStatus.INSUFFICIENT_HISTORY
            ],
            stale_market_count=counts[PerpetualAnalyticsStatus.STALE],
            technical_error_market_count=counts[PerpetualAnalyticsStatus.TECHNICAL_ERROR],
            unavailable_market_count=unavailable,
        )

    def _is_fresh(
        self,
        snapshot: PerpetualAnalyticsSnapshot | None,
        *,
        as_of: datetime,
    ) -> bool:
        if snapshot is None:
            return False
        observed_at = snapshot.observed_at.astimezone(UTC)
        if observed_at > as_of:
            return False
        return (as_of - observed_at).total_seconds() <= self._policy.cache_ttl_seconds


def _combine_statuses(statuses: tuple[PerpetualAnalyticsStatus, ...]) -> PerpetualAnalyticsStatus:
    if not statuses:
        return PerpetualAnalyticsStatus.PARTIAL
    if len(set(statuses)) == 1:
        return statuses[0]
    if all(status in (PerpetualAnalyticsStatus.STALE, PerpetualAnalyticsStatus.AVAILABLE) for status in statuses):
        return PerpetualAnalyticsStatus.PARTIAL
    if all(status is PerpetualAnalyticsStatus.TECHNICAL_ERROR for status in statuses):
        return PerpetualAnalyticsStatus.TECHNICAL_ERROR
    return PerpetualAnalyticsStatus.PARTIAL


def _validate_chronology(points: tuple[object, ...]) -> None:
    previous_timestamp: datetime | None = None
    for point in points:
        point_at = _utc(point.observed_at)  # type: ignore[attr-defined]
        if previous_timestamp is not None and point_at <= previous_timestamp:
            raise ValueError("perpetual analytics history must be strictly chronological")
        previous_timestamp = point_at


def _finalized(points: tuple, *, as_of: datetime, policy: PerpetualAnalyticsPolicy) -> tuple:
    interval = timedelta(seconds=policy.history_interval_seconds)
    return tuple(point for point in points if _utc(point.observed_at) + interval <= as_of)


def _freshness(
    point_at: datetime,
    *,
    as_of: datetime,
    policy: PerpetualAnalyticsPolicy,
) -> tuple[datetime, Decimal, bool]:
    point_at = _utc(point_at)
    bucket_end = point_at + timedelta(seconds=policy.history_interval_seconds)
    seconds = max(0.0, (as_of - bucket_end).total_seconds())
    freshness = Decimal(str(seconds))
    return point_at, freshness, seconds > policy.data_stale_after_seconds


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("perpetual analytics datetime must be timezone-aware")
    return value.astimezone(UTC)


def _safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _change_ratio(current: Decimal, previous: Decimal) -> Decimal | None:
    ratio = _safe_ratio(current, previous)
    return ratio - Decimal(1) if ratio is not None else None
