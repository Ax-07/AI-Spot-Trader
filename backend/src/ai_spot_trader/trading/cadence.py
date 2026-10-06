from __future__ import annotations

import asyncio
import logging
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

logger = logging.getLogger("ai_spot_trader.trading.cadence")


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
    """Diagnostic helper proving exact finalized candle availability for explicit markets.

    Batch 51.4 no longer wires this helper into the autonomous CANDLE_CLOSE scheduler. Dynamic
    Radar resolves its effective market universe inside the canonical cycle, so a pre-cycle gate
    over bootstrap markets cannot represent the data actually consumed by that cycle. Causal data
    availability remains enforced by ``history_as_of()`` at each downstream consumer.

    The helper stays available for focused diagnostics/tests that need to ask whether a known,
    explicit market set has an exact finalized candle at a boundary.
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
        """Return True on exact finality, False on stop or supersession.

        This polling primitive is intentionally retained only for explicit diagnostics. The
        production scheduler no longer calls it, which prevents a provider error or bootstrap
        market mismatch from suppressing the canonical strategic cycle.
        """

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
        return tuple(
            sorted(set(markets), key=lambda item: (item.market_type.value, item.symbol))
        )


def _utc(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


class ScheduledTradingEngine(TradingEngine):
    """Single strategic engine supporting legacy interval or candle-close scheduling.

    ``run_cycle()`` remains the inherited immediate/manual primitive. In CANDLE_CLOSE mode the
    autonomous loop uses the UTC candle boundary only as its trigger. Data readiness is evaluated
    causally inside the canonical cycle by the services that consume that data; the scheduler does
    not pre-resolve Radar or gate the cycle on bootstrap-market candles.
    """

    def __init__(
        self,
        *,
        runner: TradingCycleRunner,
        cadence_seconds: float,
        cadence_mode: TradingCadenceMode = TradingCadenceMode.INTERVAL,
        candle_schedule: CandleCloseSchedule | None = None,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(runner=runner, cadence_seconds=cadence_seconds)
        if cadence_mode is TradingCadenceMode.CANDLE_CLOSE:
            if candle_schedule is None:
                raise ValueError("CANDLE_CLOSE requires candle_schedule")
        elif candle_schedule is not None:
            raise ValueError("INTERVAL cannot configure candle-close scheduling components")
        self._cadence_mode = cadence_mode
        self._candle_schedule = candle_schedule
        self._schedule_clock = clock or SystemClock()
        self._last_scheduled_close: datetime | None = None

    @property
    def cadence_mode(self) -> TradingCadenceMode:
        return self._cadence_mode

    @property
    def allows_manual_cycle_while_running(self) -> bool:
        """Allow a runner-serialized manual cycle while the autonomous loop waits."""

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
        assert schedule is not None

        target_close = schedule.next_close_after(self._now())
        self._log_next_boundary(schedule, target_close)
        while not self._stop_requested.is_set():
            if not await self._wait_until_or_stop(target_close):
                break
            if self._stop_requested.is_set():
                break

            now = self._now()
            superseded_at = target_close + schedule.timeframe.duration
            if now >= superseded_at:
                latest_close = schedule.latest_close_at_or_before(now)
                next_target = (
                    latest_close
                    if latest_close > target_close
                    else target_close + schedule.timeframe.duration
                )
                skipped = max(
                    1,
                    int(
                        (next_target - target_close).total_seconds()
                        // schedule.timeframe.duration.total_seconds()
                    ),
                )
                logger.warning(
                    "scheduler_boundary_skipped mode=CANDLE_CLOSE timeframe=%s "
                    "target_close=%s replacement_close=%s skipped_count=%d reason=SCHEDULER_LATE",
                    schedule.timeframe.value,
                    target_close.isoformat(),
                    next_target.isoformat(),
                    skipped,
                )
                target_close = next_target
                continue

            logger.info(
                "scheduler_boundary_reached mode=CANDLE_CLOSE timeframe=%s target_close=%s",
                schedule.timeframe.value,
                target_close.isoformat(),
            )
            logger.info(
                "scheduler_readiness_validated mode=TEMPORAL_ONLY timeframe=%s target_close=%s "
                "causal_data=DELEGATED_TO_CYCLE",
                schedule.timeframe.value,
                target_close.isoformat(),
            )
            self._last_scheduled_close = target_close
            logger.info(
                "scheduler_cycle_started trigger=AUTO_CANDLE_CLOSE timeframe=%s target_close=%s",
                schedule.timeframe.value,
                target_close.isoformat(),
            )
            try:
                self._last_result = await self._runner.run_cycle()
            except Exception as exc:
                self._last_unexpected_error_type = type(exc).__name__
                logger.error(
                    "scheduler_cycle_raised trigger=AUTO_CANDLE_CLOSE timeframe=%s "
                    "target_close=%s error_type=%s",
                    schedule.timeframe.value,
                    target_close.isoformat(),
                    type(exc).__name__,
                )
            else:
                self._log_cycle_result(schedule, target_close, self._last_result)

            if self._stop_requested.is_set():
                break

            next_close = schedule.next_close_after(self._now())
            elapsed_boundaries = max(
                0,
                int(
                    (next_close - target_close).total_seconds()
                    // schedule.timeframe.duration.total_seconds()
                )
                - 1,
            )
            if elapsed_boundaries:
                logger.warning(
                    "scheduler_boundary_skipped mode=CANDLE_CLOSE timeframe=%s "
                    "target_close=%s next_close=%s skipped_count=%d reason=CYCLE_ELAPSED",
                    schedule.timeframe.value,
                    target_close.isoformat(),
                    next_close.isoformat(),
                    elapsed_boundaries,
                )
            target_close = next_close
            self._log_next_boundary(schedule, target_close)

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

    def _log_next_boundary(
        self,
        schedule: CandleCloseSchedule,
        target_close: datetime,
    ) -> None:
        logger.info(
            "scheduler_next_close mode=CANDLE_CLOSE timeframe=%s target_close=%s",
            schedule.timeframe.value,
            target_close.isoformat(),
        )

    def _log_cycle_result(
        self,
        schedule: CandleCloseSchedule,
        target_close: datetime,
        result: object,
    ) -> None:
        cycle_id = getattr(result, "cycle_id", None)
        status = _enum_text(getattr(result, "status", "UNKNOWN"))
        failure = getattr(result, "failure", None)
        if failure is None:
            logger.info(
                "scheduler_cycle_completed trigger=AUTO_CANDLE_CLOSE timeframe=%s "
                "target_close=%s cycle_id=%s status=%s",
                schedule.timeframe.value,
                target_close.isoformat(),
                cycle_id,
                status,
            )
            return
        logger.warning(
            "scheduler_cycle_completed trigger=AUTO_CANDLE_CLOSE timeframe=%s "
            "target_close=%s cycle_id=%s status=%s failure_stage=%s error_type=%s",
            schedule.timeframe.value,
            target_close.isoformat(),
            cycle_id,
            status,
            _enum_text(getattr(failure, "stage", "UNKNOWN")),
            getattr(failure, "error_type", type(failure).__name__),
        )

    def _now(self) -> datetime:
        return _utc(self._schedule_clock.now(), label="schedule clock")


def _enum_text(value: object) -> str:
    candidate = getattr(value, "value", value)
    return candidate if isinstance(candidate, str) else type(value).__name__


__all__ = [
    "CandleCloseReadinessGate",
    "CandleCloseSchedule",
    "CandleHistorySource",
    "MarketSetSource",
    "ScheduledTradingEngine",
]
