from __future__ import annotations

import asyncio
import math
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from statistics import median
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.market.candles import Candle, CandleKey, CandleStreamService, CandleTimeframe


class RadarStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    STALE = "STALE"
    ERROR = "ERROR"


class MarketActivityState(StrEnum):
    UNKNOWN = "UNKNOWN"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    ACCELERATING = "ACCELERATING"
    VERY_HIGH = "VERY_HIGH"


class ActivityDataQuality(StrEnum):
    COMPLETE = "COMPLETE"
    NO_TRADE_GAPS = "NO_TRADE_GAPS"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    DISCONTINUOUS_HISTORY = "DISCONTINUOUS_HISTORY"
    TECHNICAL_ERROR = "TECHNICAL_ERROR"


class LiquidityRegime(StrEnum):
    UNKNOWN = "UNKNOWN"
    MICRO = "MICRO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class PublicAttentionDirection(StrEnum):
    UNKNOWN = "UNKNOWN"
    FALLING = "FALLING"
    STABLE = "STABLE"
    RISING = "RISING"


class CrossAttentionState(StrEnum):
    NORMAL = "NORMAL"
    MARKET_ONLY = "MARKET_ONLY"
    PUBLIC_ONLY = "PUBLIC_ONLY"
    CONVERGING = "CONVERGING"


class AttentionLevel(StrEnum):
    NORMAL = "NORMAL"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AttentionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MarketAttentionPolicy(AttentionModel):
    """Bounded, observation-only runtime policy for the radar."""

    protocol_version: str = "market-attention-radar-v1"
    refresh_seconds: float = Field(default=300.0, ge=30.0, le=86_400.0)
    catalogue_ttl_seconds: float = Field(default=1800.0, ge=60.0, le=86_400.0)
    activity_ttl_seconds: float = Field(default=900.0, ge=60.0, le=86_400.0)
    public_attention_ttl_seconds: float = Field(default=1800.0, ge=60.0, le=86_400.0)
    stale_after_seconds: float = Field(default=900.0, ge=30.0, le=86_400.0)
    scan_limit: int = Field(default=120, ge=10, le=500)
    scan_concurrency: int = Field(default=8, ge=1, le=32)
    candidate_limit: int = Field(default=20, ge=1, le=30)
    diagnostic_market_limit: int = Field(default=10, ge=1, le=30)
    max_web_searches_per_refresh: int = Field(default=8, ge=0, le=30)
    candle_limit: int = Field(default=720, ge=160, le=1000)
    baseline_periods: int = Field(default=6, ge=3, le=20)
    history_limit: int = Field(default=96, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_policy(self) -> "MarketAttentionPolicy":
        if self.protocol_version != "market-attention-radar-v1":
            raise ValueError("unsupported market attention protocol")
        if self.max_web_searches_per_refresh > self.candidate_limit:
            raise ValueError("max_web_searches_per_refresh cannot exceed candidate_limit")
        return self


class ActivityHorizonSnapshot(AttentionModel):
    timeframe: CandleTimeframe
    current_volume: Decimal | None = None
    previous_comparable_volume: Decimal | None = None
    baseline_volume: Decimal | None = None
    volume_ratio: Decimal | None = None
    volume_change: Decimal | None = None
    volume_acceleration: Decimal | None = None
    current_notional_usd: Decimal | None = Field(default=None, ge=0)
    baseline_notional_usd: Decimal | None = Field(default=None, ge=0)
    notional_delta_usd: Decimal | None = None
    notional_method: str | None = None
    price_return: Decimal | None = None
    price_range: Decimal | None = None
    realized_volatility: Decimal | None = None
    observation_count: int = Field(ge=0)
    baseline_period_count: int = Field(ge=0)
    no_trade_interval_count: int = Field(default=0, ge=0)
    unexplained_gap_count: int = Field(default=0, ge=0)
    data_quality: ActivityDataQuality = ActivityDataQuality.COMPLETE
    complete: bool


class MarketActivitySnapshot(AttentionModel):
    market: ExecutableMarket
    observed_at: datetime
    status: RadarStatus
    activity_state: MarketActivityState
    liquidity_regime: LiquidityRegime = LiquidityRegime.UNKNOWN
    liquidity_reference_usd: Decimal | None = Field(default=None, ge=0)
    freshness_seconds: Decimal | None = Field(default=None, ge=0)
    horizons: tuple[ActivityHorizonSnapshot, ...]
    data_quality: ActivityDataQuality = ActivityDataQuality.COMPLETE
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_snapshot(self) -> "MarketActivitySnapshot":
        _require_aware(self.observed_at, "market activity observed_at")
        return self

    def horizon(self, timeframe: CandleTimeframe) -> ActivityHorizonSnapshot | None:
        return next((item for item in self.horizons if item.timeframe is timeframe), None)


class ActivityStatusCounts(AttentionModel):
    AVAILABLE: int = Field(default=0, ge=0)
    PARTIAL: int = Field(default=0, ge=0)
    STALE: int = Field(default=0, ge=0)
    ERROR: int = Field(default=0, ge=0)


class ActivityStateCounts(AttentionModel):
    UNKNOWN: int = Field(default=0, ge=0)
    NORMAL: int = Field(default=0, ge=0)
    ELEVATED: int = Field(default=0, ge=0)
    ACCELERATING: int = Field(default=0, ge=0)
    VERY_HIGH: int = Field(default=0, ge=0)


class ActivityDataQualityCounts(AttentionModel):
    COMPLETE: int = Field(default=0, ge=0)
    NO_TRADE_GAPS: int = Field(default=0, ge=0)
    INSUFFICIENT_HISTORY: int = Field(default=0, ge=0)
    DISCONTINUOUS_HISTORY: int = Field(default=0, ge=0)
    TECHNICAL_ERROR: int = Field(default=0, ge=0)


class ActivityErrorCounts(AttentionModel):
    KrakenConnectionError: int = Field(default=0, ge=0)
    KrakenPayloadError: int = Field(default=0, ge=0)
    UnknownKrakenSymbolError: int = Field(default=0, ge=0)
    CandleValidationError: int = Field(default=0, ge=0)
    Other: int = Field(default=0, ge=0)


class ActivityMarketTypeStatusCounts(AttentionModel):
    SPOT: ActivityStatusCounts = Field(default_factory=ActivityStatusCounts)
    PERPETUAL: ActivityStatusCounts = Field(default_factory=ActivityStatusCounts)


class LiquidityRegimeCounts(AttentionModel):
    UNKNOWN: int = Field(default=0, ge=0)
    MICRO: int = Field(default=0, ge=0)
    LOW: int = Field(default=0, ge=0)
    MEDIUM: int = Field(default=0, ge=0)
    HIGH: int = Field(default=0, ge=0)
    VERY_HIGH: int = Field(default=0, ge=0)


class SubthresholdActivitySnapshot(AttentionModel):
    market: ExecutableMarket
    peak_volume_ratio: Decimal
    peak_timeframe: CandleTimeframe


class PublicAttentionMetric(AttentionModel):
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=256)
    unit: str | None = Field(default=None, max_length=64)
    window: str | None = Field(default=None, max_length=64)
    source_url: str | None = Field(default=None, max_length=2048)
    observed_at: datetime
    published_at: datetime | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "PublicAttentionMetric":
        _require_aware(self.observed_at, "metric observed_at")
        if self.published_at is not None:
            _require_aware(self.published_at, "metric published_at")
        return self


class PublicAttentionObservation(AttentionModel):
    text: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2048)


class PublicAttentionCatalyst(AttentionModel):
    description: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2048)


class PublicAttentionSource(AttentionModel):
    title: str = Field(min_length=1, max_length=1000)
    url: str = Field(min_length=1, max_length=2048)
    source_domain: str = Field(min_length=1, max_length=255)
    observed_at: datetime
    published_at: datetime | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "PublicAttentionSource":
        _require_aware(self.observed_at, "source observed_at")
        if self.published_at is not None:
            _require_aware(self.published_at, "source published_at")
        return self


class PublicAttentionSnapshot(AttentionModel):
    asset: str = Field(min_length=1, max_length=64)
    observed_at: datetime
    research_status: RadarStatus
    attention_direction: PublicAttentionDirection
    quantitative_metrics: tuple[PublicAttentionMetric, ...] = ()
    qualitative_observations: tuple[PublicAttentionObservation, ...] = ()
    possible_catalysts: tuple[PublicAttentionCatalyst, ...] = ()
    sources: tuple[PublicAttentionSource, ...] = ()
    confidence_context: str = Field(min_length=1, max_length=2000)
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_snapshot(self) -> "PublicAttentionSnapshot":
        _require_aware(self.observed_at, "public attention observed_at")
        return self


class MarketAttentionSnapshot(AttentionModel):
    market_activity: MarketActivitySnapshot
    public_attention: PublicAttentionSnapshot
    cross_state: CrossAttentionState
    attention_level: AttentionLevel

    @property
    def market(self) -> ExecutableMarket:
        return self.market_activity.market


class MarketAttentionOverview(AttentionModel):
    protocol_version: str = "market-attention-radar-v1"
    observed_at: datetime
    status: RadarStatus
    informative_only: bool = True
    catalogue_market_count: int = Field(default=0, ge=0)
    cached_activity_market_count: int = Field(default=0, ge=0)
    scanned_market_count: int = Field(default=0, ge=0)
    candidate_market_count: int = Field(default=0, ge=0)
    web_search_count: int = Field(default=0, ge=0)
    activity_status_counts: ActivityStatusCounts = Field(default_factory=ActivityStatusCounts)
    activity_state_counts: ActivityStateCounts = Field(default_factory=ActivityStateCounts)
    activity_data_quality_counts: ActivityDataQualityCounts = Field(
        default_factory=ActivityDataQualityCounts
    )
    activity_error_counts: ActivityErrorCounts = Field(default_factory=ActivityErrorCounts)
    activity_market_type_status_counts: ActivityMarketTypeStatusCounts = Field(
        default_factory=ActivityMarketTypeStatusCounts
    )
    liquidity_regime_counts: LiquidityRegimeCounts = Field(default_factory=LiquidityRegimeCounts)
    subthreshold_activity: tuple[SubthresholdActivitySnapshot, ...] = ()
    shortlist: tuple[MarketAttentionSnapshot, ...] = ()
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_overview(self) -> "MarketAttentionOverview":
        _require_aware(self.observed_at, "market attention observed_at")
        if not self.informative_only:
            raise ValueError("Market Attention Radar v1 must remain informative_only")
        return self


class MarketCatalogue(Protocol):
    async def list_markets(self) -> tuple[ExecutableMarket, ...]: ...

    async def aclose(self) -> None: ...


class PublicAttentionResearcher(Protocol):
    async def research(
        self,
        *,
        asset: str,
        symbols: tuple[str, ...],
        observed_at: datetime,
    ) -> PublicAttentionSnapshot: ...

    async def aclose(self) -> None: ...


class MarketActivityAnalyzer:
    """Derive descriptive activity facts from canonical 5m OHLCV candles."""

    HORIZONS: tuple[CandleTimeframe, ...] = (
        CandleTimeframe.M5,
        CandleTimeframe.M15,
        CandleTimeframe.H1,
        CandleTimeframe.H4,
    )

    def __init__(self, *, baseline_periods: int = 6, stale_after: timedelta) -> None:
        if baseline_periods < 3:
            raise ValueError("baseline_periods must be at least 3")
        if stale_after.total_seconds() <= 0:
            raise ValueError("stale_after must be positive")
        self._baseline_periods = baseline_periods
        self._stale_after = stale_after

    def analyze(
        self,
        *,
        market: ExecutableMarket,
        candles: tuple[Candle, ...],
        observed_at: datetime,
        missing_intervals_mean_no_trades: bool = False,
    ) -> MarketActivitySnapshot:
        observed_at = _utc(observed_at)
        final = tuple(
            candle
            for candle in candles
            if candle.is_final
            and candle.market_type is market.market_type
            and candle.symbol == market.symbol
            and candle.timeframe is CandleTimeframe.M5
            and candle.close_time.astimezone(UTC) <= observed_at
        )
        final = tuple(sorted(final, key=lambda item: item.open_time))
        if not final:
            horizons = tuple(self._empty_horizon(timeframe) for timeframe in self.HORIZONS)
            return MarketActivitySnapshot(
                market=market,
                observed_at=observed_at,
                status=RadarStatus.PARTIAL,
                activity_state=MarketActivityState.UNKNOWN,
                freshness_seconds=None,
                horizons=horizons,
                data_quality=ActivityDataQuality.INSUFFICIENT_HISTORY,
            )

        freshness_seconds = Decimal(
            str(max(0.0, (observed_at - final[-1].close_time.astimezone(UTC)).total_seconds()))
        )
        horizons = tuple(
            self._horizon(
                final,
                timeframe,
                market=market,
                missing_intervals_mean_no_trades=missing_intervals_mean_no_trades,
            )
            for timeframe in self.HORIZONS
        )
        complete_ratios = [
            item.volume_ratio
            for item in horizons
            if item.complete and item.volume_ratio is not None
        ]
        complete_accelerations = [
            item.volume_acceleration
            for item in horizons
            if item.complete and item.volume_acceleration is not None
        ]
        activity_state = _activity_state(complete_ratios, complete_accelerations)
        if not all(item.complete for item in horizons):
            status = RadarStatus.PARTIAL
        elif freshness_seconds > Decimal(str(self._stale_after.total_seconds())):
            status = RadarStatus.STALE
        else:
            status = RadarStatus.AVAILABLE
        return MarketActivitySnapshot(
            market=market,
            observed_at=observed_at,
            status=status,
            activity_state=activity_state,
            freshness_seconds=freshness_seconds,
            horizons=horizons,
            data_quality=_snapshot_data_quality(horizons),
        )

    def _empty_horizon(self, timeframe: CandleTimeframe) -> ActivityHorizonSnapshot:
        return ActivityHorizonSnapshot(
            timeframe=timeframe,
            observation_count=0,
            baseline_period_count=0,
            no_trade_interval_count=0,
            unexplained_gap_count=0,
            data_quality=ActivityDataQuality.INSUFFICIENT_HISTORY,
            complete=False,
        )

    def _incomplete_horizon(
        self,
        timeframe: CandleTimeframe,
        *,
        observation_count: int,
        baseline_period_count: int,
        data_quality: ActivityDataQuality,
        no_trade_interval_count: int = 0,
        unexplained_gap_count: int = 0,
    ) -> ActivityHorizonSnapshot:
        return ActivityHorizonSnapshot(
            timeframe=timeframe,
            observation_count=max(0, observation_count),
            baseline_period_count=max(0, baseline_period_count),
            no_trade_interval_count=max(0, no_trade_interval_count),
            unexplained_gap_count=max(0, unexplained_gap_count),
            data_quality=data_quality,
            complete=False,
        )

    def _horizon(
        self,
        candles: tuple[Candle, ...],
        timeframe: CandleTimeframe,
        *,
        market: ExecutableMarket,
        missing_intervals_mean_no_trades: bool,
    ) -> ActivityHorizonSnapshot:
        bars = int(timeframe.duration / CandleTimeframe.M5.duration)
        required = bars * (self._baseline_periods + 2)
        step = CandleTimeframe.M5.duration
        if not candles:
            return self._incomplete_horizon(
                timeframe,
                observation_count=0,
                baseline_period_count=0,
                data_quality=ActivityDataQuality.INSUFFICIENT_HISTORY,
            )

        end = candles[-1].close_time.astimezone(UTC)
        start = end - (step * required)
        first_open = candles[0].open_time.astimezone(UTC)
        if first_open > start:
            return self._incomplete_horizon(
                timeframe,
                observation_count=min(len(candles), bars),
                baseline_period_count=max(0, (len(candles) // bars) - 2),
                data_quality=ActivityDataQuality.INSUFFICIENT_HISTORY,
            )

        window = tuple(
            candle
            for candle in candles
            if candle.open_time.astimezone(UTC) >= start
            and candle.close_time.astimezone(UTC) <= end
        )
        expected_opens = tuple(start + (step * index) for index in range(required))
        expected_set = set(expected_opens)
        by_open: dict[datetime, Candle] = {}
        malformed = 0
        for candle in window:
            open_time = candle.open_time.astimezone(UTC)
            close_time = candle.close_time.astimezone(UTC)
            if close_time - open_time != step or open_time not in expected_set or open_time in by_open:
                malformed += 1
                continue
            by_open[open_time] = candle

        missing_opens = tuple(value for value in expected_opens if value not in by_open)
        if malformed:
            return self._incomplete_horizon(
                timeframe,
                observation_count=sum(value in by_open for value in expected_opens[-bars:]),
                baseline_period_count=max(0, (len(by_open) // bars) - 2),
                data_quality=ActivityDataQuality.DISCONTINUOUS_HISTORY,
                unexplained_gap_count=malformed + len(missing_opens),
            )

        if missing_opens:
            # A missing first slot can be a truncated provider window. Keep it partial rather
            # than silently manufacturing an initial zero-volume interval.
            if missing_opens[0] == expected_opens[0]:
                return self._incomplete_horizon(
                    timeframe,
                    observation_count=sum(value in by_open for value in expected_opens[-bars:]),
                    baseline_period_count=max(0, (len(by_open) // bars) - 2),
                    data_quality=ActivityDataQuality.INSUFFICIENT_HISTORY,
                    unexplained_gap_count=len(missing_opens),
                )
            if not missing_intervals_mean_no_trades:
                return self._incomplete_horizon(
                    timeframe,
                    observation_count=sum(value in by_open for value in expected_opens[-bars:]),
                    baseline_period_count=max(0, (len(by_open) // bars) - 2),
                    data_quality=ActivityDataQuality.DISCONTINUOUS_HISTORY,
                    unexplained_gap_count=len(missing_opens),
                )

        slots: tuple[Candle | None, ...] = tuple(by_open.get(value) for value in expected_opens)
        current = slots[-bars:]
        previous = slots[-2 * bars : -bars]
        baseline_pool = slots[: -2 * bars]
        baseline_groups = tuple(
            baseline_pool[index : index + bars]
            for index in range(0, len(baseline_pool), bars)
        )
        if len(baseline_groups) < 3:
            return self._incomplete_horizon(
                timeframe,
                observation_count=sum(item is not None for item in current),
                baseline_period_count=len(baseline_groups),
                data_quality=ActivityDataQuality.INSUFFICIENT_HISTORY,
                no_trade_interval_count=len(missing_opens) if missing_intervals_mean_no_trades else 0,
            )

        def volume(group: tuple[Candle | None, ...]) -> Decimal:
            return sum((item.volume if item is not None else Decimal(0) for item in group), Decimal(0))

        def real(group: tuple[Candle | None, ...]) -> tuple[Candle, ...]:
            return tuple(item for item in group if item is not None)

        current_volume = volume(current)
        previous_volume = volume(previous)
        baseline_volumes = tuple(volume(group) for group in baseline_groups)
        baseline_volume = Decimal(median(baseline_volumes))
        volume_ratio = _safe_ratio(current_volume, baseline_volume)
        current_vs_previous = _safe_ratio(current_volume, previous_volume)
        previous_vs_baseline = _safe_ratio(previous_volume, baseline_volume)
        volume_change = (
            current_vs_previous - Decimal(1) if current_vs_previous is not None else None
        )
        volume_acceleration = (
            (current_vs_previous - Decimal(1)) - (previous_vs_baseline - Decimal(1))
            if current_vs_previous is not None and previous_vs_baseline is not None
            else None
        )

        current_real = real(current)
        baseline_real_groups = tuple(real(group) for group in baseline_groups)
        current_notional_usd = _spot_usd_notional(current_real, market=market)
        baseline_notional_usd: Decimal | None = None
        notional_delta_usd: Decimal | None = None
        notional_method: str | None = None
        if current_notional_usd is not None:
            baseline_notionals = tuple(
                value
                for group in baseline_real_groups
                if (value := _spot_usd_notional(group, market=market)) is not None
            )
            if len(baseline_notionals) == len(baseline_groups):
                baseline_notional_usd = Decimal(median(baseline_notionals))
                notional_delta_usd = current_notional_usd - baseline_notional_usd
                notional_method = "SPOT_BASE_VOLUME_X_5M_CLOSE_ESTIMATE"

        price_return: Decimal | None = None
        price_range: Decimal | None = None
        realized_volatility: Decimal | None = None
        if current_real:
            price_return = _safe_ratio(current_real[-1].close, current_real[0].open)
            price_return = price_return - Decimal(1) if price_return is not None else None
            high = max(item.high for item in current_real)
            low = min(item.low for item in current_real)
            price_range = _safe_ratio(high, low)
            price_range = price_range - Decimal(1) if price_range is not None else None
            realized_volatility = _realized_volatility(current_real)

        quality = (
            ActivityDataQuality.NO_TRADE_GAPS
            if missing_opens and missing_intervals_mean_no_trades
            else ActivityDataQuality.COMPLETE
        )
        return ActivityHorizonSnapshot(
            timeframe=timeframe,
            current_volume=current_volume,
            previous_comparable_volume=previous_volume,
            baseline_volume=baseline_volume,
            volume_ratio=volume_ratio,
            volume_change=volume_change,
            volume_acceleration=volume_acceleration,
            current_notional_usd=current_notional_usd,
            baseline_notional_usd=baseline_notional_usd,
            notional_delta_usd=notional_delta_usd,
            notional_method=notional_method,
            price_return=price_return,
            price_range=price_range,
            realized_volatility=realized_volatility,
            observation_count=len(current_real),
            baseline_period_count=len(baseline_groups),
            no_trade_interval_count=len(missing_opens) if missing_intervals_mean_no_trades else 0,
            unexplained_gap_count=0,
            data_quality=quality,
            complete=volume_ratio is not None,
        )


class MarketAttentionRadar:
    """Independent, fail-soft observation service. It has no trading interfaces."""

    def __init__(
        self,
        *,
        candle_service: CandleStreamService,
        catalogue: MarketCatalogue,
        researcher: PublicAttentionResearcher | None,
        policy: MarketAttentionPolicy | None = None,
    ) -> None:
        self._candles = candle_service
        self._catalogue_provider = catalogue
        self._researcher = researcher
        self._policy = policy or MarketAttentionPolicy()
        self._analyzer = MarketActivityAnalyzer(
            baseline_periods=self._policy.baseline_periods,
            stale_after=timedelta(seconds=self._policy.stale_after_seconds),
        )
        self._catalogue: tuple[ExecutableMarket, ...] = ()
        self._catalogue_at: datetime | None = None
        self._scan_cursor = 0
        self._activity_cache: dict[ExecutableMarket, MarketActivitySnapshot] = {}
        self._public_cache: dict[str, PublicAttentionSnapshot] = {}
        self._history: deque[MarketAttentionOverview] = deque(maxlen=self._policy.history_limit)
        self._latest: MarketAttentionOverview | None = None
        self._task: asyncio.Task[None] | None = None
        self._closed = False
        self._refresh_lock = asyncio.Lock()

    @property
    def latest(self) -> MarketAttentionOverview:
        if self._latest is not None:
            return self._latest
        return MarketAttentionOverview(
            observed_at=datetime.now(UTC),
            status=RadarStatus.PARTIAL,
            informative_only=True,
        )

    def history(self, *, limit: int = 24) -> tuple[MarketAttentionOverview, ...]:
        if isinstance(limit, bool) or limit <= 0 or limit > self._policy.history_limit:
            raise ValueError("invalid market attention history limit")
        return tuple(self._history)[-limit:]

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("market attention radar is closed")
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="market-attention-radar")

    async def refresh_once(self, *, observed_at: datetime | None = None) -> MarketAttentionOverview:
        async with self._refresh_lock:
            now = _utc(observed_at or datetime.now(UTC))
            scanned_count = 0
            web_search_count = 0
            try:
                catalogue = await self._catalogue_if_due(now)
                scan_batch = self._next_scan_batch(catalogue)
                scanned_count = len(scan_batch)
                await self._scan_activity(scan_batch, now=now)
                fresh_activities = self._classify_liquidity(self._fresh_activities(now))
                status_counts = _activity_status_counts(fresh_activities)
                state_counts = _activity_state_counts(fresh_activities)
                data_quality_counts = _activity_data_quality_counts(fresh_activities)
                error_counts = _activity_error_counts(fresh_activities)
                market_type_status_counts = _activity_market_type_status_counts(fresh_activities)
                liquidity_counts = _liquidity_regime_counts(fresh_activities)
                subthreshold_activity = self._subthreshold_activity(fresh_activities)
                candidates = self._candidates_from(fresh_activities)
                public_by_asset, web_search_count = await self._public_attention(
                    candidates,
                    now=now,
                )
                combined = tuple(
                    self._combine(
                        activity,
                        public_by_asset.get(_base_asset(activity.market.symbol))
                        or self._public_placeholder(
                            _base_asset(activity.market.symbol),
                            now=now,
                            status=(
                                RadarStatus.NOT_CONFIGURED
                                if self._researcher is None
                                else RadarStatus.PARTIAL
                            ),
                            context=(
                                "OpenAI web search is not configured."
                                if self._researcher is None
                                else (
                                    "No public web research was allocated to this candidate "
                                    "in this refresh."
                                )
                            ),
                        ),
                    )
                    for activity in candidates
                )
                shortlist = tuple(sorted(combined, key=_attention_sort_key, reverse=True))
                status = _overview_status(
                    shortlist,
                    fresh_activities=fresh_activities,
                    researcher_configured=self._researcher is not None,
                )
                overview = MarketAttentionOverview(
                    observed_at=now,
                    status=status,
                    informative_only=True,
                    catalogue_market_count=len(catalogue),
                    cached_activity_market_count=len(fresh_activities),
                    scanned_market_count=scanned_count,
                    candidate_market_count=len(shortlist),
                    web_search_count=web_search_count,
                    activity_status_counts=status_counts,
                    activity_state_counts=state_counts,
                    activity_data_quality_counts=data_quality_counts,
                    activity_error_counts=error_counts,
                    activity_market_type_status_counts=market_type_status_counts,
                    liquidity_regime_counts=liquidity_counts,
                    subthreshold_activity=subthreshold_activity,
                    shortlist=shortlist,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                fresh_activities = self._classify_liquidity(self._fresh_activities(now))
                overview = MarketAttentionOverview(
                    observed_at=now,
                    status=RadarStatus.ERROR,
                    informative_only=True,
                    catalogue_market_count=len(self._catalogue),
                    cached_activity_market_count=len(fresh_activities),
                    scanned_market_count=scanned_count,
                    candidate_market_count=0,
                    web_search_count=web_search_count,
                    activity_status_counts=_activity_status_counts(fresh_activities),
                    activity_state_counts=_activity_state_counts(fresh_activities),
                    activity_data_quality_counts=_activity_data_quality_counts(fresh_activities),
                    activity_error_counts=_activity_error_counts(fresh_activities),
                    activity_market_type_status_counts=_activity_market_type_status_counts(
                        fresh_activities
                    ),
                    liquidity_regime_counts=_liquidity_regime_counts(fresh_activities),
                    subthreshold_activity=self._subthreshold_activity(fresh_activities),
                    error_type=type(exc).__name__,
                )
            self._latest = overview
            self._history.append(overview)
            return overview

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        await self._catalogue_provider.aclose()
        if self._researcher is not None:
            await self._researcher.aclose()

    async def _run(self) -> None:
        while not self._closed:
            try:
                await self.refresh_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # refresh_once is already fail-soft; this is a final isolation barrier.
                pass
            await asyncio.sleep(self._policy.refresh_seconds)

    async def _catalogue_if_due(self, now: datetime) -> tuple[ExecutableMarket, ...]:
        if (
            self._catalogue_at is None
            or now - self._catalogue_at >= timedelta(seconds=self._policy.catalogue_ttl_seconds)
            or not self._catalogue
        ):
            raw = await self._catalogue_provider.list_markets()
            self._catalogue = tuple(
                sorted(
                    {
                        market
                        for market in raw
                        if market.market_type in (MarketType.SPOT, MarketType.PERPETUAL)
                    },
                    key=lambda item: (item.market_type.value, item.symbol),
                )
            )
            self._catalogue_at = now
            if self._scan_cursor >= len(self._catalogue):
                self._scan_cursor = 0
        return self._catalogue

    def _next_scan_batch(
        self,
        catalogue: tuple[ExecutableMarket, ...],
    ) -> tuple[ExecutableMarket, ...]:
        if not catalogue:
            return ()
        count = min(len(catalogue), self._policy.scan_limit)
        start = self._scan_cursor % len(catalogue)
        indices = tuple((start + offset) % len(catalogue) for offset in range(count))
        self._scan_cursor = (start + count) % len(catalogue)
        return tuple(catalogue[index] for index in indices)

    async def _scan_activity(
        self,
        markets: tuple[ExecutableMarket, ...],
        *,
        now: datetime,
    ) -> None:
        semaphore = asyncio.Semaphore(self._policy.scan_concurrency)

        async def one(market: ExecutableMarket) -> None:
            async with semaphore:
                key = CandleKey(
                    symbol=market.symbol,
                    market_type=market.market_type,
                    timeframe=CandleTimeframe.M5,
                )
                try:
                    candles = await self._candles.history(
                        key,
                        limit=self._policy.candle_limit,
                    )
                    snapshot = self._analyzer.analyze(
                        market=market,
                        candles=candles,
                        observed_at=now,
                        missing_intervals_mean_no_trades=(
                            market.market_type is MarketType.SPOT
                        ),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    snapshot = MarketActivitySnapshot(
                        market=market,
                        observed_at=now,
                        status=RadarStatus.ERROR,
                        activity_state=MarketActivityState.UNKNOWN,
                        freshness_seconds=None,
                        horizons=tuple(
                            self._analyzer._empty_horizon(timeframe)
                            for timeframe in self._analyzer.HORIZONS
                        ),
                        data_quality=ActivityDataQuality.TECHNICAL_ERROR,
                        error_type=type(exc).__name__,
                    )
                self._activity_cache[market] = snapshot

        if markets:
            await asyncio.gather(*(one(market) for market in markets))

    def _fresh_activities(self, now: datetime) -> tuple[MarketActivitySnapshot, ...]:
        ttl = timedelta(seconds=self._policy.activity_ttl_seconds)
        return tuple(
            snapshot
            for snapshot in self._activity_cache.values()
            if now - snapshot.observed_at.astimezone(UTC) <= ttl
        )

    def _classify_liquidity(
        self,
        activities: tuple[MarketActivitySnapshot, ...],
    ) -> tuple[MarketActivitySnapshot, ...]:
        references: dict[MarketType, tuple[Decimal, ...]] = {}
        reference_by_market: dict[ExecutableMarket, Decimal | None] = {}
        for snapshot in activities:
            reference = _liquidity_reference_usd(snapshot)
            reference_by_market[snapshot.market] = reference
        for market_type in (MarketType.SPOT, MarketType.PERPETUAL):
            values = tuple(
                reference
                for snapshot in activities
                if snapshot.market.market_type is market_type
                and (reference := reference_by_market[snapshot.market]) is not None
            )
            references[market_type] = tuple(sorted(values))

        return tuple(
            snapshot.model_copy(
                update={
                    "liquidity_reference_usd": reference_by_market[snapshot.market],
                    "liquidity_regime": _liquidity_regime(
                        reference_by_market[snapshot.market],
                        references[snapshot.market.market_type],
                    ),
                }
            )
            for snapshot in activities
        )

    def _candidates(self, now: datetime) -> tuple[MarketActivitySnapshot, ...]:
        return self._candidates_from(self._classify_liquidity(self._fresh_activities(now)))

    def _candidates_from(
        self,
        activities: tuple[MarketActivitySnapshot, ...],
    ) -> tuple[MarketActivitySnapshot, ...]:
        unusual_states = {
            MarketActivityState.ELEVATED,
            MarketActivityState.ACCELERATING,
            MarketActivityState.VERY_HIGH,
        }
        eligible = tuple(
            snapshot
            for snapshot in activities
            if snapshot.status is RadarStatus.AVAILABLE
            and snapshot.activity_state in unusual_states
        )
        if not eligible:
            return ()

        ranked = tuple(sorted(eligible, key=_activity_sort_key, reverse=True))
        by_regime: dict[LiquidityRegime, list[MarketActivitySnapshot]] = {}
        for snapshot in ranked:
            by_regime.setdefault(snapshot.liquidity_regime, []).append(snapshot)

        regime_leaders = sorted(
            (items[0] for items in by_regime.values()),
            key=_activity_sort_key,
            reverse=True,
        )
        chosen: list[MarketActivitySnapshot] = regime_leaders[: self._policy.candidate_limit]
        chosen_markets = {snapshot.market for snapshot in chosen}
        if len(chosen) < self._policy.candidate_limit:
            for snapshot in ranked:
                if snapshot.market in chosen_markets:
                    continue
                chosen.append(snapshot)
                chosen_markets.add(snapshot.market)
                if len(chosen) >= self._policy.candidate_limit:
                    break
        return tuple(chosen)

    def _subthreshold_activity(
        self,
        activities: tuple[MarketActivitySnapshot, ...],
    ) -> tuple[SubthresholdActivitySnapshot, ...]:
        diagnostics: list[tuple[tuple[Decimal, Decimal, Decimal], SubthresholdActivitySnapshot]] = []
        for snapshot in activities:
            if (
                snapshot.status is not RadarStatus.AVAILABLE
                or snapshot.activity_state is not MarketActivityState.NORMAL
            ):
                continue
            best = _best_ratio_horizon(snapshot)
            if best is None:
                continue
            diagnostics.append(
                (
                    _activity_sort_key(snapshot),
                    SubthresholdActivitySnapshot(
                        market=snapshot.market,
                        peak_volume_ratio=best.volume_ratio,  # type: ignore[arg-type]
                        peak_timeframe=best.timeframe,
                    ),
                )
            )
        diagnostics.sort(key=lambda item: item[0], reverse=True)
        return tuple(item for _key, item in diagnostics[: self._policy.diagnostic_market_limit])

    async def _public_attention(
        self,
        candidates: tuple[MarketActivitySnapshot, ...],
        *,
        now: datetime,
    ) -> tuple[dict[str, PublicAttentionSnapshot], int]:
        assets: dict[str, list[str]] = {}
        for candidate in candidates:
            asset = _base_asset(candidate.market.symbol)
            assets.setdefault(asset, []).append(candidate.market.symbol)

        results: dict[str, PublicAttentionSnapshot] = {}
        scheduled = 0
        for asset, symbols in assets.items():
            cached = self._public_cache.get(asset)
            if cached is not None and now - cached.observed_at.astimezone(UTC) <= timedelta(
                seconds=self._policy.public_attention_ttl_seconds
            ):
                results[asset] = cached
                continue
            if cached is not None:
                results[asset] = cached.model_copy(update={"research_status": RadarStatus.STALE})
            if self._researcher is None:
                results[asset] = self._public_placeholder(
                    asset,
                    now=now,
                    status=RadarStatus.NOT_CONFIGURED,
                    context="OpenAI web search is not configured.",
                )
                continue
            if scheduled >= self._policy.max_web_searches_per_refresh:
                continue
            scheduled += 1
            try:
                snapshot = await self._researcher.research(
                    asset=asset,
                    symbols=tuple(sorted(set(symbols))),
                    observed_at=now,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                snapshot = self._public_placeholder(
                    asset,
                    now=now,
                    status=RadarStatus.ERROR,
                    context="Public web research failed; market activity remains available.",
                    error_type=type(exc).__name__,
                )
            self._public_cache[asset] = snapshot
            results[asset] = snapshot
        return results, scheduled

    def _public_placeholder(
        self,
        asset: str,
        *,
        now: datetime,
        status: RadarStatus,
        context: str,
        error_type: str | None = None,
    ) -> PublicAttentionSnapshot:
        return PublicAttentionSnapshot(
            asset=asset,
            observed_at=now,
            research_status=status,
            attention_direction=PublicAttentionDirection.UNKNOWN,
            confidence_context=context,
            error_type=error_type,
        )

    def _combine(
        self,
        activity: MarketActivitySnapshot,
        public: PublicAttentionSnapshot,
    ) -> MarketAttentionSnapshot:
        market_unusual = activity.activity_state in {
            MarketActivityState.ELEVATED,
            MarketActivityState.ACCELERATING,
            MarketActivityState.VERY_HIGH,
        }
        public_rising = (
            public.research_status is RadarStatus.AVAILABLE
            and public.attention_direction is PublicAttentionDirection.RISING
        )
        if market_unusual and public_rising:
            cross_state = CrossAttentionState.CONVERGING
            level = AttentionLevel.HIGH
        elif market_unusual:
            cross_state = CrossAttentionState.MARKET_ONLY
            level = (
                AttentionLevel.HIGH
                if activity.activity_state is MarketActivityState.VERY_HIGH
                else AttentionLevel.MEDIUM
            )
        elif public_rising:
            cross_state = CrossAttentionState.PUBLIC_ONLY
            level = AttentionLevel.MEDIUM
        else:
            cross_state = CrossAttentionState.NORMAL
            level = AttentionLevel.NORMAL
        return MarketAttentionSnapshot(
            market_activity=activity,
            public_attention=public,
            cross_state=cross_state,
            attention_level=level,
        )


def _activity_state(
    ratios: Iterable[Decimal | None],
    accelerations: Iterable[Decimal | None],
) -> MarketActivityState:
    usable_ratios = [value for value in ratios if value is not None]
    usable_accelerations = [value for value in accelerations if value is not None]
    if not usable_ratios:
        return MarketActivityState.UNKNOWN
    peak = max(usable_ratios)
    acceleration = max(usable_accelerations, default=Decimal(0))
    if peak >= Decimal("2.50") and acceleration >= Decimal("0.50"):
        return MarketActivityState.VERY_HIGH
    if peak >= Decimal("1.75") and acceleration >= Decimal("0.25"):
        return MarketActivityState.ACCELERATING
    if peak >= Decimal("1.40"):
        return MarketActivityState.ELEVATED
    return MarketActivityState.NORMAL


def _activity_sort_key(snapshot: MarketActivitySnapshot) -> tuple[Decimal, Decimal, Decimal]:
    ratios = [item.volume_ratio for item in snapshot.horizons if item.volume_ratio is not None]
    accelerations = [
        item.volume_acceleration
        for item in snapshot.horizons
        if item.volume_acceleration is not None
    ]
    moves = [abs(item.price_return) for item in snapshot.horizons if item.price_return is not None]
    return (
        max(ratios, default=Decimal(0)),
        max(accelerations, default=Decimal(0)),
        max(moves, default=Decimal(0)),
    )


def _best_ratio_horizon(snapshot: MarketActivitySnapshot) -> ActivityHorizonSnapshot | None:
    eligible = tuple(
        item
        for item in snapshot.horizons
        if item.complete and item.volume_ratio is not None
    )
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda item: (
            item.volume_ratio or Decimal(0),
            item.volume_acceleration or Decimal(0),
            abs(item.price_return) if item.price_return is not None else Decimal(0),
        ),
    )


def _activity_status_counts(
    activities: tuple[MarketActivitySnapshot, ...],
) -> ActivityStatusCounts:
    return ActivityStatusCounts(
        AVAILABLE=sum(item.status is RadarStatus.AVAILABLE for item in activities),
        PARTIAL=sum(item.status is RadarStatus.PARTIAL for item in activities),
        STALE=sum(item.status is RadarStatus.STALE for item in activities),
        ERROR=sum(item.status is RadarStatus.ERROR for item in activities),
    )


def _activity_state_counts(
    activities: tuple[MarketActivitySnapshot, ...],
) -> ActivityStateCounts:
    return ActivityStateCounts(
        UNKNOWN=sum(item.activity_state is MarketActivityState.UNKNOWN for item in activities),
        NORMAL=sum(item.activity_state is MarketActivityState.NORMAL for item in activities),
        ELEVATED=sum(item.activity_state is MarketActivityState.ELEVATED for item in activities),
        ACCELERATING=sum(
            item.activity_state is MarketActivityState.ACCELERATING for item in activities
        ),
        VERY_HIGH=sum(item.activity_state is MarketActivityState.VERY_HIGH for item in activities),
    )


def _snapshot_data_quality(
    horizons: tuple[ActivityHorizonSnapshot, ...],
) -> ActivityDataQuality:
    qualities = {item.data_quality for item in horizons}
    if ActivityDataQuality.TECHNICAL_ERROR in qualities:
        return ActivityDataQuality.TECHNICAL_ERROR
    if ActivityDataQuality.DISCONTINUOUS_HISTORY in qualities:
        return ActivityDataQuality.DISCONTINUOUS_HISTORY
    if ActivityDataQuality.INSUFFICIENT_HISTORY in qualities:
        return ActivityDataQuality.INSUFFICIENT_HISTORY
    if ActivityDataQuality.NO_TRADE_GAPS in qualities:
        return ActivityDataQuality.NO_TRADE_GAPS
    return ActivityDataQuality.COMPLETE


def _activity_data_quality_counts(
    activities: tuple[MarketActivitySnapshot, ...],
) -> ActivityDataQualityCounts:
    return ActivityDataQualityCounts(
        COMPLETE=sum(item.data_quality is ActivityDataQuality.COMPLETE for item in activities),
        NO_TRADE_GAPS=sum(
            item.data_quality is ActivityDataQuality.NO_TRADE_GAPS for item in activities
        ),
        INSUFFICIENT_HISTORY=sum(
            item.data_quality is ActivityDataQuality.INSUFFICIENT_HISTORY for item in activities
        ),
        DISCONTINUOUS_HISTORY=sum(
            item.data_quality is ActivityDataQuality.DISCONTINUOUS_HISTORY for item in activities
        ),
        TECHNICAL_ERROR=sum(
            item.data_quality is ActivityDataQuality.TECHNICAL_ERROR for item in activities
        ),
    )


def _activity_error_counts(
    activities: tuple[MarketActivitySnapshot, ...],
) -> ActivityErrorCounts:
    known = {
        "KrakenConnectionError",
        "KrakenPayloadError",
        "UnknownKrakenSymbolError",
        "CandleValidationError",
    }
    raw = {name: 0 for name in known}
    other = 0
    for item in activities:
        if item.status is not RadarStatus.ERROR:
            continue
        if item.error_type in known:
            raw[item.error_type] += 1  # type: ignore[index]
        else:
            other += 1
    return ActivityErrorCounts(
        KrakenConnectionError=raw["KrakenConnectionError"],
        KrakenPayloadError=raw["KrakenPayloadError"],
        UnknownKrakenSymbolError=raw["UnknownKrakenSymbolError"],
        CandleValidationError=raw["CandleValidationError"],
        Other=other,
    )


def _activity_market_type_status_counts(
    activities: tuple[MarketActivitySnapshot, ...],
) -> ActivityMarketTypeStatusCounts:
    return ActivityMarketTypeStatusCounts(
        SPOT=_activity_status_counts(
            tuple(item for item in activities if item.market.market_type is MarketType.SPOT)
        ),
        PERPETUAL=_activity_status_counts(
            tuple(item for item in activities if item.market.market_type is MarketType.PERPETUAL)
        ),
    )


def _liquidity_regime_counts(
    activities: tuple[MarketActivitySnapshot, ...],
) -> LiquidityRegimeCounts:
    return LiquidityRegimeCounts(
        UNKNOWN=sum(item.liquidity_regime is LiquidityRegime.UNKNOWN for item in activities),
        MICRO=sum(item.liquidity_regime is LiquidityRegime.MICRO for item in activities),
        LOW=sum(item.liquidity_regime is LiquidityRegime.LOW for item in activities),
        MEDIUM=sum(item.liquidity_regime is LiquidityRegime.MEDIUM for item in activities),
        HIGH=sum(item.liquidity_regime is LiquidityRegime.HIGH for item in activities),
        VERY_HIGH=sum(item.liquidity_regime is LiquidityRegime.VERY_HIGH for item in activities),
    )


def _attention_sort_key(
    snapshot: MarketAttentionSnapshot,
) -> tuple[int, int, int, Decimal, Decimal]:
    cross = {
        CrossAttentionState.CONVERGING: 3,
        CrossAttentionState.MARKET_ONLY: 2,
        CrossAttentionState.PUBLIC_ONLY: 1,
        CrossAttentionState.NORMAL: 0,
    }[snapshot.cross_state]
    level = {
        AttentionLevel.HIGH: 2,
        AttentionLevel.MEDIUM: 1,
        AttentionLevel.NORMAL: 0,
    }[snapshot.attention_level]
    source_count = len(snapshot.public_attention.sources)
    ratio, acceleration, _move = _activity_sort_key(snapshot.market_activity)
    return cross, level, source_count, ratio, acceleration


def _overview_status(
    shortlist: tuple[MarketAttentionSnapshot, ...],
    *,
    fresh_activities: tuple[MarketActivitySnapshot, ...],
    researcher_configured: bool,
) -> RadarStatus:
    if not fresh_activities:
        return RadarStatus.PARTIAL

    activity_statuses = {item.status for item in fresh_activities}
    available_count = sum(item.status is RadarStatus.AVAILABLE for item in fresh_activities)
    if available_count == 0:
        if activity_statuses == {RadarStatus.STALE}:
            return RadarStatus.STALE
        if activity_statuses == {RadarStatus.ERROR}:
            return RadarStatus.ERROR
        return RadarStatus.PARTIAL

    if not shortlist:
        return RadarStatus.AVAILABLE
    if not researcher_configured:
        return RadarStatus.PARTIAL
    statuses = {item.public_attention.research_status for item in shortlist}
    if statuses == {RadarStatus.AVAILABLE}:
        return RadarStatus.AVAILABLE
    if RadarStatus.AVAILABLE in statuses:
        return RadarStatus.PARTIAL
    if statuses == {RadarStatus.STALE}:
        return RadarStatus.STALE
    return RadarStatus.PARTIAL


def _spot_usd_notional(
    candles: tuple[Candle, ...],
    *,
    market: ExecutableMarket,
) -> Decimal | None:
    if market.market_type is not MarketType.SPOT:
        return None
    _base, quote = parse_canonical_symbol(market.symbol)
    if quote != "USD":
        return None
    return sum((item.volume * item.close for item in candles), Decimal(0))


def _liquidity_reference_usd(snapshot: MarketActivitySnapshot) -> Decimal | None:
    normalized: list[Decimal] = []
    hour_seconds = Decimal(3600)
    for horizon in snapshot.horizons:
        baseline = horizon.baseline_notional_usd
        if baseline is None or baseline <= 0:
            continue
        duration_seconds = Decimal(str(horizon.timeframe.duration.total_seconds()))
        if duration_seconds <= 0:
            continue
        normalized.append(baseline * hour_seconds / duration_seconds)
    if not normalized:
        return None
    return Decimal(median(normalized))


def _liquidity_regime(
    reference: Decimal | None,
    population: tuple[Decimal, ...],
) -> LiquidityRegime:
    if reference is None or reference < 0 or not population:
        return LiquidityRegime.UNKNOWN
    if len(population) == 1:
        return LiquidityRegime.MEDIUM

    first = population.index(reference)
    last = len(population) - 1 - tuple(reversed(population)).index(reference)
    percentile = Decimal(first + last) / Decimal(2 * (len(population) - 1))
    if percentile < Decimal("0.20"):
        return LiquidityRegime.MICRO
    if percentile < Decimal("0.40"):
        return LiquidityRegime.LOW
    if percentile < Decimal("0.60"):
        return LiquidityRegime.MEDIUM
    if percentile < Decimal("0.80"):
        return LiquidityRegime.HIGH
    return LiquidityRegime.VERY_HIGH


def _safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    try:
        value = numerator / denominator
    except (InvalidOperation, ZeroDivisionError):
        return None
    return value if value.is_finite() else None


def _is_contiguous(candles: tuple[Candle, ...]) -> bool:
    if len(candles) < 2:
        return True
    return all(
        current.open_time.astimezone(UTC) == previous.close_time.astimezone(UTC)
        for previous, current in zip(candles, candles[1:], strict=False)
    )


def _realized_volatility(candles: tuple[Candle, ...]) -> Decimal | None:
    squared = 0.0
    for candle in candles:
        open_value = float(candle.open)
        close_value = float(candle.close)
        if open_value <= 0 or close_value <= 0:
            return None
        value = math.log(close_value / open_value)
        squared += value * value
    return Decimal(str(math.sqrt(squared)))


def _base_asset(symbol: str) -> str:
    base, _quote = parse_canonical_symbol(symbol)
    return base


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _utc(value: datetime) -> datetime:
    _require_aware(value, "timestamp")
    return value.astimezone(UTC)
