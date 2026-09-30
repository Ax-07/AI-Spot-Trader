from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import TradingCadenceMode
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.candles import (
    Candle,
    CandleKey,
    CandleTimeframe,
    floor_time,
)

from ai_spot_trader.trading.engine import TradingCycleRunner, TradingEngine


class CandleHistorySource(Protocol):
    async def history_as_of(
        self,
        key: CandleKey,
        *,
        as_of: datetime,
        limit: int = 1000,
    ) -> tuple[Candle, ...]: ...


MarketSetSource = Callable[[], tuple[ExecutableMarket, ...]]


@dataclass(frozen=True, slots=True)
class CandleCloseSchedule:
    """UTC-aligned schedule for one canonical candle timeframe."""

    timeframe: CandleTimeframe

    def next_close_after(self, value: datetime) -> datetime:
        """Return the first candle close strictly after ``value``.

        A strict future boundary means startup/restart never replays a candle that already
        closed before the autonomous loop became active.
        """

        current = _utc(value, label="schedule clock")
        return floor_time(current, self.timeframe) + self.timeframe.duration

    def latest_close_at_or_before(self, value: datetime) -> datetime:
        """Return the current UTC grid boundary without inventing a future close."""

        return floor_time(_utc(value, label="schedule clock"), self.timeframe)

    def seconds_until(self, target_close: datetime, *, now: datetime) -> float:
        target = _utc(target_close, label="target close")
        current = _utc(now, label="schedule clock")
        return max(0.0, (target - current).total_seconds())


class CandleCloseReadinessGate:
    """Wait until the scheduled candle is explicitly finalized by the canonical candle service.

    The gate never manufactures a close and never calls an LLM. If the requested close is still
    unavailable when the next boundary arrives, it is considered superseded so the engine can
    move to the latest relevant boundary instead of replaying stale decisions in a burst.
    """

    def __init__(
        self,
        candle_history: CandleHistorySource,
        *,
        markets: tuple[ExecutableMarket, ...] | MarketSetSource,
        timeframe: CandleTimeframe,
        clock: Clock | None = None,
        poll_seconds: float = 0.5,
    ) -> None:
        if isinstance(poll_seconds, bool) or not isinstance(poll_seconds, (int, float)):
            raise ValueError("poll_seconds must be a positive finite number")
        if not math.isfinite(poll_seconds) or poll_seconds <= 0:
            raise ValueError("poll_seconds must be a positive finite number")
        self._candles = candle_history
        self._markets = markets
        self._timeframe = timeframe
        self._clock = clock or SystemClock()
        self._poll_seconds = float(poll_seconds)
        self._last_error_type: str | None = None

    @property
    def timeframe(self) -> CandleTimeframe:
        return self._timeframe

    @property
    def last_error_type(self) -> str | None:
        return self._last_error_type

    async def is_ready(
        self,
        target_close: datetime,
        *,
        as_of: datetime | None = None,
    ) -> bool:
        target = _utc(target_close, label="target close")
        observed_at = _utc(as_of or self._clock.now(), label="readiness clock")
        if target > observed_at:
            return False
        if floor_time(target, self._timeframe) != target:
            raise ValueError("target_close must align with the configured candle timeframe")

        markets = self._resolve_markets()
        if not markets:
            raise ValueError("candle-close readiness requires at least one executable market")

        self._last_error_type = None
        for market in markets:
            try:
                rows = await self._candles.history_as_of(
                    CandleKey(
                        symbol=market.symbol,
                        market_type=market.market_type,
                        timeframe=self._timeframe,
                    ),
                    as_of=observed_at,
                    limit=2,
                )
            except Exception as exc:
                self._last_error_type = type(exc).__name__
                return False
            if not any(
                candle.is_final
                and candle.close_time.astimezone(UTC) == target
                and candle.updated_at.astimezone(UTC) <= observed_at
                for candle in rows
            ):
                return False
        return True

    async def wait_until_ready(
        self,
        target_close: datetime,
        *,
        stop_requested: asyncio.Event,
    ) -> bool:
        """Return True when finalized data is available, False on stop or supersession."""

        target = _utc(target_close, label="target close")
        superseded_at = target + self._timeframe.duration
        while not stop_requested.is_set():
            now = _utc(self._clock.now(), label="readiness clock")
            if now >= superseded_at:
                return False
            if await self.is_ready(target, as_of=now):
                return True
            remaining = max(0.0, (superseded_at - now).total_seconds())
            if remaining <= 0:
                return False
            try:
                await asyncio.wait_for(
                    stop_requested.wait(),
                    timeout=min(self._poll_seconds, remaining),
                )
            except TimeoutError:
                continue
        return False

    def _resolve_markets(self) -> tuple[ExecutableMarket, ...]:
        markets = self._markets() if callable(self._markets) else self._markets
        ordered = tuple(
            sorted(set(markets), key=lambda item: (item.market_type.value, item.symbol))
        )
        return ordered


def _utc(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


class ScheduledTradingEngine(TradingEngine):
    """Single strategic engine supporting legacy interval or candle-close scheduling.

    ``run_cycle()`` remains the inherited immediate/manual primitive. Only the autonomous
    background loop is aligned to candle closes.
    """

    def __init__(
        self,
        *,
        runner: TradingCycleRunner,
        cadence_seconds: float,
        cadence_mode: TradingCadenceMode = TradingCadenceMode.INTERVAL,
        candle_schedule: CandleCloseSchedule | None = None,
        readiness_gate: CandleCloseReadinessGate | None = None,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(runner=runner, cadence_seconds=cadence_seconds)
        if cadence_mode is TradingCadenceMode.CANDLE_CLOSE:
            if candle_schedule is None or readiness_gate is None:
                raise ValueError(
                    "CANDLE_CLOSE requires candle_schedule and readiness_gate"
                )
            if readiness_gate.timeframe is not candle_schedule.timeframe:
                raise ValueError(
                    "candle schedule and readiness gate must use the same timeframe"
                )
        elif candle_schedule is not None or readiness_gate is not None:
            raise ValueError(
                "INTERVAL cannot configure candle-close scheduling components"
            )
        self._cadence_mode = cadence_mode
        self._candle_schedule = candle_schedule
        self._readiness_gate = readiness_gate
        self._schedule_clock = clock or SystemClock()
        self._last_scheduled_close: datetime | None = None

    @property
    def cadence_mode(self) -> TradingCadenceMode:
        return self._cadence_mode

    @property
    def allows_manual_cycle_while_running(self) -> bool:
        """Allow the runtime to request a runner-serialized manual cycle while the loop waits."""

        return True

    @property
    def last_scheduled_close(self) -> datetime | None:
        return self._last_scheduled_close

    async def _run_loop(self) -> None:
        if self._cadence_mode is TradingCadenceMode.INTERVAL:
            await super()._run_loop()
            return
        await self._run_candle_close_loop()

    async def _run_candle_close_loop(self) -> None:
        schedule = self._candle_schedule
        gate = self._readiness_gate
        assert schedule is not None and gate is not None

        target_close = schedule.next_close_after(self._now())
        while not self._stop_requested.is_set():
            if not await self._wait_until_or_stop(target_close):
                break
            ready = await gate.wait_until_ready(
                target_close,
                stop_requested=self._stop_requested,
            )
            if self._stop_requested.is_set():
                break
            if not ready:
                # The old boundary became stale while waiting for provider finality. Skip it and
                # move to the latest relevant grid point instead of replaying every missed candle.
                latest = schedule.latest_close_at_or_before(self._now())
                target_close = (
                    latest
                    if latest > target_close
                    else target_close + schedule.timeframe.duration
                )
                continue

            self._last_scheduled_close = target_close
            try:
                self._last_result = await self._runner.run_cycle()
            except Exception as exc:
                self._last_unexpected_error_type = type(exc).__name__
            if self._stop_requested.is_set():
                break

            # Recompute from wall-clock time after the cycle. A long cycle therefore skips any
            # elapsed boundaries instead of shifting the grid or creating a catch-up burst.
            target_close = schedule.next_close_after(self._now())

    async def _wait_until_or_stop(self, target: datetime) -> bool:
        schedule = self._candle_schedule
        assert schedule is not None
        while not self._stop_requested.is_set():
            remaining = schedule.seconds_until(target, now=self._now())
            if remaining <= 0:
                return True
            try:
                await asyncio.wait_for(self._stop_requested.wait(), timeout=remaining)
            except TimeoutError:
                return True
        return False

    def _now(self) -> datetime:
        return _utc(self._schedule_clock.now(), label="schedule clock")


__all__ = [
    "CandleCloseReadinessGate",
    "CandleCloseSchedule",
    "CandleHistorySource",
    "MarketSetSource",
    "ScheduledTradingEngine",
]
