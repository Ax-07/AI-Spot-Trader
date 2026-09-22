from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket
from ai_spot_trader.persistence.models import PaperRunRecord

RunIdFactory = Callable[[], UUID]


class PaperRunSortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class PaperRunNotFoundError(RuntimeError):
    pass


class PaperRunClosedError(RuntimeError):
    pass


class PaperRunStoreUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PaperRunDefinition:
    paper_run_id: UUID
    started_at: datetime
    market_type: str | None = None
    symbol: str | None = None
    execution_universe: tuple[ExecutableMarket, ...] = ()

    def __post_init__(self) -> None:
        has_legacy = self.market_type is not None or self.symbol is not None
        if (self.market_type is None) != (self.symbol is None):
            raise ValueError("legacy paper run metadata requires both market_type and symbol")
        if self.execution_universe and has_legacy:
            raise ValueError(
                "paper run definition must use either execution_universe or legacy metadata"
            )


@dataclass(frozen=True, slots=True)
class PaperRunView:
    paper_run_id: UUID
    started_at: datetime
    ended_at: datetime | None
    market_type: str | None
    symbol: str | None
    execution_universe: tuple[ExecutableMarket, ...] = ()


@dataclass(frozen=True, slots=True)
class PaperRunPage:
    items: tuple[PaperRunView, ...]
    total: int
    limit: int
    offset: int


class PaperRunLifecycle(Protocol):
    @property
    def current_run_id(self) -> UUID | None: ...
    async def initialize(self) -> PaperRunView: ...
    async def close(self) -> None: ...


class PaperRunReader(Protocol):
    async def list_runs(
        self,
        *,
        limit: int,
        offset: int,
        order: PaperRunSortOrder,
    ) -> PaperRunPage: ...
    async def get_run(self, paper_run_id: UUID) -> PaperRunView | None: ...


class SqlAlchemyPaperRunLifecycle:
    """Create one fresh durable run with an honest typed executable universe."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        market_type: str | None = None,
        symbol: str | None = None,
        execution_universe: tuple[ExecutableMarket, ...] | None = None,
        definition: PaperRunDefinition | None = None,
        clock: Clock | None = None,
        run_id_factory: RunIdFactory = uuid4,
    ) -> None:
        if definition is not None:
            if market_type is not None or symbol is not None or execution_universe is not None:
                raise ValueError("definition cannot be combined with run metadata")
            if definition.execution_universe:
                execution_universe = definition.execution_universe
                market_type = None
                symbol = None
            else:
                market_type = definition.market_type
                symbol = definition.symbol
                execution_universe = None

        universe = _normalize_universe(
            execution_universe=execution_universe,
            market_type=market_type,
            symbol=symbol,
        )
        legacy_type, legacy_symbol = _legacy_projection(universe)
        self._sessions = sessions
        self._execution_universe = universe
        self._market_type = legacy_type
        self._symbol = legacy_symbol
        self._definition = definition
        self._clock = clock or SystemClock()
        self._run_id_factory = run_id_factory
        self._current_run_id: UUID | None = None

    @property
    def current_run_id(self) -> UUID | None:
        return self._current_run_id

    async def initialize(self) -> PaperRunView:
        current_id = self._current_run_id
        if current_id is not None:
            existing = await SqlAlchemyPaperRunQueryService(self._sessions).get_run(current_id)
            if existing is None:
                raise PaperRunNotFoundError(f"paper run {current_id} does not exist")
            return existing

        definition = self._definition
        record = PaperRunRecord(
            paper_run_id=(
                definition.paper_run_id
                if definition is not None
                else self._run_id_factory()
            ),
            started_at=(
                _utc(definition.started_at)
                if definition is not None
                else _clock_utc(self._clock)
            ),
            ended_at=None,
            market_type=self._market_type,
            symbol=self._symbol,
            execution_universe_payload=[
                item.model_dump(mode="json") for item in self._execution_universe
            ],
        )
        try:
            async with self._sessions() as session, session.begin():
                session.add(record)
            self._current_run_id = record.paper_run_id
            return _view(record)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise PaperRunStoreUnavailableError("paper run store unavailable") from exc

    async def close(self) -> None:
        current_id = self._current_run_id
        if current_id is None:
            return
        ended_at = _clock_utc(self._clock)
        try:
            async with self._sessions() as session, session.begin():
                current = await session.get(PaperRunRecord, current_id)
                if current is None:
                    raise PaperRunNotFoundError(f"paper run {current_id} does not exist")
                if current.ended_at is None:
                    current.ended_at = ended_at
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise PaperRunStoreUnavailableError("paper run store unavailable") from exc
        finally:
            self._current_run_id = None


class SqlAlchemyPaperRunQueryService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_runs(self, *, limit: int, offset: int, order: PaperRunSortOrder) -> PaperRunPage:
        try:
            async with self._sessions() as session:
                statement = select(PaperRunRecord)
                if order is PaperRunSortOrder.ASC:
                    statement = statement.order_by(
                        PaperRunRecord.started_at.asc(),
                        PaperRunRecord.paper_run_id.asc(),
                    )
                else:
                    statement = statement.order_by(
                        PaperRunRecord.started_at.desc(),
                        PaperRunRecord.paper_run_id.desc(),
                    )
                count_statement = select(func.count()).select_from(PaperRunRecord)
                total = int(await session.scalar(count_statement) or 0)
                records = (await session.scalars(statement.offset(offset).limit(limit))).all()
                return PaperRunPage(
                    tuple(_view(record) for record in records),
                    total,
                    limit,
                    offset,
                )
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise PaperRunStoreUnavailableError("paper run store unavailable") from exc

    async def get_run(self, paper_run_id: UUID) -> PaperRunView | None:
        try:
            async with self._sessions() as session:
                record = await session.get(PaperRunRecord, paper_run_id)
                return None if record is None else _view(record)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise PaperRunStoreUnavailableError("paper run store unavailable") from exc


def _normalize_universe(
    *,
    execution_universe: tuple[ExecutableMarket, ...] | None,
    market_type: str | None,
    symbol: str | None,
) -> tuple[ExecutableMarket, ...]:
    universe: tuple[ExecutableMarket, ...]
    if execution_universe is not None and (market_type is not None or symbol is not None):
        raise ValueError(
            "execution_universe cannot be combined with legacy market_type or symbol"
        )
    if execution_universe is None:
        if market_type is None or not market_type.strip() or symbol is None or not symbol.strip():
            raise ValueError(
                "paper run requires an execution universe or legacy market_type + symbol"
            )
        try:
            universe = (ExecutableMarket(symbol=symbol, market_type=MarketType(market_type)),)
        except ValueError as exc:
            raise ValueError("invalid legacy paper run market") from exc
    else:
        if not execution_universe:
            raise ValueError("paper run execution_universe cannot be empty")
        universe = tuple(
            sorted(
                execution_universe,
                key=lambda item: (item.market_type.value, item.symbol),
            )
        )
        if len(set(universe)) != len(universe):
            raise ValueError("paper run execution_universe contains duplicates")
    return universe


def _legacy_projection(universe: tuple[ExecutableMarket, ...]) -> tuple[str | None, str | None]:
    if len(universe) != 1:
        return None, None
    item = universe[0]
    return item.market_type.value, item.symbol


def _universe_from_record(record: PaperRunRecord) -> tuple[ExecutableMarket, ...]:
    payload = record.execution_universe_payload
    if payload:
        try:
            return tuple(
                ExecutableMarket(
                    symbol=str(item["symbol"]),
                    market_type=MarketType(str(item["market_type"])),
                )
                for item in payload
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PaperRunStoreUnavailableError("invalid paper run execution universe") from exc
    # Defensive compatibility for rows created before migration backfill.
    if record.market_type is not None and record.symbol is not None:
        return (ExecutableMarket(symbol=record.symbol, market_type=MarketType(record.market_type)),)
    raise PaperRunStoreUnavailableError("paper run has no executable universe")


def _view(record: PaperRunRecord) -> PaperRunView:
    universe = _universe_from_record(record)
    legacy_type, legacy_symbol = _legacy_projection(universe)
    return PaperRunView(
        paper_run_id=record.paper_run_id,
        started_at=_utc(record.started_at),
        ended_at=None if record.ended_at is None else _utc(record.ended_at),
        market_type=legacy_type,
        symbol=legacy_symbol,
        execution_universe=universe,
    )


def _clock_utc(clock: Clock) -> datetime:
    value = clock.now()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("paper run clock must be timezone-aware")
    return value.astimezone(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
