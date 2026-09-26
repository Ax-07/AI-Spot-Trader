from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.symbols import parse_canonical_symbol


class CandleError(RuntimeError):
    """Base error for the canonical candle pipeline."""


class CandleValidationError(CandleError):
    """Raised when a candle request violates the bounded contract."""


class CandleCapacityError(CandleError):
    """Raised when the bounded number of active backend streams is exhausted."""


class CandleCausalityError(CandleError):
    """Raised when provider data would introduce future/look-ahead information."""


class CandleTimeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    H12 = "12h"
    D1 = "1d"
    W1 = "1w"
    D15 = "15d"

    @property
    def duration(self) -> timedelta:
        return {
            CandleTimeframe.M1: timedelta(minutes=1),
            CandleTimeframe.M5: timedelta(minutes=5),
            CandleTimeframe.M15: timedelta(minutes=15),
            CandleTimeframe.M30: timedelta(minutes=30),
            CandleTimeframe.H1: timedelta(hours=1),
            CandleTimeframe.H4: timedelta(hours=4),
            CandleTimeframe.H12: timedelta(hours=12),
            CandleTimeframe.D1: timedelta(days=1),
            CandleTimeframe.W1: timedelta(days=7),
            CandleTimeframe.D15: timedelta(days=15),
        }[self]

    @property
    def spot_interval_minutes(self) -> int:
        value = {
            CandleTimeframe.M1: 1,
            CandleTimeframe.M5: 5,
            CandleTimeframe.M15: 15,
            CandleTimeframe.M30: 30,
            CandleTimeframe.H1: 60,
            CandleTimeframe.H4: 240,
            CandleTimeframe.D1: 1440,
            CandleTimeframe.W1: 10080,
            CandleTimeframe.D15: 21600,
        }.get(self)
        if value is None:
            raise CandleValidationError(f"{self.value} is not supported by Kraken Spot OHLC")
        return value

    @property
    def futures_resolution(self) -> str:
        if self is CandleTimeframe.D15:
            raise CandleValidationError("15d is not supported by Kraken Futures charts")
        return self.value

    def validate_market_type(self, market_type: MarketType) -> None:
        if market_type is MarketType.SPOT:
            _ = self.spot_interval_minutes
            return
        if market_type is MarketType.PERPETUAL:
            _ = self.futures_resolution
            return
        raise CandleValidationError("candles are exposed for SPOT and PERPETUAL only")


class CandleKey(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    symbol: str = Field(min_length=3, max_length=64)
    market_type: MarketType
    timeframe: CandleTimeframe

    @model_validator(mode="after")
    def validate_key(self) -> "CandleKey":
        parse_canonical_symbol(self.symbol)
        if self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must use the canonical uppercase BASE/QUOTE form")
        self.timeframe.validate_market_type(self.market_type)
        return self


class Candle(BaseModel):
    """Provider-normalized OHLCV candle with explicit causal state."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    symbol: str = Field(min_length=3, max_length=64)
    market_type: MarketType
    timeframe: CandleTimeframe
    open_time: datetime
    close_time: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)
    is_final: bool
    updated_at: datetime

    @model_validator(mode="after")
    def validate_candle(self) -> "Candle":
        parse_canonical_symbol(self.symbol)
        if self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must use the canonical uppercase BASE/QUOTE form")
        self.timeframe.validate_market_type(self.market_type)
        for value, label in (
            (self.open_time, "open_time"),
            (self.close_time, "close_time"),
            (self.updated_at, "updated_at"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{label} must be timezone-aware")
        open_time = self.open_time.astimezone(UTC)
        close_time = self.close_time.astimezone(UTC)
        updated_at = self.updated_at.astimezone(UTC)
        if close_time - open_time != self.timeframe.duration:
            raise ValueError("candle close_time must equal open_time + timeframe")
        if updated_at < open_time:
            raise ValueError("updated_at cannot be older than open_time")
        if self.is_final and updated_at < close_time:
            raise ValueError("final candle cannot be available before close_time")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("OHLC bounds are inconsistent")
        if self.low > self.high:
            raise ValueError("low cannot be greater than high")
        return self

    @property
    def key(self) -> CandleKey:
        return CandleKey(
            symbol=self.symbol,
            market_type=self.market_type,
            timeframe=self.timeframe,
        )


class CandleStreamStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    key: CandleKey
    connected: bool
    stale: bool
    last_update_at: datetime | None = None
    last_error: str | None = None


class CandleProvider(Protocol):
    async def fetch_history(
        self,
        key: CandleKey,
        *,
        limit: int,
        before: datetime,
    ) -> tuple[Candle, ...]: ...

    def stream(self, key: CandleKey) -> AsyncIterator[Candle]: ...

    async def aclose(self) -> None: ...


class CandleCache:
    """Bounded process-local cache keyed by canonical market + timeframe."""

    def __init__(self, *, max_depth: int = 1000) -> None:
        if isinstance(max_depth, bool) or max_depth <= 0:
            raise ValueError("max_depth must be a positive integer")
        self._max_depth = max_depth
        self._series: dict[CandleKey, OrderedDict[datetime, Candle]] = {}

    @property
    def max_depth(self) -> int:
        return self._max_depth

    def upsert(self, candle: Candle, *, now: datetime) -> bool:
        now = _utc(now, label="cache clock")
        if candle.open_time.astimezone(UTC) > now:
            raise CandleCausalityError("future candle open_time rejected")
        series = self._series.setdefault(candle.key, OrderedDict())
        open_time = candle.open_time.astimezone(UTC)
        existing = series.get(open_time)
        if existing is not None:
            if existing.is_final and not candle.is_final:
                return False
            if candle.updated_at.astimezone(UTC) < existing.updated_at.astimezone(UTC):
                return False
            if candle == existing:
                return False
        series[open_time] = candle
        ordered = OrderedDict(sorted(series.items(), key=lambda item: item[0]))
        while len(ordered) > self._max_depth:
            ordered.popitem(last=False)
        self._series[candle.key] = ordered
        return True

    def merge(self, candles: tuple[Candle, ...], *, now: datetime) -> tuple[Candle, ...]:
        changed: list[Candle] = []
        for candle in sorted(candles, key=lambda item: item.open_time):
            if self.upsert(candle, now=now):
                changed.append(candle)
        return tuple(changed)

    def history(self, key: CandleKey, *, limit: int | None = None) -> tuple[Candle, ...]:
        values = tuple(self._series.get(key, {}).values())
        if limit is None or limit >= len(values):
            return values
        if limit <= 0:
            return ()
        return values[-limit:]

    def history_as_of(
        self,
        key: CandleKey,
        *,
        as_of: datetime,
        limit: int | None = None,
    ) -> tuple[Candle, ...]:
        """Return only cache observations that were knowable at ``as_of``."""

        as_of = _utc(as_of, label="history as_of")
        values = tuple(
            candle
            for candle in self._series.get(key, {}).values()
            if _candle_is_causal_at(candle, as_of=as_of)
        )
        if limit is None or limit >= len(values):
            return values
        if limit <= 0:
            return ()
        return values[-limit:]

    def latest(self, key: CandleKey) -> Candle | None:
        series = self._series.get(key)
        if not series:
            return None
        return next(reversed(series.values()))


class CandleStreamService:
    """Backend-owned history/cache/stream hub shared by all candle consumers."""

    def __init__(
        self,
        provider: CandleProvider,
        *,
        cache: CandleCache | None = None,
        max_streams: int = 32,
        subscriber_queue_size: int = 256,
        stale_after: timedelta = timedelta(seconds=90),
        reconnect_delay_seconds: float = 1.0,
    ) -> None:
        if max_streams <= 0 or subscriber_queue_size <= 0:
            raise ValueError("stream bounds must be positive")
        self._provider = provider
        self._cache = cache or CandleCache()
        self._max_streams = max_streams
        self._subscriber_queue_size = subscriber_queue_size
        self._stale_after = stale_after
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._tasks: dict[CandleKey, asyncio.Task[None]] = {}
        self._subscribers: dict[CandleKey, set[asyncio.Queue[Candle]]] = {}
        self._locks: dict[CandleKey, asyncio.Lock] = {}
        self._connected: set[CandleKey] = set()
        self._last_update: dict[CandleKey, datetime] = {}
        self._last_error: dict[CandleKey, str] = {}
        self._closed = False

    @property
    def cache(self) -> CandleCache:
        return self._cache

    async def history(self, key: CandleKey, *, limit: int = 1000) -> tuple[Candle, ...]:
        self._validate_limit(limit)
        await self._backfill(key, limit=limit)
        return self._cache.history(key, limit=limit)

    async def history_as_of(
        self,
        key: CandleKey,
        *,
        as_of: datetime,
        limit: int = 1000,
    ) -> tuple[Candle, ...]:
        """Read a causal bounded history for a decision-time snapshot.

        Provider history requested after ``as_of`` may only contribute finalized candles whose
        close and provider availability timestamps were already knowable by ``as_of``. A cached
        non-final candle is accepted only when its own ``updated_at`` proves it existed by then.
        """

        self._validate_limit(limit)
        as_of = _utc(as_of, label="history as_of")
        cached = self._cache.history_as_of(key, as_of=as_of, limit=limit)
        last_closed_boundary = floor_time(as_of, key.timeframe)
        latest_final_close = max(
            (
                candle.close_time.astimezone(UTC)
                for candle in cached
                if candle.is_final
            ),
            default=None,
        )
        if len(cached) < limit or latest_final_close != last_closed_boundary:
            await self._backfill_as_of(key, limit=limit, as_of=as_of)
        return self._cache.history_as_of(key, as_of=as_of, limit=limit)

    async def subscribe(
        self,
        key: CandleKey,
        *,
        history_limit: int = 1000,
    ) -> AsyncIterator[Candle]:
        await self.history(key, limit=history_limit)
        queue: asyncio.Queue[Candle] = asyncio.Queue(maxsize=self._subscriber_queue_size)
        self._subscribers.setdefault(key, set()).add(queue)
        await self._ensure_stream(key)
        try:
            while not self._closed:
                yield await queue.get()
        finally:
            subscribers = self._subscribers.get(key)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(key, None)

    def status(self, key: CandleKey, *, now: datetime | None = None) -> CandleStreamStatus:
        current = _utc(now or datetime.now(UTC), label="status clock")
        last_update = self._last_update.get(key)
        stale = last_update is None or current - last_update > self._stale_after
        return CandleStreamStatus(
            key=key,
            connected=key in self._connected,
            stale=stale,
            last_update_at=last_update,
            last_error=self._last_error.get(key),
        )

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._subscribers.clear()
        await self._provider.aclose()

    def _validate_limit(self, limit: int) -> None:
        if isinstance(limit, bool) or limit <= 0 or limit > self._cache.max_depth:
            raise CandleValidationError(
                f"limit must be between 1 and {self._cache.max_depth}"
            )

    async def _ensure_stream(self, key: CandleKey) -> None:
        existing = self._tasks.get(key)
        if existing is not None and not existing.done():
            return
        if len([task for task in self._tasks.values() if not task.done()]) >= self._max_streams:
            raise CandleCapacityError("maximum number of backend candle streams reached")
        self._tasks[key] = asyncio.create_task(
            self._run_stream(key),
            name=f"candle-stream:{key.market_type.value}:{key.symbol}:{key.timeframe.value}",
        )

    async def _run_stream(self, key: CandleKey) -> None:
        while not self._closed:
            try:
                await self._backfill(key, limit=self._cache.max_depth, publish=True)
                self._connected.add(key)
                self._last_error.pop(key, None)
                async for candle in self._provider.stream(key):
                    if self._closed:
                        return
                    self._connected.add(key)
                    await self._recover_gap_if_needed(key, candle)
                    changed = self._cache.upsert(candle, now=datetime.now(UTC))
                    self._last_update[key] = datetime.now(UTC)
                    if changed:
                        self._publish(key, candle)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected.discard(key)
                self._last_error[key] = type(exc).__name__
                if self._reconnect_delay_seconds:
                    await asyncio.sleep(self._reconnect_delay_seconds)
            finally:
                self._connected.discard(key)

    async def _recover_gap_if_needed(self, key: CandleKey, incoming: Candle) -> None:
        latest = self._cache.latest(key)
        if latest is None:
            return
        expected_next = latest.open_time.astimezone(UTC) + key.timeframe.duration
        incoming_open = incoming.open_time.astimezone(UTC)
        if incoming_open > expected_next:
            await self._backfill(key, limit=self._cache.max_depth, publish=True)

    async def _backfill(
        self,
        key: CandleKey,
        *,
        limit: int,
        publish: bool = False,
    ) -> tuple[Candle, ...]:
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = datetime.now(UTC)
            candles = await self._provider.fetch_history(key, limit=limit, before=now)
            safe = tuple(
                candle
                for candle in candles
                if candle.open_time.astimezone(UTC) <= now
                and (not candle.is_final or candle.close_time.astimezone(UTC) <= now)
            )
            changed = self._cache.merge(safe, now=now)
            if safe:
                self._last_update[key] = max(
                    candle.updated_at.astimezone(UTC) for candle in safe
                )
            if publish:
                for candle in changed:
                    self._publish(key, candle)
            return changed

    async def _backfill_as_of(
        self,
        key: CandleKey,
        *,
        limit: int,
        as_of: datetime,
    ) -> tuple[Candle, ...]:
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            candles = await self._provider.fetch_history(key, limit=limit, before=as_of)
            safe = tuple(
                candle
                for candle in candles
                if candle.is_final
                and candle.open_time.astimezone(UTC) <= as_of
                and candle.close_time.astimezone(UTC) <= as_of
                and candle.updated_at.astimezone(UTC) <= as_of
            )
            # Merge against the historical decision clock. This rejects any accidental future row.
            changed = self._cache.merge(safe, now=as_of)
            return changed

    def _publish(self, key: CandleKey, candle: Candle) -> None:
        for queue in tuple(self._subscribers.get(key, ())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(candle)


def floor_time(value: datetime, timeframe: CandleTimeframe) -> datetime:
    value = _utc(value, label="timestamp")
    seconds = int(timeframe.duration.total_seconds())
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=UTC)


def _candle_is_causal_at(candle: Candle, *, as_of: datetime) -> bool:
    open_time = candle.open_time.astimezone(UTC)
    close_time = candle.close_time.astimezone(UTC)
    updated_at = candle.updated_at.astimezone(UTC)
    if open_time > as_of or updated_at > as_of:
        return False
    if candle.is_final:
        return close_time <= as_of
    return open_time <= as_of < close_time


def _utc(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CandleCausalityError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)
