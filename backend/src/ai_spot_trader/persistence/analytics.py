from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from ai_spot_trader.analytics.paper import (
    PaperAnalyticsCycleFact,
    PaperAnalyticsDataError,
    PaperAnalyticsReport,
    build_paper_analytics_report,
)
from ai_spot_trader.persistence.models import (
    CycleRecord,
    ExecutionIntentRecord,
    PaperRunRecord,
)
from ai_spot_trader.persistence.query import (
    AuditDataIntegrityError,
    AuditStoreUnavailableError,
)
from ai_spot_trader.persistence.runs import PaperRunNotFoundError


class PaperAnalyticsReader(Protocol):
    """Read-only analytics surface derived from the durable PAPER audit journal."""

    async def paper_analytics(self) -> PaperAnalyticsReport: ...


@runtime_checkable
class RunScopedPaperAnalyticsReader(PaperAnalyticsReader, Protocol):
    async def paper_analytics_for_run(self, paper_run_id: UUID) -> PaperAnalyticsReport: ...


class SqlAlchemyPaperAnalyticsQueryService:
    """Replay analytics for one durable PAPER run at a time."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        default_paper_run_id: UUID | None = None,
    ) -> None:
        self._sessions = sessions
        self._default_paper_run_id = default_paper_run_id

    async def paper_analytics(self) -> PaperAnalyticsReport:
        """Use the current run when configured, otherwise the latest durable run."""

        try:
            run_id = self._default_paper_run_id
            if run_id is None:
                async with self._sessions() as session:
                    run_id = await session.scalar(
                        select(PaperRunRecord.paper_run_id)
                        .order_by(
                            PaperRunRecord.started_at.desc(),
                            PaperRunRecord.paper_run_id.desc(),
                        )
                        .limit(1)
                    )
            if run_id is None:
                return build_paper_analytics_report(())
            return await self.paper_analytics_for_run(run_id)
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise AuditStoreUnavailableError("audit store unavailable") from exc

    async def paper_analytics_for_run(self, paper_run_id: UUID) -> PaperAnalyticsReport:
        try:
            async with self._sessions() as session:
                if await session.get(PaperRunRecord, paper_run_id) is None:
                    raise PaperRunNotFoundError(
                        f"paper run {paper_run_id} does not exist"
                    )
                statement = (
                    select(CycleRecord)
                    .where(CycleRecord.paper_run_id == paper_run_id)
                    .options(
                        selectinload(CycleRecord.decision),
                        selectinload(CycleRecord.risk_assessment),
                        selectinload(CycleRecord.execution_intent).selectinload(
                            ExecutionIntentRecord.fills
                        ),
                    )
                    .order_by(CycleRecord.recorded_at.asc(), CycleRecord.cycle_id.asc())
                )
                records = (await session.scalars(statement)).all()
                facts = tuple(_fact(record) for record in records)
                try:
                    return build_paper_analytics_report(facts)
                except PaperAnalyticsDataError as exc:
                    raise AuditDataIntegrityError("analytics facts are inconsistent") from exc
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise AuditStoreUnavailableError("audit store unavailable") from exc


def _fact(record: CycleRecord) -> PaperAnalyticsCycleFact:
    decision = record.decision
    risk = record.risk_assessment
    intent = record.execution_intent
    fills = () if intent is None else tuple(
        dict(fill.payload)
        for fill in sorted(
            intent.fills,
            key=lambda item: (item.filled_at, str(item.fill_id)),
        )
    )
    return PaperAnalyticsCycleFact(
        cycle_id=record.cycle_id,
        status=record.status,
        recorded_at=record.recorded_at,
        result_digest=record.result_digest,
        agent_input_payload=(
            None if record.agent_input_payload is None else dict(record.agent_input_payload)
        ),
        decision_payload=None if decision is None else dict(decision.payload),
        risk_assessment_payload=None if risk is None else dict(risk.payload),
        fill_payloads=fills,
        portfolio_after_payload=(
            None
            if record.portfolio_after_payload is None
            else dict(record.portfolio_after_payload)
        ),
    )
