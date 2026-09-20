import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel

from ai_spot_trader.persistence.analytics import PaperAnalyticsReader
from ai_spot_trader.persistence.query import CycleAuditReader


class EngineCycleFailureLike(Protocol):
    @property
    def stage(self) -> object: ...

    @property
    def error_type(self) -> str: ...

    @property
    def timed_out(self) -> bool: ...


class EngineCycleResultLike(Protocol):
    @property
    def cycle_id(self) -> UUID: ...

    @property
    def status(self) -> object: ...

    @property
    def failure(self) -> EngineCycleFailureLike | None: ...


class StoppableTradingEngine(Protocol):
    """Minimal lifecycle dependency retained for cooperative application shutdown."""

    async def stop(self) -> None: ...


@runtime_checkable
class ControllableTradingEngine(StoppableTradingEngine, Protocol):
    """Lifecycle/observation surface required by the HTTP control endpoints."""

    @property
    def is_running(self) -> bool: ...

    @property
    def last_result(self) -> EngineCycleResultLike | None: ...

    @property
    def last_unexpected_error_type(self) -> str | None: ...

    async def start(self) -> None: ...


class PortfolioSnapshotSource(Protocol):
    """Read-only surface needed to expose the current in-memory PAPER portfolio."""

    def snapshot(self) -> BaseModel | Mapping[str, object]: ...


class AsyncCloseable(Protocol):
    async def close(self) -> None: ...


class TradingEngineUnavailableError(RuntimeError):
    """Raised when lifecycle control is requested without an injected engine."""


class TradingEngineAlreadyRunningError(RuntimeError):
    """Raised when the API receives a duplicate start request."""


@dataclass(frozen=True, slots=True)
class EngineFailureSnapshot:
    stage: str
    error_type: str
    timed_out: bool


@dataclass(frozen=True, slots=True)
class EngineRuntimeSnapshot:
    configured: bool
    status: Literal["RUNNING", "STOPPED", "UNAVAILABLE"]
    last_cycle_id: UUID | None = None
    last_cycle_status: str | None = None
    last_cycle_failure: EngineFailureSnapshot | None = None
    last_unexpected_error_type: str | None = None


@dataclass(slots=True)
class AppRuntime:
    """Own process-local API dependencies without auto-starting the trading engine."""

    shutdown_requested: asyncio.Event = field(default_factory=asyncio.Event)
    trading_engine: StoppableTradingEngine | None = None
    portfolio: PortfolioSnapshotSource | None = None
    audit_reader: CycleAuditReader | None = None
    analytics_reader: PaperAnalyticsReader | None = None
    owned_database: AsyncCloseable | None = None
    _engine_command_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def engine_snapshot(self) -> EngineRuntimeSnapshot:
        engine = self._controllable_engine()
        if engine is None:
            return EngineRuntimeSnapshot(configured=False, status="UNAVAILABLE")

        result = engine.last_result
        failure_snapshot: EngineFailureSnapshot | None = None
        if result is not None and result.failure is not None:
            failure_snapshot = EngineFailureSnapshot(
                stage=_enum_text(result.failure.stage),
                error_type=result.failure.error_type,
                timed_out=result.failure.timed_out,
            )
        return EngineRuntimeSnapshot(
            configured=True,
            status="RUNNING" if engine.is_running else "STOPPED",
            last_cycle_id=result.cycle_id if result is not None else None,
            last_cycle_status=(
                _enum_text(result.status) if result is not None else None
            ),
            last_cycle_failure=failure_snapshot,
            last_unexpected_error_type=engine.last_unexpected_error_type,
        )

    async def start_engine(self) -> EngineRuntimeSnapshot:
        """Start the injected canonical engine without creating another orchestration path."""

        async with self._engine_command_lock:
            engine = self._require_controllable_engine()
            if engine.is_running:
                raise TradingEngineAlreadyRunningError("trading engine is already running")
            await engine.start()
            return self.engine_snapshot()

    async def stop_engine(self) -> EngineRuntimeSnapshot:
        """Cooperatively stop the injected engine; repeated stops remain idempotent."""

        async with self._engine_command_lock:
            engine = self._require_controllable_engine()
            await engine.stop()
            return self.engine_snapshot()

    def _controllable_engine(self) -> ControllableTradingEngine | None:
        engine = self.trading_engine
        if engine is None or not isinstance(engine, ControllableTradingEngine):
            return None
        return engine

    def _require_controllable_engine(self) -> ControllableTradingEngine:
        engine = self._controllable_engine()
        if engine is None:
            raise TradingEngineUnavailableError("trading engine is not configured")
        return engine

    async def close(self) -> None:
        """Stop owned runtime activity and dispose an internally created database."""

        self.shutdown_requested.set()
        try:
            if self.trading_engine is not None:
                await self.trading_engine.stop()
        finally:
            if self.owned_database is not None:
                await self.owned_database.close()
            await asyncio.sleep(0)


def _enum_text(value: object) -> str:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, str):
        return value
    return type(value).__name__
