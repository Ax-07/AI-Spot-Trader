from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_spot_trader.core.clock import Clock, SystemClock
from ai_spot_trader.domain.models import ExecutableMarket, PortfolioState
from ai_spot_trader.persistence.models import CycleRecord, PaperRunRecord
from ai_spot_trader.persistence.runs import (
    PAPER_LEDGER_RECOVERY_VERSION,
    PaperPortfolioRecoverySink,
    PaperRunNotFoundError,
    PaperRunPage,
    PaperRunRecoveryError,
    PaperRunSortOrder,
    PaperRunStoreUnavailableError,
    PaperRunView,
    _clock_utc,
    _legacy_projection,
    _normalize_universe,
    _portfolio_from_payload,
    _universe_from_record,
    _utc,
    _validate_recovered_portfolio,
)


@dataclass(frozen=True, slots=True)
class CampaignPaperRunView(PaperRunView):
    campaign_id: UUID | None = None


class CampaignPaperRunLifecycle:
    """Campaign-scoped recovery: a run can only continue its immutable campaign."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        campaign_id: UUID,
        execution_universe: tuple[ExecutableMarket, ...],
        initial_portfolio: PortfolioState,
        portfolio_sink: PaperPortfolioRecoverySink,
        resume: bool,
        clock: Clock | None = None,
    ) -> None:
        self._sessions = sessions
        self._campaign_id = campaign_id
        self._execution_universe = _normalize_universe(
            execution_universe=execution_universe,
            market_type=None,
            symbol=None,
        )
        self._market_type, self._symbol = _legacy_projection(self._execution_universe)
        self._initial_portfolio = initial_portfolio
        self._portfolio_sink = portfolio_sink
        self._resume = resume
        self._clock = clock or SystemClock()
        self._current_run_id: UUID | None = None

    @property
    def current_run_id(self) -> UUID | None:
        return self._current_run_id

    @property
    def campaign_id(self) -> UUID:
        return self._campaign_id

    async def initialize(self) -> CampaignPaperRunView:
        if self._current_run_id is not None:
            existing = await CampaignPaperRunQueryService(self._sessions).get_run(
                self._current_run_id
            )
            if existing is None:
                raise PaperRunNotFoundError(
                    f"paper run {self._current_run_id} does not exist"
                )
            return existing

        started_at = _clock_utc(self._clock)
        record: PaperRunRecord
        recovered = self._initial_portfolio
        try:
            async with self._sessions() as session, session.begin():
                latest = await session.scalar(
                    select(PaperRunRecord)
                    .where(PaperRunRecord.campaign_id == self._campaign_id)
                    .order_by(
                        PaperRunRecord.started_at.desc(),
                        PaperRunRecord.paper_run_id.desc(),
                    )
                    .limit(1)
                    .with_for_update()
                )
                resumed_from: UUID | None = None
                if self._resume:
                    if latest is None:
                        raise PaperRunRecoveryError("campaign has no PAPER run to resume")
                    self._validate_parent(latest)
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
                elif latest is not None:
                    raise PaperRunRecoveryError(
                        "campaign already has a PAPER run; explicit resume is required"
                    )

                _validate_recovered_portfolio(
                    recovered,
                    bootstrap=self._initial_portfolio,
                    execution_universe=self._execution_universe,
                )
                record = PaperRunRecord(
                    paper_run_id=uuid4(),
                    campaign_id=self._campaign_id,
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
                "PAPER campaign handoff conflicted with another runtime"
            ) from exc
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise PaperRunStoreUnavailableError("paper run store unavailable") from exc

        self._portfolio_sink.restore(recovered)
        self._current_run_id = record.paper_run_id
        return _view(record)

    def _validate_parent(self, parent: PaperRunRecord) -> None:
        if parent.campaign_id != self._campaign_id:
            raise PaperRunRecoveryError("PAPER recovery campaign mismatch")
        if _universe_from_record(parent) != self._execution_universe:
            raise PaperRunRecoveryError(
                "latest PAPER run execution universe differs from campaign configuration"
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
        if latest_cycle is not None and latest_cycle.status == "FAILED":
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
            raise PaperRunRecoveryError("completed PAPER cycle has no durable portfolio state")
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


class CampaignPaperRunQueryService:
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
                total = int(
                    await session.scalar(select(func.count()).select_from(PaperRunRecord)) or 0
                )
                records = (await session.scalars(statement.offset(offset).limit(limit))).all()
                return PaperRunPage(
                    tuple(_view(record) for record in records),
                    total,
                    limit,
                    offset,
                )
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise PaperRunStoreUnavailableError("paper run store unavailable") from exc

    async def get_run(self, paper_run_id: UUID) -> CampaignPaperRunView | None:
        try:
            async with self._sessions() as session:
                record = await session.get(PaperRunRecord, paper_run_id)
                return None if record is None else _view(record)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise PaperRunStoreUnavailableError("paper run store unavailable") from exc

    async def latest_for_campaign(
        self, campaign_id: UUID
    ) -> CampaignPaperRunView | None:
        try:
            async with self._sessions() as session:
                record = await session.scalar(
                    select(PaperRunRecord)
                    .where(PaperRunRecord.campaign_id == campaign_id)
                    .order_by(
                        PaperRunRecord.started_at.desc(),
                        PaperRunRecord.paper_run_id.desc(),
                    )
                    .limit(1)
                )
                return None if record is None else _view(record)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise PaperRunStoreUnavailableError("paper run store unavailable") from exc


def _view(record: PaperRunRecord) -> CampaignPaperRunView:
    try:
        universe = _universe_from_record(record)
    except PaperRunRecoveryError as exc:
        raise PaperRunStoreUnavailableError(str(exc)) from exc
    legacy_type, legacy_symbol = _legacy_projection(universe)
    return CampaignPaperRunView(
        paper_run_id=record.paper_run_id,
        started_at=_utc(record.started_at),
        ended_at=None if record.ended_at is None else _utc(record.ended_at),
        market_type=legacy_type,
        symbol=legacy_symbol,
        execution_universe=universe,
        resumed_from_paper_run_id=record.resumed_from_paper_run_id,
        recovery_version=record.recovery_version,
        campaign_id=record.campaign_id,
    )
