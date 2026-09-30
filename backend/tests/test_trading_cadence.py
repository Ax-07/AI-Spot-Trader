import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ai_spot_trader.core.runtime import AppRuntime
from ai_spot_trader.domain.enums import MarketType, TradingCadenceMode
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.market.candles import Candle, CandleTimeframe
from ai_spot_trader.trading.cadence import (
    CandleCloseReadinessGate,
    CandleCloseSchedule,
    ScheduledTradingEngine,
)


BASE = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)
MARKET = ExecutableMarket(symbol="BTC/USD", market_type=MarketType.SPOT)


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class FakeHistory:
    def __init__(self, rows: tuple[Candle, ...] = ()) -> None:
        self.rows = rows
        self.calls = []

    async def history_as_of(self, key, *, as_of: datetime, limit: int = 1000):
        self.calls.append((key, as_of, limit))
        return self.rows


class CountingRunner:
    def __init__(self) -> None:
        self.calls = 0

    async def run_cycle(self):
        self.calls += 1
        return SimpleNamespace(cycle_id=self.calls, status="COMPLETED", failure=None)


class AlwaysReadyGate:
    def __init__(self, timeframe: CandleTimeframe) -> None:
        self.timeframe = timeframe
        self.targets: list[datetime] = []

    async def wait_until_ready(self, target_close: datetime, *, stop_requested: asyncio.Event):
        self.targets.append(target_close)
        return not stop_requested.is_set()


def final_candle(
    timeframe: CandleTimeframe,
    target_close: datetime,
    *,
    is_final: bool = True,
    updated_at: datetime | None = None,
) -> Candle:
    return Candle(
        symbol="BTC/USD",
        market_type=MarketType.SPOT,
        timeframe=timeframe,
        open_time=target_close - timeframe.duration,
        close_time=target_close,
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=Decimal("3"),
        is_final=is_final,
        updated_at=updated_at or (target_close if is_final else target_close - timedelta(seconds=1)),
    )


@pytest.mark.parametrize(
    ("timeframe", "value", "expected"),
    [
        (CandleTimeframe.M1, datetime(2026, 9, 30, 12, 0, 17, tzinfo=UTC), datetime(2026, 9, 30, 12, 1, tzinfo=UTC)),
        (CandleTimeframe.M5, datetime(2026, 9, 30, 12, 3, tzinfo=UTC), datetime(2026, 9, 30, 12, 5, tzinfo=UTC)),
        (CandleTimeframe.M15, datetime(2026, 9, 30, 12, 3, tzinfo=UTC), datetime(2026, 9, 30, 12, 15, tzinfo=UTC)),
        (CandleTimeframe.M30, datetime(2026, 9, 30, 12, 3, tzinfo=UTC), datetime(2026, 9, 30, 12, 30, tzinfo=UTC)),
        (CandleTimeframe.H1, datetime(2026, 9, 30, 12, 3, tzinfo=UTC), datetime(2026, 9, 30, 13, 0, tzinfo=UTC)),
        (CandleTimeframe.H4, datetime(2026, 9, 30, 13, 3, tzinfo=UTC), datetime(2026, 9, 30, 16, 0, tzinfo=UTC)),
        (CandleTimeframe.D1, datetime(2026, 9, 30, 13, 3, tzinfo=UTC), datetime(2026, 10, 1, 0, 0, tzinfo=UTC)),
    ],
)
def test_candle_close_schedule_aligns_to_canonical_utc_grid(
    timeframe: CandleTimeframe,
    value: datetime,
    expected: datetime,
) -> None:
    assert CandleCloseSchedule(timeframe).next_close_after(value) == expected


def test_startup_on_exact_boundary_uses_next_close_and_never_replays_current_boundary() -> None:
    schedule = CandleCloseSchedule(CandleTimeframe.M5)
    assert schedule.next_close_after(BASE) == BASE + timedelta(minutes=5)
    assert schedule.latest_close_at_or_before(BASE) == BASE


def test_long_cycle_recomputes_from_wall_clock_without_drift_or_catch_up() -> None:
    schedule = CandleCloseSchedule(CandleTimeframe.M5)
    first = schedule.next_close_after(datetime(2026, 9, 30, 12, 0, 1, tzinfo=UTC))
    assert first == datetime(2026, 9, 30, 12, 5, tzinfo=UTC)

    after_long_cycle = datetime(2026, 9, 30, 12, 16, 37, tzinfo=UTC)
    assert schedule.next_close_after(after_long_cycle) == datetime(
        2026, 9, 30, 12, 20, tzinfo=UTC
    )


def test_readiness_gate_requires_exact_finalized_target_candle() -> None:
    async def scenario() -> None:
        timeframe = CandleTimeframe.M5
        target = BASE + timedelta(minutes=5)
        clock = MutableClock(target + timedelta(seconds=2))
        history = FakeHistory((final_candle(timeframe, target),))
        gate = CandleCloseReadinessGate(
            history,
            markets=(MARKET,),
            timeframe=timeframe,
            clock=clock,
            poll_seconds=0.01,
        )

        assert await gate.is_ready(target) is True
        assert len(history.calls) == 1
        key, as_of, limit = history.calls[0]
        assert key.timeframe is timeframe
        assert key.symbol == "BTC/USD"
        assert as_of == clock.value
        assert limit == 2

    asyncio.run(scenario())


def test_readiness_gate_never_treats_non_final_or_future_revision_as_closed() -> None:
    async def scenario() -> None:
        timeframe = CandleTimeframe.M5
        target = BASE + timedelta(minutes=5)
        clock = MutableClock(target)

        non_final = FakeHistory((final_candle(timeframe, target, is_final=False),))
        non_final_gate = CandleCloseReadinessGate(
            non_final,
            markets=(MARKET,),
            timeframe=timeframe,
            clock=clock,
            poll_seconds=0.01,
        )
        assert await non_final_gate.is_ready(target) is False

        future_revision = FakeHistory(
            (final_candle(timeframe, target, updated_at=target + timedelta(seconds=1)),)
        )
        future_gate = CandleCloseReadinessGate(
            future_revision,
            markets=(MARKET,),
            timeframe=timeframe,
            clock=clock,
            poll_seconds=0.01,
        )
        assert await future_gate.is_ready(target, as_of=target) is False

    asyncio.run(scenario())


def test_manual_run_cycle_is_immediate_in_candle_close_mode() -> None:
    async def scenario() -> None:
        runner = CountingRunner()
        timeframe = CandleTimeframe.H4
        clock = MutableClock(BASE)
        engine = ScheduledTradingEngine(
            runner=runner,  # type: ignore[arg-type]
            cadence_seconds=60,
            cadence_mode=TradingCadenceMode.CANDLE_CLOSE,
            candle_schedule=CandleCloseSchedule(timeframe),
            readiness_gate=AlwaysReadyGate(timeframe),  # type: ignore[arg-type]
            clock=clock,
        )

        result = await engine.run_cycle()
        assert runner.calls == 1
        assert result.status == "COMPLETED"
        assert engine.last_scheduled_close is None

    asyncio.run(scenario())



def test_runtime_manual_cycle_can_run_while_scheduled_engine_is_waiting() -> None:
    async def scenario() -> None:
        runner = CountingRunner()
        timeframe = CandleTimeframe.D1
        engine = ScheduledTradingEngine(
            runner=runner,  # type: ignore[arg-type]
            cadence_seconds=60,
            cadence_mode=TradingCadenceMode.CANDLE_CLOSE,
            candle_schedule=CandleCloseSchedule(timeframe),
            readiness_gate=AlwaysReadyGate(timeframe),  # type: ignore[arg-type]
        )
        runtime = AppRuntime(trading_engine=engine)
        await engine.start()
        await asyncio.sleep(0)

        snapshot = await asyncio.wait_for(runtime.run_engine_cycle_once(), timeout=0.2)

        assert runner.calls == 1
        assert snapshot.status == "RUNNING"
        assert engine.last_scheduled_close is None
        await engine.stop()

    asyncio.run(scenario())


def test_stop_interrupts_candle_close_wait_without_running_a_cycle() -> None:
    async def scenario() -> None:
        runner = CountingRunner()
        timeframe = CandleTimeframe.D1
        engine = ScheduledTradingEngine(
            runner=runner,  # type: ignore[arg-type]
            cadence_seconds=60,
            cadence_mode=TradingCadenceMode.CANDLE_CLOSE,
            candle_schedule=CandleCloseSchedule(timeframe),
            readiness_gate=AlwaysReadyGate(timeframe),  # type: ignore[arg-type]
        )
        await engine.start()
        await asyncio.sleep(0)
        await asyncio.wait_for(engine.stop(), timeout=0.2)
        assert runner.calls == 0
        assert not engine.is_running

    asyncio.run(scenario())


def test_candle_close_loop_skips_missed_boundaries_instead_of_catching_up() -> None:
    class AdvancingRunner(CountingRunner):
        def __init__(self, clock: MutableClock) -> None:
            super().__init__()
            self.clock = clock
            self.engine = None

        async def run_cycle(self):
            result = await super().run_cycle()
            if self.calls == 1:
                self.clock.value += timedelta(minutes=11)
            else:
                assert self.engine is not None
                self.engine._stop_requested.set()  # noqa: SLF001 - scheduler regression boundary
            return result

    class ImmediateBoundaryEngine(ScheduledTradingEngine):
        def __init__(self, *args, clock: MutableClock, **kwargs) -> None:
            self.targets: list[datetime] = []
            self.test_clock = clock
            super().__init__(*args, clock=clock, **kwargs)

        async def _wait_until_or_stop(self, target: datetime) -> bool:
            self.targets.append(target)
            self.test_clock.value = target
            return not self._stop_requested.is_set()  # noqa: SLF001

    async def scenario() -> None:
        clock = MutableClock(datetime(2026, 9, 30, 12, 0, 1, tzinfo=UTC))
        runner = AdvancingRunner(clock)
        timeframe = CandleTimeframe.M5
        engine = ImmediateBoundaryEngine(
            runner=runner,  # type: ignore[arg-type]
            cadence_seconds=60,
            cadence_mode=TradingCadenceMode.CANDLE_CLOSE,
            candle_schedule=CandleCloseSchedule(timeframe),
            readiness_gate=AlwaysReadyGate(timeframe),  # type: ignore[arg-type]
            clock=clock,
        )
        runner.engine = engine

        await engine._run_loop()  # noqa: SLF001 - deterministic autonomous-loop test

        assert runner.calls == 2
        assert engine.targets == [
            datetime(2026, 9, 30, 12, 5, tzinfo=UTC),
            datetime(2026, 9, 30, 12, 20, tzinfo=UTC),
        ]

    asyncio.run(scenario())


def test_interval_mode_retains_historical_autonomous_loop_behavior() -> None:
    async def scenario() -> None:
        runner = CountingRunner()
        engine = ScheduledTradingEngine(
            runner=runner,  # type: ignore[arg-type]
            cadence_seconds=0.01,
            cadence_mode=TradingCadenceMode.INTERVAL,
        )
        await engine.start()
        while runner.calls < 2:
            await asyncio.sleep(0.005)
        await engine.stop()
        assert runner.calls >= 2

    asyncio.run(scenario())


def test_schedule_configuration_components_are_mode_consistent() -> None:
    runner = CountingRunner()
    timeframe = CandleTimeframe.M5
    gate = AlwaysReadyGate(timeframe)

    with pytest.raises(ValueError, match="CANDLE_CLOSE requires"):
        ScheduledTradingEngine(
            runner=runner,  # type: ignore[arg-type]
            cadence_seconds=60,
            cadence_mode=TradingCadenceMode.CANDLE_CLOSE,
        )

    with pytest.raises(ValueError, match="INTERVAL cannot"):
        ScheduledTradingEngine(
            runner=runner,  # type: ignore[arg-type]
            cadence_seconds=60,
            cadence_mode=TradingCadenceMode.INTERVAL,
            candle_schedule=CandleCloseSchedule(timeframe),
            readiness_gate=gate,  # type: ignore[arg-type]
        )
