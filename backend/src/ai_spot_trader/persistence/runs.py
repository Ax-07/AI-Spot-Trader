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
from ai_spot_trader.persistence.models import PaperRunRecord

RunIdFactory = Callable[[], UUID]


class PaperRunSortOrder(StrEnum):
    """Stable sort directions supported by PAPER-run list endpoints."""

    ASC = "asc"
    DESC = "desc"


class PaperRunNotFoundError(RuntimeError):
    """Raised when a requested durable PAPER run does not exist."""


class PaperRunClosedError(RuntimeError):
    """Raised when a cycle would be written to an already closed PAPER run."""


class PaperRunStoreUnavailableError(RuntimeError):
    """Raised when durable PAPER run metadata cannot be queried."""


@dataclass(frozen=True, slots=True)
class PaperRunDefinition:
    paper_run_id: UUID
    started_at: datetime
    market_type: str
    symbol: str


@dataclass(frozen=True, slots=True)
class PaperRunView:
    paper_run_id: UUID
    started_at: datetime
    ended_at: datetime | None
    market_type: str
    symbol: str


@dataclass(frozen=True, slots=True)
class PaperRunPage:
    items: tuple[PaperRunView, ...]
    total: int
    limit: int
    offset: int


class PaperRunLifecycle(Protocol):
    """Process-local lifecycle for the durable identity of one PAPER experiment."""

    @property
    def current_run_id(self) -> UUID | None: ...

    async def initialize(self) -> PaperRunView: ...

    async def close(self) -> None: ...


class PaperRunReader(Protocol):
    """Read-only durable PAPER-run catalog."""

    async def list_runs(
        self,
        *,
        limit: int,
        offset: int,
        order: PaperRunSortOrder,
    ) -> PaperRunPage: ...

    async def get_run(self, paper_run_id: UUID) -> PaperRunView | None: ...


class SqlAlchemyPaperRunLifecycle:
    """Create one fresh run per backend lifetime and close it on graceful shutdown."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        market_type: str | None = None,
        symbol: str | None = None,
        definition: PaperRunDefinition | None = None,
        clock: Clock | None = None,
        run_id_factory: RunIdFactory = uuid4,
    ) -> None:
        if definition is not None:
            if market_type is not None or symbol is not None:
                raise ValueError("definition cannot be combined with market_type or symbol")
            market_type = definition.market_type
            symbol = definition.symbol
        if market_type is None or not market_type.strip():
            raise ValueError("paper run market_type cannot be empty")
        if symbol is None or not symbol.strip():
            raise ValueError("paper run symbol cannot be empty")
        self._sessions = sessions
        self._market_type = market_type
        self._symbol = symbol
        self._definition = definition
        self._clock = clock or SystemClock()
        self._run_id_factory = run_id_factory
        self._current_run_id: UUID | None = None

    @property
    def current_run_id(self) -> UUID | None:
        return self._current_run_id

    async def initialize(self) -> PaperRunView:
        """Create a fresh run because composition also creates a fresh in-memory ledger."""

        current_id = self._current_run_id
        if current_id is not None:
            existing = await SqlAlchemyPaperRunQueryService(self._sessions).get_run(
                current_id
            )
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
        )
        try:
            async with self._sessions() as session, session.begin():
                session.add(record)
            self._current_run_id = record.paper_run_id
            return _view(record)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise PaperRunStoreUnavailableError("paper run store unavailable") from exc

    async def close(self) -> None:
        """Close only this process' current run; interrupted runs stay explicitly open-ended."""

        current_id = self._current_run_id
        if current_id is None:
            return
        ended_at = _clock_utc(self._clock)
        try:
            async with self._sessions() as session, session.begin():
                current = await session.get(PaperRunRecord, current_id)
                if current is None:
                    raise PaperRunNotFoundError(
                        f"paper run {current_id} does not exist"
                    )
                if current.ended_at is None:
                    current.ended_at = ended_at
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise PaperRunStoreUnavailableError("paper run store unavailable") from exc
        finally:
            self._current_run_id = None


class SqlAlchemyPaperRunQueryService:
    """Read durable PAPER run identities without inventing legacy run boundaries."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_runs(
        self,
        *,
        limit: int,
        offset: int,
        order: PaperRunSortOrder,
    ) -> PaperRunPage:
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
                records = (
                    await session.scalars(statement.offset(offset).limit(limit))
                ).all()
                return PaperRunPage(
                    items=tuple(_view(record) for record in records),
                    total=total,
                    limit=limit,
                    offset=offset,
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


def _view(record: PaperRunRecord) -> PaperRunView:
    return PaperRunView(
        paper_run_id=record.paper_run_id,
        started_at=_utc(record.started_at),
        ended_at=None if record.ended_at is None else _utc(record.ended_at),
        market_type=record.market_type,
        symbol=record.symbol,
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
