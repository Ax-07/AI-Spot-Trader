from __future__ import annotations

from typing import Protocol

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
from ai_spot_trader.persistence.models import CycleRecord, ExecutionIntentRecord
from ai_spot_trader.persistence.query import (
    AuditDataIntegrityError,
    AuditStoreUnavailableError,
)


class PaperAnalyticsReader(Protocol):
    """Read-only analytics surface derived from the durable PAPER audit journal."""

    async def paper_analytics(self) -> PaperAnalyticsReport: ...


class SqlAlchemyPaperAnalyticsQueryService:
    """Load immutable audit facts and deterministically replay PAPER analytics."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def paper_analytics(self) -> PaperAnalyticsReport:
        try:
            async with self._sessions() as session:
                statement = (
                    select(CycleRecord)
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
