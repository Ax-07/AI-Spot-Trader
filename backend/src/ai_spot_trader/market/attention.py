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
    price_return: Decimal | None = None
    price_range: Decimal | None = None
    realized_volatility: Decimal | None = None
    observation_count: int = Field(ge=0)
    baseline_period_count: int = Field(ge=0)
    complete: bool


class MarketActivitySnapshot(AttentionModel):
    market: ExecutableMarket
    observed_at: datetime
    status: RadarStatus
    activity_state: MarketActivityState
    freshness_seconds: Decimal | None = Field(default=None, ge=0)
    horizons: tuple[ActivityHorizonSnapshot, ...]
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_snapshot(self) -> "MarketActivitySnapshot":
        _require_aware(self.observed_at, "market activity observed_at")
        return self

    def horizon(self, timeframe: CandleTimeframe) -> ActivityHorizonSnapshot | None:
        return next((item for item in self.horizons if item.timeframe is timeframe), None)


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
            return MarketActivitySnapshot(
                market=market,
                observed_at=observed_at,
                status=RadarStatus.PARTIAL,
                activity_state=MarketActivityState.UNKNOWN,
                freshness_seconds=None,
                horizons=tuple(
                    self._empty_horizon(timeframe) for timeframe in self.HORIZONS
                ),
            )

        freshness_seconds = Decimal(
            str(max(0.0, (observed_at - final[-1].close_time.astimezone(UTC)).total_seconds()))
        )
        horizons = tuple(self._horizon(final, timeframe) for timeframe in self.HORIZONS)
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
        )

    def _empty_horizon(self, timeframe: CandleTimeframe) -> ActivityHorizonSnapshot:
        return ActivityHorizonSnapshot(
            timeframe=timeframe,
            observation_count=0,
            baseline_period_count=0,
            complete=False,
        )

    def _horizon(
        self,
        candles: tuple[Candle, ...],
        timeframe: CandleTimeframe,
    ) -> ActivityHorizonSnapshot:
        bars = int(timeframe.duration / CandleTimeframe.M5.duration)
        required = bars * (self._baseline_periods + 2)
        if len(candles) < required:
            return ActivityHorizonSnapshot(
                timeframe=timeframe,
                observation_count=min(len(candles), bars),
                baseline_period_count=max(0, (len(candles) // bars) - 2),
                complete=False,
            )

        comparable_tail = candles[-required:]
        if not _is_contiguous(comparable_tail):
            return ActivityHorizonSnapshot(
                timeframe=timeframe,
                observation_count=min(len(candles), bars),
                baseline_period_count=max(0, (len(candles) // bars) - 2),
                complete=False,
            )

        current = comparable_tail[-bars:]
        previous = comparable_tail[-2 * bars : -bars]
        baseline_pool = comparable_tail[: -2 * bars]
        baseline_groups = tuple(
            baseline_pool[index : index + bars]
            for index in range(0, len(baseline_pool), bars)
        )
        baseline_groups = tuple(group for group in baseline_groups if len(group) == bars)
        if len(baseline_groups) < 3:
            return ActivityHorizonSnapshot(
                timeframe=timeframe,
                observation_count=len(current),
                baseline_period_count=len(baseline_groups),
                complete=False,
            )

        current_volume = sum((item.volume for item in current), Decimal(0))
        previous_volume = sum((item.volume for item in previous), Decimal(0))
        baseline_volumes = tuple(
            sum((item.volume for item in group), Decimal(0)) for group in baseline_groups
        )
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
        price_return = _safe_ratio(current[-1].close, current[0].open)
        price_return = price_return - Decimal(1) if price_return is not None else None
        high = max(item.high for item in current)
        low = min(item.low for item in current)
        price_range = _safe_ratio(high, low)
        price_range = price_range - Decimal(1) if price_range is not None else None
        realized_volatility = _realized_volatility(current)
        return ActivityHorizonSnapshot(
            timeframe=timeframe,
            current_volume=current_volume,
            previous_comparable_volume=previous_volume,
            baseline_volume=baseline_volume,
            volume_ratio=volume_ratio,
            volume_change=volume_change,
            volume_acceleration=volume_acceleration,
            price_return=price_return,
            price_range=price_range,
            realized_volatility=realized_volatility,
            observation_count=len(current),
            baseline_period_count=len(baseline_groups),
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
                candidates = self._candidates(now)
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
                    researcher_configured=self._researcher is not None,
                )
                overview = MarketAttentionOverview(
                    observed_at=now,
                    status=status,
                    informative_only=True,
                    catalogue_market_count=len(catalogue),
                    cached_activity_market_count=len(self._fresh_activities(now)),
                    scanned_market_count=scanned_count,
                    candidate_market_count=len(shortlist),
                    web_search_count=web_search_count,
                    shortlist=shortlist,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                overview = MarketAttentionOverview(
                    observed_at=now,
                    status=RadarStatus.ERROR,
                    informative_only=True,
                    catalogue_market_count=len(self._catalogue),
                    cached_activity_market_count=len(self._fresh_activities(now)),
                    scanned_market_count=scanned_count,
                    candidate_market_count=0,
                    web_search_count=web_search_count,
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

    def _candidates(self, now: datetime) -> tuple[MarketActivitySnapshot, ...]:
        unusual_states = {
            MarketActivityState.ELEVATED,
            MarketActivityState.ACCELERATING,
            MarketActivityState.VERY_HIGH,
        }
        eligible = tuple(
            snapshot
            for snapshot in self._fresh_activities(now)
            if snapshot.status is RadarStatus.AVAILABLE
            and snapshot.activity_state in unusual_states
        )
        return tuple(
            sorted(eligible, key=_activity_sort_key, reverse=True)[: self._policy.candidate_limit]
        )

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
    researcher_configured: bool,
) -> RadarStatus:
    if not shortlist:
        return RadarStatus.PARTIAL
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
