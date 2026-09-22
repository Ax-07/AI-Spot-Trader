from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from ai_spot_trader.persistence.models import (
    CycleRecord,
    DecisionRecord,
    ExecutionIntentRecord,
    FillRecord,
    RiskAssessmentRecord,
)

JsonObject = dict[str, object]


class AuditSortOrder(StrEnum):
    """Stable sort directions supported by audit-list endpoints."""

    ASC = "asc"
    DESC = "desc"


class AuditStoreUnavailableError(RuntimeError):
    """Raised when the durable audit store cannot be queried."""


class AuditDataIntegrityError(RuntimeError):
    """Raised when persisted audit payloads do not match the expected read shape."""


@dataclass(frozen=True, slots=True)
class AuditPage[T]:
    items: tuple[T, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class CycleFailureView:
    stage: str
    error_type: str
    timed_out: bool


@dataclass(frozen=True, slots=True)
class CycleAuditSummary:
    cycle_id: UUID
    status: str
    recorded_at: datetime
    decision_action: str | None
    symbol: str | None
    risk_status: str | None
    execution_id: UUID | None
    fill_count: int
    failure: CycleFailureView | None
    paper_run_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class FillAuditItem:
    fill_id: UUID
    execution_id: UUID
    market_state_id: UUID
    filled_at: datetime
    payload: JsonObject


@dataclass(frozen=True, slots=True)
class CycleAuditDetail:
    cycle_id: UUID
    status: str
    recorded_at: datetime
    failure: CycleFailureView | None
    market_state_id: UUID | None
    portfolio_state_before_id: UUID | None
    portfolio_state_after_id: UUID | None
    market_as_of: datetime | None
    portfolio_before_as_of: datetime | None
    portfolio_after_as_of: datetime | None
    agent_input: JsonObject | None
    decision: JsonObject | None
    risk_assessment: JsonObject | None
    execution_intent: JsonObject | None
    fills: tuple[FillAuditItem, ...]
    portfolio_state_after: JsonObject | None
    paper_run_id: UUID | None = None
    agent_tool_traces: tuple[JsonObject, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionAuditItem:
    decision_id: UUID
    cycle_id: UUID
    created_at: datetime
    action: str
    symbol: str
    payload: JsonObject


@dataclass(frozen=True, slots=True)
class RiskAssessmentAuditItem:
    risk_assessment_id: UUID
    cycle_id: UUID
    decision_id: UUID
    assessed_at: datetime
    status: str
    payload: JsonObject


@dataclass(frozen=True, slots=True)
class ExecutionAuditItem:
    execution_id: UUID
    cycle_id: UUID
    decision_id: UUID
    risk_assessment_id: UUID
    created_at: datetime
    action: str
    symbol: str
    payload: JsonObject
    fills: tuple[FillAuditItem, ...]


@dataclass(frozen=True, slots=True)
class LatestErrorView:
    cycle_id: UUID
    recorded_at: datetime
    failure: CycleFailureView
    paper_run_id: UUID | None = None


class CycleAuditReader(Protocol):
    """Read-only durable history surface used by the HTTP API."""

    async def list_cycles(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
        action: str | None = None,
        risk_status: str | None = None,
    ) -> AuditPage[CycleAuditSummary]: ...

    async def get_cycle(self, cycle_id: UUID) -> CycleAuditDetail | None: ...

    async def latest_cycle(self) -> CycleAuditDetail | None: ...

    async def list_decisions(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        action: str | None = None,
        symbol: str | None = None,
    ) -> AuditPage[DecisionAuditItem]: ...

    async def list_risk_assessments(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
    ) -> AuditPage[RiskAssessmentAuditItem]: ...

    async def list_executions(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        action: str | None = None,
        symbol: str | None = None,
    ) -> AuditPage[ExecutionAuditItem]: ...

    async def latest_error(self) -> LatestErrorView | None: ...

    async def latest_market_state(self) -> JsonObject | None: ...


@runtime_checkable
class RunScopedCycleAuditReader(CycleAuditReader, Protocol):
    async def list_cycles_for_run(
        self,
        paper_run_id: UUID,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
        action: str | None = None,
        risk_status: str | None = None,
    ) -> AuditPage[CycleAuditSummary]: ...

    async def latest_cycle_for_run(
        self, paper_run_id: UUID
    ) -> CycleAuditDetail | None: ...

    async def list_decisions_for_run(
        self,
        paper_run_id: UUID,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        action: str | None = None,
        symbol: str | None = None,
    ) -> AuditPage[DecisionAuditItem]: ...

    async def list_risk_assessments_for_run(
        self,
        paper_run_id: UUID,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
    ) -> AuditPage[RiskAssessmentAuditItem]: ...

    async def list_executions_for_run(
        self,
        paper_run_id: UUID,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        action: str | None = None,
        symbol: str | None = None,
    ) -> AuditPage[ExecutionAuditItem]: ...

    async def latest_error_for_run(
        self, paper_run_id: UUID
    ) -> LatestErrorView | None: ...

    async def latest_market_state_for_run(
        self, paper_run_id: UUID
    ) -> JsonObject | None: ...


class SqlAlchemyCycleAuditQueryService:
    """Read durable audit facts without exposing SQLAlchemy models to FastAPI routes."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        default_paper_run_id: UUID | None = None,
    ) -> None:
        self._sessions = sessions
        self._default_paper_run_id = default_paper_run_id

    def _run_id(self, paper_run_id: UUID | None) -> UUID | None:
        return paper_run_id or self._default_paper_run_id

    async def list_cycles(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
        action: str | None = None,
        risk_status: str | None = None,
        paper_run_id: UUID | None = None,
    ) -> AuditPage[CycleAuditSummary]:
        try:
            async with self._sessions() as session:
                statement = select(CycleRecord)
                count_statement = select(func.count(func.distinct(CycleRecord.cycle_id)))
                resolved_run_id = self._run_id(paper_run_id)
                if action is not None:
                    statement = statement.join(DecisionRecord)
                    count_statement = count_statement.join(DecisionRecord)
                if risk_status is not None:
                    statement = statement.join(RiskAssessmentRecord)
                    count_statement = count_statement.join(RiskAssessmentRecord)
                if resolved_run_id is not None:
                    statement = statement.where(CycleRecord.paper_run_id == resolved_run_id)
                    count_statement = count_statement.where(
                        CycleRecord.paper_run_id == resolved_run_id
                    )
                if status is not None:
                    statement = statement.where(CycleRecord.status == status)
                    count_statement = count_statement.where(CycleRecord.status == status)
                if action is not None:
                    statement = statement.where(DecisionRecord.action == action)
                    count_statement = count_statement.where(DecisionRecord.action == action)
                if risk_status is not None:
                    statement = statement.where(RiskAssessmentRecord.status == risk_status)
                    count_statement = count_statement.where(
                        RiskAssessmentRecord.status == risk_status
                    )

                statement = statement.options(
                    selectinload(CycleRecord.decision),
                    selectinload(CycleRecord.risk_assessment),
                    selectinload(CycleRecord.execution_intent).selectinload(
                        ExecutionIntentRecord.fills
                    ),
                )
                if order is AuditSortOrder.ASC:
                    statement = statement.order_by(
                        CycleRecord.recorded_at.asc(), CycleRecord.cycle_id.asc()
                    )
                else:
                    statement = statement.order_by(
                        CycleRecord.recorded_at.desc(), CycleRecord.cycle_id.desc()
                    )
                statement = statement.offset(offset).limit(limit)
                total = int(await session.scalar(count_statement) or 0)
                records = (await session.scalars(statement)).all()
                return AuditPage(
                    items=tuple(_cycle_summary(record) for record in records),
                    total=total,
                    limit=limit,
                    offset=offset,
                )
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise AuditStoreUnavailableError("audit store unavailable") from exc

    async def list_cycles_for_run(
        self,
        paper_run_id: UUID,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
        action: str | None = None,
        risk_status: str | None = None,
    ) -> AuditPage[CycleAuditSummary]:
        return await self.list_cycles(
            limit=limit,
            offset=offset,
            order=order,
            status=status,
            action=action,
            risk_status=risk_status,
            paper_run_id=paper_run_id,
        )

    async def latest_cycle_for_run(
        self, paper_run_id: UUID
    ) -> CycleAuditDetail | None:
        return await self.latest_cycle(paper_run_id=paper_run_id)

    async def get_cycle(self, cycle_id: UUID) -> CycleAuditDetail | None:
        try:
            async with self._sessions() as session:
                statement = (
                    select(CycleRecord)
                    .where(CycleRecord.cycle_id == cycle_id)
                    .options(
                        selectinload(CycleRecord.decision),
                        selectinload(CycleRecord.risk_assessment),
                        selectinload(CycleRecord.execution_intent).selectinload(
                            ExecutionIntentRecord.fills
                        ),
                    )
                )
                record = await session.scalar(statement)
                return None if record is None else _cycle_detail(record)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise AuditStoreUnavailableError("audit store unavailable") from exc

    async def latest_cycle(
        self,
        *,
        paper_run_id: UUID | None = None,
    ) -> CycleAuditDetail | None:
        try:
            async with self._sessions() as session:
                statement = select(CycleRecord)
                resolved_run_id = self._run_id(paper_run_id)
                if resolved_run_id is not None:
                    statement = statement.where(CycleRecord.paper_run_id == resolved_run_id)
                statement = (
                    statement.options(
                        selectinload(CycleRecord.decision),
                        selectinload(CycleRecord.risk_assessment),
                        selectinload(CycleRecord.execution_intent).selectinload(
                            ExecutionIntentRecord.fills
                        ),
                    )
                    .order_by(CycleRecord.recorded_at.desc(), CycleRecord.cycle_id.desc())
                    .limit(1)
                )
                record = await session.scalar(statement)
                return None if record is None else _cycle_detail(record)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise AuditStoreUnavailableError("audit store unavailable") from exc

    async def list_decisions(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        action: str | None = None,
        symbol: str | None = None,
        paper_run_id: UUID | None = None,
    ) -> AuditPage[DecisionAuditItem]:
        try:
            async with self._sessions() as session:
                statement = select(DecisionRecord)
                count_statement = select(func.count()).select_from(DecisionRecord)
                resolved_run_id = self._run_id(paper_run_id)
                if resolved_run_id is not None:
                    statement = statement.join(CycleRecord).where(
                        CycleRecord.paper_run_id == resolved_run_id
                    )
                    count_statement = count_statement.join(CycleRecord).where(
                        CycleRecord.paper_run_id == resolved_run_id
                    )
                if action is not None:
                    statement = statement.where(DecisionRecord.action == action)
                    count_statement = count_statement.where(DecisionRecord.action == action)
                if symbol is not None:
                    statement = statement.where(DecisionRecord.symbol == symbol)
                    count_statement = count_statement.where(DecisionRecord.symbol == symbol)
                if order is AuditSortOrder.ASC:
                    statement = statement.order_by(
                        DecisionRecord.created_at.asc(), DecisionRecord.decision_id.asc()
                    )
                else:
                    statement = statement.order_by(
                        DecisionRecord.created_at.desc(), DecisionRecord.decision_id.desc()
                    )
                statement = statement.offset(offset).limit(limit)
                total = int(await session.scalar(count_statement) or 0)
                records = (await session.scalars(statement)).all()
                return AuditPage(
                    items=tuple(_decision_item(record) for record in records),
                    total=total,
                    limit=limit,
                    offset=offset,
                )
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise AuditStoreUnavailableError("audit store unavailable") from exc

    async def list_risk_assessments(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
        paper_run_id: UUID | None = None,
    ) -> AuditPage[RiskAssessmentAuditItem]:
        try:
            async with self._sessions() as session:
                statement = select(RiskAssessmentRecord)
                count_statement = select(func.count()).select_from(RiskAssessmentRecord)
                resolved_run_id = self._run_id(paper_run_id)
                if resolved_run_id is not None:
                    statement = statement.join(CycleRecord).where(
                        CycleRecord.paper_run_id == resolved_run_id
                    )
                    count_statement = count_statement.join(CycleRecord).where(
                        CycleRecord.paper_run_id == resolved_run_id
                    )
                if status is not None:
                    statement = statement.where(RiskAssessmentRecord.status == status)
                    count_statement = count_statement.where(
                        RiskAssessmentRecord.status == status
                    )
                if order is AuditSortOrder.ASC:
                    statement = statement.order_by(
                        RiskAssessmentRecord.assessed_at.asc(),
                        RiskAssessmentRecord.risk_assessment_id.asc(),
                    )
                else:
                    statement = statement.order_by(
                        RiskAssessmentRecord.assessed_at.desc(),
                        RiskAssessmentRecord.risk_assessment_id.desc(),
                    )
                statement = statement.offset(offset).limit(limit)
                total = int(await session.scalar(count_statement) or 0)
                records = (await session.scalars(statement)).all()
                return AuditPage(
                    items=tuple(_risk_item(record) for record in records),
                    total=total,
                    limit=limit,
                    offset=offset,
                )
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise AuditStoreUnavailableError("audit store unavailable") from exc

    async def list_executions(
        self,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        action: str | None = None,
        symbol: str | None = None,
        paper_run_id: UUID | None = None,
    ) -> AuditPage[ExecutionAuditItem]:
        try:
            async with self._sessions() as session:
                statement = select(ExecutionIntentRecord).options(
                    selectinload(ExecutionIntentRecord.fills)
                )
                count_statement = select(func.count()).select_from(ExecutionIntentRecord)
                resolved_run_id = self._run_id(paper_run_id)
                if resolved_run_id is not None:
                    statement = statement.join(CycleRecord).where(
                        CycleRecord.paper_run_id == resolved_run_id
                    )
                    count_statement = count_statement.join(CycleRecord).where(
                        CycleRecord.paper_run_id == resolved_run_id
                    )
                if action is not None:
                    statement = statement.where(ExecutionIntentRecord.action == action)
                    count_statement = count_statement.where(
                        ExecutionIntentRecord.action == action
                    )
                if symbol is not None:
                    statement = statement.where(ExecutionIntentRecord.symbol == symbol)
                    count_statement = count_statement.where(
                        ExecutionIntentRecord.symbol == symbol
                    )
                if order is AuditSortOrder.ASC:
                    statement = statement.order_by(
                        ExecutionIntentRecord.created_at.asc(),
                        ExecutionIntentRecord.execution_id.asc(),
                    )
                else:
                    statement = statement.order_by(
                        ExecutionIntentRecord.created_at.desc(),
                        ExecutionIntentRecord.execution_id.desc(),
                    )
                statement = statement.offset(offset).limit(limit)
                total = int(await session.scalar(count_statement) or 0)
                records = (await session.scalars(statement)).all()
                return AuditPage(
                    items=tuple(_execution_item(record) for record in records),
                    total=total,
                    limit=limit,
                    offset=offset,
                )
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise AuditStoreUnavailableError("audit store unavailable") from exc

    async def list_decisions_for_run(
        self,
        paper_run_id: UUID,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        action: str | None = None,
        symbol: str | None = None,
    ) -> AuditPage[DecisionAuditItem]:
        return await self.list_decisions(
            limit=limit, offset=offset, order=order, action=action, symbol=symbol,
            paper_run_id=paper_run_id,
        )

    async def list_risk_assessments_for_run(
        self,
        paper_run_id: UUID,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        status: str | None = None,
    ) -> AuditPage[RiskAssessmentAuditItem]:
        return await self.list_risk_assessments(
            limit=limit, offset=offset, order=order, status=status,
            paper_run_id=paper_run_id,
        )

    async def list_executions_for_run(
        self,
        paper_run_id: UUID,
        *,
        limit: int,
        offset: int,
        order: AuditSortOrder,
        action: str | None = None,
        symbol: str | None = None,
    ) -> AuditPage[ExecutionAuditItem]:
        return await self.list_executions(
            limit=limit, offset=offset, order=order, action=action, symbol=symbol,
            paper_run_id=paper_run_id,
        )

    async def latest_error(
        self,
        *,
        paper_run_id: UUID | None = None,
    ) -> LatestErrorView | None:
        try:
            async with self._sessions() as session:
                statement = select(CycleRecord).where(
                    CycleRecord.status == "FAILED",
                    CycleRecord.failure_stage.is_not(None),
                    CycleRecord.failure_error_type.is_not(None),
                )
                resolved_run_id = self._run_id(paper_run_id)
                if resolved_run_id is not None:
                    statement = statement.where(CycleRecord.paper_run_id == resolved_run_id)
                statement = statement.order_by(
                    CycleRecord.recorded_at.desc(), CycleRecord.cycle_id.desc()
                ).limit(1)
                record = await session.scalar(statement)
                if record is None:
                    return None
                failure = _failure(record)
                if failure is None:
                    raise AuditDataIntegrityError("failed cycle has no failure metadata")
                recorded_at = _utc(record.recorded_at)
                assert recorded_at is not None
                return LatestErrorView(
                    cycle_id=record.cycle_id,
                    recorded_at=recorded_at,
                    failure=failure,
                    paper_run_id=record.paper_run_id,
                )
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise AuditStoreUnavailableError("audit store unavailable") from exc

    async def latest_error_for_run(
        self, paper_run_id: UUID
    ) -> LatestErrorView | None:
        return await self.latest_error(paper_run_id=paper_run_id)

    async def latest_market_state(
        self,
        *,
        paper_run_id: UUID | None = None,
    ) -> JsonObject | None:
        try:
            async with self._sessions() as session:
                statement = select(CycleRecord).where(
                    CycleRecord.market_state_id.is_not(None)
                )
                resolved_run_id = self._run_id(paper_run_id)
                if resolved_run_id is not None:
                    statement = statement.where(CycleRecord.paper_run_id == resolved_run_id)
                statement = statement.order_by(
                    CycleRecord.recorded_at.desc(), CycleRecord.cycle_id.desc()
                ).limit(1)
                record = await session.scalar(statement)
                if record is None:
                    return None
                payload = record.agent_input_payload
                if payload is None:
                    raise AuditDataIntegrityError(
                        "cycle with market_state_id has no agent input payload"
                    )
                market_state = payload.get("market_state")
                if not isinstance(market_state, dict):
                    raise AuditDataIntegrityError(
                        "agent input payload has no market_state object"
                    )
                return dict(market_state)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise AuditStoreUnavailableError("audit store unavailable") from exc

    async def latest_market_state_for_run(
        self, paper_run_id: UUID
    ) -> JsonObject | None:
        return await self.latest_market_state(paper_run_id=paper_run_id)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _json(value: dict[str, object] | None) -> JsonObject | None:
    return None if value is None else dict(value)


def _json_list(value: list[dict[str, object]] | None) -> tuple[JsonObject, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise AuditDataIntegrityError("agent tool traces payload must be an array of objects")
    return tuple(dict(item) for item in value)


def _failure(record: CycleRecord) -> CycleFailureView | None:
    if record.failure_stage is None and record.failure_error_type is None:
        return None
    if record.failure_stage is None or record.failure_error_type is None:
        raise AuditDataIntegrityError("partial cycle failure metadata")
    return CycleFailureView(
        stage=record.failure_stage,
        error_type=record.failure_error_type,
        timed_out=bool(record.failure_timed_out),
    )


def _fill_item(record: FillRecord) -> FillAuditItem:
    filled_at = _utc(record.filled_at)
    assert filled_at is not None
    return FillAuditItem(
        fill_id=record.fill_id,
        execution_id=record.execution_id,
        market_state_id=record.market_state_id,
        filled_at=filled_at,
        payload=dict(record.payload),
    )


def _cycle_summary(record: CycleRecord) -> CycleAuditSummary:
    intent = record.execution_intent
    recorded_at = _utc(record.recorded_at)
    assert recorded_at is not None
    return CycleAuditSummary(
        cycle_id=record.cycle_id,
        paper_run_id=record.paper_run_id,
        status=record.status,
        recorded_at=recorded_at,
        decision_action=record.decision.action if record.decision is not None else None,
        symbol=record.decision.symbol if record.decision is not None else None,
        risk_status=(
            record.risk_assessment.status if record.risk_assessment is not None else None
        ),
        execution_id=intent.execution_id if intent is not None else None,
        fill_count=len(intent.fills) if intent is not None else 0,
        failure=_failure(record),
    )


def _cycle_detail(record: CycleRecord) -> CycleAuditDetail:
    intent = record.execution_intent
    fills = () if intent is None else tuple(
        sorted(
            (_fill_item(fill) for fill in intent.fills),
            key=lambda item: (item.filled_at, str(item.fill_id)),
        )
    )
    recorded_at = _utc(record.recorded_at)
    assert recorded_at is not None
    return CycleAuditDetail(
        cycle_id=record.cycle_id,
        paper_run_id=record.paper_run_id,
        status=record.status,
        recorded_at=recorded_at,
        failure=_failure(record),
        market_state_id=record.market_state_id,
        portfolio_state_before_id=record.portfolio_state_before_id,
        portfolio_state_after_id=record.portfolio_state_after_id,
        market_as_of=_utc(record.market_as_of),
        portfolio_before_as_of=_utc(record.portfolio_before_as_of),
        portfolio_after_as_of=_utc(record.portfolio_after_as_of),
        agent_input=_json(record.agent_input_payload),
        agent_tool_traces=_json_list(record.agent_tool_traces_payload),
        decision=_json(record.decision.payload) if record.decision is not None else None,
        risk_assessment=(
            _json(record.risk_assessment.payload)
            if record.risk_assessment is not None
            else None
        ),
        execution_intent=_json(intent.payload) if intent is not None else None,
        fills=fills,
        portfolio_state_after=_json(record.portfolio_after_payload),
    )


def _decision_item(record: DecisionRecord) -> DecisionAuditItem:
    created_at = _utc(record.created_at)
    assert created_at is not None
    return DecisionAuditItem(
        decision_id=record.decision_id,
        cycle_id=record.cycle_id,
        created_at=created_at,
        action=record.action,
        symbol=record.symbol,
        payload=dict(record.payload),
    )


def _risk_item(record: RiskAssessmentRecord) -> RiskAssessmentAuditItem:
    assessed_at = _utc(record.assessed_at)
    assert assessed_at is not None
    return RiskAssessmentAuditItem(
        risk_assessment_id=record.risk_assessment_id,
        cycle_id=record.cycle_id,
        decision_id=record.decision_id,
        assessed_at=assessed_at,
        status=record.status,
        payload=dict(record.payload),
    )


def _execution_item(record: ExecutionIntentRecord) -> ExecutionAuditItem:
    created_at = _utc(record.created_at)
    assert created_at is not None
    fills = tuple(
        sorted(
            (_fill_item(fill) for fill in record.fills),
            key=lambda item: (item.filled_at, str(item.fill_id)),
        )
    )
    return ExecutionAuditItem(
        execution_id=record.execution_id,
        cycle_id=record.cycle_id,
        decision_id=record.decision_id,
        risk_assessment_id=record.risk_assessment_id,
        created_at=created_at,
        action=record.action,
        symbol=record.symbol,
        payload=dict(record.payload),
        fills=fills,
    )
