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


_KRAKEN_PAYLOAD_STAGES = frozenset(
    {
        "ASSET_PAIRS_PAYLOAD",
        "ASSET_PAIRS_ENTRY",
        "ASSET_PAIRS_SYMBOL",
        "OHLC_RESULT",
        "OHLC_SERIES",
        "OHLC_PAIR_KEY",
        "OHLC_ROW",
        "OHLC_TIMESTAMP",
        "OHLC_NUMERIC",
    }
)


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


class MarketCharacteristic(StrEnum):
    """Descriptive, non-strategic market facts derived only from canonical candles."""

    TRENDING = "TRENDING"
    VOLUME_ANOMALY = "VOLUME_ANOMALY"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    BREAKOUT_WATCH = "BREAKOUT_WATCH"
    REVERSAL_WATCH = "REVERSAL_WATCH"
    CONSOLIDATING = "CONSOLIDATING"
    PRICE_VOLUME_DIVERGENCE = "PRICE_VOLUME_DIVERGENCE"


class RadarInterestLevel(StrEnum):
    """Deterministic attention priority; never a BUY/SELL/HOLD recommendation."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class AttentionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MarketAttentionPolicy(AttentionModel):
    """Bounded Kraken-only observation policy for the deterministic radar."""

    protocol_version: str = "market-attention-radar-v2"
    refresh_seconds: float = Field(default=300.0, ge=30.0, le=86_400.0)
    catalogue_ttl_seconds: float = Field(default=1800.0, ge=60.0, le=86_400.0)
    activity_ttl_seconds: float = Field(default=900.0, ge=60.0, le=86_400.0)
    stale_after_seconds: float = Field(default=900.0, ge=30.0, le=86_400.0)
    scan_limit: int = Field(default=120, ge=10, le=500)
    scan_concurrency: int = Field(default=8, ge=1, le=32)
    candidate_limit: int = Field(default=10, ge=1, le=30)
    diagnostic_market_limit: int = Field(default=10, ge=1, le=30)
    candle_limit: int = Field(default=720, ge=160, le=1000)
    baseline_periods: int = Field(default=6, ge=3, le=20)
    history_limit: int = Field(default=96, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_policy(self) -> "MarketAttentionPolicy":
        if self.protocol_version != "market-attention-radar-v2":
            raise ValueError("unsupported market attention protocol")
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
    previous_price_return: Decimal | None = None
    price_range: Decimal | None = None
    baseline_price_range: Decimal | None = None
    range_expansion_ratio: Decimal | None = None
    realized_volatility: Decimal | None = None
    baseline_realized_volatility: Decimal | None = None
    volatility_expansion_ratio: Decimal | None = None
    breakout_distance: Decimal | None = None
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
    characteristics: tuple[MarketCharacteristic, ...] = ()
    interest_level: RadarInterestLevel = RadarInterestLevel.LOW
    interest_reasons: tuple[str, ...] = ()
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
    KrakenNetworkError: int = Field(default=0, ge=0)
    KrakenTimeoutError: int = Field(default=0, ge=0)
    KrakenHTTPError: int = Field(default=0, ge=0)
    KrakenServerError: int = Field(default=0, ge=0)
    KrakenRateLimitError: int = Field(default=0, ge=0)
    KrakenAPIError: int = Field(default=0, ge=0)
    KrakenPayloadError: int = Field(default=0, ge=0)
    UnknownKrakenSymbolError: int = Field(default=0, ge=0)
    CandleValidationError: int = Field(default=0, ge=0)
    Other: int = Field(default=0, ge=0)


class ActivityPayloadStageCounts(AttentionModel):
    ASSET_PAIRS_PAYLOAD: int = Field(default=0, ge=0)
    ASSET_PAIRS_ENTRY: int = Field(default=0, ge=0)
    ASSET_PAIRS_SYMBOL: int = Field(default=0, ge=0)
    OHLC_RESULT: int = Field(default=0, ge=0)
    OHLC_SERIES: int = Field(default=0, ge=0)
    OHLC_PAIR_KEY: int = Field(default=0, ge=0)
    OHLC_ROW: int = Field(default=0, ge=0)
    OHLC_TIMESTAMP: int = Field(default=0, ge=0)
    OHLC_NUMERIC: int = Field(default=0, ge=0)


class ActivityMarketTypeStatusCounts(AttentionModel):
    SPOT: ActivityStatusCounts = Field(default_factory=ActivityStatusCounts)
    PERPETUAL: ActivityStatusCounts = Field(default_factory=ActivityStatusCounts)


class MarketTypeCounts(AttentionModel):
    SPOT: int = Field(default=0, ge=0)
    PERPETUAL: int = Field(default=0, ge=0)


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


class MarketAttentionSnapshot(AttentionModel):
    market_activity: MarketActivitySnapshot

    @property
    def market(self) -> ExecutableMarket:
        return self.market_activity.market


class MarketAttentionOverview(AttentionModel):
    protocol_version: str = "market-attention-radar-v2"
    observed_at: datetime
    status: RadarStatus
    informative_only: bool = True
    catalogue_market_count: int = Field(default=0, ge=0)
    cached_activity_market_count: int = Field(default=0, ge=0)
    scanned_market_count: int = Field(default=0, ge=0)
    scanned_market_type_counts: MarketTypeCounts = Field(default_factory=MarketTypeCounts)
    fresh_market_type_counts: MarketTypeCounts = Field(default_factory=MarketTypeCounts)
    candidate_market_count: int = Field(default=0, ge=0)
    activity_status_counts: ActivityStatusCounts = Field(default_factory=ActivityStatusCounts)
    activity_state_counts: ActivityStateCounts = Field(default_factory=ActivityStateCounts)
    activity_data_quality_counts: ActivityDataQualityCounts = Field(
        default_factory=ActivityDataQualityCounts
    )
    activity_error_counts: ActivityErrorCounts = Field(default_factory=ActivityErrorCounts)
    activity_payload_stage_counts: ActivityPayloadStageCounts = Field(
        default_factory=ActivityPayloadStageCounts
    )
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
            raise ValueError("Market Attention Radar v2 must remain informative_only")
        return self


class MarketCatalogue(Protocol):
    async def list_markets(self) -> tuple[ExecutableMarket, ...]: ...

    async def aclose(self) -> None: ...


class MarketActivityAnalyzer:
    """Derive descriptive activity facts from canonical finalized 5m OHLCV candles."""

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
        complete_ratios = [item.volume_ratio if item.complete else None for item in horizons]
        complete_accelerations = [
            item.volume_acceleration if item.complete else None for item in horizons
        ]
        activity_state = _activity_state(complete_ratios, complete_accelerations)
        if not all(item.complete for item in horizons):
            status = RadarStatus.PARTIAL
        elif freshness_seconds > Decimal(str(self._stale_after.total_seconds())):
            status = RadarStatus.STALE
        else:
            status = RadarStatus.AVAILABLE
        return _with_market_structure(
            MarketActivitySnapshot(
                market=market,
                observed_at=observed_at,
                status=status,
                activity_state=activity_state,
                freshness_seconds=freshness_seconds,
                horizons=horizons,
                data_quality=_snapshot_data_quality(horizons),
            )
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
            return sum(
                (item.volume if item is not None else Decimal(0) for item in group),
                Decimal(0),
            )

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
        previous_real = real(previous)
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

        price_return = _price_return(current_real)
        previous_price_return = _price_return(previous_real)
        price_range = _price_range(current_real)
        realized_volatility = _realized_volatility(current_real) if current_real else None

        baseline_ranges = tuple(
            value
            for group in baseline_real_groups
            if (value := _price_range(group)) is not None
        )
        baseline_price_range = (
            Decimal(median(baseline_ranges))
            if len(baseline_ranges) == len(baseline_real_groups) and baseline_ranges
            else None
        )
        range_expansion_ratio = (
            _safe_ratio(price_range, baseline_price_range)
            if price_range is not None
            and baseline_price_range is not None
            and baseline_price_range > 0
            else None
        )

        baseline_volatilities = tuple(
            value
            for group in baseline_real_groups
            if (value := _realized_volatility(group)) is not None
        )
        baseline_realized_volatility = (
            Decimal(median(baseline_volatilities))
            if len(baseline_volatilities) == len(baseline_real_groups)
            and baseline_volatilities
            else None
        )
        volatility_expansion_ratio = (
            _safe_ratio(realized_volatility, baseline_realized_volatility)
            if realized_volatility is not None
            and baseline_realized_volatility is not None
            and baseline_realized_volatility > 0
            else None
        )

        breakout_distance: Decimal | None = None
        reference_real = previous_real + tuple(
            candle for group in baseline_real_groups for candle in group
        )
        if current_real and reference_real:
            reference_high = max(item.high for item in reference_real)
            reference_low = min(item.low for item in reference_real)
            last_close = current_real[-1].close
            if last_close > reference_high:
                ratio = _safe_ratio(last_close, reference_high)
                breakout_distance = ratio - Decimal(1) if ratio is not None else None
            elif last_close < reference_low:
                ratio = _safe_ratio(last_close, reference_low)
                breakout_distance = ratio - Decimal(1) if ratio is not None else None
            else:
                breakout_distance = Decimal(0)

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
            previous_price_return=previous_price_return,
            price_range=price_range,
            baseline_price_range=baseline_price_range,
            range_expansion_ratio=range_expansion_ratio,
            realized_volatility=realized_volatility,
            baseline_realized_volatility=baseline_realized_volatility,
            volatility_expansion_ratio=volatility_expansion_ratio,
            breakout_distance=breakout_distance,
            observation_count=len(current_real),
            baseline_period_count=len(baseline_groups),
            no_trade_interval_count=len(missing_opens) if missing_intervals_mean_no_trades else 0,
            unexplained_gap_count=0,
            data_quality=quality,
            complete=volume_ratio is not None,
        )


class MarketAttentionRadar:
    """Independent, fail-soft, Kraken-only deterministic observation service."""

    def __init__(
        self,
        *,
        candle_service: CandleStreamService,
        catalogue: MarketCatalogue,
        policy: MarketAttentionPolicy | None = None,
    ) -> None:
        self._candles = candle_service
        self._catalogue_provider = catalogue
        self._policy = policy or MarketAttentionPolicy()
        self._analyzer = MarketActivityAnalyzer(
            baseline_periods=self._policy.baseline_periods,
            stale_after=timedelta(seconds=self._policy.stale_after_seconds),
        )
        self._catalogue: tuple[ExecutableMarket, ...] = ()
        self._catalogue_at: datetime | None = None
        self._scan_cursors: dict[MarketType, int] = {
            MarketType.SPOT: 0,
            MarketType.PERPETUAL: 0,
        }
        self._activity_cache: dict[ExecutableMarket, MarketActivitySnapshot] = {}
        self._activity_payload_stages: dict[ExecutableMarket, str] = {}
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
            scanned_market_type_counts = MarketTypeCounts()
            try:
                catalogue = await self._catalogue_if_due(now)
                scan_batch = self._next_scan_batch(catalogue)
                scanned_count = len(scan_batch)
                scanned_market_type_counts = _market_type_counts(scan_batch)
                await self._scan_activity(scan_batch, now=now)
                fresh_activities = self._classify_liquidity(self._fresh_activities(now))
                fresh_market_type_counts = _market_type_counts(
                    tuple(snapshot.market for snapshot in fresh_activities)
                )
                status_counts = _activity_status_counts(fresh_activities)
                state_counts = _activity_state_counts(fresh_activities)
                data_quality_counts = _activity_data_quality_counts(fresh_activities)
                error_counts = _activity_error_counts(fresh_activities)
                payload_stage_counts = _activity_payload_stage_counts(
                    fresh_activities, self._activity_payload_stages
                )
                market_type_status_counts = _activity_market_type_status_counts(fresh_activities)
                liquidity_counts = _liquidity_regime_counts(fresh_activities)
                subthreshold_activity = self._subthreshold_activity(fresh_activities)
                candidates = self._candidates_from(fresh_activities)
                shortlist = tuple(
                    MarketAttentionSnapshot(market_activity=activity)
                    for activity in candidates
                )
                overview = MarketAttentionOverview(
                    observed_at=now,
                    status=_overview_status(fresh_activities),
                    informative_only=True,
                    catalogue_market_count=len(catalogue),
                    cached_activity_market_count=len(fresh_activities),
                    scanned_market_count=scanned_count,
                    scanned_market_type_counts=scanned_market_type_counts,
                    fresh_market_type_counts=fresh_market_type_counts,
                    candidate_market_count=len(shortlist),
                    activity_status_counts=status_counts,
                    activity_state_counts=state_counts,
                    activity_data_quality_counts=data_quality_counts,
                    activity_error_counts=error_counts,
                    activity_payload_stage_counts=payload_stage_counts,
                    activity_market_type_status_counts=market_type_status_counts,
                    liquidity_regime_counts=liquidity_counts,
                    subthreshold_activity=subthreshold_activity,
                    shortlist=shortlist,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                fresh_activities = self._classify_liquidity(self._fresh_activities(now))
                fresh_market_type_counts = _market_type_counts(
                    tuple(snapshot.market for snapshot in fresh_activities)
                )
                overview = MarketAttentionOverview(
                    observed_at=now,
                    status=RadarStatus.ERROR,
                    informative_only=True,
                    catalogue_market_count=len(self._catalogue),
                    cached_activity_market_count=len(fresh_activities),
                    scanned_market_count=scanned_count,
                    scanned_market_type_counts=scanned_market_type_counts,
                    fresh_market_type_counts=fresh_market_type_counts,
                    candidate_market_count=0,
                    activity_status_counts=_activity_status_counts(fresh_activities),
                    activity_state_counts=_activity_state_counts(fresh_activities),
                    activity_data_quality_counts=_activity_data_quality_counts(fresh_activities),
                    activity_error_counts=_activity_error_counts(fresh_activities),
                    activity_payload_stage_counts=_activity_payload_stage_counts(
                        fresh_activities, self._activity_payload_stages
                    ),
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
            for market_type in (MarketType.SPOT, MarketType.PERPETUAL):
                population = sum(
                    market.market_type is market_type for market in self._catalogue
                )
                if population:
                    self._scan_cursors[market_type] %= population
                else:
                    self._scan_cursors[market_type] = 0
        return self._catalogue

    def _next_scan_batch(
        self,
        catalogue: tuple[ExecutableMarket, ...],
    ) -> tuple[ExecutableMarket, ...]:
        if not catalogue:
            return ()

        families = {
            market_type: tuple(
                market for market in catalogue if market.market_type is market_type
            )
            for market_type in (MarketType.SPOT, MarketType.PERPETUAL)
        }
        allocations = _scan_allocations(
            {market_type: len(markets) for market_type, markets in families.items()},
            limit=self._policy.scan_limit,
        )
        selected: list[ExecutableMarket] = []
        for market_type in (MarketType.SPOT, MarketType.PERPETUAL):
            family = families[market_type]
            count = allocations[market_type]
            if not family or count <= 0:
                continue
            start = self._scan_cursors[market_type] % len(family)
            selected.extend(
                family[(start + offset) % len(family)] for offset in range(count)
            )
            self._scan_cursors[market_type] = (start + count) % len(family)
        return tuple(selected)

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
                payload_stage: str | None = None
                try:
                    candles = await self._candles.history(
                        key,
                        limit=self._policy.candle_limit,
                    )
                    snapshot = self._analyzer.analyze(
                        market=market,
                        candles=candles,
                        observed_at=now,
                        missing_intervals_mean_no_trades=(market.market_type is MarketType.SPOT),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    payload_stage = _safe_payload_stage(exc)
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
                if payload_stage is None:
                    self._activity_payload_stages.pop(market, None)
                else:
                    self._activity_payload_stages[market] = payload_stage
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
            reference_by_market[snapshot.market] = _liquidity_reference_usd(snapshot)
        for market_type in (MarketType.SPOT, MarketType.PERPETUAL):
            values = tuple(
                reference
                for snapshot in activities
                if snapshot.market.market_type is market_type
                and (reference := reference_by_market[snapshot.market]) is not None
            )
            references[market_type] = tuple(sorted(values))

        classified: list[MarketActivitySnapshot] = []
        for snapshot in activities:
            with_liquidity = snapshot.model_copy(
                update={
                    "liquidity_reference_usd": reference_by_market[snapshot.market],
                    "liquidity_regime": _liquidity_regime(
                        reference_by_market[snapshot.market],
                        references[snapshot.market.market_type],
                    ),
                }
            )
            classified.append(_with_market_structure(with_liquidity))
        return tuple(classified)

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
            and (
                snapshot.activity_state in unusual_states
                or _interest_rank(snapshot.interest_level)
                >= _interest_rank(RadarInterestLevel.MEDIUM)
            )
        )
        if not eligible:
            return ()

        ranked = tuple(sorted(eligible, key=_deterministic_radar_sort_key, reverse=True))
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
        return tuple(sorted(chosen, key=_deterministic_radar_sort_key, reverse=True))

    def _subthreshold_activity(
        self,
        activities: tuple[MarketActivitySnapshot, ...],
    ) -> tuple[SubthresholdActivitySnapshot, ...]:
        diagnostics: list[
            tuple[tuple[Decimal, Decimal, Decimal], SubthresholdActivitySnapshot]
        ] = []
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


_MATERIAL_RETURN = {
    CandleTimeframe.M5: Decimal("0.003"),
    CandleTimeframe.M15: Decimal("0.005"),
    CandleTimeframe.H1: Decimal("0.010"),
    CandleTimeframe.H4: Decimal("0.020"),
}


def _price_return(candles: tuple[Candle, ...]) -> Decimal | None:
    if not candles:
        return None
    ratio = _safe_ratio(candles[-1].close, candles[0].open)
    return ratio - Decimal(1) if ratio is not None else None


def _price_range(candles: tuple[Candle, ...]) -> Decimal | None:
    if not candles:
        return None
    high = max(item.high for item in candles)
    low = min(item.low for item in candles)
    ratio = _safe_ratio(high, low)
    return ratio - Decimal(1) if ratio is not None else None


def _interest_rank(level: RadarInterestLevel) -> int:
    return {
        RadarInterestLevel.LOW: 0,
        RadarInterestLevel.MEDIUM: 1,
        RadarInterestLevel.HIGH: 2,
        RadarInterestLevel.VERY_HIGH: 3,
    }[level]


def _market_characteristics(snapshot: MarketActivitySnapshot) -> tuple[MarketCharacteristic, ...]:
    complete = tuple(item for item in snapshot.horizons if item.complete)
    if not complete:
        return ()
    found: set[MarketCharacteristic] = set()

    if any(
        item.volume_ratio is not None and item.volume_ratio >= Decimal("1.40")
        for item in complete
    ):
        found.add(MarketCharacteristic.VOLUME_ANOMALY)

    if any(
        (item.range_expansion_ratio is not None and item.range_expansion_ratio >= Decimal("1.50"))
        or (
            item.volatility_expansion_ratio is not None
            and item.volatility_expansion_ratio >= Decimal("1.50")
        )
        for item in complete
    ):
        found.add(MarketCharacteristic.VOLATILITY_EXPANSION)

    material_returns = []
    for item in complete:
        value = item.price_return
        threshold = _MATERIAL_RETURN.get(item.timeframe, Decimal("0.01"))
        if value is not None and abs(value) >= threshold:
            material_returns.append(value)
    positive = sum(value > 0 for value in material_returns)
    negative = sum(value < 0 for value in material_returns)
    if max(positive, negative) >= 2:
        found.add(MarketCharacteristic.TRENDING)

    if any(
        item.breakout_distance is not None
        and abs(item.breakout_distance)
        >= max(
            Decimal("0.0025"),
            _MATERIAL_RETURN.get(item.timeframe, Decimal("0.01")) / Decimal(2),
        )
        and item.price_return is not None
        and abs(item.price_return) >= _MATERIAL_RETURN.get(item.timeframe, Decimal("0.01"))
        and (
            (item.volume_ratio is not None and item.volume_ratio >= Decimal("1.20"))
            or (
                item.range_expansion_ratio is not None
                and item.range_expansion_ratio >= Decimal("1.20")
            )
        )
        for item in complete
    ):
        found.add(MarketCharacteristic.BREAKOUT_WATCH)

    if any(
        item.price_return is not None
        and item.previous_price_return is not None
        and item.price_return * item.previous_price_return < 0
        and abs(item.price_return) >= _MATERIAL_RETURN.get(item.timeframe, Decimal("0.01"))
        and abs(item.previous_price_return)
        >= _MATERIAL_RETURN.get(item.timeframe, Decimal("0.01"))
        and (
            (item.volume_ratio is not None and item.volume_ratio >= Decimal("1.30"))
            or (
                item.range_expansion_ratio is not None
                and item.range_expansion_ratio >= Decimal("1.30")
            )
        )
        for item in complete
    ):
        found.add(MarketCharacteristic.REVERSAL_WATCH)

    compressed = sum(
        item.range_expansion_ratio is not None
        and item.range_expansion_ratio <= Decimal("0.70")
        and (item.volume_ratio is None or item.volume_ratio <= Decimal("1.20"))
        for item in complete
    )
    if compressed >= 2:
        found.add(MarketCharacteristic.CONSOLIDATING)

    if any(
        (
            item.price_return is not None
            and abs(item.price_return) >= _MATERIAL_RETURN.get(item.timeframe, Decimal("0.01"))
            and item.volume_ratio is not None
            and item.volume_ratio <= Decimal("0.75")
        )
        or (
            item.volume_ratio is not None
            and item.volume_ratio >= Decimal("2.00")
            and item.price_return is not None
            and abs(item.price_return)
            < _MATERIAL_RETURN.get(item.timeframe, Decimal("0.01")) / Decimal(2)
        )
        for item in complete
    ):
        found.add(MarketCharacteristic.PRICE_VOLUME_DIVERGENCE)

    order = tuple(MarketCharacteristic)
    return tuple(item for item in order if item in found)


def _interest_level_and_reasons(
    snapshot: MarketActivitySnapshot,
    characteristics: tuple[MarketCharacteristic, ...],
) -> tuple[RadarInterestLevel, tuple[str, ...]]:
    if snapshot.status is not RadarStatus.AVAILABLE:
        return RadarInterestLevel.LOW, ("Données insuffisantes ou non fraîches",)

    score = 0
    reasons: list[str] = []
    weights = {
        MarketCharacteristic.VOLUME_ANOMALY: 1,
        MarketCharacteristic.VOLATILITY_EXPANSION: 1,
        MarketCharacteristic.TRENDING: 1,
        MarketCharacteristic.BREAKOUT_WATCH: 2,
        MarketCharacteristic.REVERSAL_WATCH: 2,
        MarketCharacteristic.CONSOLIDATING: 0,
        MarketCharacteristic.PRICE_VOLUME_DIVERGENCE: 1,
    }
    labels = {
        MarketCharacteristic.VOLUME_ANOMALY: "Volume inhabituel",
        MarketCharacteristic.VOLATILITY_EXPANSION: "Volatilité en expansion",
        MarketCharacteristic.TRENDING: "Tendance cohérente sur plusieurs horizons",
        MarketCharacteristic.BREAKOUT_WATCH: "Sortie de zone à surveiller",
        MarketCharacteristic.REVERSAL_WATCH: "Retournement potentiel à surveiller",
        MarketCharacteristic.CONSOLIDATING: "Consolidation",
        MarketCharacteristic.PRICE_VOLUME_DIVERGENCE: "Divergence prix/volume",
    }
    for characteristic in characteristics:
        score += weights[characteristic]
        if weights[characteristic] > 0:
            reasons.append(labels[characteristic])

    if snapshot.activity_state is MarketActivityState.ACCELERATING:
        score += 1
        reasons.append("Activité en accélération")
    elif snapshot.activity_state is MarketActivityState.VERY_HIGH:
        score += 2
        reasons.append("Activité très élevée")

    if snapshot.liquidity_regime in {LiquidityRegime.HIGH, LiquidityRegime.VERY_HIGH}:
        score += 1
        reasons.append("Liquidité relative élevée")
    elif snapshot.liquidity_regime is LiquidityRegime.MICRO:
        score = max(0, score - 1)
        reasons.append("Liquidité relative très faible")

    if score >= 5:
        level = RadarInterestLevel.VERY_HIGH
    elif score >= 3:
        level = RadarInterestLevel.HIGH
    elif score >= 2:
        level = RadarInterestLevel.MEDIUM
    else:
        level = RadarInterestLevel.LOW
    return level, tuple(dict.fromkeys(reasons))[:5]


def _with_market_structure(snapshot: MarketActivitySnapshot) -> MarketActivitySnapshot:
    characteristics = _market_characteristics(snapshot)
    level, reasons = _interest_level_and_reasons(snapshot, characteristics)
    return snapshot.model_copy(
        update={
            "characteristics": characteristics,
            "interest_level": level,
            "interest_reasons": reasons,
        }
    )


def _deterministic_radar_sort_key(
    snapshot: MarketActivitySnapshot,
) -> tuple[int, int, int, Decimal, Decimal, Decimal, str]:
    characteristic_priority = sum(
        {
            MarketCharacteristic.BREAKOUT_WATCH: 4,
            MarketCharacteristic.REVERSAL_WATCH: 4,
            MarketCharacteristic.TRENDING: 2,
            MarketCharacteristic.VOLATILITY_EXPANSION: 2,
            MarketCharacteristic.VOLUME_ANOMALY: 1,
            MarketCharacteristic.PRICE_VOLUME_DIVERGENCE: 1,
            MarketCharacteristic.CONSOLIDATING: 0,
        }[item]
        for item in snapshot.characteristics
    )
    liquidity = {
        LiquidityRegime.UNKNOWN: 0,
        LiquidityRegime.MICRO: 0,
        LiquidityRegime.LOW: 1,
        LiquidityRegime.MEDIUM: 2,
        LiquidityRegime.HIGH: 3,
        LiquidityRegime.VERY_HIGH: 4,
    }[snapshot.liquidity_regime]
    ratio, acceleration, move = _activity_sort_key(snapshot)
    return (
        _interest_rank(snapshot.interest_level),
        characteristic_priority,
        liquidity,
        ratio,
        acceleration,
        move,
        snapshot.market.symbol,
    )


def _activity_state(
    ratios: Iterable[Decimal | None],
    accelerations: Iterable[Decimal | None],
) -> MarketActivityState:
    ratio_values = tuple(ratios)
    acceleration_values = tuple(accelerations)
    if not any(value is not None for value in ratio_values):
        return MarketActivityState.UNKNOWN

    pairs = tuple(
        (
            ratio,
            acceleration_values[index] if index < len(acceleration_values) else None,
        )
        for index, ratio in enumerate(ratio_values)
        if ratio is not None
    )
    if any(
        ratio >= Decimal("2.50")
        and acceleration is not None
        and acceleration >= Decimal("0.50")
        for ratio, acceleration in pairs
    ):
        return MarketActivityState.VERY_HIGH
    if any(
        ratio >= Decimal("1.75")
        and acceleration is not None
        and acceleration >= Decimal("0.25")
        for ratio, acceleration in pairs
    ):
        return MarketActivityState.ACCELERATING
    if any(ratio >= Decimal("1.40") for ratio, _acceleration in pairs):
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


def _scan_allocations(
    populations: dict[MarketType, int],
    *,
    limit: int,
) -> dict[MarketType, int]:
    """Allocate a bounded scan proportionally while representing every available family."""

    market_types = (MarketType.SPOT, MarketType.PERPETUAL)
    allocation = {market_type: 0 for market_type in market_types}
    available = tuple(
        market_type for market_type in market_types if populations.get(market_type, 0) > 0
    )
    total_population = sum(populations.get(market_type, 0) for market_type in available)
    target = min(limit, total_population)
    if target <= 0:
        return allocation
    if target < len(available):
        for market_type in available[:target]:
            allocation[market_type] = 1
        return allocation

    exact = {
        market_type: Decimal(target) * Decimal(populations[market_type]) / Decimal(total_population)
        for market_type in available
    }
    for market_type in available:
        allocation[market_type] = min(
            populations[market_type],
            max(1, int(exact[market_type])),
        )

    remaining = target - sum(allocation.values())
    order = {market_type: index for index, market_type in enumerate(market_types)}
    while remaining > 0:
        candidates = tuple(
            market_type
            for market_type in available
            if allocation[market_type] < populations[market_type]
        )
        if not candidates:
            break
        chosen = max(
            candidates,
            key=lambda market_type: (
                exact[market_type] - Decimal(allocation[market_type]),
                populations[market_type] - allocation[market_type],
                -order[market_type],
            ),
        )
        allocation[chosen] += 1
        remaining -= 1
    return allocation


def _market_type_counts(markets: Iterable[ExecutableMarket]) -> MarketTypeCounts:
    counts = {MarketType.SPOT: 0, MarketType.PERPETUAL: 0}
    for market in markets:
        if market.market_type in counts:
            counts[market.market_type] += 1
    return MarketTypeCounts(
        SPOT=counts[MarketType.SPOT],
        PERPETUAL=counts[MarketType.PERPETUAL],
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
        "KrakenNetworkError",
        "KrakenTimeoutError",
        "KrakenHTTPError",
        "KrakenServerError",
        "KrakenRateLimitError",
        "KrakenAPIError",
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
        KrakenNetworkError=raw["KrakenNetworkError"],
        KrakenTimeoutError=raw["KrakenTimeoutError"],
        KrakenHTTPError=raw["KrakenHTTPError"],
        KrakenServerError=raw["KrakenServerError"],
        KrakenRateLimitError=raw["KrakenRateLimitError"],
        KrakenAPIError=raw["KrakenAPIError"],
        KrakenPayloadError=raw["KrakenPayloadError"],
        UnknownKrakenSymbolError=raw["UnknownKrakenSymbolError"],
        CandleValidationError=raw["CandleValidationError"],
        Other=other,
    )


def _safe_payload_stage(exc: Exception) -> str | None:
    if type(exc).__name__ != "KrakenPayloadError":
        return None
    stage = getattr(exc, "stage", None)
    if isinstance(stage, StrEnum):
        stage = stage.value
    if not isinstance(stage, str):
        return None
    normalized = stage.strip().upper()
    return normalized if normalized in _KRAKEN_PAYLOAD_STAGES else None


def _activity_payload_stage_counts(
    activities: tuple[MarketActivitySnapshot, ...],
    stage_by_market: dict[ExecutableMarket, str],
) -> ActivityPayloadStageCounts:
    raw = {stage: 0 for stage in _KRAKEN_PAYLOAD_STAGES}
    for item in activities:
        if item.status is not RadarStatus.ERROR or item.error_type != "KrakenPayloadError":
            continue
        stage = stage_by_market.get(item.market)
        if stage in raw:
            raw[stage] += 1  # type: ignore[index]
    return ActivityPayloadStageCounts(
        ASSET_PAIRS_PAYLOAD=raw["ASSET_PAIRS_PAYLOAD"],
        ASSET_PAIRS_ENTRY=raw["ASSET_PAIRS_ENTRY"],
        ASSET_PAIRS_SYMBOL=raw["ASSET_PAIRS_SYMBOL"],
        OHLC_RESULT=raw["OHLC_RESULT"],
        OHLC_SERIES=raw["OHLC_SERIES"],
        OHLC_PAIR_KEY=raw["OHLC_PAIR_KEY"],
        OHLC_ROW=raw["OHLC_ROW"],
        OHLC_TIMESTAMP=raw["OHLC_TIMESTAMP"],
        OHLC_NUMERIC=raw["OHLC_NUMERIC"],
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


def _overview_status(
    fresh_activities: tuple[MarketActivitySnapshot, ...],
) -> RadarStatus:
    if not fresh_activities:
        return RadarStatus.PARTIAL

    statuses = {item.status for item in fresh_activities}
    available_count = sum(item.status is RadarStatus.AVAILABLE for item in fresh_activities)
    if available_count == 0:
        if statuses == {RadarStatus.STALE}:
            return RadarStatus.STALE
        if statuses == {RadarStatus.ERROR}:
            return RadarStatus.ERROR
        return RadarStatus.PARTIAL
    if any(item.status is not RadarStatus.AVAILABLE for item in fresh_activities):
        return RadarStatus.PARTIAL
    return RadarStatus.AVAILABLE


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


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _utc(value: datetime) -> datetime:
    _require_aware(value, "timestamp")
    return value.astimezone(UTC)
