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
    DecisionRecord,
    ExecutionIntentRecord,
    PaperRunRecord,
    RiskAssessmentRecord,
)
from ai_spot_trader.persistence.query import AuditDataIntegrityError, AuditStoreUnavailableError
from ai_spot_trader.persistence.runs import PaperRunNotFoundError


class PaperAnalyticsReader(Protocol):
    async def paper_analytics(self) -> PaperAnalyticsReport: ...


@runtime_checkable
class RunScopedPaperAnalyticsReader(PaperAnalyticsReader, Protocol):
    async def paper_analytics_for_run(self, paper_run_id: UUID) -> PaperAnalyticsReport: ...


class SqlAlchemyPaperAnalyticsQueryService:
    """Replay analytics from economically committed PAPER facts only."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        default_paper_run_id: UUID | None = None,
    ) -> None:
        self._sessions = sessions
        self._default_paper_run_id = default_paper_run_id

    async def paper_analytics(self) -> PaperAnalyticsReport:
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
                run = await session.get(PaperRunRecord, paper_run_id)
                if run is None:
                    raise PaperRunNotFoundError(f"paper run {paper_run_id} does not exist")
                lineage = await _paper_run_lineage(session, run)
                records: list[CycleRecord] = []
                for run_id in lineage:
                    statement = (
                        select(CycleRecord)
                        .where(CycleRecord.paper_run_id == run_id)
                        .options(_cycle_graph_load())
                        .order_by(CycleRecord.recorded_at.asc(), CycleRecord.cycle_id.asc())
                    )
                    records.extend((await session.scalars(statement)).unique().all())
                facts = tuple(
                    fact
                    for record in records
                    for fact in _facts(record)
                )
                try:
                    return build_paper_analytics_report(facts)
                except PaperAnalyticsDataError as exc:
                    raise AuditDataIntegrityError("analytics facts are inconsistent") from exc
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            raise AuditStoreUnavailableError("audit store unavailable") from exc


async def _paper_run_lineage(
    session: AsyncSession,
    run: PaperRunRecord,
) -> tuple[UUID, ...]:
    reverse: list[UUID] = []
    seen: set[UUID] = set()
    current = run
    while True:
        run_id = current.paper_run_id
        if run_id in seen:
            raise AuditDataIntegrityError("PAPER run recovery lineage contains a cycle")
        seen.add(run_id)
        reverse.append(run_id)
        parent_id = current.resumed_from_paper_run_id
        if parent_id is None:
            break
        parent = await session.get(PaperRunRecord, parent_id)
        if parent is None:
            raise AuditDataIntegrityError("PAPER run recovery lineage references a missing parent")
        current = parent
    return tuple(reversed(reverse))


def _cycle_graph_load():
    return (
        selectinload(CycleRecord.decisions)
        .selectinload(DecisionRecord.risk_assessment)
        .selectinload(RiskAssessmentRecord.execution_intent)
        .selectinload(ExecutionIntentRecord.fills)
    )


def _facts(record: CycleRecord) -> tuple[PaperAnalyticsCycleFact, ...]:
    decisions = sorted(record.decisions, key=lambda item: item.decision_index)
    if not decisions:
        return (
            PaperAnalyticsCycleFact(
                cycle_id=record.cycle_id,
                status=record.status,
                recorded_at=record.recorded_at,
                result_digest=record.result_digest,
                agent_input_payload=(
                    None if record.agent_input_payload is None else dict(record.agent_input_payload)
                ),
                decision_payload=None,
                risk_assessment_payload=None,
                fill_payloads=(),
                portfolio_after_payload=(
                    None
                    if record.portfolio_after_payload is None
                    else dict(record.portfolio_after_payload)
                ),
            ),
        )

    # A FAILED cycle was rolled back by AuditedTradingCycleRunner. Its fills remain audit evidence
    # but must never be counted as economically committed trades/P&L.
    if record.status == "FAILED":
        first = decisions[0]
        return (
            PaperAnalyticsCycleFact(
                cycle_id=record.cycle_id,
                status="FAILED",
                recorded_at=record.recorded_at,
                result_digest=record.result_digest,
                agent_input_payload=_decision_agent_input(record, first),
                decision_payload=None,
                risk_assessment_payload=None,
                fill_payloads=(),
                portfolio_after_payload=None,
            ),
        )

    facts: list[PaperAnalyticsCycleFact] = []
    for index, decision in enumerate(decisions):
        risk = decision.risk_assessment
        intent = None if risk is None else risk.execution_intent
        fills = (
            ()
            if intent is None
            else tuple(
                dict(fill.payload)
                for fill in sorted(
                    intent.fills,
                    key=lambda item: (item.filled_at, str(item.fill_id)),
                )
            )
        )
        facts.append(
            PaperAnalyticsCycleFact(
                cycle_id=record.cycle_id,
                # The report counts cycle statuses; only the first trajectory carries the cycle
                # status so a 1:N cycle is not miscounted as N completed cycles.
                status=record.status if index == 0 else "DECISION",
                recorded_at=record.recorded_at,
                result_digest=f"{record.result_digest}:{decision.decision_index}",
                agent_input_payload=_decision_agent_input(record, decision),
                decision_payload=dict(decision.payload),
                risk_assessment_payload=None if risk is None else dict(risk.payload),
                fill_payloads=fills,
                portfolio_after_payload=(
                    dict(decision.portfolio_after_payload)
                    if decision.portfolio_after_payload is not None
                    else dict(record.portfolio_after_payload)
                    if len(decisions) == 1 and record.portfolio_after_payload is not None
                    else None
                ),
            )
        )
    return tuple(facts)


def _decision_agent_input(
    cycle: CycleRecord,
    decision: DecisionRecord,
) -> dict[str, object] | None:
    if decision.agent_input_payload is not None:
        return dict(decision.agent_input_payload)
    if len(cycle.decisions) == 1 and cycle.agent_input_payload is not None:
        return dict(cycle.agent_input_payload)
    return None
