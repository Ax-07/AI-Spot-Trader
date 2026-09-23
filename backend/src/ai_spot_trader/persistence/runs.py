from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.enums import MarketType
from ai_spot_trader.domain.models import ExecutableMarket, PortfolioState
from ai_spot_trader.domain.symbols import parse_canonical_symbol
from ai_spot_trader.persistence.models import CycleRecord, PaperRunRecord

RunIdFactory = Callable[[], UUID]
PAPER_LEDGER_RECOVERY_VERSION = "paper-ledger-recovery-v1"


class PaperRunSortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class PaperRunNotFoundError(RuntimeError):
    pass


class PaperRunClosedError(RuntimeError):
    pass


class PaperRunStoreUnavailableError(RuntimeError):
    pass


class PaperRunRecoveryError(RuntimeError):
    """Raised when the durable PAPER ledger cannot be reconstructed exactly."""


class PaperPortfolioRecoverySink(Protocol):
    def restore(self, state: PortfolioState) -> None: ...


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
    resumed_from_paper_run_id: UUID | None = None
    recovery_version: str | None = None


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
    """Create a PAPER run, optionally recovering the canonical ledger from its predecessor."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        market_type: str | None = None,
        symbol: str | None = None,
        execution_universe: tuple[ExecutableMarket, ...] | None = None,
        definition: PaperRunDefinition | None = None,
        initial_portfolio: PortfolioState | None = None,
        portfolio_sink: PaperPortfolioRecoverySink | None = None,
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
        if (initial_portfolio is None) != (portfolio_sink is None):
            raise ValueError("initial_portfolio and portfolio_sink must be configured together")
        if definition is not None and initial_portfolio is not None:
            raise ValueError("explicit test run definitions cannot enable automatic recovery")

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
        self._initial_portfolio = initial_portfolio
        self._portfolio_sink = portfolio_sink
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

        if self._initial_portfolio is not None:
            return await self._initialize_with_recovery()
        return await self._initialize_fresh()

    async def _initialize_fresh(self) -> PaperRunView:
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

    async def _initialize_with_recovery(self) -> PaperRunView:
        bootstrap = self._initial_portfolio
        sink = self._portfolio_sink
        assert bootstrap is not None and sink is not None
        started_at = _clock_utc(self._clock)
        record: PaperRunRecord
        recovered: PortfolioState
        try:
            async with self._sessions() as session, session.begin():
                latest = await session.scalar(
                    select(PaperRunRecord)
                    .order_by(
                        PaperRunRecord.started_at.desc(),
                        PaperRunRecord.paper_run_id.desc(),
                    )
                    .limit(1)
                    .with_for_update()
                )
                resumed_from: UUID | None = None
                recovered = bootstrap
                if latest is not None:
                    self._validate_parent_universe(latest)
                    successor = await session.scalar(
                        select(PaperRunRecord.paper_run_id)
                        .where(
                            PaperRunRecord.resumed_from_paper_run_id
                            == latest.paper_run_id
                        )
                        .limit(1)
                    )
                    if successor is not None:
                        raise PaperRunRecoveryError(
                            "latest PAPER run already has a recovery successor"
                        )
                    recovered = await self._recover_terminal_state(session, latest)
                    resumed_from = latest.paper_run_id
                    if latest.ended_at is None:
                        latest.ended_at = started_at

                _validate_recovered_portfolio(
                    recovered,
                    bootstrap=bootstrap,
                    execution_universe=self._execution_universe,
                )
                record = PaperRunRecord(
                    paper_run_id=self._run_id_factory(),
                    started_at=started_at,
                    ended_at=None,
                    market_type=self._market_type,
                    symbol=self._symbol,
                    execution_universe_payload=[
                        item.model_dump(mode="json") for item in self._execution_universe
                    ],
                    resumed_from_paper_run_id=resumed_from,
                    recovery_version=PAPER_LEDGER_RECOVERY_VERSION,
                    initial_portfolio_payload=recovered.model_dump(mode="json"),
                    current_portfolio_payload=recovered.model_dump(mode="json"),
                )
                session.add(record)
                await session.flush()
        except PaperRunRecoveryError:
            raise
        except IntegrityError as exc:
            raise PaperRunRecoveryError(
                "PAPER recovery handoff conflicted with another runtime"
            ) from exc
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise PaperRunStoreUnavailableError("paper run store unavailable") from exc

        sink.restore(recovered)
        self._current_run_id = record.paper_run_id
        return _view(record)

    def _validate_parent_universe(self, parent: PaperRunRecord) -> None:
        parent_universe = _universe_from_record(parent)
        if parent_universe != self._execution_universe:
            raise PaperRunRecoveryError(
                "latest PAPER run execution universe differs from current configuration"
            )

    async def _recover_terminal_state(
        self,
        session: AsyncSession,
        parent: PaperRunRecord,
    ) -> PortfolioState:
        if parent.recovery_version == PAPER_LEDGER_RECOVERY_VERSION:
            if parent.current_portfolio_payload is None:
                raise PaperRunRecoveryError(
                    "recoverable PAPER run has no durable current portfolio"
                )
            return _portfolio_from_payload(parent.current_portfolio_payload)

        latest_cycle = await session.scalar(
            select(CycleRecord)
            .where(CycleRecord.paper_run_id == parent.paper_run_id)
            .order_by(CycleRecord.recorded_at.desc(), CycleRecord.cycle_id.desc())
            .limit(1)
        )
        if (
            latest_cycle is not None
            and latest_cycle.status == "FAILED"
            and parent.recovery_version != PAPER_LEDGER_RECOVERY_VERSION
        ):
            raise PaperRunRecoveryError(
                "legacy PAPER run ends with a failed cycle; terminal ledger state is ambiguous"
            )
        if latest_cycle is not None and latest_cycle.status not in {"COMPLETED", "FAILED"}:
            raise PaperRunRecoveryError("PAPER run contains an unknown cycle status")

        completed = await session.scalar(
            select(CycleRecord)
            .where(
                CycleRecord.paper_run_id == parent.paper_run_id,
                CycleRecord.status == "COMPLETED",
            )
            .order_by(CycleRecord.recorded_at.desc(), CycleRecord.cycle_id.desc())
            .limit(1)
        )
        if completed is None:
            if parent.initial_portfolio_payload is None:
                raise PaperRunRecoveryError(
                    "PAPER run has no completed cycle or durable initial portfolio"
                )
            return _portfolio_from_payload(parent.initial_portfolio_payload)

        if completed.portfolio_after_payload is not None:
            return _portfolio_from_payload(completed.portfolio_after_payload)
        agent_input = completed.agent_input_payload
        if not isinstance(agent_input, dict):
            raise PaperRunRecoveryError(
                "completed PAPER cycle has no durable portfolio state"
            )
        payload = agent_input.get("portfolio_state")
        if not isinstance(payload, dict):
            raise PaperRunRecoveryError(
                "completed PAPER cycle has an invalid durable portfolio state"
            )
        return _portfolio_from_payload(payload)

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
            raise PaperRunRecoveryError("invalid paper run execution universe") from exc
    # Defensive compatibility for rows created before migration backfill.
    if record.market_type is not None and record.symbol is not None:
        try:
            return (
                ExecutableMarket(
                    symbol=record.symbol,
                    market_type=MarketType(record.market_type),
                ),
            )
        except ValueError as exc:
            raise PaperRunRecoveryError("invalid legacy paper run market") from exc
    raise PaperRunRecoveryError("paper run has no executable universe")


def _portfolio_from_payload(payload: dict[str, object]) -> PortfolioState:
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return PortfolioState.model_validate_json(encoded)
    except (TypeError, ValueError) as exc:
        raise PaperRunRecoveryError("invalid durable PAPER portfolio snapshot") from exc


def _validate_recovered_portfolio(
    state: PortfolioState,
    *,
    bootstrap: PortfolioState,
    execution_universe: tuple[ExecutableMarket, ...],
) -> None:
    expected_balances = {item.asset for item in bootstrap.balances}
    actual_balances = {item.asset for item in state.balances}
    if actual_balances != expected_balances:
        raise PaperRunRecoveryError(
            "recovered PAPER settlement balances differ from current configuration"
        )

    spot_assets = {
        parse_canonical_symbol(item.symbol)[0]
        for item in execution_universe
        if item.market_type is MarketType.SPOT
    }
    held_assets = {item.asset for item in state.positions}
    if not held_assets.issubset(spot_assets):
        raise PaperRunRecoveryError(
            "recovered SPOT inventory is outside the configured execution universe"
        )

    perpetual_symbols = {
        item.symbol
        for item in execution_universe
        if item.market_type is MarketType.PERPETUAL
    }
    held_derivatives = {item.symbol for item in state.derivative_positions}
    if not held_derivatives.issubset(perpetual_symbols):
        raise PaperRunRecoveryError(
            "recovered derivative position is outside the configured execution universe"
        )


def _view(record: PaperRunRecord) -> PaperRunView:
    try:
        universe = _universe_from_record(record)
    except PaperRunRecoveryError as exc:
        raise PaperRunStoreUnavailableError(str(exc)) from exc
    legacy_type, legacy_symbol = _legacy_projection(universe)
    return PaperRunView(
        paper_run_id=record.paper_run_id,
        started_at=_utc(record.started_at),
        ended_at=None if record.ended_at is None else _utc(record.ended_at),
        market_type=legacy_type,
        symbol=legacy_symbol,
        execution_universe=universe,
        resumed_from_paper_run_id=record.resumed_from_paper_run_id,
        recovery_version=record.recovery_version,
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
